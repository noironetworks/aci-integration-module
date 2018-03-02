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

from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes import base_universe as base
from aim.api import resource as aim_resource
from aim.api import status as aim_status
from aim.common import utils
from aim import context
from aim.db import hashtree_db_listener
from aim import exceptions as aim_exc
from aim import tree_manager


LOG = logging.getLogger(__name__)


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

    @utils.fix_session_if_needed
    def observe(self):
        # TODO(ivar): move this to a separate thread and add scheduled reset
        # mechanism
        hashtree_db_listener.HashTreeDbListener(
            self.manager).catch_up_with_action_log(self.context.store,
                                                   self._served_tenants)
        # REVISIT(ivar): what if a root is marked as needs_reset? we could
        # avoid syncing it altogether
        self._state.update(self.get_optimized_state(self.state))

    @utils.fix_session_if_needed
    def reset(self, tenants):
        LOG.warn('Reset called for roots %s' % tenants)
        for root in tenants:
            hashtree_db_listener.HashTreeDbListener(
                self.manager).tt_mgr.set_needs_reset_by_root_rn(
                self.context, root)

    def get_optimized_state(self, other_state, tree=tree_manager.CONFIG_TREE):
        # TODO(ivar): make it tree-version based to reflect metadata changes
        return self._get_state(tree=tree)

    @utils.fix_session_if_needed
    def cleanup_state(self, key):
        # Only delete if state is still empty. Never remove a tenant if there
        # are leftovers.
        with self.context.store.begin(subtransactions=True):
            # There could still be logs, but they will re-create the
            # tenants in the next iteration.
            self.tree_manager.delete_by_root_rn(self.context, key,
                                                if_empty=True)

    @utils.fix_session_if_needed
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

    def vote_deletion_candidates(self, other_universe, delete_candidates,
                                 vetoes):
        # Deletion candidates will be decided solely by the AIM configuration
        # universe.
        my_state = self.state
        for tenant, tree in my_state.iteritems():
            if not tree.root and tenant not in vetoes:
                # The desired state for this tentant is empty
                delete_candidates.add(tenant)

    def finalize_deletion_candidates(self, other_universe, delete_candidates):
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
                    self._push_resource(resource, method, monitored)
                except aim_exc.InvalidMonitoredStateUpdate as e:
                    msg = ("Failed to %s object %s in AIM: %s." %
                           (method, resource, e.message))
                    LOG.warn(msg)
                except Exception as e:
                    LOG.error("Failed to %s object %s in AIM: %s." %
                              (method, resource, e.message))
                    LOG.debug(traceback.format_exc())
                    if method == 'delete':
                        self.deletion_failed(resource)
                else:
                    self._monitored_state_update_failures = 0

    @utils.fix_session_if_needed
    def _push_resource(self, resource, method, monitored):
        if isinstance(resource, aim_status.AciFault):
            # Retrieve fault's parent and set/unset the fault
            if method == 'create':
                parents = utils.retrieve_fault_parent(
                    resource.external_identifier, converter.resource_map)
                for parent in parents:
                    if self.manager.get_status(self.context, parent):
                        LOG.debug("%s for object %s: %s",
                                  self.manager.set_fault.__name__, parent,
                                  resource)
                        self.manager.set_fault(self.context, resource=parent,
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
                        ext = self.context.store.extract_attributes
                        obj = self.manager.update(
                            self.context, resource,
                            fix_ownership=monitored,
                            **ext(resource, "other"))
                        if obj:
                            # Declare victory for the update
                            self.creation_succeeded(resource)
                    else:
                        self.manager.create(
                            self.context, resource, overwrite=True,
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
                    with self.context.store.begin(subtransactions=True):
                        existing = self.manager.get(self.context,
                                                    resource)
                        if existing and existing.monitored:
                            self.manager.delete(self.context,
                                                resource)
                else:
                    self.manager.delete(self.context, resource)

    @utils.fix_session_if_needed
    def _set_sync_pending_state(self, transformed_diff, raw_diff,
                                other_universe, skip_roots=None):
        skip_roots = skip_roots or []
        aim_add = transformed_diff[base.CREATE]
        # Set AIM differences to sync_pending
        for obj in aim_add:
            if obj.root not in skip_roots:
                self.manager.set_resource_sync_pending(self.context, obj)

    @utils.fix_session_if_needed
    def _set_synced_state(self, my_state, raw_diff, skip_roots=None):
        skip_roots = skip_roots or []
        all_modified_keys = set(raw_diff[base.CREATE] + raw_diff[base.DELETE])
        pending_nodes = []
        for root, tree in my_state.iteritems():
            if root not in skip_roots:
                pending_nodes.extend(tree.find_by_metadata('pending', True))
                pending_nodes.extend(tree.find_no_metadata('pending'))
        keys_to_sync = set(pending_nodes) - all_modified_keys
        aim_to_sync = self.get_resources(list(keys_to_sync))
        for obj in aim_to_sync:
            self.manager.set_resource_sync_synced(self.context, obj)

    def update_status_objects(self, my_state, other_universe, other_state,
                              raw_diff, transformed_diff, skip_roots=None):
        # AIM Config Universe is the desired state
        self._set_sync_pending_state(transformed_diff, raw_diff,
                                     other_universe, skip_roots=skip_roots)
        self._set_synced_state(my_state, raw_diff, skip_roots=skip_roots)

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
                res.values()[0]['attributes']['dn'])


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

    def vote_deletion_candidates(self, other_universe, delete_candidates,
                                 vetoes):
        pass

    def finalize_deletion_candidates(self, other_universe, delete_candidates):
        my_state = self.state
        for tenant in list(delete_candidates):
            # Remove tenants that have been emptied.
            if tenant not in my_state or not my_state[tenant].root:
                pass
            else:
                # AIM monitored DB still has stuff to delete
                delete_candidates.discard(tenant)

    def reconcile(self, other_universe, delete_candidates):
        self._mask_tenant_state(other_universe, delete_candidates)
        return self._reconcile(other_universe, delete_candidates)

    def update_status_objects(self, my_state, other_state, other_universe,
                              raw_diff, transformed_diff, skip_roots=None):
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

    def vote_deletion_candidates(self, other_universe, delete_candidates,
                                 vetoes):
        my_state = self.state
        # Veto tenants with non-dummy roots
        for tenant, tree in my_state.iteritems():
            if tree.root and not tree.root.dummy:
                delete_candidates.discard(tenant)
                vetoes.add(tenant)

    def finalize_deletion_candidates(self, other_universe, delete_candidates):
        my_state = self.state
        for tenant in list(delete_candidates):
            # Remove tenants that have been emptied.
            if tenant not in my_state or not my_state[tenant].root:
                pass
            else:
                # AIM monitored DB still has stuff to delete
                delete_candidates.discard(tenant)

    def reconcile(self, other_universe, delete_candidates):
        self._mask_tenant_state(other_universe, delete_candidates)
        return self._reconcile(other_universe, delete_candidates)

    def update_status_objects(self, my_state, other_universe, other_state,
                              raw_diff, transformed_diff, skip_roots=None):
        # AIM Monitored Universe is current state
        add_diff = {
            base.CREATE: self.get_resources(list(raw_diff[base.CREATE]))}
        self._set_sync_pending_state(add_diff, raw_diff, other_universe,
                                     skip_roots=skip_roots)
        self._set_synced_state(my_state, raw_diff, skip_roots=skip_roots)

    def get_resources_for_delete(self, resource_keys):
        des_mon = self.multiverse[base.MONITOR_UNIVERSE]['desired'].state

        def action(result, aci_object, node):
            key = tree_manager.AimHashTreeMaker._dn_to_key(
                aci_object.keys()[0],
                aci_object.values()[0]['attributes']['dn'])
            if len(key) == 1:
                LOG.debug('Skipping delete for monitored root object: %s '
                          % aci_object)
                return
            if not node or node.dummy:
                result.append(aci_object)
        return self._converter.convert(
            self._get_resources_for_delete(resource_keys, des_mon, action))
