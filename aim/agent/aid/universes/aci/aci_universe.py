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
import random
import time
import traceback

from acitoolkit import acitoolkit
from apicapi import apic_client
from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes.aci import tenant as aci_tenant
from aim.agent.aid.universes import base_universe as base
from aim.agent.aid.universes import constants as lcon
from aim.agent.aid.universes import errors
from aim.api import infra as api_infra
from aim.api import resource
from aim.common import utils
from aim import config as aim_cfg
from aim import context as aim_ctx
from aim.db import api
from aim import exceptions
from aim import tree_manager

NORMAL_PURPOSE = 'normal'
BACKUP_PURPOSE = 'backup'
RECOVERY_PURPOSE = 'recovery'

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


class WebSocketUnsubscriptionFailed(exceptions.AimException):
    message = ("Web socket session failed to unsubscribe for url %(urls)s "
               "with error %(code)s: %(text)s")


class WebSocketContext(object):
    """Placeholder for websocket session"""
    EMPTY_URLS = ["empty/url"]

    def __init__(self, apic_config, aim_manager):
        self.apic_config = apic_config
        self.session = None
        self.ws_urls = collections.deque()
        self.is_session_reconnected = False
        self.monitor_runs = {'monitor_runs': float('inf')}
        self.monitor_sleep_time = aim_cfg.CONF.aim.websocket_monitor_sleep
        self.monitor_max_backoff = 30
        self.login_thread = None
        self.subs_thread = None
        self.monitor_thread = None
        self.agent_id = 'aid-%s' % aim_cfg.CONF.aim.aim_service_identifier
        self.apic_assign_obj = None
        self.need_recovery = False
        self.recovery_max_backoff = 600
        self.manager = aim_manager
        self.establish_ws_session()

    def _spawn_monitors(self):
        self.login_thread = None
        self.subs_thread = None
        if not self.monitor_thread:
            self.monitor_thread = utils.spawn_thread(self._thread_monitor,
                                                     self.monitor_runs)
        self.login_thread = self.session.login_thread
        self.subs_thread = self.session.subscription_thread

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
        ws_urls = collections.deque(
            ['%s://%s' % (protocol, host) for host in self.apic_hosts])
        if set(ws_urls) != set(self.ws_urls):
            self.ws_urls = ws_urls

    def _update_apic_assign_db(self, aim_context, apic_assign,
                               apic_assign_obj):
        try:
            if apic_assign_obj is None:
                apic_assign.aim_aid_id = self.agent_id
                return self.manager.create(aim_context, apic_assign)

            if apic_assign_obj.aim_aid_id != self.agent_id:
                obj = self.manager.update(aim_context, apic_assign_obj,
                                          aim_aid_id=self.agent_id)
            else:
                # This will update the last_update_timestamp
                # automatically
                obj = self.manager.update(aim_context, apic_assign_obj)
            return obj
        # This means another controller is also adding/updating
        # the same entry at the same time and he has beat us.
        except Exception as e:
            LOG.info(e)
            return None

    def _ws_session_login(self, url, url_max_retries, purpose,
                          aim_context=None, apic_assign=None,
                          apic_assign_obj=None):
        retries = 0
        LOG.info('Establishing %s WS connection with url: %s',
                 purpose, url)
        valid_session = None
        while retries < url_max_retries:
            session = acitoolkit.Session(
                url, self.apic_username,
                self.apic_password,
                verify_ssl=self.verify_ssl_certificate,
                cert_name=self.cert_name,
                key=self.private_key_file)
            resp = session.login()
            if not resp.ok:
                LOG.warn('%s Websocket connection failed: %s',
                         purpose, resp.text)
                retries += 1
                if session.session:
                    session.close()
                continue
            LOG.info('%s Websocket connection succeeded with url: %s',
                     purpose, url)
            valid_session = session
            break

        if valid_session:
            # We don't need to claim the ownership if we are just
            # picking up a backup APIC.
            if purpose != BACKUP_PURPOSE:
                obj = self._update_apic_assign_db(
                    aim_context, apic_assign, apic_assign_obj)
                if obj is None:
                    valid_session.close()
                    return False
            if purpose == BACKUP_PURPOSE or obj:
                if self.session and self.session.session:
                    self.session.close()
                    self.is_session_reconnected = True
                self.session = valid_session
                self._spawn_monitors()
                if purpose == BACKUP_PURPOSE:
                    self.need_recovery = True
                else:
                    self.apic_assign_obj = obj
                    self.need_recovery = False
                return True

        return False

    def establish_ws_session(self, max_retries=None, recovery_mode=False):
        try:
            with utils.get_rlock(lcon.ACI_WS_CONNECTION_LOCK, blocking=False):
                if not recovery_mode:
                    purpose = NORMAL_PURPOSE
                    self._reload_websocket_config()
                    self.need_recovery = False
                else:
                    purpose = RECOVERY_PURPOSE
                backup_urls = collections.deque()
                max_retries = max_retries or 2 * len(self.ws_urls)
                url_max_retries = max(1, max_retries / len(self.ws_urls))
                aim_context = aim_ctx.AimContext(store=api.get_store())
                for url in self.ws_urls:
                    apic_assign = api_infra.ApicAssignment(apic_host=url)
                    apic_assign_obj = self.manager.get(aim_context,
                                                       apic_assign)
                    if (apic_assign_obj and
                        apic_assign_obj.aim_aid_id != self.agent_id and
                            not apic_assign_obj.is_available(aim_context)):
                        backup_urls.append(url)
                        continue

                    # This means the original aim-aid owner might have
                    # crashed or something. We will just take it!
                    if (recovery_mode and apic_assign_obj and
                            self.session.ipaddr in url):
                        obj = self._update_apic_assign_db(
                            aim_context, apic_assign, apic_assign_obj)
                        if obj is None:
                            continue
                        self.need_recovery = False
                        self.apic_assign_obj = obj
                        return

                    is_conn_successful = self._ws_session_login(
                        url, url_max_retries, purpose,
                        aim_context, apic_assign, apic_assign_obj)
                    if is_conn_successful:
                        return
                    else:
                        backup_urls.append(url)

                if recovery_mode:
                    return
                # Try the backup urls. Randomly rotate the list first so that
                # the extra aim-aids won't all go for the same backup url.
                backup_urls_len = len(backup_urls)
                if backup_urls_len > 1:
                    backup_urls.rotate(random.randint(1, backup_urls_len))
                for url in backup_urls:
                    is_conn_successful = self._ws_session_login(
                        url, url_max_retries, BACKUP_PURPOSE)
                    if is_conn_successful:
                        return
                utils.perform_harakiri(LOG, "Cannot establish WS connection "
                                            "after %s retries." % max_retries)
        except utils.LockNotAcquired:
            # Some other thread is trying to reconnect
            return

    def _ws_config_callback(self, new_conf):
        # If any of the WS related configurations changed, reload fresh values
        # and reconnect the WS
        if getattr(self, new_conf['key']) != new_conf['value']:
            LOG.debug("New APIC remote configuration, restarting web socket "
                      "session.")
            # Log out WS
            self.establish_ws_session()

    def _subscribe(self, urls):
        """Subscribe to the urls if not subscribed yet."""
        resp = None
        for url in urls:
            if not self.session.is_subscribed(url):
                resp = self.session.subscribe(url)
                if not resp.ok:
                    return resp
                LOG.debug('Subscribed to %s %s %s ', url, resp,
                          resp.text)
        return resp

    def _unsubscribe(self, urls):
        resp = None
        for url in urls:
            resp = self.session.unsubscribe(url)
            if resp is not None and not resp.ok:
                return resp
            LOG.debug('Unsubscribed to %s', url)
        return resp

    def subscribe(self, urls):
        if urls == self.EMPTY_URLS:
            raise WebSocketSubscriptionFailed(urls=urls,
                                              code=400,
                                              text="Empty URLS")
        resp = self._subscribe(urls)
        if resp is not None:
            if resp.ok:
                return utils.json_loads(resp.text)['imdata']
            else:
                if resp.status_code in [405, 598, 500]:
                    self.establish_ws_session()
                raise WebSocketSubscriptionFailed(urls=urls,
                                                  code=resp.status_code,
                                                  text=resp.text)

    def unsubscribe(self, urls):
        if urls == self.EMPTY_URLS:
            return
        resp = self._unsubscribe(urls)
        if resp is not None and not resp.ok:
            if resp.status_code in [405, 598, 500]:
                self.establish_ws_session()
            raise WebSocketUnsubscriptionFailed(urls=urls,
                                                code=resp.status_code,
                                                text=resp.text)

    def get_event_data(self, urls):
        result = []
        for url in urls:
            # Aggregate similar events
            while self.session.has_events(url):
                event = self.session.get_event(url)['imdata'][0]
                result.append(event)
        return result

    def has_event(self, urls):
        if urls == self.EMPTY_URLS:
            return False
        return any(self.session.has_events(url) for url in urls)

    def _thread_monitor(self, flag):
        login_thread_name = 'login_thread'
        subscription_thread_name = 'subscription_thread'
        name_to_retry = {login_thread_name: None,
                         subscription_thread_name: None}
        max_retries = len(self.ws_urls)
        recovery_timer = utils.get_time()
        recovery_retry = 0
        aim_context = aim_ctx.AimContext(store=api.get_store())
        LOG.debug("Monitoring threads login and subscription")
        try:
            if (self.private_key_file or self.cert_name):
                threads = ((self.subs_thread, 'subscription_thread'),)
            else:
                threads = ((self.login_thread, 'login_thread'),
                           (self.subs_thread, 'subscription_thread'))

            while flag['monitor_runs']:
                for thd, name in threads:
                    if thd and not thd.isAlive():
                        if name_to_retry[name] and name_to_retry[
                                name].get() >= max_retries:
                            utils.perform_harakiri(
                                LOG, "Critical thread %s stopped "
                                     "working" % name)
                        else:
                            name_to_retry[name] = utils.exponential_backoff(
                                self.monitor_max_backoff,
                                tentative=name_to_retry[name])
                            try:
                                self.establish_ws_session()
                            except Exception as e:
                                LOG.debug(
                                    "Monitor for thread %s tried to reconnect "
                                    "web socket, but something went wrong. "
                                    "Will retry %s more times: %s" %
                                    (name,
                                     max_retries - name_to_retry[name].get(),
                                     str(e)))
                                continue
                    elif thd:
                        LOG.debug("Thread %s is in good shape" % name)
                        name_to_retry[name] = None

                if self.need_recovery:
                    # No point to do any recovery session if we
                    # only have 1 ws_url.
                    if (len(self.ws_urls) > 1 and
                            utils.get_time() > recovery_timer):
                        self.establish_ws_session(recovery_mode=True)
                        # Still fail to recover
                        if self.need_recovery:
                            recovery_retry += 1
                            recovery_timer = (
                                utils.get_time() + utils.get_backoff_time(
                                    self.recovery_max_backoff, recovery_retry))
                        else:
                            recovery_retry = 0
                else:
                    # Update the last_update_timestamp
                    if self.apic_assign_obj:
                        self.apic_assign_obj = self.manager.update(
                            aim_context, self.apic_assign_obj)
                    else:
                        # This should never happen
                        LOG.error('There is no such apic_assign_obj exist '
                                  'for %s!' % self.session.ipaddr)

                time.sleep(self.monitor_sleep_time)
                # for testing purposes
                flag['monitor_runs'] -= 1
        except Exception as e:
            msg = ("Unknown error in thread monitor: %s" % str(e))
            LOG.error(msg)
            utils.perform_harakiri(LOG, msg)


# REVIST: see if there is a way that we don't have to pass aim_manager in
# to get the WebSocketContext object initialized.
def get_websocket_context(apic_config, aim_manager):
    global ws_context
    if not ws_context:
        ws_context = WebSocketContext(apic_config, aim_manager)
    return ws_context


class AciUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the ACI state.

    This Hash Tree bases observer retrieves and stores state information
    from the ACI REST API.
    """

    def initialize(self, conf_mgr, multiverse):
        super(AciUniverse, self).initialize(conf_mgr, multiverse)
        self._aim_converter = converter.AciToAimModelConverter()
        self.aci_session = self.establish_aci_session(self.conf_manager)
        # Initialize children MOS here so that it globally fails if there's
        # any bug or network partition.
        aci_tenant.get_children_mos(self.aci_session, 'tn-common')
        aci_tenant.get_children_mos(self.aci_session, 'pod-1')
        self.ws_context = get_websocket_context(self.conf_manager,
                                                self.manager)
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

    def serve(self, context, tenants):
        # Verify differences
        global serving_tenants
        if self.ws_context.is_session_reconnected is True:
            self.reset(context, serving_tenants)
            self.ws_context.is_session_reconnected = False
            return
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
                except Exception as e:
                    LOG.debug(traceback.format_exc())
                    LOG.error('Killing manager failed for tenant %s: %s' %
                              (removed, str(e)))
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
                    serving_tenants[added] = aci_tenant.AciTenantManager(
                        added, self.conf_manager, self.aci_session,
                        self.ws_context, self.creation_succeeded,
                        self.tenant_creation_failed, self.aim_system_id,
                        self.get_resources)
                    # A subscription might be leaking here
                    serving_tenants[added]._unsubscribe_tenant()
                    serving_tenants[added].start()
        except Exception as e:
            LOG.error(traceback.format_exc())
            LOG.error('Failed to serve new tenants %s' % tenants)
            # Rollback served tenants
            serving_tenants = serving_tenant_copy
            raise e

    def tenant_creation_failed(self, aim_object, reason='unknown',
                               error=errors.UNKNOWN):
        # New context, sessions are not thread safe.
        store = api.get_store()
        context = aim_ctx.AimContext(store=store)
        self.creation_failed(context, aim_object, reason=reason, error=error)

    def observe(self, context):
        # Copy state accumulated so far
        global serving_tenants
        new_state = {}
        for tenant in serving_tenants.keys():
            # Only copy state if the tenant is warm
            with utils.get_rlock(lcon.ACI_TREE_LOCK_NAME_PREFIX + tenant):
                if serving_tenants[tenant].is_warm():
                    new_state[tenant] = self._get_state_copy(tenant)
        self._state = new_state

    def reset(self, context, tenants):
        # Reset can only be called during reconciliation. serving_tenants
        # can't be modified meanwhile
        global serving_tenants
        LOG.warn('Reset called for roots %s' % tenants)
        for root in tenants:
            if root in serving_tenants:
                try:
                    serving_tenants[root].kill()
                except Exception:
                    LOG.error(traceback.format_exc())
                    LOG.error('Failed to reset tenant %s' % root)

    def push_resources(self, context, resources):
        # Organize by tenant, and push into APIC
        global serving_tenants
        by_tenant = {}
        for method, objects in resources.items():
            for data in objects:
                tenant_name = self._retrieve_tenant_rn(data)
                if tenant_name:
                    by_tenant.setdefault(tenant_name, {}).setdefault(
                        method, []).append(data)

        for tenant, conf in by_tenant.items():
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
            if list(data.keys())[0] == 'tagInst':
                # Retrieve tag parent
                dn = list(data.values())[0]['attributes']['dn']
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
                LOG.debug("Deleting tag for transitioning object %s",
                          list(aci_object.values())[0]['attributes']['dn'])
                aci_type = 'tagInst'
                dn = list(aci_object.values())[0]['attributes'][
                    'dn'] + '/tag-' + self.aim_system_id
                result.append({aci_type: {'attributes': {'dn': dn}}})
            else:
                # If the parent object was already deleted in the config
                # desired tree then we don't have to send this child deletion
                # to APIC
                dn = list(aci_object.values())[0]['attributes']['dn']
                res_type = list(aci_object.keys())[0]
                dn_mgr = apic_client.DNManager()
                mo, rns = dn_mgr.aci_decompose_dn_guess(dn, res_type)
                if len(rns) > 1:
                    parent_dn = dn_mgr.build(rns[:-1])
                    parent_type, xxx = rns[-2]
                    parent_key = tree_manager.AimHashTreeMaker._dn_to_key(
                        parent_type, parent_dn)
                    root = tree_manager.AimHashTreeMaker._extract_root_rn(
                        parent_key)
                    config_desire = self.multiverse[
                        base.CONFIG_UNIVERSE]['desired'].state
                    node = config_desire[root].find(parent_key)
                    if node:
                        result.append(aci_object)
                    # Also has to make sure the parent is not in the monitor
                    # desired tree before we skip it
                    else:
                        mon_desire = self.multiverse[
                            base.MONITOR_UNIVERSE]['desired'].state
                        node = mon_desire[root].find(parent_key)
                        if node:
                            result.append(aci_object)
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

    def update_status_objects(self, context, my_state, raw_diff, skip_keys):
        pass

    def _action_items_to_aim_resources(self, actions, action):
        if action == base.CREATE:
            return actions[action]
        else:
            # it's in ACI format
            return self._aim_converter.convert(actions[action])

    def _get_resource_root(self, action, res):
        if action == base.CREATE:
            return res.root
        else:
            # it's in ACI format
            return tree_manager.AimHashTreeMaker._extract_root_from_dn(
                list(res.values())[0]['attributes']['dn'])


class AciOperationalUniverse(AciUniverse):
    """ACI Universe for operational state."""

    @property
    def name(self):
        return "ACI_Operational_Universe"

    def _get_state_copy(self, tenant):
        global serving_tenants
        return serving_tenants[tenant].get_operational_state_copy()

    def get_resources_for_delete(self, resource_keys):
        curr_mon = self.multiverse[base.MONITOR_UNIVERSE]['current'].state

        def action(result, aci_object, node):
            if node and not node.dummy:
                # Monitored state transition -> Delete the TAG instead
                LOG.debug("Deleting tag for transitioning object %s",
                          list(aci_object.values())[0]['attributes']['dn'])
                aci_type = 'tagInst'
                dn = list(aci_object.values())[0]['attributes'][
                    'dn'] + '/tag-' + self.aim_system_id
                result.append({aci_type: {'attributes': {'dn': dn}}})
            else:
                result.append(aci_object)
        return self._get_resources_for_delete(resource_keys, curr_mon, action)


class AciMonitoredUniverse(AciOperationalUniverse):
    """ACI Universe for monitored state."""

    @property
    def name(self):
        return "ACI_Monitored_Universe"

    def _get_state_copy(self, tenant):
        global serving_tenants
        return serving_tenants[tenant].get_monitored_state_copy()
