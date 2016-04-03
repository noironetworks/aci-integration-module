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

from aim.api import resource as api_res
from aim.common.hashtree import exceptions as hexc
from aim.common.hashtree import structured_tree as htree
from aim.db import tree_model


LOG = logging.getLogger(__name__)


class HashTreeDbListener(object):
    """Updates persistent hash-tree in response to DB updates."""

    def __init__(self, aim_manager):
        aim_manager.register_update_listener(self.on_commit)
        self.tt_mgr = tree_model.TenantHashTreeManager()

    def on_commit(self, session, added, updated, deleted):
        # Segregate updates by tenant
        updates_by_tenant = {}
        all_updates = [added, updated, deleted]
        for idx in range(len(all_updates)):
            for res in all_updates[idx]:
                key = self._build_hash_tree_key(res)
                if not key:
                    continue
                updates_by_tenant.setdefault(key[0], ([], []))
                updates_by_tenant[key[0]][0 if idx < 2 else 1].append(
                    (key, res))

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
            for key_res in upd[0]:
                ttree.add(key_res[0],
                          **{x: getattr(key_res[1], x, None)
                             for x in key_res[1].other_attributes})
            for key_res in upd[1]:
                ttree.pop(key_res[0])

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

    def _build_hash_tree_key(self, resource):
        if not isinstance(resource, api_res.AciResourceBase):
            return None

        cls_list = []
        klass = type(resource)
        while klass and hasattr(klass, '_tree_parent'):
            cls_list.append(klass)
            klass = klass._tree_parent
        cls_list.reverse()

        if cls_list[0] != api_res.Tenant:
            return None

        id_values = resource.identity
        if len(id_values) != len(cls_list):
            LOG.warning("Mismatch between number of identity values (%d) and "
                        "parent classes (%d) for %s",
                        len(id_values), len(cls_list), resource)
            return None

        cls_list = ['%s.%s' % (c.__module__, c.__name__) for c in cls_list]
        key = tuple(['|'.join(x) for x in zip(cls_list, id_values)])
        return key
