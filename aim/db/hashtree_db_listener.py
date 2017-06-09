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

from aim.api import resource
from aim.common.hashtree import exceptions as hexc
from aim.common.hashtree import structured_tree as htree
from aim.common import utils
from aim import tree_manager


LOG = logging.getLogger(__name__)


class HashTreeDbListener(object):
    """Updates persistent hash-tree in response to DB updates."""

    def __init__(self, aim_manager):
        self.aim_manager = aim_manager
        self.tt_mgr = tree_manager.HashTreeManager()
        self.tt_maker = tree_manager.AimHashTreeMaker()
        self.tt_builder = tree_manager.HashTreeBuilder(self.aim_manager)

    def on_commit(self, store, added, updated, deleted, curr_cfg=None,
                  curr_oper=None, curr_monitor=None):
        # Query hash-tree for each tenant and modify the tree based on DB
        # updates
        # TODO(ivar): Use proper store context once dependency issue is fixed
        ctx = utils.FakeContext(store=store)
        # Build tree map

        conf = tree_manager.CONFIG_TREE
        monitor = tree_manager.MONITORED_TREE
        oper = tree_manager.OPERATIONAL_TREE
        tree_map = {}
        affected_tenants = set()
        with ctx.store.begin(subtransactions=True):
            for resources in added, updated, deleted:
                for res in resources:
                    key = self.tt_maker.get_root_key(res)
                    if key:
                        affected_tenants.add(key)

            for tenant in affected_tenants:
                try:
                    ttree = self.tt_mgr.get(ctx, tenant, lock_update=True,
                                            tree=conf)
                    ttree_operational = self.tt_mgr.get(ctx, tenant,
                                                        lock_update=True,
                                                        tree=oper)
                    ttree_monitor = self.tt_mgr.get(ctx, tenant,
                                                    lock_update=True,
                                                    tree=monitor)
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

    def _delete_trees(self, aim_ctx, root=None):
        with aim_ctx.store.begin(subtransactions=True):
            # Delete existing trees
            if root:
                self.tt_mgr.delete_by_root_rn(aim_ctx, root)
            else:
                self.tt_mgr.delete_all(aim_ctx)

    def _recreate_trees(self, aim_ctx, root=None):
        with aim_ctx.store.begin(subtransactions=True):
            created = []
            cache = {}
            # Delete existing trees
            if root:
                type, name = self.tt_mgr.root_key_funct(root)[0].split('|')
            # Retrieve objects
            for klass in self.aim_manager.aim_resources:
                if issubclass(klass, resource.AciResourceBase):
                    filters = {}
                    if root:
                        if self._retrieve_class_root_type(
                                klass, cache=cache) != type:
                            # Not the right subtree
                            continue
                        # TODO(ivar): this is not going to work for the
                        # topology objects. For now only full reset
                        # has effect on that subtree
                        filters[klass.root_ref_attribute()] = name
                    # Get all objects of that type
                    for obj in self.aim_manager.find(aim_ctx, klass,
                                                     **filters):
                        # Need all the faults and statuses as well
                        stat = self.aim_manager.get_status(aim_ctx, obj)
                        if stat:
                            created.append(stat)
                            created.extend(stat.faults)
                            del stat.faults
                        created.append(obj)
            # Reset the trees
            self.on_commit(aim_ctx.store, created, [], [])

    def reset(self, store, root=None):
        aim_ctx = utils.FakeContext(store=store)
        with aim_ctx.store.begin(subtransactions=True):
            self._delete_trees(aim_ctx, root=root)
            self._recreate_trees(aim_ctx, root=root)

    def _retrieve_class_root_type(self, klass, cache=None):
        cache = cache if cache is not None else {}
        if klass in cache:
            return cache[klass]
        stack = [klass]
        while klass._tree_parent:
            klass = klass._tree_parent
            stack.append(klass)
        for k in stack:
            cache[k] = klass._aci_mo_name
        return cache[klass]
