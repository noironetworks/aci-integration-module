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

from apicapi import apic_client
from apicapi import exceptions as apic_exc
from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes.aci import tenant as aci_tenant
from aim.agent.aid.universes import base_universe as base
from aim.api import resource
from aim import config


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


class AciUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the ACI state.

    This Hash Tree bases observer retrieves and stores state information
    from the ACI REST API.
    """

    def initialize(self, db_session):
        super(AciUniverse, self).initialize(db_session)
        self.apic_config = self._retrieve_apic_config(db_session)
        self._aim_converter = converter.AciToAimModelConverter()
        self.aci_session = self.establish_aci_session(self.apic_config)
        return self

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
                    serving_tenants[added] = aci_tenant.AciTenantManager(
                        added, self.apic_config, self.aci_session)
                    serving_tenants[added].start()
        except Exception as e:
            LOG.error('Failed to serve new tenants %s' % tenants)
            # Rollback served tenants
            serving_tenants = serving_tenant_copy
            raise e

    def observe(self):
        # Copy state accumulated so far
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

    def _dn_from_key_parts(self, parts):
        rns = ['uni']
        mo = None
        for p in parts:
            mo = apic_client.ManagedObjectClass(p[0])
            rns.append(mo.rn(p[1]) if mo.rn_param_count else mo.rn())
        return mo.klass_name, '/'.join(rns)

    def get_resources(self, resource_keys):
        result = []
        for key in resource_keys:
            fault_code = None
            key_parts = self._split_key(key)
            if key_parts[-1][0] == 'faultInst':
                fault_code = key_parts[-1][1]
                key_parts = key_parts[:-1]
            _, dn = self._dn_from_key_parts(key_parts)
            if fault_code:
                dn += '/fault-%s' % fault_code
            try:
                data = self.aci_session.get_data('mo/' + dn)
                result.append(data[0])
            except apic_exc.ApicResponseNotOk as e:
                if str(e.err_code) == '404':
                    LOG.debug("Resource %s not found", dn)
                    continue
                else:
                    LOG.error(e.message)
                    raise
        return result

    def _retrieve_apic_config(self, db_session):
        # TODO(ivar): DB oriented config
        return config.CONF.apic

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
            mo, dn = self._dn_from_key_parts(self._split_key(key))
            result.append({mo: {'attributes': {'dn': dn}}})
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
            # TODO(ivar): retrieve APIC system ID
            '',
            apic_config.apic_hosts,
            apic_config.apic_username,
            apic_config.apic_password,
            apic_config.apic_use_ssl,
            scope_names=False,
            scope_infra=apic_config.scope_infra,
            renew_names=False,
            verify=apic_config.verify_ssl_certificate,
            request_timeout=apic_config.apic_request_timeout,
            cert_name=apic_config.certificate_name,
            private_key_file=apic_config.private_key_file,
            sign_algo=apic_config.signature_verification_algorithm,
            sign_hash=apic_config.signature_hash_type)


class AciOperationalUniverse(AciUniverse):
    """ACI Universe for operational state."""

    def _get_state_copy(self, tenant):
        global serving_tenants
        return serving_tenants[tenant].get_operational_state_copy()
