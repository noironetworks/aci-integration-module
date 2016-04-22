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


import mock

from aim.common.hashtree import structured_tree as tree
from aim.db import agent_model      # noqa
from aim.db import hashtree_db_listener as ht_db_l
from aim.db import tree_model
from aim.tests import base


class TestHashTreeDbListener(base.TestAimDBBase):

    def setUp(self):
        super(TestHashTreeDbListener, self).setUp()
        self.tt_mgr = tree_model.TenantHashTreeManager()
        self.db_l = ht_db_l.HashTreeDbListener(mock.Mock())

    def _test_resource_ops(self, tenant, key, resource):
        attr = {x: getattr(resource, x, None)
                for x in resource.other_attributes if
                x not in tree_model.AimHashTreeMaker._exclude}

        # add
        self.db_l.on_commit(self.ctx.db_session, [resource], [], [])

        db_tree = self.tt_mgr.get(self.ctx, tenant)
        exp_tree = tree.StructuredHashTree().add(key, **attr)
        self.assertEqual(exp_tree, db_tree)

        # update
        attr['vrf_name'] = 'shared'
        resource.vrf_name = attr['vrf_name']
        self.db_l.on_commit(self.ctx.db_session, [], [resource], [])

        db_tree = self.tt_mgr.get(self.ctx, tenant)
        exp_tree = tree.StructuredHashTree().add(key, **attr)
        self.assertEqual(exp_tree, db_tree)

        # delete
        self.db_l.on_commit(self.ctx.db_session, [], [], [resource])
        db_tree = self.tt_mgr.get(self.ctx, tenant)
        exp_tree = tree.StructuredHashTree().add(key[:-1])
        self.assertEqual(exp_tree, db_tree)

    def test_bd_ops(self):
        bd = self._get_example_aim_bd(tenant_name='t1', name='bd1')
        self._test_resource_ops(
            't1',
            ('aim.api.resource.Tenant|t1',
             'aim.api.resource.BridgeDomain|bd1'), bd)
