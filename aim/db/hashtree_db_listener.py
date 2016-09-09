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

from aim.api import status as aim_status
from aim.common.hashtree import exceptions as hexc
from aim.common.hashtree import structured_tree as htree
from aim.db import tree_model


LOG = logging.getLogger(__name__)


class HashTreeDbListener(object):
    """Updates persistent hash-tree in response to DB updates."""

    def __init__(self, aim_manager):
        aim_manager.register_update_listener(self.on_commit)
        self.tt_mgr = tree_model.TenantHashTreeManager()
        self.tt_maker = tree_model.AimHashTreeMaker()

    def on_commit(self, session, added, updated, deleted):
        # Segregate updates by tenant
        updates_by_tenant = {}
        all_updates = [added, updated, deleted]
        conf = tree_model.CONFIG_TREE
        monitor = tree_model.MONITORED_TREE
        oper = tree_model.OPERATIONAL_TREE
        for idx in range(len(all_updates)):
            tree_index = 0 if idx < 2 else 1
            for res in all_updates[idx]:
                key = self.tt_maker.get_tenant_key(res)
                if not key:
                    continue
                updates_by_tenant.setdefault(
                    key, {conf: ([], []), monitor: ([], []), oper: ([], [])})
                if isinstance(res, aim_status.OperationalResource):
                    # Operational Tree
                    updates_by_tenant[key][oper][tree_index].append(res)
                elif getattr(res, 'monitored', None):
                    # Monitored Tree
                    updates_by_tenant[key][monitor][tree_index].append(res)
                else:
                    # Configuration Tree
                    updates_by_tenant[key][conf][tree_index].append(res)

        # Query hash-tree for each tenant and modify the tree based on DB
        # updates
        class DummyContext(object):
            db_session = session
        ctx = DummyContext()

        upd_trees, udp_op_trees, udp_mon_trees = [], [], []
        for tenant, upd in updates_by_tenant.iteritems():
            try:
                ttree = self.tt_mgr.get(ctx, tenant, tree=conf)
                ttree_operational = self.tt_mgr.get(ctx, tenant, tree=oper)
                ttree_monitor = self.tt_mgr.get(ctx, tenant, tree=monitor)
            except hexc.HashTreeNotFound:
                ttree = htree.StructuredHashTree()
                ttree_operational = htree.StructuredHashTree()
                ttree_monitor = htree.StructuredHashTree()
            # Update Configuration Tree
            self.tt_maker.update(ttree, upd[conf][0])
            self.tt_maker.delete(ttree, upd[conf][1])
            # Update Operational Tree
            self.tt_maker.update(ttree_operational, upd[oper][0])
            self.tt_maker.delete(ttree_operational, upd[oper][1])
            # Update Monitored Tree
            self.tt_maker.update(ttree_monitor, upd[monitor][0])
            self.tt_maker.delete(ttree_monitor, upd[monitor][1])

            if ttree.root_key:
                upd_trees.append(ttree)
            if ttree_operational.root_key:
                udp_op_trees.append(ttree_operational)
            if ttree_monitor.root_key:
                udp_mon_trees.append(ttree_monitor)

        # Finally save the modified trees
        if upd_trees:
            self.tt_mgr.update_bulk(ctx, upd_trees)
        if udp_op_trees:
            self.tt_mgr.update_bulk(ctx, udp_op_trees, tree=oper)
        if udp_mon_trees:
            self.tt_mgr.update_bulk(ctx, udp_mon_trees, tree=monitor)
