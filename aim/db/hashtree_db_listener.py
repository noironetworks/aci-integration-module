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
        for idx in range(len(all_updates)):
            for res in all_updates[idx]:
                key = self.tt_maker.get_tenant_key(res)
                if not key:
                    continue
                updates_by_tenant.setdefault(key, ([], []))
                updates_by_tenant[key][0 if idx < 2 else 1].append(res)

        # Query hash-tree for each tenant and modify the tree based on DB
        # updates
        class DummyContext(object):
            db_session = session
        ctx = DummyContext()

        upd_trees = []
        del_trees = []
        for tenant, upd in updates_by_tenant.iteritems():
            ttree_exists = True
            try:
                ttree = self.tt_mgr.get(ctx, tenant)
            except hexc.HashTreeNotFound:
                ttree = htree.StructuredHashTree()
                ttree_exists = False
            self.tt_maker.update(ttree, upd[0])
            self.tt_maker.delete(ttree, upd[1])

            if not ttree.has_subtree():
                if ttree_exists:
                    del_trees.append(ttree)
            else:
                upd_trees.append(ttree)

        # Finally save the modified trees
        if upd_trees:
            self.tt_mgr.update_bulk(ctx, upd_trees)
        if del_trees:
            self.tt_mgr.delete_bulk(ctx, del_trees)
