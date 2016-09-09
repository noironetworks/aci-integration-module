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

from acitoolkit import acitoolkit
from apicapi import apic_client
from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes.aci import tenant as aci_tenant
from aim.agent.aid.universes import base_universe as base
from aim.api import resource
from aim import exceptions


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
    message = ("Web socket session failed to login for tenant %(tn_name)s "
               "with error %(code)s: %(text)s")


class WebSocketContext(object):
    """Placeholder for websocket session"""

    def __init__(self, apic_config):
        self.apic_config = apic_config
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
        protocol = 'https' if self.apic_use_ssl else 'http'
        self.ws_urls = ['%s://%s' % (protocol, host) for host in
                        self.apic_hosts]
        self.establish_ws_session()

    def _reload_websocket_config(self):
        # Don't subscribe in this case
        self.apic_use_ssl = self.apic_config.get_option(
            'apic_use_ssl', group='apic')
        self.apic_hosts = self.apic_config.get_option(
            'apic_hosts', group='apic')
        self.apic_username = self.apic_config.get_option(
            'apic_username', group='apic')
        self.apic_password = self.apic_config.get_option(
            'apic_password', group='apic')
        self.verify_ssl_certificate = self.apic_config.get_option(
            'verify_ssl_certificate', group='apic')
        protocol = 'https' if self.apic_use_ssl else 'http'
        self.ws_urls = ['%s://%s' % (protocol, host) for host in
                        self.apic_hosts]

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
            verify_ssl=self.verify_ssl_certificate)
        resp = self.session.login()
        if not resp.ok:
            # TODO(ivar): tenant name doesn't make sense here
            raise WebSocketSessionLoginFailed(tn_name='',
                                              code=resp.status_code,
                                              text=resp.text)

    def _ws_config_callback(self, new_conf):
        # If any of the WS related configurations changed, reload fresh values
        # and reconnect the WS
        if getattr(self, new_conf['key']) != new_conf['value']:
            LOG.debug("New APIC remote configuration, restarting web socket "
                      "session.")
            self._reload_websocket_config()
            # Log out WS
            if self.session.session:
                self.session.close()
            self.establish_ws_session()


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

    def initialize(self, db_session, conf_mgr):
        super(AciUniverse, self).initialize(db_session, conf_mgr)
        self._aim_converter = converter.AciToAimModelConverter()
        self.aci_session = self.establish_aci_session(self.conf_manager)
        self.ws_context = get_websocket_context(self.conf_manager)
        return self

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
                if (added not in serving_tenants or not
                        serving_tenants[added].health_state or
                        serving_tenants[added].is_dead()):
                    LOG.debug("Adding new tenant %s" % added)
                    # Start thread or replace broken one
                    # Checking the 'dead' state helps those cases in which
                    # a kill successfully happened but then  the state was
                    # rolled back by a further exception
                    if added in serving_tenants:
                        LOG.debug(
                            "Tenant %s was served but needs to be replaced: "
                            "healthy-%s, dead-%s",
                            added,
                            serving_tenants[added].health_state,
                            serving_tenants[added].is_dead())
                        # Cleanup the tenant's state
                        serving_tenants[added].kill()
                        serving_tenants[added]._unsubscribe_tenant()
                    serving_tenants[added] = aci_tenant.AciTenantManager(
                        added, self.conf_manager, self.aci_session,
                        self.ws_context)
                    serving_tenants[added].start()
        except Exception as e:
            LOG.error('Failed to serve new tenants %s' % tenants)
            # Rollback served tenants
            serving_tenants = serving_tenant_copy
            raise e

    def observe(self):
        # Copy state accumulated so far
        global serving_tenants
        for tenant in serving_tenants:
            # Only copy state if the tenant is warm
            if serving_tenants[tenant].is_warm():
                self._state[tenant] = self._get_state_copy(tenant)

    def push_resources(self, resources):
        # Organize by tenant, and push into APIC
        global serving_tenants
        by_tenant = {}
        for method, objects in resources.iteritems():
            for data in objects:
                tenant_name = self._retrieve_tenant_name(data)
                by_tenant.setdefault(tenant_name, {}).setdefault(
                    method, []).append(data)

        for tenant, conf in by_tenant.iteritems():
            try:
                serving_tenants[tenant].push_aim_resources(conf)
            except KeyError:
                LOG.warn("Tenant %s is not being served anymore" % tenant)

    def _split_key(self, key):
        return [k.split('|', 2) for k in key]

    def get_resources(self, resource_keys):
        result = []
        for key in resource_keys:
            fault_code = None
            key_parts = self._split_key(key)
            mo_type = key_parts[-1][0]
            aci_object = {mo_type: {'attributes': {}}}
            if mo_type == 'faultInst':
                fault_code = key_parts[-1][1]
                key_parts = key_parts[:-1]
            dn = apic_client.DNManager().build(key_parts)
            if fault_code:
                dn += '/fault-%s' % fault_code
                aci_object[mo_type]['attributes']['code'] = fault_code
            aci_object[mo_type]['attributes']['dn'] = dn
            result.append(aci_object)
        return aci_tenant.AciTenantManager.retrieve_aci_objects(
            result, self._aim_converter, self.aci_session, get_all=True,
            include_tags=False)

    def _retrieve_tenant_name(self, data):
        if isinstance(data, dict):
            data = self._aim_converter.convert([data])[0]
        if isinstance(data, resource.Tenant):
            return data.name
        elif isinstance(data, resource.ResourceBase):
            return data.tenant_name

    def get_resources_for_delete(self, resource_keys):
        result = []
        for key in resource_keys:
            key_parts = self._split_key(key)
            dn = apic_client.DNManager().build(key_parts)
            result.append({key_parts[-1][0]: {'attributes': {'dn': dn}}})
        return result

    def _get_state_copy(self, tenant):
        global serving_tenants
        return serving_tenants[tenant].get_state_copy()

    @staticmethod
    def establish_aci_session(apic_config):
        # TODO(IVAR): unnecessary things will be removed once apicapi gets its
        # own refactor.
        return apic_client.RestClient(
            logging,
            apic_config.get_option('apic_system_id'),
            apic_config.get_option('apic_hosts', group='apic'),
            apic_config.get_option('apic_username', group='apic'),
            apic_config.get_option('apic_password', group='apic'),
            apic_config.get_option('apic_use_ssl', group='apic'),
            scope_names=apic_config.get_option('scope_names', group='apic'),
            scope_infra=apic_config.get_option('scope_infra', group='apic'),
            renew_names=False,
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
