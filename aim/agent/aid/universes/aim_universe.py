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

import traceback

from apicapi import apic_client
from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes import base_universe as base
from aim.api import resource as aim_resource
from aim.api import status as aim_status
from aim import context
from aim.db import tree_model
from aim import exceptions as aim_exc


LOG = logging.getLogger(__name__)
ACI_FAULT = 'faultInst'


class AimDbUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the AIM DB state.

    This Hash Tree bases observer retrieves and stores state information
    from the AIM database.
    """

    def initialize(self, db_session, conf_mgr):
        super(AimDbUniverse, self).initialize(db_session, conf_mgr)
        self.tree_manager = tree_model.TenantHashTreeManager()
        self.context = context.AimContext(db_session)
        self._converter = converter.AciToAimModelConverter()
        self._converter_aim_to_aci = converter.AimToAciModelConverter()
        self._served_tenants = set()
        return self

    @property
    def name(self):
        return "AIM_Config_Universe"

    def serve(self, tenants):
        LOG.debug('Serving tenants: %s' % tenants)
        self._served_tenants = set(tenants)

    def observe(self):
        pass

    def get_optimized_state(self, other_state, tree=tree_model.CONFIG_TREE):
        request = {}
        for tenant in self._served_tenants:
            request[tenant] = None
            if tenant in other_state:
                try:
                    request[tenant] = other_state[tenant].root_full_hash
                except AttributeError:
                    # Empty tree
                    request[tenant] = None
        return self.tree_manager.find_changed(self.context, request, tree=tree)

    def cleanup_state(self, key):
        self.tree_manager.delete_by_tenant_rn(self.context, key)

    def _get_state(self, tree=tree_model.CONFIG_TREE):
        return self.tree_manager.find_changed(
            self.context, dict([(x, None) for x in self._served_tenants]),
            tree=tree)

    @property
    def state(self):
        """State is not kept in memory by this universe, retrieve remotely

        :return: current state
        """
        # Returns state for all the tenants regardless
        return self._get_state()

    def get_resources(self, resource_keys):
        if resource_keys:
            LOG.debug("Requesting resource keys in AIM Universe: %s",
                      resource_keys)
        result = []
        id_set = set()
        for key in resource_keys:
            fault_code = None
            dissected = self._dissect_key(key)
            if dissected[0] == ACI_FAULT:
                fault_code = dissected[1][-1]
                dissected = self._dissect_key(key[:-1])
                key = key[:-1]
            aci_dn = apic_client.DNManager().build(
                [tuple(x.split('|')) for x in key])
            aci_klass = apic_client.DNManager().aci_decompose_dn_guess(
                aci_dn, dissected[0])[0]
            klass = converter.resource_map[aci_klass][0]['resource']
            res = klass(
                **dict([(y, dissected[1][x])
                        for x, y in enumerate(klass.identity_attributes)]))
            id_tuple = tuple([(x, getattr(res, x)) for x in
                              res.identity_attributes])
            if fault_code:
                id_tuple += ('fault', fault_code)
            if id_tuple not in id_set:
                try:
                    if fault_code:
                        res_db = None
                        res_status = self.manager.get_status(self.context, res)
                        if res_status:
                            for fault in res_status.faults:
                                if fault.fault_code == fault_code:
                                    res_db = fault
                                    break
                    else:
                        res_db = self.manager.get(self.context, res)
                    if res_db:
                        result.append(res_db)
                        id_set.add(id_tuple)
                except aim_exc.UnknownResourceType:
                    LOG.warn("Resource %s is not defined in AIM", dissected)
                    result.append(res)
                    id_set.add(id_tuple)
        if resource_keys:
            LOG.debug("Result for keys %s in AIM Universe: %s" %
                      (resource_keys, result))
        return list(result)

    def get_resources_for_delete(self, resource_keys):
        return self.get_resources(resource_keys)

    def push_resources(self, resources):
        return self._push_resources(resources, monitored=False)

    def _push_resources(self, resources, monitored=False):
        fault_method = {'create': self.manager.set_fault,
                        'delete': self.manager.clear_fault}
        for method in resources:
            if method == 'delete':
                # Use ACI items directly
                items = resources[method]
            else:
                # Convert everything before creating
                items = self._converter.convert(resources[method])
            for resource in items:
                # Items are in the other universe's format unless deletion
                try:
                    if isinstance(resource, aim_status.AciFault):
                        # Retrieve fault's parent and set/unset the fault
                        parent = self._retrieve_fault_parent(resource)
                        LOG.debug(
                            "%s for object %s: %s" %
                            (fault_method[method].__name__,
                             parent.__dict__, resource.__dict__))
                        fault_method[method](self.context,
                                             resource=parent,
                                             fault=resource)
                    else:
                        LOG.debug(
                            "%s object %s" %
                            (fault_method[method].__name__,
                             resource.__dict__))
                        if isinstance(resource,
                                      aim_resource.Tenant) and monitored:
                            # Monitored Universe doesn't interact with Tenant
                            # Resources
                            continue
                        if method == 'create':
                            if monitored:
                                # We need two more conversions to screen out
                                # unmanaged items
                                resource.monitored = monitored
                                resource = self._converter_aim_to_aci.convert(
                                    [resource])
                                resource = self._converter.convert(resource)[0]
                                resource.monitored = monitored
                            self.manager.create(self.context, resource,
                                                overwrite=True)
                        else:
                            self.manager.delete(self.context, resource)
                except Exception as e:
                    LOG.error("Failed to %s object %s in AIM: %s." %
                              (method, resource, e.message))
                    LOG.debug(traceback.format_exc())

    def _retrieve_fault_parent(self, fault):
        external = fault.external_identifier
        # external is the DN of the ACI resource
        dn_mgr = apic_client.DNManager()
        # this will be enough in order to get the parent
        decomposed = dn_mgr.aci_decompose_with_type(external, ACI_FAULT)[:-1]
        aci_parent = {
            decomposed[-1][0]: {
                'attributes': {'dn': dn_mgr.build(decomposed)}}}
        return self._converter.convert([aci_parent])[0]


class AimDbOperationalUniverse(AimDbUniverse):

    @property
    def state(self):
        return self._get_state(tree=tree_model.OPERATIONAL_TREE)

    @property
    def name(self):
        return "AIM_Operational_Universe"

    def get_optimized_state(self, other_state):
        return super(AimDbOperationalUniverse, self).get_optimized_state(
            other_state, tree=tree_model.OPERATIONAL_TREE)

    def reconcile(self, other_universe, delete_candidates):
        # When the other universes are ok with deleting a Tenant, there's no
        # reason for the Operational Universe to oppose that decision
        return self._reconcile(other_universe, delete_candidates,
                               always_vote_deletion=True)


class AimDbMonitoredUniverse(AimDbUniverse):
    @property
    def state(self):
        return self._get_state(tree=tree_model.MONITORED_TREE)

    @property
    def name(self):
        return "AIM_Monitored_Universe"

    def get_optimized_state(self, other_state):
        return super(AimDbMonitoredUniverse, self).get_optimized_state(
            other_state, tree=tree_model.MONITORED_TREE)

    def push_resources(self, resources):
        self._push_resources(resources, monitored=True)

    def reconcile(self, other_universe, delete_candidates):
        # We want monitored universe to stop reconciling when the corresponding
        # AIM tenant doesn't exist.
        return self._reconcile(other_universe, delete_candidates,
                               skip_dummy=True)
