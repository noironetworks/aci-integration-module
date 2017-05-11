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
from aim.agent.aid.universes import errors
from aim.api import resource as aim_resource
from aim.api import status as aim_status
from aim import context
from aim import exceptions as aim_exc
from aim import tree_manager


LOG = logging.getLogger(__name__)
ACI_FAULT = 'faultInst'


class AimDbUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the AIM DB state.

    This Hash Tree bases observer retrieves and stores state information
    from the AIM database.
    """

    def initialize(self, store, conf_mgr, multiverse):
        super(AimDbUniverse, self).initialize(store, conf_mgr, multiverse)
        self.tree_manager = tree_manager.HashTreeManager()
        self.context = context.AimContext(store=store)
        self._converter = converter.AciToAimModelConverter()
        self._converter_aim_to_aci = converter.AimToAciModelConverter()
        self._served_tenants = set()
        self._monitored_state_update_failures = 0
        self._max_monitored_state_update_failures = 5
        return self

    def get_state_by_type(self, type):
        try:
            if type == base.CONFIG_UNIVERSE:
                return self.multiverse[base.CONFIG_UNIVERSE]['desired'].state
            else:
                return self.multiverse[type]['current'].state
        except IndexError:
            LOG.warn('Requested universe type %s not found', type)
            return self.state

    def get_relevant_state_for_read(self):
        return [self.state, self.get_state_by_type(base.MONITOR_UNIVERSE)]

    @property
    def name(self):
        return "AIM_Config_Universe"

    def serve(self, tenants):
        tenants = set(tenants)
        new_state = {}
        if self._served_tenants != tenants:
            LOG.debug('%s serving tenants: %s' % (self.name, tenants))
            self._served_tenants = set(tenants)
        for tenant in self._served_tenants:
            new_state.setdefault(tenant, self._state.get(tenant))
        self._state = new_state

    def observe(self):
        self._state.update(self.get_optimized_state(self.state))

    def get_optimized_state(self, other_state, tree=tree_manager.CONFIG_TREE):
        # TODO(ivar): make it tree-version based to reflect metadata changes
        return self._get_state(tree=tree)
        # request = {}
        # for tenant in self._served_tenants:
        #     request[tenant] = None
        #     if tenant in other_state:
        #         try:
        #             request[tenant] = other_state[tenant].root_full_hash
        #         except AttributeError:
        #             # Empty tree
        #             request[tenant] = None
        # return self.tree_manager.find_changed(self.context, request,
        #                                       tree=tree)

    def cleanup_state(self, key):
        self.tree_manager.delete_by_root_rn(self.context, key)

    def _get_state(self, tree=tree_manager.CONFIG_TREE):
        return self.tree_manager.find_changed(
            self.context, dict([(x, None) for x in self._served_tenants]),
            tree=tree)

    @property
    def state(self):
        """State is not kept in memory by this universe, retrieve remotely

        :return: current state
        """
        # Returns state for all the tenants regardless
        return self._state

    def _convert_get_resources_result(self, result, monitored_set):
        result = converter.AciToAimModelConverter().convert(result)
        for item in result:
            if item.dn in monitored_set:
                item.monitored = True
        return result

    def get_resources_for_delete(self, resource_keys):
        des_mon = self.multiverse[base.MONITOR_UNIVERSE]['desired'].state

        def action(result, aci_object, node):
            if not node or node.dummy:
                result.append(aci_object)
        return self._converter.convert(
            self._get_resources_for_delete(resource_keys, des_mon, action))

    def push_resources(self, resources):
        return self._push_resources(resources, monitored=False)

    def _push_resources(self, resources, monitored=False):
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
                        if method == 'create':
                            parents = self._retrieve_fault_parent(resource)
                            for parent in parents:
                                if self.manager.get_status(self.context,
                                                           parent):
                                    LOG.debug("%s for object %s: %s",
                                              self.manager.set_fault.__name__,
                                              parent, resource)
                                    self.manager.set_fault(self.context,
                                                           resource=parent,
                                                           fault=resource)
                                    break
                        else:
                            self.manager.delete(self.context, resource)
                    else:
                        LOG.debug("%s object in AIM %s" %
                                  (method, resource))
                        if method == 'create':
                            if monitored:
                                # We need two more conversions to screen out
                                # unmanaged items
                                resource.monitored = monitored
                                resource = self._converter_aim_to_aci.convert(
                                    [resource])
                                resource = self._converter.convert(resource)[0]
                                resource.monitored = monitored
                            with self.context.store.begin(
                                    subtransactions=True):
                                self.manager.create(self.context, resource,
                                                    overwrite=True,
                                                    fix_ownership=monitored)
                                # Declare victory for the created object
                                self.creation_succeeded(resource)
                        else:
                            if isinstance(resource,
                                          aim_resource.AciRoot) and monitored:
                                # Monitored Universe doesn't delete Tenant
                                # Resources
                                LOG.info('%s skipping delete for object %s' %
                                         (self.name, resource))
                                continue
                            if monitored:
                                # Only delete a resource if monitored
                                with self.context.store.begin(
                                        subtransactions=True):
                                    existing = self.manager.get(self.context,
                                                                resource)
                                    if existing and existing.monitored:
                                        self.manager.delete(self.context,
                                                            resource)
                            else:
                                self.manager.delete(self.context, resource)
                except aim_exc.InvalidMonitoredStateUpdate as e:
                    msg = ("Failed to %s object %s in AIM: %s." %
                           (method, resource, e.message))
                    LOG.error(msg)
                    self.creation_failed(resource, reason=e.message,
                                         error=errors.OPERATION_CRITICAL)
                except Exception as e:
                    LOG.error("Failed to %s object %s in AIM: %s." %
                              (method, resource, e.message))
                    LOG.debug(traceback.format_exc())
                    # REVISIT(ivar): can creation on the AIM side fail? If so,
                    # what can the universe do about it? We can't set sync
                    # status of non existing objects, neither we can remove
                    # objects from ACI-side trees (how would the manual
                    # operation for resync be triggered?)
                    if method == 'delete':
                        self.deletion_failed(resource)
                else:
                    self._monitored_state_update_failures = 0

    def _retrieve_fault_parent(self, fault):
        external = fault.external_identifier
        # external is the DN of the ACI resource
        dn_mgr = apic_client.DNManager()
        mos_rns = dn_mgr.aci_decompose_with_type(external, ACI_FAULT)[:-1]
        rns = dn_mgr.filter_rns(mos_rns)
        conv_info = None
        step = -1
        while conv_info is None or len(conv_info) > 1:
            aci_klass = mos_rns[step][0]
            conv_info = converter.resource_map[aci_klass]
            step -= 1
        conv_info = conv_info[0]
        klasses = [conv_info['resource']]
        if conv_info.get('alt_resource'):
            klasses.append(conv_info['alt_resource'])
        parents = []
        for klass in klasses:
            a_obj = klass(**{y: rns[x]
                             for x, y in enumerate(klass.identity_attributes)})
            parents.append(a_obj)
        return parents

    def _set_sync_pending_state(self, transformed_diff, raw_diff,
                                other_universe):
        aim_add = transformed_diff[base.CREATE]
        # Set AIM differences to sync_pending
        for obj in aim_add:
            self.manager.set_resource_sync_pending(self.context, obj)

    def _set_synced_state(self, my_state, raw_diff):
        all_modified_keys = set(raw_diff[base.CREATE] + raw_diff[base.DELETE])
        pending_nodes = []
        for root, tree in my_state.iteritems():
            pending_nodes.extend(tree.find_by_metadata('pending', True))
            pending_nodes.extend(tree.find_no_metadata('pending'))
        keys_to_sync = set(pending_nodes) - all_modified_keys
        aim_to_sync = self.get_resources(list(keys_to_sync))
        for obj in aim_to_sync:
            self.manager.set_resource_sync_synced(self.context, obj)

    def update_status_objects(self, my_state, other_universe, other_state,
                              raw_diff, transformed_diff):
        # AIM Config Universe is the desired state
        self._set_sync_pending_state(transformed_diff, raw_diff,
                                     other_universe)
        self._set_synced_state(my_state, raw_diff)


class AimDbOperationalUniverse(AimDbUniverse):

    @property
    def name(self):
        return "AIM_Operational_Universe"

    def get_relevant_state_for_read(self):
        return [self.state]

    def get_optimized_state(
            self, other_state, tree=tree_manager.OPERATIONAL_TREE):
        return super(AimDbOperationalUniverse, self).get_optimized_state(
            other_state, tree=tree)

    def reconcile(self, other_universe, delete_candidates):
        # When the other universes are ok with deleting a Tenant, there's no
        # reason for the Operational Universe to oppose that decision
        return self._reconcile(other_universe, delete_candidates,
                               always_vote_deletion=True)

    def update_status_objects(self, my_state, other_state, other_universe,
                              raw_diff, transformed_diff):
        pass


class AimDbMonitoredUniverse(AimDbUniverse):

    @property
    def name(self):
        return "AIM_Monitored_Universe"

    def get_relevant_state_for_read(self):
        return [self.state, self.get_state_by_type(base.CONFIG_UNIVERSE)]

    def get_optimized_state(
            self, other_state, tree=tree_manager.MONITORED_TREE):
        return super(AimDbMonitoredUniverse, self).get_optimized_state(
            other_state, tree=tree)

    def push_resources(self, resources):
        self._push_resources(resources, monitored=True)

    def reconcile(self, other_universe, delete_candidates):
        # We want monitored universe to stop reconciling when the corresponding
        # AIM tenant doesn't exist.
        return self._reconcile(other_universe, delete_candidates,
                               skip_dummy=True)

    def update_status_objects(self, my_state, other_universe, other_state,
                              raw_diff, transformed_diff):
        # AIM Monitored Universe is current state
        add_diff = {
            base.CREATE: self.get_resources(list(raw_diff[base.CREATE]))}
        self._set_sync_pending_state(add_diff, raw_diff, other_universe)
        self._set_synced_state(my_state, raw_diff)
