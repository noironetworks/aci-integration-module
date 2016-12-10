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

from aim import aim_manager
from aim.api import resource as aim_res
from aim.api import status as aim_status
from aim.common.hashtree import structured_tree as tree
from aim.db import agent_model      # noqa
from aim.db import tree_model
from aim.tests import base


class TestHashTreeDbListener(base.TestAimDBBase):

    def setUp(self):
        super(TestHashTreeDbListener, self).setUp()
        self.tt_mgr = tree_model.TenantHashTreeManager()
        self.mgr = aim_manager.AimManager()
        self.db_l = self.mgr._hashtree_db_listener

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

    def _test_sync_failed(self, monitored=False):
        tn_name = 'tn1'
        tn = aim_res.Tenant(name=tn_name)
        ap = aim_res.ApplicationProfile(tenant_name=tn_name, name='ap')
        epg = aim_res.EndpointGroup(
            tenant_name=tn_name, app_profile_name='ap', name='epg',
            monitored=monitored, bd_name='some')
        epg2 = aim_res.EndpointGroup(
            tenant_name=tn_name, app_profile_name='ap', name='epg2',
            monitored=monitored, bd_name='some')

        # Add Tenant and AP
        self.mgr.create(self.ctx, tn)
        no_ap_tree_cfg = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.CONFIG_TREE)
        no_ap_tree_mon = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.MONITORED_TREE)

        self.mgr.create(self.ctx, ap)
        self.mgr.create(self.ctx, epg2)
        # Get the tree
        no_epg_tree_cfg = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.CONFIG_TREE)
        no_epg_tree_mon = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.MONITORED_TREE)
        # Now add EPG
        self.mgr.create(self.ctx, epg)
        # Get the tree once again and verify it's different from the previous
        # one
        epg_tree_cfg = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.CONFIG_TREE)
        epg_tree_mon = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.MONITORED_TREE)

        self.assertNotEqual(epg_tree_cfg, no_epg_tree_cfg)
        self.assertNotEqual(epg_tree_mon, no_epg_tree_mon)
        # Set EPG status to delete error
        self.mgr.set_resource_sync_error(self.ctx, epg)
        # Get tree once again
        final_tree_cfg = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.CONFIG_TREE)
        final_tree_mon = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.MONITORED_TREE)
        # This tree is just like the one without EPG
        self.assertEqual(no_epg_tree_cfg, final_tree_cfg)
        self.assertEqual(no_epg_tree_mon, final_tree_mon)
        # Update epg, it will be re-created. Note that I'm not actually
        # changing attributed
        self.mgr.update(self.ctx, epg, bd_name='some')
        final_tree_cfg = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.CONFIG_TREE)
        final_tree_mon = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.MONITORED_TREE)
        self.assertEqual(epg_tree_cfg, final_tree_cfg)
        self.assertEqual(epg_tree_mon, final_tree_mon)

        # Set AP in error state, will effect all the children
        self.mgr.set_resource_sync_error(self.ctx, ap)
        tenant_only_cfg = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.CONFIG_TREE)
        tenant_only_mon = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.MONITORED_TREE)
        self.assertEqual(no_ap_tree_cfg, tenant_only_cfg)
        self.assertEqual(no_ap_tree_mon, tenant_only_mon)

        # All the objects are in failed state
        for obj in [ap, epg2, epg]:
            self.assertEqual(aim_status.AciStatus.SYNC_FAILED,
                             self.mgr.get_status(self.ctx, obj).sync_status)
        # Changing sync status of the EPG will bring everything back
        self.mgr.update(self.ctx, epg)
        full_cfg = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.CONFIG_TREE)
        full_mon = self.tt_mgr.get(
            self.ctx, tn_name, tree=tree_model.MONITORED_TREE)
        # All the objects are in synced state
        for obj in [ap, epg2, epg]:
            self.assertEqual(aim_status.AciStatus.SYNC_PENDING,
                             self.mgr.get_status(self.ctx, obj).sync_status)
        self.assertEqual(epg_tree_cfg, full_cfg)
        self.assertEqual(epg_tree_mon, full_mon)

    def test_sync_failed(self):
        self._test_sync_failed(monitored=False)

    def test_sync_failed_monitored(self):
        self._test_sync_failed(monitored=True)

    def test_tree_hooks(self):
        with mock.patch('aim.agent.aid.event_services.'
                        'rpc.AIDEventRpcApi._cast') as cast:
            tn_name = 'test_tree_hooks'
            tn = aim_res.Tenant(name='test_tree_hooks_2')
            ap = aim_res.ApplicationProfile(tenant_name=tn_name, name='ap')
            epg = aim_res.EndpointGroup(
                tenant_name=tn_name, app_profile_name='ap', name='epg',
                bd_name='some')
            # Add Tenant and AP
            self.mgr.create(self.ctx, tn)
            cast.assert_called_once_with(mock.ANY, 'serve', None)
            cast.reset_mock()
            self.mgr.create(self.ctx, ap)
            self.mgr.create(self.ctx, epg)
            # Create AP will create tenant, create EPG will modify it
            exp_calls = [
                mock.call(mock.ANY, 'serve', None),
                mock.call(mock.ANY, 'reconcile', None),
                mock.call(mock.ANY, 'reconcile', None)]
            self._check_call_list(exp_calls, cast)
            cast.reset_mock()
            self.mgr.update(self.ctx, epg, bd_name='bd2')
            cast.assert_called_once_with(mock.ANY, 'reconcile', None)
            cast.reset_mock()
            self.tt_mgr.delete_by_tenant_rn(self.ctx, 'test_tree_hooks_2')
            cast.assert_called_once_with(mock.ANY, 'serve', None)
