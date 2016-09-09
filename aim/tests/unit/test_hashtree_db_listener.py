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

    def _test_resource_ops(self, resource, tenant, tree_objects,
                           tree_objects_update,
                           tree_type=tree_model.CONFIG_TREE, **updates):
        # add
        self.db_l.on_commit(self.ctx.db_session, [resource], [], [])

        db_tree = self.tt_mgr.get(self.ctx, tenant, tree=tree_type)
        exp_tree = tree.StructuredHashTree().include(tree_objects)
        self.assertEqual(exp_tree, db_tree)

        # update
        resource.__dict__.update(**updates)
        self.db_l.on_commit(self.ctx.db_session, [], [resource], [])

        db_tree = self.tt_mgr.get(self.ctx, tenant, tree=tree_type)
        exp_tree = tree.StructuredHashTree().include(tree_objects_update)
        self.assertEqual(exp_tree, db_tree)

        # delete
        self.db_l.on_commit(self.ctx.db_session, [], [], [resource])
        db_tree = self.tt_mgr.get(self.ctx, tenant, tree=tree_type)
        exp_tree = tree.StructuredHashTree()
        self.assertEqual(exp_tree, db_tree)

    def test_bd_ops(self):
        bd = self._get_example_aim_bd(tenant_name='t1', name='bd1')
        tree_objects = [
            {'key': ('fvTenant|t1', 'fvBD|bd1'),
             'arpFlood': 'no',
             'epMoveDetectMode': '',
             'limitIpLearnToSubnets': 'no',
             'unicastRoute': 'yes',
             'unkMacUcastAct': 'proxy'},
            {'key': ('fvTenant|t1', 'fvBD|bd1', 'fvRsCtx|rsctx'),
             'tnFvCtxName': 'default'}]
        tree_objects_update = copy.deepcopy(tree_objects)
        tree_objects_update[1]['tnFvCtxName'] = 'shared'
        self._test_resource_ops(
            bd, 't1', tree_objects, tree_objects_update,
            tree_type=tree_model.CONFIG_TREE, vrf_name='shared')

    def test_monitored_bd_ops(self):
        bd = self._get_example_aim_bd(tenant_name='t1', name='bd1',
                                      monitored=True)
        tree_objects = [
            {'key': ('fvTenant|t1', 'fvBD|bd1'),
             'arpFlood': 'no',
             'epMoveDetectMode': '',
             'limitIpLearnToSubnets': 'no',
             'unicastRoute': 'yes',
             'unkMacUcastAct': 'proxy'},
            {'key': ('fvTenant|t1', 'fvBD|bd1', 'fvRsCtx|rsctx'),
             'tnFvCtxName': 'default'}]
        tree_objects_update = copy.deepcopy(tree_objects)
        tree_objects_update[1]['tnFvCtxName'] = 'shared'
        self._test_resource_ops(
            bd, 't1', tree_objects, tree_objects_update,
            tree_type=tree_model.MONITORED_TREE, vrf_name='shared')

    def test_operational_fault_ops(self):
        fault = self._get_example_aim_fault(
            fault_code='101',
            external_identifier='uni/tn-t1/BD-bd1/fault-101',
            description='cannot resolve',
            cause='resolution-failed',
            severity='warning')
        tree_objects = [
            {'key': ('fvTenant|t1', 'fvBD|bd1', 'faultInst|101'),
             'descr': 'cannot resolve',
             'code': '101',
             'severity': 'warning',
             'cause': 'resolution-failed'}]
        tree_objects_update = copy.deepcopy(tree_objects)
        tree_objects_update[0]['severity'] = 'critical'
        self._test_resource_ops(
            fault, 't1', tree_objects, tree_objects_update,
            tree_type=tree_model.OPERATIONAL_TREE, severity='critical')
