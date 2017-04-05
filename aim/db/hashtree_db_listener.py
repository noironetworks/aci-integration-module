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
from aim.api import status as aim_status
from aim.api import tree as aim_tree
from aim.common.hashtree import exceptions as hexc
from aim.common.hashtree import structured_tree as htree
from aim.common import utils
from aim import tree_manager


LOG = logging.getLogger(__name__)


class HashTreeDbListener(object):
    """Updates persistent hash-tree in response to DB updates."""

    def __init__(self, aim_manager):
        self.aim_manager = aim_manager
        self.tt_mgr = tree_manager.TenantHashTreeManager()
        self.tt_maker = tree_manager.AimHashTreeMaker()
        self.tt_builder = tree_manager.HashTreeBuilder(self.aim_manager)

    def on_commit(self, store, added, updated, deleted, curr_cfg=None,
                  curr_oper=None, curr_monitor=None):
        # Query hash-tree for each tenant and modify the tree based on DB
        # updates
        # TODO(ivar): Use proper store context once dependency issue is fixed
        ctx = utils.FakeContext(store=store)
        # Build tree map

        conf = aim_tree.ConfigTenantTree
        monitor = aim_tree.MonitoredTenantTree
        oper = aim_tree.OperationalTenantTree
        tree_map = {}
        affected_tenants = set()
        with ctx.store.begin(subtransactions=True):
            for resources in added, updated, deleted:
                for res in resources:
                    if isinstance(res, aim_status.AciStatus):
                        # TODO(ivar): this is a DB query not worth doing. Find
                        # a better way to retrieve tenant from a Status object
                        res = self.aim_manager.get_by_id(ctx, res.parent_class,
                                                         res.resource_id)
                    key = self.tt_maker.get_tenant_key(res)
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

    def reset(self, store, tenant=None):
        aim_ctx = utils.FakeContext(store=store)
        with aim_ctx.store.begin(subtransactions=True):
            created = []
            # Delete existing trees
            filters = {}
            if tenant:
                filters['name'] = tenant
            tenants = self.aim_manager.find(aim_ctx, resource.Tenant,
                                            **filters)
            for t in tenants:
                self.tt_mgr.delete_by_tenant_rn(aim_ctx, t.name)
            # Retrieve objects
            for klass in self.aim_manager.aim_resources:
                if issubclass(klass, resource.AciResourceBase):
                    filters = {}
                    if tenant:
                        filters[klass.tenant_ref_attribute] = tenant
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
            self.on_commit(store, created, [], [])
