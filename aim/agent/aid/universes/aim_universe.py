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

import copy
import traceback

from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes import base_universe as base
from aim.api import resource as aim_resource
from aim.api import status as aim_status
from aim.common import utils
from aim.db import hashtree_db_listener
from aim import exceptions as aim_exc
from aim import tree_manager


LOG = logging.getLogger(__name__)


class AimDbUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the AIM DB state.

    This Hash Tree bases observer retrieves and stores state information
    from the AIM database.
    """

    def initialize(self, conf_mgr, multiverse):
        super(AimDbUniverse, self).initialize(conf_mgr, multiverse)
        self.tree_manager = tree_manager.HashTreeManager()
        self._converter = converter.AciToAimModelConverter()
        self._converter_aim_to_aci = converter.AimToAciModelConverter()
        self._served_tenants = set()
        self._monitored_state_update_failures = 0
        self._max_monitored_state_update_failures = 5
        self._recovery_interval = conf_mgr.get_option(
            'error_state_recovery_interval', 'aim')
        self.schedule_next_recovery()
        return self

    def schedule_next_recovery(self):
        self._scheduled_recovery = utils.schedule_next_event(
            self._recovery_interval, 0.2)

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

    def serve(self, context, tenants):
        tenants = set(tenants)
        new_state = {}
        if self._served_tenants != tenants:
            LOG.debug('%s serving tenants: %s' % (self.name, tenants))
            self._served_tenants = set(tenants)
        for tenant in self._served_tenants:
            new_state.setdefault(tenant, self._state.get(tenant))
        self._state = new_state

    def observe(self, context):
        # TODO(ivar): move this to a separate thread and add scheduled reset
        # mechanism
        served_tenants = copy.deepcopy(self._served_tenants)
        # TODO(ivar): object based reset scheduling would be more correct
        # to prevent objects from being re-tried too soon.
        # This will require working with the DB timestamp and proper range
        # query design.
        htdbl = hashtree_db_listener.HashTreeDbListener(self.manager)
        if utils.get_time() > self._scheduled_recovery:
            for root in served_tenants:
                self.manager.recover_root_errors(context, root)
            htdbl.cleanup_zombie_status_objects(context, served_tenants)
            self.schedule_next_recovery()
        htdbl.catch_up_with_action_log(context.store, served_tenants)
        # REVISIT(ivar): what if a root is marked as needs_reset? we could
        # avoid syncing it altogether
        self._state.update(self.get_optimized_state(context, self.state))

    def reset(self, context, tenants):
        LOG.warn('Reset called for roots %s' % tenants)
        for root in tenants:
            hashtree_db_listener.HashTreeDbListener(
                self.manager).tt_mgr.set_needs_reset_by_root_rn(context, root)

    def get_optimized_state(self, context, other_state,
                            tree=tree_manager.CONFIG_TREE):
        # TODO(ivar): make it tree-version based to reflect metadata changes
        return self._get_state(context, tree=tree)

    def cleanup_state(self, context, key):
        # Only delete if state is still empty. Never remove a tenant if there
        # are leftovers.
        with context.store.begin(subtransactions=True):
            # There could still be logs, but they will re-create the
            # tenants in the next iteration.
            self.tree_manager.delete_by_root_rn(context, key, if_empty=True)

    def _get_state(self, context, tree=tree_manager.CONFIG_TREE):
        return self.tree_manager.find_changed(
            context, dict([(x, None) for x in self._served_tenants]),
            tree=tree)

    @property
    def state(self):
        """State is not kept in memory by this universe, retrieve remotely

        :return: current state
        """
        # Returns state for all the tenants regardless
        return self._state

    def vote_deletion_candidates(self, context, other_universe,
                                 delete_candidates, vetoes):
        # Deletion candidates will be decided solely by the AIM configuration
        # universe.
        my_state = self.state
        for tenant, tree in my_state.items():
            if not tree.root and tenant not in vetoes:
                # The desired state for this tentant is empty
                delete_candidates.add(tenant)

    def finalize_deletion_candidates(self, context, other_universe,
                                     delete_candidates):
        super(AimDbUniverse, self).finalize_deletion_candidates(
            context, other_universe, delete_candidates)
        other_state = other_universe.state
        for tenant in list(delete_candidates):
            # Remove tenants that have been emptied.
            if tenant not in other_state or not other_state[tenant].root:
                pass
            else:
                delete_candidates.discard(tenant)

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

    def push_resources(self, context, resources):
        return self._push_resources(context, resources, monitored=False)

    def _push_resources(self, context, resources, monitored=False):
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
                    self._push_resource(context, resource, method, monitored)
                except aim_exc.InvalidMonitoredStateUpdate as e:
                    msg = ("Failed to %s object %s in AIM: %s." %
                           (method, resource, str(e)))
                    LOG.warn(msg)
                except Exception as e:
                    LOG.error("Failed to %s object %s in AIM: %s." %
                              (method, resource, str(e)))
                    LOG.debug(traceback.format_exc())
                    if method == 'delete':
                        self.deletion_failed(context, resource)
                else:
                    self._monitored_state_update_failures = 0

    def _push_resource(self, context, resource, method, monitored):
        if isinstance(resource, aim_status.AciFault):
            # Retrieve fault's parent and set/unset the fault
            if method == 'create':
                parents = utils.retrieve_fault_parent(
                    resource.external_identifier, converter.resource_map)
                for parent in parents:
                    if self.manager.get_status(context, parent):
                        LOG.debug("%s for object %s: %s",
                                  self.manager.set_fault.__name__, parent,
                                  resource)
                        self.manager.set_fault(context, resource=parent,
                                               fault=resource)
                        break
            else:
                self.manager.delete(context, resource)
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
                with context.store.begin(subtransactions=True):
                    if isinstance(resource, aim_resource.AciRoot):
                        # Roots should not be created by the
                        # AIM monitored universe.
                        # NOTE(ivar): there are contention cases
                        # where a user might delete a Root object
                        # right before the AIM Monitored Universe
                        # pushes an update on it. If we run a
                        # simple "create overwrite" this would
                        # re-create the object and AID would keep
                        # monitoring said root. by only updating
                        # roots and never creating them, we give
                        # full control over which trees to monitor
                        # to the user.
                        ext = context.store.extract_attributes
                        obj = self.manager.update(
                            context, resource, fix_ownership=monitored,
                            **ext(resource, "other"))
                        if obj:
                            # Declare victory for the update
                            self.creation_succeeded(resource)
                    else:
                        self.manager.create(
                            context, resource, overwrite=True,
                            fix_ownership=monitored)
                        # Declare victory for the created object
                        self.creation_succeeded(resource)
            else:
                if isinstance(resource, aim_resource.AciRoot) and monitored:
                    # Monitored Universe doesn't delete Tenant
                    # Resources
                    LOG.info('%s skipping delete for object %s' %
                             (self.name, resource))
                    return
                if monitored:
                    # Only delete a resource if monitored
                    with context.store.begin(subtransactions=True):
                        existing = self.manager.get(context, resource)
                        if existing and existing.monitored:
                            self.manager.delete(context, resource)
                else:
                    self.manager.delete(context, resource)

    def _get_state_pending_na_nodes(self, tenant_state):
        pending_nodes = []
        na_nodes = []
        pending_nodes.extend(tenant_state.find_by_metadata('pending', True))
        na_nodes.extend(tenant_state.find_no_metadata('pending'))
        return pending_nodes, na_nodes

    def _set_sync_pending_state(self, context, raw_diff, pending_nodes):
        all_modified_keys = set(raw_diff[base.CREATE])
        keys_to_sync = all_modified_keys - set(pending_nodes)
        aim_to_sync = self.get_resources(list(keys_to_sync))
        for obj in aim_to_sync:
            self.manager.set_resource_sync_pending(context, obj)

    def _set_synced_state(self, context, raw_diff, unsynced_nodes, skip_keys):
        all_modified_keys = set(raw_diff[base.CREATE] + raw_diff[base.DELETE])
        keys_to_sync = (set(unsynced_nodes) - all_modified_keys) - skip_keys
        aim_to_sync = self.get_resources(list(keys_to_sync))
        for obj in aim_to_sync:
            self.manager.set_resource_sync_synced(context, obj)

    def update_status_objects(self, context, tenant_state, raw_diff,
                              skip_keys):
        # AIM Config Universe is the desired state
        pending_nodes, na_nodes = self._get_state_pending_na_nodes(
            tenant_state)
        self._set_sync_pending_state(context, raw_diff, pending_nodes)
        self._set_synced_state(context, raw_diff, pending_nodes + na_nodes,
                               skip_keys)

    def _action_items_to_aim_resources(self, actions, action):
        if action == base.DELETE:
            return actions[action]
        else:
            return self._converter.convert(actions[action])

    def _get_resource_root(self, action, res):
        if action == base.DELETE:
            return res.root
        else:
            # it's in ACI format
            return tree_manager.AimHashTreeMaker._extract_root_from_dn(
                list(res.values())[0]['attributes']['dn'])


class AimDbOperationalUniverse(AimDbUniverse):

    def initialize(self, conf_mgr, multiverse):
        # Only one AIM universe does the recovery
        super(AimDbOperationalUniverse, self).initialize(conf_mgr, multiverse)
        self._scheduled_recovery = float('inf')
        return self

    @property
    def name(self):
        return "AIM_Operational_Universe"

    def schedule_next_recovery(self):
        pass

    def get_relevant_state_for_read(self):
        return [self.state]

    def get_optimized_state(self, context, other_state,
                            tree=tree_manager.OPERATIONAL_TREE):
        return super(AimDbOperationalUniverse, self).get_optimized_state(
            context, other_state, tree=tree)

    def vote_deletion_candidates(self, context, other_universe,
                                 delete_candidates, vetoes):
        pass

    def finalize_deletion_candidates(self, context, other_universe,
                                     delete_candidates):
        super(AimDbOperationalUniverse, self).finalize_deletion_candidates(
            context, other_universe, delete_candidates)
        my_state = self.state
        for tenant in list(delete_candidates):
            # Remove tenants that have been emptied.
            if tenant not in my_state or not my_state[tenant].root:
                pass
            else:
                # AIM monitored DB still has stuff to delete
                delete_candidates.discard(tenant)

    def reconcile(self, context, other_universe, delete_candidates):
        self._mask_tenant_state(other_universe, delete_candidates)
        return self._reconcile(context, other_universe)

    def update_status_objects(self, context, tenant_state, raw_diff,
                              skip_keys):
        pass


class AimDbMonitoredUniverse(AimDbUniverse):

    def initialize(self, conf_mgr, multiverse):
        # Only one AIM universe does the recovery
        super(AimDbMonitoredUniverse, self).initialize(conf_mgr, multiverse)
        self._scheduled_recovery = float('inf')
        return self

    @property
    def name(self):
        return "AIM_Monitored_Universe"

    def schedule_next_recovery(self):
        pass

    def get_relevant_state_for_read(self):
        return [self.state, self.get_state_by_type(base.CONFIG_UNIVERSE)]

    def get_optimized_state(self, context, other_state,
                            tree=tree_manager.MONITORED_TREE):
        return super(AimDbMonitoredUniverse, self).get_optimized_state(
            context, other_state, tree=tree)

    def push_resources(self, context, resources):
        self._push_resources(context, resources, monitored=True)

    def vote_deletion_candidates(self, context, other_universe,
                                 delete_candidates, vetoes):
        my_state = self.state
        # Veto tenants with non-dummy roots
        for tenant, tree in my_state.items():
            if tree.root and not tree.root.dummy:
                delete_candidates.discard(tenant)
                vetoes.add(tenant)

    def finalize_deletion_candidates(self, context, other_universe,
                                     delete_candidates):
        super(AimDbMonitoredUniverse, self).finalize_deletion_candidates(
            context, other_universe, delete_candidates)
        my_state = self.state
        for tenant in list(delete_candidates):
            # Remove tenants that have been emptied.
            if tenant not in my_state or not my_state[tenant].root:
                pass
            else:
                # AIM monitored DB still has stuff to delete
                delete_candidates.discard(tenant)

    def reconcile(self, context, other_universe, delete_candidates):
        self._mask_tenant_state(other_universe, delete_candidates)
        return self._reconcile(context, other_universe)

    def get_resources_for_delete(self, resource_keys):
        des_mon = self.multiverse[base.MONITOR_UNIVERSE]['desired'].state

        def action(result, aci_object, node):
            key = tree_manager.AimHashTreeMaker._dn_to_key(
                list(aci_object.keys())[0],
                list(aci_object.values())[0]['attributes']['dn'])
            if len(key) == 1:
                LOG.debug('Skipping delete for monitored root object: %s '
                          % aci_object)
                return
            if not node or node.dummy:
                result.append(aci_object)
        return self._converter.convert(
            self._get_resources_for_delete(resource_keys, des_mon, action))
