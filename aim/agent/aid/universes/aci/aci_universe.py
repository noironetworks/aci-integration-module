# Copyright (c) 2016 Cisco Systems
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import collections
import json
import time
import traceback

from acitoolkit import acitoolkit
from apicapi import apic_client
from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes.aci import tenant as aci_tenant
from aim.agent.aid.universes import base_universe as base
from aim.api import resource
from aim.common import utils
from aim import exceptions
from aim import tree_manager


LOG = logging.getLogger(__name__)

# Dictionary of currently served tenants. For each tenant defined by name,
# we store the corresponding TenantManager.
# To avoid websocket subscription duplication, share the serving tenants
# between config and operational ACI universes
# REVISIT(ivar): we are assuming that one single AciUniverse instance will
# access this at any time. This is realistic today, because AciUniverse and
# AciOperationalUniverse won't run in parallel, and there will be only one
# instance of each per AID agent.
serving_tenants = {}
ws_context = None


class WebSocketSessionLoginFailed(exceptions.AimException):
    message = ("Web socket session failed to login "
               "with error %(code)s: %(text)s")


class WebSocketSubscriptionFailed(exceptions.AimException):
    message = ("Web socket session failed to subscribe for url %(urls)s "
               "with error %(code)s: %(text)s")


class WebSocketContext(object):
    """Placeholder for websocket session"""

    def __init__(self, apic_config):
        self.apic_config = apic_config
        self._reload_websocket_config()
        self.establish_ws_session()
        self.monitor_runs = float('inf')
        self.monitor_sleep_time = 10
        self.monitor_max_backoff = 30
        self._spawn_monitors()

    def _spawn_monitors(self):
        utils.spawn_thread(self._thread_monitor, self.session.login_thread,
                           'login_thread')
        utils.spawn_thread(
            self._thread_monitor, self.session.subscription_thread,
            'subscription_thread')

    def _reload_websocket_config(self):
        # Don't subscribe in this case
        self.apic_use_ssl = self.apic_config.get_option_and_subscribe(
            self._ws_config_callback, 'apic_use_ssl', group='apic')
        self.apic_hosts = self.apic_config.get_option_and_subscribe(
            self._ws_config_callback, 'apic_hosts', group='apic')
        self.apic_username = self.apic_config.get_option_and_subscribe(
            self._ws_config_callback, 'apic_username', group='apic')
        self.apic_password = self.apic_config.get_option_and_subscribe(
            self._ws_config_callback, 'apic_password', group='apic')
        self.verify_ssl_certificate = (
            self.apic_config.get_option_and_subscribe(
                self._ws_config_callback, 'verify_ssl_certificate',
                group='apic'))
        self.cert_name = self.apic_config.get_option('certificate_name',
                                                     group='apic')
        self.private_key_file = self.apic_config.get_option('private_key_file',
                                                            group='apic')
        protocol = 'https' if self.apic_use_ssl else 'http'
        self.ws_urls = collections.deque(
            ['%s://%s' % (protocol, host) for host in self.apic_hosts])

    def establish_ws_session(self):
        # REVISIT(ivar): acitoolkit is missing some features like certificate
        # identification and multi controller support.
        # A decision should be taken whether we want to add features to
        # acitoolkit to at least support certificate identification, or if
        # we want to implement the WS interface in APICAPI altogether
        LOG.debug('Establishing WS connection with parameters: %s',
                  [self.ws_urls[0], self.apic_username, self.apic_password,
                   self.verify_ssl_certificate])

        self.session = acitoolkit.Session(
            self.ws_urls[0], self.apic_username, self.apic_password,
            verify_ssl=self.verify_ssl_certificate, cert_name=self.cert_name,
            key=self.private_key_file)
        resp = self.session.login()
        if not resp.ok:
            raise WebSocketSessionLoginFailed(code=resp.status_code,
                                              text=resp.text)

    def _ws_config_callback(self, new_conf):
        # If any of the WS related configurations changed, reload fresh values
        # and reconnect the WS
        if getattr(self, new_conf['key']) != new_conf['value']:
            LOG.debug("New APIC remote configuration, restarting web socket "
                      "session.")
            # Log out WS
            self.reconnect_ws_session()

    def reconnect_ws_session(self):
        # Log out WS
        if self.session.session:
            self.session.close()
        self._reload_websocket_config()
        self.ws_urls.rotate()
        self.establish_ws_session()

    def _subscribe(self, urls, extension=''):
        """Subscribe to the urls if not subscribed yet."""
        resp = None
        for url in urls:
            if not self.session.is_subscribed(url + extension):
                resp = self.session.subscribe(url + extension)
                LOG.debug('Subscribed to %s %s %s ', url + extension, resp,
                          resp.text)
                if not resp.ok:
                    return resp
        return resp

    def subscribe(self, urls):
        resp = self._subscribe(urls)
        if resp is not None:
            if resp.ok:
                return json.loads(resp.text)['imdata']
            else:
                if resp.status_code == 405:
                    self.reconnect_ws_session()
                raise WebSocketSubscriptionFailed(urls=urls,
                                                  code=resp.status_code,
                                                  text=resp.text)

    def unsubscribe(self, urls):
        LOG.debug("Subscription urls: %s", urls)
        for url in urls:
            self.session.unsubscribe(url)

    def get_event_data(self, urls):
        result = []
        for url in urls:
            # Aggregate similar events
            while self.session.has_events(url):
                event = self.session.get_event(url)['imdata'][0]
                result.append(event)
        return result

    def has_event(self, urls):
        return any(self.session.has_events(url) for url in urls)

    def _thread_monitor(self, thread, name):
        # TODO(ivar): I could have used thread.join instead of this
        retries = None
        max_retries = len(self.ws_urls)
        LOG.debug("Monitoring thread %s" % name)
        try:
            while self.monitor_runs:
                if not thread.isAlive():
                    if retries and retries.get() >= max_retries:
                        utils.perform_harakiri(
                            LOG, "Critical thread %s stopped working" % name)
                    else:
                        retries = utils.exponential_backoff(
                            self.monitor_max_backoff, tentative=retries)
                        try:
                            self.reconnect_ws_session()
                        except Exception as e:
                            LOG.debug(
                                "Monitor for thread %s tried to reconnect web "
                                "socket, but something went wrong. Will retry "
                                "%s more times: %s" %
                                (name, max_retries - retries.get(), e.message))
                            continue
                else:
                    LOG.debug("Thread %s is in good shape" % name)
                    retries = None
                time.sleep(self.monitor_sleep_time)
                # for testing purposes
                self.monitor_runs -= 1
        except Exception as e:
            msg = ("Unknown error in thread monitor "
                   "for %s: %s" % (name, e.message))
            LOG.error(msg)
            utils.perform_harakiri(LOG, msg)


def get_websocket_context(apic_config):
    global ws_context
    if not ws_context:
        ws_context = WebSocketContext(apic_config)
    return ws_context


class AciUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the ACI state.

    This Hash Tree bases observer retrieves and stores state information
    from the ACI REST API.
    """

    def initialize(self, store, conf_mgr, multiverse):
        super(AciUniverse, self).initialize(store, conf_mgr, multiverse)
        self._aim_converter = converter.AciToAimModelConverter()
        self.aci_session = self.establish_aci_session(self.conf_manager)
        # Initialize children MOS here so that it globally fails if there's
        # any bug or network partition.
        aci_tenant.get_children_mos(self.aci_session, 'tn-common')
        aci_tenant.get_children_mos(self.aci_session, 'pod-1')
        self.ws_context = get_websocket_context(self.conf_manager)
        self.aim_system_id = self.conf_manager.get_option('aim_system_id',
                                                          'aim')
        return self

    def get_state_by_type(self, type):
        try:
            if type == base.CONFIG_UNIVERSE:
                return self.multiverse[base.CONFIG_UNIVERSE]['current'].state
            else:
                return self.multiverse[type]['desired'].state
        except IndexError:
            LOG.warn('Requested universe type %s not found', type)
            return self.state

    def get_relevant_state_for_read(self):
        return [self.get_state_by_type(base.CONFIG_UNIVERSE),
                self.get_state_by_type(base.MONITOR_UNIVERSE),
                self.get_state_by_type(base.OPER_UNIVERSE)]

    @property
    def name(self):
        return "ACI_Config_Universe"

    @property
    def serving_tenants(self):
        global serving_tenants
        return serving_tenants

    def serve(self, tenants):
        # Verify differences
        global serving_tenants
        try:
            serving_tenant_copy = serving_tenants
            serving_tenants = {}
            remove = set(serving_tenant_copy.keys()) - set(tenants)
            for removed in remove:
                # pop from the current state. This is not thread safe, but the
                # caller will not asynchronously use the 'observe' method so we
                # are gonna be fine. Make it Thread safe if required
                self._state.pop(removed, None)
                try:
                    serving_tenant_copy[removed].kill()
                    serving_tenant_copy[removed]._unsubscribe_tenant()
                except Exception:
                    LOG.error('Killing manager failed for tenant %s' % removed)
                    continue
            for added in tenants:
                if added in serving_tenant_copy:
                    # Move it back to serving tenant, no need to restart
                    # the Thread
                    try:
                        serving_tenants[added] = serving_tenant_copy[
                            added]
                    except KeyError:
                        LOG.debug("%s not found in %s during serving copy" %
                                  (added, serving_tenant_copy))
                if (added not in serving_tenants or
                        serving_tenants[added].is_dead()):
                    LOG.debug("Adding new tenant %s" % added)
                    # Start thread or replace broken one
                    # Checking the 'dead' state helps those cases in which
                    # a kill successfully happened but then  the state was
                    # rolled back by a further exception
                    if added in serving_tenants:
                        LOG.info(
                            "Tenant %s was served but needs to be replaced: "
                            "dead-%s",
                            added, serving_tenants[added].is_dead())
                        # Cleanup the tenant's state
                        serving_tenants[added].kill()
                        serving_tenants[added]._unsubscribe_tenant()
                    serving_tenants[added] = aci_tenant.AciTenantManager(
                        added, self.conf_manager, self.aci_session,
                        self.ws_context, self.creation_succeeded,
                        self.creation_failed, self.aim_system_id, self)
                    # A subscription might be leaking here
                    serving_tenants[added]._unsubscribe_tenant()
                    serving_tenants[added].start()
        except Exception as e:
            LOG.error(traceback.format_exc())
            LOG.error('Failed to serve new tenants %s' % tenants)
            # Rollback served tenants
            serving_tenants = serving_tenant_copy
            raise e

    def observe(self):
        # Copy state accumulated so far
        global serving_tenants
        new_state = {}
        for tenant in serving_tenants:
            # Only copy state if the tenant is warm
            if serving_tenants[tenant].is_warm():
                new_state[tenant] = self._get_state_copy(tenant)
        self._state = new_state

    def push_resources(self, resources):
        # Organize by tenant, and push into APIC
        global serving_tenants
        by_tenant = {}
        for method, objects in resources.iteritems():
            for data in objects:
                tenant_name = self._retrieve_tenant_rn(data)
                if tenant_name:
                    by_tenant.setdefault(tenant_name, {}).setdefault(
                        method, []).append(data)

        for tenant, conf in by_tenant.iteritems():
            try:
                serving_tenants[tenant]
            except KeyError:
                LOG.warn("Tenant %s is not being served anymore. "
                         "Currently served tenants: %s" % (
                             tenant, serving_tenants.keys()))
            else:
                serving_tenants[tenant].push_aim_resources(conf)

    def _retrieve_tenant_rn(self, data):
        if isinstance(data, dict):
            if data.keys()[0] == 'tagInst':
                # Retrieve tag parent
                dn = data.values()[0]['attributes']['dn']
                decomposed = apic_client.DNManager().aci_decompose_dn_guess(
                    dn, 'tagInst')
                parent_type = decomposed[1][-2][0]
                data = {
                    parent_type: {
                        'attributes': {
                            'dn': apic_client.DNManager().build(
                                decomposed[1][:-1])}}}
            data = self._aim_converter.convert([data])
            data = data[0] if data else None
        if isinstance(data, resource.AciResourceBase):
            return tree_manager.AimHashTreeMaker().get_root_key(data)

    def get_resources_for_delete(self, resource_keys):
        curr_mon = self.multiverse[base.MONITOR_UNIVERSE]['current'].state

        def action(result, aci_object, node):
            if node and not node.dummy:
                # Monitored state transition -> Delete the TAG instead
                aci_type = 'tagInst'
                dn = aci_object.values()[0]['attributes'][
                    'dn'] + '/tag-' + self.aim_system_id
                result.append({aci_type: {'attributes': {'dn': dn}}})
            else:
                result.append(aci_object)
        return self._get_resources_for_delete(resource_keys, curr_mon, action)

    def _get_state_copy(self, tenant):
        global serving_tenants
        return serving_tenants[tenant].get_state_copy()

    @staticmethod
    def establish_aci_session(apic_config):
        return apic_client.RestClient(
            logging, '',
            apic_config.get_option('apic_hosts', group='apic'),
            apic_config.get_option('apic_username', group='apic'),
            apic_config.get_option('apic_password', group='apic'),
            apic_config.get_option('apic_use_ssl', group='apic'),
            scope_names=False, scope_infra=False, renew_names=False,
            verify=apic_config.get_option('verify_ssl_certificate',
                                          group='apic'),
            request_timeout=apic_config.get_option('apic_request_timeout',
                                                   group='apic'),
            cert_name=apic_config.get_option('certificate_name',
                                             group='apic'),
            private_key_file=apic_config.get_option('private_key_file',
                                                    group='apic'),
            sign_algo=apic_config.get_option(
                'signature_verification_algorithm', group='apic'),
            sign_hash=apic_config.get_option(
                'signature_hash_type', group='apic'))

    def update_status_objects(self, my_state, other_state, other_universe,
                              raw_diff, transformed_diff):
        pass


class AciOperationalUniverse(AciUniverse):
    """ACI Universe for operational state."""

    @property
    def name(self):
        return "ACI_Operational_Universe"

    def _get_state_copy(self, tenant):
        global serving_tenants
        return serving_tenants[tenant].get_operational_state_copy()


class AciMonitoredUniverse(AciUniverse):
    """ACI Universe for monitored state."""

    @property
    def name(self):
        return "ACI_Monitored_Universe"

    def _get_state_copy(self, tenant):
        global serving_tenants
        return serving_tenants[tenant].get_monitored_state_copy()
