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

from aim.agent.aid.universes import base_universe as base
from aim import context
from aim.db import tree_model


LOG = logging.getLogger(__name__)


class AimDbUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the AIM DB state.

    This Hash Tree bases observer retrieves and stores state information
    from the AIM database.
    """

    def initialize(self, db_session):
        super(AimDbUniverse, self).initialize(db_session)
        self.tree_manager = tree_model.TenantHashTreeManager()
        self.context = context.AimContext(db_session)
        self._served_tenants = set()
        return self

    def serve(self, tenants):
        LOG.debug('Serving tenants: %s' % tenants)
        self._served_tenants = set(tenants)

    def observe(self):
        pass

    def get_optimized_state(self, other_state):
        request = {}
        for tenant in self._served_tenants:
            request[tenant] = None
            if tenant in other_state:
                try:
                    request[tenant] = other_state[tenant].root_full_hash
                except AttributeError:
                    # Empty tree
                    request[tenant] = None
        return self.tree_manager.find_changed(self.context, request)

    def cleanup_state(self, key):
        self.tree_manager.delete_by_tenant_rn(self.context, key)

    @property
    def state(self):
        """State is not kept in memory by this universe, retrieve remotely

        :return: current state
        """
        # Returns state for all the tenants regardless
        return self.tree_manager.find_changed(
            self.context, dict([(x, None) for x in self._served_tenants]))

    def reconcile(self, other_universe):
        # For now, reconciliation into AIM cannot be done
        raise NotImplementedError
