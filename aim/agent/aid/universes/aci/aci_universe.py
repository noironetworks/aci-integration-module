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

from oslo_log import log as logging

from aim.agent.aid.universes.aci import tenant as aci_tenant
from aim.agent.aid.universes import base_universe as base
from aim import config


LOG = logging.getLogger(__name__)


class AciUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the ACI state.

    This Hash Tree bases observer retrieves and stores state information
    from the ACI REST API.
    """

    def initialize(self, db_session):
        super(AciUniverse, self).initialize(db_session)
        self.apic_config = self._retrieve_apic_config(db_session)
        # dictionary of tenants currently served tenants. Keys are the tenants'
        # name, values the Web Socket interfaces
        self._serving_tenants = {}
        return self

    def serve(self, tenants):
        # Verify differences
        try:
            serving_tenant_copy = self._serving_tenants
            self._serving_tenants = {}
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
                        self._serving_tenants[added] = serving_tenant_copy[
                            added]
                    except KeyError:
                        LOG.debug("%s not found in %s during serving copy" %
                                  (added, serving_tenant_copy))
                if (added not in self._serving_tenants or not
                        self._serving_tenants[added].health_state or
                        self._serving_tenants[added].is_dead()):
                    # Start thread or replace broken one
                    # Checking the 'dead' state helps those cases in which
                    # a kill successfully happened but then  the state was
                    # rolled back by a further exception
                    self._serving_tenants[added] = aci_tenant.AciTenantManager(
                        added, self.apic_config)
                    self._serving_tenants[added].start()
        except Exception as e:
            LOG.error('Failed to serve new tenants %s' % tenants)
            # Rollback served tenants
            self._serving_tenants = serving_tenant_copy
            raise e

    def observe(self):
        # Copy state accumulated so far
        for tenant in self._serving_tenants:
            self._state[tenant] = self._serving_tenants[
                tenant].get_state_copy()

    def push_aim_resources(self, resources):
        # Organize by tenant, and push into APIC
        by_tenant = {}
        for method, objects in resources.iteritems():
            for data in objects:
                by_tenant.setdefault(
                    data.tenant_name, {}).setdefault(
                    method, []).append(data)

        for tenant, conf in by_tenant.iteritems():
            try:
                self._serving_tenants[tenant].push_aim_resources(conf)
            except KeyError:
                LOG.warn("Tenant %s is not being served anymore" % tenant)

    def _retrieve_apic_config(self, db_session):
        # TODO(ivar): DB oriented config
        return config.CONF.apic
