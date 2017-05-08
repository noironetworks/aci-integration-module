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
from aim.common import utils
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

    def initialize(self, store, conf_mgr):
        super(AimDbUniverse, self).initialize(store, conf_mgr)
        self.tree_manager = tree_manager.HashTreeManager()
        self.context = context.AimContext(store=store)
        self._converter = converter.AciToAimModelConverter()
        self._converter_aim_to_aci = converter.AimToAciModelConverter()
        self._served_tenants = set()
        self._monitored_state_update_failures = 0
        self._max_monitored_state_update_failures = 5
        return self

    @property
    def name(self):
        return "AIM_Config_Universe"

    def serve(self, tenants):
        tenants = set(tenants)
        if self._served_tenants != tenants:
            LOG.debug('%s serving tenants: %s' % (self.name, tenants))
            self._served_tenants = set(tenants)

    def observe(self):
        pass

    def get_optimized_state(self, other_state, tree=tree_manager.CONFIG_TREE):
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
            dn_mgr = apic_client.DNManager()
            aci_klass, mos_rns = dn_mgr.aci_decompose_dn_guess(aci_dn,
                                                               dissected[0])
            rns = dn_mgr.filter_rns(mos_rns)
            # TODO(amitbose) We should be using 'alt_resource' only if we don't
            # find an AIM object by using 'resource'
            conv_info = converter.resource_map[aci_klass][0]
            klass = conv_info.get('alt_resource') or conv_info['resource']
            res = klass(
                **dict([(y, rns[x])
                        for x, y in enumerate(klass.identity_attributes)]))
            id_tuple = tuple([(x, getattr(res, x)) for x in
                              res.identity_attributes])
            if fault_code:
                id_tuple += ('fault', fault_code)
            id_tuple = (klass,) + id_tuple
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
                    else:
                        LOG.debug("Resource %s not found in AIM, here is a "
                                  "list of similar resources: %s" %
                                  (str(res),
                                   [str(x) for x in self.manager.find(
                                       self.context, type(res))]))
                except aim_exc.UnknownResourceType:
                    LOG.warn("Resource %s is not defined in AIM", dissected)
                    result.append(res)
                    id_set.add(id_tuple)
        if resource_keys:
            LOG.debug("Result for keys %s\n in AIM Universe:\n %s" %
                      (resource_keys, result))
        return list(result)

    def get_resources_for_delete(self, resource_keys):
        return self._converter.convert(
            self._keys_to_bare_aci_objects(resource_keys))

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
                    self._monitored_state_update_failures += 1
                    if (self._monitored_state_update_failures >
                            self._max_monitored_state_update_failures):
                        utils.perform_harakiri(LOG, msg)
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
        # Check if there are transitioning objects
        transitioning_keys = []
        if raw_diff[base.DELETE]:
            mon_state = self._get_state(tree=tree_manager.MONITORED_TREE)
            for key in raw_diff[base.DELETE]:
                root = tree_manager.AimHashTreeMaker._extract_root_rn(key)
                if root in mon_state and mon_state[root].find(key):
                    transitioning_keys.append(key)
        aim_transition = [x for x in self.get_resources(transitioning_keys)
                          if getattr(x, 'monitored', False)]
        # Set AIM differences to sync_pending
        for obj in aim_add + aim_transition:
            self.manager.set_resource_sync_pending(self.context, obj)
        # If any aim_del, recalculate deletion
        if aim_transition:
            transformed_diff[base.DELETE] = (
                other_universe.get_resources_for_delete(raw_diff[base.DELETE]))

    def _set_synced_state(self, my_state, raw_diff):
        all_modified_keys = set(raw_diff[base.CREATE] + raw_diff[base.DELETE])
        pending_nodes = []
        for root, tree in my_state.iteritems():
            pending_nodes.extend(tree.find_by_metadata('pending', True))
            pending_nodes.extend(tree.find_no_metadata('pending'))
        keys_to_sync = set(pending_nodes) - all_modified_keys
        # get_resources_for_delete is enough here, since we only need the AIM
        # object identity.
        aim_to_sync = self.get_resources_for_delete(keys_to_sync)
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
    def state(self):
        return self._get_state(tree=tree_manager.OPERATIONAL_TREE)

    @property
    def name(self):
        return "AIM_Operational_Universe"

    def get_optimized_state(self, other_state):
        return super(AimDbOperationalUniverse, self).get_optimized_state(
            other_state, tree=tree_manager.OPERATIONAL_TREE)

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
    def state(self):
        return self._get_state(tree=tree_manager.MONITORED_TREE)

    @property
    def name(self):
        return "AIM_Monitored_Universe"

    def get_optimized_state(self, other_state):
        return super(AimDbMonitoredUniverse, self).get_optimized_state(
            other_state, tree=tree_manager.MONITORED_TREE)

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
        self._set_synced_state(my_state, raw_diff)
