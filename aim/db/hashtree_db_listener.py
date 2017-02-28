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

from oslo_log import log as logging

from aim.api import status as aim_status
from aim.api import tree as aim_tree
from aim.common.hashtree import exceptions as hexc
from aim.common.hashtree import structured_tree as htree
from aim.common import utils
from aim import tree_manager


LOG = logging.getLogger(__name__)


class HashTreeBuilder(object):
    CONFIG = 'config'
    OPER = 'oper'
    MONITOR = 'monitor'

    def __init__(self, aim_manager):
        self.aim_manager = aim_manager
        self.tt_maker = tree_manager.AimHashTreeMaker()

    def build(self, added, updated, deleted, tree_map, aim_ctx=None):
        """Build hash tree

        :param updated: list of AIM objects
        :param deleted: list of AIM objects
        :param tree_map: map of trees by type and tenant
        eg: {'config': {'tn1': <tenant hashtree>}}
        :return: tree updates
        """

        # Segregate updates by tenant
        updates_by_tenant = {}
        all_updates = [added, updated, deleted]
        conf = aim_tree.ConfigTenantTree
        monitor = aim_tree.MonitoredTenantTree
        oper = aim_tree.OperationalTenantTree
        for idx in range(len(all_updates)):
            tree_index = 0 if idx < 2 else 1
            for res in all_updates[idx]:
                if isinstance(res, aim_status.AciStatus) and aim_ctx:
                    parent = self.aim_manager.get_by_id(
                        aim_ctx, res.parent_class, res.resource_id)
                    # Remove main object from config tree if in sync error
                    # during an update
                    if tree_index == 0:
                        if res.sync_status == res.SYNC_FAILED:
                            parent = self.aim_manager.get_by_id(
                                aim_ctx, res.parent_class, res.resource_id)
                            # Put the object in error state
                            parent._error = True
                            all_updates[1].append(parent)
                        elif res.sync_status == res.SYNC_PENDING:
                            # A sync pending monitored object is in a limbo
                            # state, potentially switching from Owned to
                            # Monitored, and therefore should be removed from
                            # all the trees
                            if parent.monitored:
                                all_updates[-1].append(parent)
                            else:
                                all_updates[1].append(parent)
                        elif res.sync_status == res.SYNCED:
                            all_updates[1].append(parent)
                    else:
                        if parent:
                            # Delete parent on operational tree
                            parent_key = self.tt_maker.get_tenant_key(parent)
                            updates_by_tenant.setdefault(
                                parent_key, {conf: ([], []), monitor: ([], []),
                                             oper: ([], [])})
                            updates_by_tenant[
                                parent_key][oper][tree_index].append(parent)
                key = self.tt_maker.get_tenant_key(res)
                if not key:
                    continue
                updates_by_tenant.setdefault(
                    key, {conf: ([], []), monitor: ([], []), oper: ([], [])})
                if isinstance(res, aim_status.AciFault):
                    # Operational Tree
                    updates_by_tenant[key][oper][tree_index].append(res)
                else:
                    if getattr(res, 'monitored', None):
                        # Monitored Tree
                        res_copy = copy.deepcopy(res)
                        updates_by_tenant[key][monitor][tree_index].append(
                            res_copy)
                        # Don't modify the original resource in a visible
                        # way
                        res = copy.deepcopy(res)
                        # Fake this as pre-existing
                        res.pre_existing = True
                        res.monitored = False
                    # Configuration Tree
                    updates_by_tenant[key][conf][tree_index].append(res)

        upd_trees, udp_op_trees, udp_mon_trees = [], [], []
        for tenant, upd in updates_by_tenant.iteritems():
            ttree = tree_map[self.CONFIG][tenant]
            ttree_operational = tree_map[self.OPER][tenant]
            ttree_monitor = tree_map[self.MONITOR][tenant]
            # Update Configuration Tree
            self.tt_maker.update(ttree, upd[conf][0])
            self.tt_maker.delete(ttree, upd[conf][1])
            # Clear new monitored objects
            self.tt_maker.clear(ttree, upd[monitor][0])

            # Update Operational Tree
            self.tt_maker.update(ttree_operational, upd[oper][0])
            self.tt_maker.delete(ttree_operational, upd[oper][1])
            # Delete operational resources as well
            self.tt_maker.delete(ttree_operational, upd[conf][1])
            self.tt_maker.delete(ttree_operational, upd[monitor][1])

            # Update Monitored Tree
            self.tt_maker.update(ttree_monitor, upd[monitor][0])
            self.tt_maker.delete(ttree_monitor, upd[monitor][1])
            # Clear new owned objects
            self.tt_maker.clear(ttree_monitor, upd[conf][0])

            if ttree.root_key:
                upd_trees.append(ttree)
            if ttree_operational.root_key:
                udp_op_trees.append(ttree_operational)
            if ttree_monitor.root_key:
                udp_mon_trees.append(ttree_monitor)
        return upd_trees, udp_op_trees, udp_mon_trees


class HashTreeDbListener(object):
    """Updates persistent hash-tree in response to DB updates."""

    def __init__(self, aim_manager, store):
        self.aim_manager = aim_manager
        self.tt_mgr = tree_manager.TenantHashTreeManager()
        self.tt_maker = tree_manager.AimHashTreeMaker()
        self.tt_builder = HashTreeBuilder(self.aim_manager)
        self.store = store

    def on_commit(self, session, added, updated, deleted, curr_cfg=None,
                  curr_oper=None, curr_monitor=None):
        # Query hash-tree for each tenant and modify the tree based on DB
        # updates
        # TODO(ivar): Use proper store context once dependency issue is fixed
        ctx = utils.FakeContext(session, self.store)
        # Build tree map

        conf = aim_tree.ConfigTenantTree
        monitor = aim_tree.MonitoredTenantTree
        oper = aim_tree.OperationalTenantTree
        tree_map = {}
        affected_tenants = set()
        for resources in added, updated, deleted:
            for res in resources:
                if isinstance(res, aim_status.AciStatus):
                    # TODO(ivar): this is a DB query not worth doing. Fing
                    # a better way to retrieve tenant from a Status object
                    res = self.aim_manager.get_by_id(
                        ctx, res.parent_class, res.resource_id)
                key = self.tt_maker.get_tenant_key(res)
                if key:
                    affected_tenants.add(key)

        for tenant in affected_tenants:
            try:
                ttree = self.tt_mgr.get(ctx, tenant, tree=conf)
                ttree_operational = self.tt_mgr.get(ctx, tenant, tree=oper)
                ttree_monitor = self.tt_mgr.get(ctx, tenant, tree=monitor)
            except hexc.HashTreeNotFound:
                ttree = htree.StructuredHashTree()
                ttree_operational = htree.StructuredHashTree()
                ttree_monitor = htree.StructuredHashTree()
            tree_map.setdefault(
                self.tt_builder.CONFIG, {})[tenant] = ttree
            tree_map.setdefault(
                self.tt_builder.OPER, {})[tenant] = ttree_operational
            tree_map.setdefault(
                self.tt_builder.MONITOR, {})[tenant] = ttree_monitor

        upd_trees, udp_op_trees, udp_mon_trees = self.tt_builder.build(
            added, updated, deleted, tree_map, aim_ctx=ctx)

        # Finally save the modified trees
        if upd_trees:
            self.tt_mgr.update_bulk(ctx, upd_trees)
        if udp_op_trees:
            self.tt_mgr.update_bulk(ctx, udp_op_trees, tree=oper)
        if udp_mon_trees:
            self.tt_mgr.update_bulk(ctx, udp_mon_trees, tree=monitor)
