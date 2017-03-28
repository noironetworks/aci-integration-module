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
from aim.db import agent_model  # noqa
from aim.db import hashtree_db_listener as ht_db_l
from aim.tests import base
from aim import tree_manager


class TestHashTreeDbListener(base.TestAimDBBase):

    def setUp(self):
        super(TestHashTreeDbListener, self).setUp()
        self.tt_mgr = tree_manager.TenantHashTreeManager()
        self.mgr = aim_manager.AimManager()
        self.db_l = ht_db_l.HashTreeDbListener(aim_manager.AimManager())

    def _test_resource_ops(self, resource, tenant, tree_objects,
                           tree_objects_update,
                           tree_type=tree_manager.CONFIG_TREE, **updates):
        # add
        self.db_l.on_commit(self.ctx.store, [resource], [], [])

        db_tree = self.tt_mgr.get(self.ctx, tenant, tree=tree_type)
        exp_tree = tree.StructuredHashTree().include(tree_objects)
        self.assertEqual(exp_tree, db_tree)

        # update
        resource.__dict__.update(**updates)
        self.db_l.on_commit(self.ctx.store, [], [resource], [])

        db_tree = self.tt_mgr.get(self.ctx, tenant, tree=tree_type)
        exp_tree = tree.StructuredHashTree().include(tree_objects_update)
        self.assertEqual(exp_tree, db_tree)

        # delete
        self.db_l.on_commit(self.ctx.store, [], [], [resource])
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
             'nameAlias': '',
             'unkMacUcastAct': 'proxy'},
            {'key': ('fvTenant|t1', 'fvBD|bd1', 'fvRsCtx|rsctx'),
             'tnFvCtxName': 'default'}]
        tree_objects_update = copy.deepcopy(tree_objects)
        tree_objects_update[1]['tnFvCtxName'] = 'shared'
        self._test_resource_ops(
            bd, 't1', tree_objects, tree_objects_update,
            tree_type=tree_manager.CONFIG_TREE, vrf_name='shared')

    def test_monitored_bd_ops(self):
        bd = self._get_example_aim_bd(tenant_name='t1', name='bd1',
                                      monitored=True)
        tree_objects = [
            {'key': ('fvTenant|t1', 'fvBD|bd1'),
             'arpFlood': 'no',
             'epMoveDetectMode': '',
             'limitIpLearnToSubnets': 'no',
             'unicastRoute': 'yes',
             'nameAlias': '',
             'unkMacUcastAct': 'proxy'},
            {'key': ('fvTenant|t1', 'fvBD|bd1', 'fvRsCtx|rsctx'),
             'tnFvCtxName': 'default'}]
        tree_objects_update = copy.deepcopy(tree_objects)
        tree_objects_update[1]['tnFvCtxName'] = 'shared'
        self._test_resource_ops(
            bd, 't1', tree_objects, tree_objects_update,
            tree_type=tree_manager.MONITORED_TREE, vrf_name='shared')

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
            tree_type=tree_manager.OPERATIONAL_TREE, severity='critical')

    def _test_sync_failed(self, monitored=False):
        tn_name = 'tn1'
        tn = aim_res.Tenant(name=tn_name, monitored=monitored)
        ap = aim_res.ApplicationProfile(tenant_name=tn_name, name='ap',
                                        monitored=monitored)
        epg = aim_res.EndpointGroup(
            tenant_name=tn_name, app_profile_name='ap', name='epg',
            monitored=monitored, bd_name='some')
        epg2 = aim_res.EndpointGroup(
            tenant_name=tn_name, app_profile_name='ap', name='epg2',
            monitored=monitored, bd_name='some')
        empty_map = {True: tree_manager.CONFIG_TREE,
                     False: tree_manager.MONITORED_TREE}

        exp_tree = tree.StructuredHashTree()
        exp_empty_tree = tree.StructuredHashTree()
        # Add Tenant and AP
        tn = self.mgr.create(self.ctx, tn)
        self.mgr.set_resource_sync_synced(self.ctx, tn)
        ap = self.mgr.create(self.ctx, ap)
        self.mgr.set_resource_sync_synced(self.ctx, ap)
        epg2 = self.mgr.create(self.ctx, epg2)
        self.mgr.set_resource_sync_synced(self.ctx, epg2)
        epg = self.mgr.create(self.ctx, epg)
        self.mgr.set_resource_sync_synced(self.ctx, epg)
        # Set EPG status to delete error
        self.mgr.set_resource_sync_error(self.ctx, epg)
        # Get the trees
        empty_tree = self.tt_mgr.get(
            self.ctx, tn_name, tree=empty_map[monitored])
        configured_tree = self.tt_mgr.get(
            self.ctx, tn_name, tree=empty_map[not monitored])

        epg._error = True
        self.db_l.tt_maker.update(exp_tree, [tn, ap, epg2, epg])
        self.assertEqual({'add': [], 'remove': []},
                         exp_tree.diff(configured_tree))
        self.assertEqual({'add': [], 'remove': []},
                         exp_empty_tree.diff(empty_tree))
        # Even if something changes in the EPG the difference will still be
        # empty
        epg.display_name = 'somethingelse'
        self.db_l.tt_maker.update(exp_tree, [epg])
        self.assertEqual({'add': [], 'remove': []},
                         exp_tree.diff(configured_tree))
        self.assertEqual({'add': [], 'remove': []},
                         exp_empty_tree.diff(empty_tree))

        # Update epg, it will be re-created. Note that I'm not actually
        # changing attributes
        epg = self.mgr.update(self.ctx, epg, bd_name='some')
        self.mgr.set_resource_sync_synced(self.ctx, epg)
        # Fix the expected tree as well
        self.db_l.tt_maker.update(exp_tree, [epg])
        # Get the trees
        empty_tree = self.tt_mgr.get(
            self.ctx, tn_name, tree=empty_map[monitored])
        configured_tree = self.tt_mgr.get(
            self.ctx, tn_name, tree=empty_map[not monitored])
        self.assertEqual(exp_tree, configured_tree)
        self.assertEqual(exp_empty_tree, empty_tree)

        # Modifying the EPG will make the difference visible
        epg.display_name = 'somethingelse'
        self.db_l.tt_maker.update(exp_tree, [epg])
        self.assertEqual({'add': [('fvTenant|tn1', 'fvAp|ap', 'fvAEPg|epg')],
                          'remove': []},
                         exp_tree.diff(configured_tree))
        self.assertEqual({'add': [], 'remove': []},
                         exp_empty_tree.diff(empty_tree))

        # Set AP in error state, will effect all the children
        self.mgr.set_resource_sync_error(self.ctx, ap)
        empty_tree = self.tt_mgr.get(
            self.ctx, tn_name, tree=empty_map[monitored])
        configured_tree = self.tt_mgr.get(
            self.ctx, tn_name, tree=empty_map[not monitored])
        # This time around, the AP and both its EPGs are in error state
        ap._error = True
        epg._error = True
        epg2._error = True
        self.db_l.tt_maker.update(exp_tree, [ap, epg, epg2])
        self.assertEqual({'add': [], 'remove': []},
                         exp_tree.diff(configured_tree))
        self.assertEqual({'add': [], 'remove': []},
                         exp_empty_tree.diff(empty_tree))

        # All the objects are in failed state
        for obj in [ap, epg2, epg]:
            self.assertEqual(aim_status.AciStatus.SYNC_FAILED,
                             self.mgr.get_status(self.ctx, obj).sync_status)

        if not monitored:
            # Changing sync status of the EPG will bring everything back
            epg = self.mgr.update(self.ctx, epg)
            # All the objects are in synced state
            for obj in [ap, epg2, epg]:
                self.assertEqual(
                    aim_status.AciStatus.SYNC_PENDING,
                    self.mgr.get_status(self.ctx, obj).sync_status)
            empty_tree = self.tt_mgr.get(
                self.ctx, tn_name, tree=empty_map[monitored])
            configured_tree = self.tt_mgr.get(
                self.ctx, tn_name, tree=empty_map[not monitored])
            del ap._error
            del epg2._error
            self.db_l.tt_maker.update(exp_tree, [ap, epg, epg2])

            self.assertEqual(exp_tree, configured_tree)
            self.assertEqual(exp_empty_tree, empty_tree)

    def test_sync_failed(self):
        self._test_sync_failed(monitored=False)

    def test_sync_failed_monitored(self):
        self._test_sync_failed(monitored=True)

    @base.requires(['hooks'])
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
            self.mgr.create(self.ctx, aim_res.Tenant(name=tn_name))
            exp_calls = [
                mock.call(mock.ANY, 'serve', None)]
            self._check_call_list(exp_calls, cast)
            self.mgr.create(self.ctx, tn)
            cast.reset_mock()
            self.mgr.create(self.ctx, ap)
            self.mgr.create(self.ctx, epg)
            # Create AP will create tenant, create EPG will modify it
            exp_calls = [
                mock.call(mock.ANY, 'reconcile', None),
                mock.call(mock.ANY, 'reconcile', None)]
            self._check_call_list(exp_calls, cast)
            cast.reset_mock()
            self.mgr.update(self.ctx, epg, bd_name='bd2')
            cast.assert_called_once_with(mock.ANY, 'reconcile', None)
            cast.reset_mock()
            self.tt_mgr.delete_by_tenant_rn(self.ctx, 'test_tree_hooks_2')
            cast.assert_called_once_with(mock.ANY, 'serve', None)

    @base.requires(['hooks'])
    def test_tree_hooks_transactions(self):
        with mock.patch('aim.agent.aid.event_services.'
                        'rpc.AIDEventRpcApi._cast') as cast:
            tn = aim_res.Tenant(name='test_tree_hooks')
            ap = aim_res.ApplicationProfile(tenant_name='test_tree_hooks',
                                            name='ap')
            epg = aim_res.EndpointGroup(
                tenant_name='test_tree_hooks', app_profile_name='ap',
                name='epg', bd_name='some')

            tn1 = aim_res.Tenant(name='test_tree_hooks1')
            ap1 = aim_res.ApplicationProfile(
                tenant_name='test_tree_hooks1', name='ap')
            epg1 = aim_res.EndpointGroup(
                tenant_name='test_tree_hooks1', app_profile_name='ap',
                name='epg', bd_name='some')
            # Try a transaction
            with self.ctx.store.begin(subtransactions=True):
                with self.ctx.store.begin(subtransactions=True):
                    self.mgr.create(self.ctx, tn)
                    self.mgr.create(self.ctx, ap)
                    self.mgr.create(self.ctx, epg)
                self.assertEqual(0, cast.call_count)
                with self.ctx.store.begin(subtransactions=True):
                    self.mgr.create(self.ctx, tn1)
                    self.mgr.create(self.ctx, ap1)
                    self.mgr.create(self.ctx, epg1)
                self.assertEqual(0, cast.call_count)
            # Only a single "serve" call is issued
            cast.assert_called_once_with(mock.ANY, 'serve', None)

    def test_monitored_state_change(self):
        tn_name = 'test_monitored_state_change'
        tn = aim_res.Tenant(name=tn_name, monitored=True)
        ap = aim_res.ApplicationProfile(tenant_name=tn_name, name='ap',
                                        monitored=True)
        epg = aim_res.EndpointGroup(
            tenant_name=tn_name, app_profile_name='ap', name='epg',
            bd_name='some', monitored=True)
        self.mgr.create(self.ctx, tn)
        self.mgr.create(self.ctx, ap)
        self.mgr.create(self.ctx, epg)
        cfg_tree = self.tt_mgr.get(self.ctx, tn_name,
                                   tree=tree_manager.CONFIG_TREE)
        mon_tree = self.tt_mgr.get(self.ctx, tn_name,
                                   tree=tree_manager.MONITORED_TREE)
        # Create my own tree representation
        my_cfg_tree = tree.StructuredHashTree()
        my_mon_tree = tree.StructuredHashTree()
        self.db_l.tt_maker.update(my_mon_tree, [tn])
        # Since the objects except the tenant created are in sync pending,
        # they will be out of all trees
        self.assertEqual(my_mon_tree, mon_tree)
        self.assertEqual(my_cfg_tree, cfg_tree)
        # Succeed their creation
        self.mgr.set_resource_sync_synced(self.ctx, ap)
        self.mgr.set_resource_sync_synced(self.ctx, epg)
        self.db_l.tt_maker.update(my_mon_tree, [ap, epg])
        cfg_tree = self.tt_mgr.get(self.ctx, tn_name,
                                   tree=tree_manager.CONFIG_TREE)
        mon_tree = self.tt_mgr.get(self.ctx, tn_name,
                                   tree=tree_manager.MONITORED_TREE)
        self.assertEqual(my_mon_tree, mon_tree)
        self.assertEqual(my_cfg_tree, cfg_tree)

        # Change ownership of the AP
        self.mgr.update(self.ctx, ap, monitored=False)
        my_mon_tree = tree.StructuredHashTree()
        # This is equivalent of adding only tenant and epg to the conf tree
        self.db_l.tt_maker.update(my_mon_tree, [tn, epg])
        self.db_l.tt_maker.update(my_cfg_tree, [ap])
        # Refresh trees
        cfg_tree = self.tt_mgr.get(self.ctx, tn_name,
                                   tree=tree_manager.CONFIG_TREE)
        mon_tree = self.tt_mgr.get(self.ctx, tn_name,
                                   tree=tree_manager.MONITORED_TREE)
        self.assertEqual(my_mon_tree, mon_tree)
        self.assertEqual(my_cfg_tree, cfg_tree)
        # Unset monitored to EPG as well
        self.mgr.update(self.ctx, epg, monitored=False)
        my_mon_tree = tree.StructuredHashTree()
        self.db_l.tt_maker.update(my_mon_tree, [tn])
        self.db_l.tt_maker.update(my_cfg_tree, [epg])
        # Refresh trees
        cfg_tree = self.tt_mgr.get(self.ctx, tn_name,
                                   tree=tree_manager.CONFIG_TREE)
        mon_tree = self.tt_mgr.get(self.ctx, tn_name,
                                   tree=tree_manager.MONITORED_TREE)
        self.assertEqual(my_mon_tree, mon_tree)
        self.assertEqual(my_cfg_tree, cfg_tree)

    def test_subject_related_objects(self):
        self.mgr.create(self.ctx, aim_res.Tenant(name='common'))
        self.mgr.create(
            self.ctx, aim_res.Contract(tenant_name='common', name='c-name'))
        subj = aim_res.ContractSubject(
            **{'contract_name': 'c-name',
               'out_filters': ['pr_1', 'reverse-pr_1', 'pr_2', 'reverse-pr_2'],
               'name': 's-name',
               'tenant_name': 'common', 'monitored': False, 'bi_filters': [],
               'in_filters': ['pr_1', 'reverse-pr_1', 'pr_2', 'reverse-pr_2']})
        subj = self.mgr.create(self.ctx, subj)
        cfg_tree = self.tt_mgr.get(self.ctx, 'common',
                                   tree=tree_manager.CONFIG_TREE)
        # verify pr_1 and its reverse are in the tree
        pr_1 = cfg_tree.find(
            ("fvTenant|common", "vzBrCP|c-name", "vzSubj|s-name",
             "vzOutTerm|outtmnl", "vzRsFiltAtt|pr_1"))
        rev_pr_1 = cfg_tree.find(
            ("fvTenant|common", "vzBrCP|c-name", "vzSubj|s-name",
             "vzOutTerm|outtmnl", "vzRsFiltAtt|reverse-pr_1"))
        self.assertIsNotNone(pr_1)
        self.assertIsNotNone(rev_pr_1)

        self.mgr.update(self.ctx, subj, out_filters=['pr_2', 'reverse-pr_2'],
                        in_filters=['pr_2', 'reverse-pr_2'])
        cfg_tree = self.tt_mgr.get(self.ctx, 'common',
                                   tree=tree_manager.CONFIG_TREE)
        pr_1 = cfg_tree.find(
            ("fvTenant|common", "vzBrCP|c-name", "vzSubj|s-name",
             "vzOutTerm|outtmnl", "vzRsFiltAtt|pr_1"))
        rev_pr_1 = cfg_tree.find(
            ("fvTenant|common", "vzBrCP|c-name", "vzSubj|s-name",
             "vzOutTerm|outtmnl", "vzRsFiltAtt|reverse-pr_1"))
        self.assertIsNone(pr_1)
        self.assertIsNone(rev_pr_1)

    def test_delete_all_trees(self):
        self.mgr.create(self.ctx, aim_res.Tenant(name='common'))
        self.mgr.create(self.ctx, aim_res.Tenant(name='tn1'))
        self.mgr.create(self.ctx, aim_res.Tenant(name='tn2'))
        self.assertTrue(len(self.tt_mgr.find(self.ctx)) > 0)
        self.tt_mgr.delete_all(self.ctx)
        self.assertEqual(0, len(self.tt_mgr.find(self.ctx)))

    # REVISIT(ivar): for some reason, FK cascade is not honored by our UTs
    # therefore the following test doesn't pass. Need to find the root cause.
    # def test_aim_status_deleted(self):
    #    tn_name = 'test_aim_status_deleted'
    #    tn = aim_res.Tenant(name=tn_name, monitored=True)
    #    ap = aim_res.ApplicationProfile(tenant_name=tn_name, name='ap',
    #                                    monitored=True)
    #    epg = aim_res.EndpointGroup(
    #        tenant_name=tn_name, app_profile_name='ap', name='epg',
    #        bd_name='some', monitored=True)
    #    self.mgr.create(self.ctx, tn)
    #    self.mgr.create(self.ctx, ap)
    #    self.mgr.create(self.ctx, epg)

    #    op_tree = self.tt_mgr.get(self.ctx, tn_name,
    #                              tree=tree_manager.OPERATIONAL_TREE)
    #    # Operational tree is currently empty
    #    empty_tree = tree.StructuredHashTree()
    #    self.assertEqual(empty_tree, op_tree)
    #    # Create a fault
    #    self.mgr.set_fault(
    #        self.ctx, epg, aim_status.AciFault(
    #            fault_code='152', external_identifier=epg.dn + '/fault-152'))
    #    # Operational tree is not empty anymore
    #    op_tree = self.tt_mgr.get(self.ctx, tn_name,
    #                              tree=tree_manager.OPERATIONAL_TREE)
    #    self.assertFalse(empty_tree == op_tree)

    #    # Delete AIM status directly, should clear the tree
    #    epg_status = self.mgr.get_status(self.ctx, epg)
    #    self.mgr.delete(self.ctx, epg_status)
    #    op_tree = self.tt_mgr.get(self.ctx, tn_name,
    #                              tree=tree_manager.OPERATIONAL_TREE)
    #    self.assertEqual(empty_tree, op_tree)
