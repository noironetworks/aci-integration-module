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

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes import aim_universe
from aim import aim_manager
from aim.api import resource
from aim.api import service_graph as aim_service_graph
from aim.api import status as aim_status
from aim.common.hashtree import structured_tree as tree
from aim import config as aim_cfg
from aim.db import agent_model  # noqa
from aim.tests import base
from aim import tree_manager


class TestAimDbUniverseBase(object):

    def setUp(self, klass=aim_universe.AimDbUniverse):
        super(TestAimDbUniverseBase, self).setUp()
        self.klass = klass
        self.universe = self.klass().initialize(
            self.store, aim_cfg.ConfigManager(self.ctx, ''), [])
        self.tree_mgr = tree_manager.HashTreeManager()
        self.monitor_universe = False

    def test_serve(self):
        # Serve the first batch of tenants
        tenants = ['tn%s' % x for x in range(10)]
        self.universe.serve(tenants)
        self.assertEqual(set(tenants), set(self.universe._served_tenants))

    def test_state(self, tree_type=tree_manager.CONFIG_TREE):
        # Create some trees in the AIM DB
        data1 = tree.StructuredHashTree().include(
            [{'key': ('fvTenant|tnA', 'keyB')},
             {'key': ('fvTenant|tnA', 'keyC')},
             {'key': ('fvTenant|tnA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('fvTenant|tnA1', 'keyB')},
             {'key': ('fvTenant|tnA1', 'keyC')},
             {'key': ('fvTenant|tnA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('fvTenant|tnA2', 'keyB')},
             {'key': ('fvTenant|tnA2', 'keyC')},
             {'key': ('fvTenant|tnA2', 'keyC', 'keyD')}])
        self.tree_mgr.update_bulk(self.ctx, [data1, data2, data3],
                                  tree=tree_type)
        # Serve tnA, tnA2 and tnExtra
        self.universe.serve(['tn-tnA', 'tn-tnA2', 'tn-tnExtra'])
        # Now observe
        self.universe.observe()
        state = self.universe.state
        # tnA and tnA2 have updated values, tnExtra is still empty
        self.assertEqual(data1, state['tn-tnA'])
        self.assertEqual(data3, state['tn-tnA2'])
        self.assertIsNone(state.get('tn-tnExtra'))

        # Change tree in the DB
        data1.add(('fvTenant|tnA', 'keyB'), attribute='something')
        self.tree_mgr.update_bulk(self.ctx, [data1], tree=tree_type)
        # Observe and verify that trees are back in sync
        self.assertNotEqual(data1, state['tn-tnA'])
        self.universe.observe()
        state = self.universe.state
        self.assertEqual(data1, state['tn-tnA'])

    # TODO(ivar): unskip once the method has been fixed with the proper
    # semantics
    @base.requires(['skip'])
    def test_get_optimized_state(self, tree_type=tree_manager.CONFIG_TREE):
        data1 = tree.StructuredHashTree().include(
            [{'key': ('fvTenant|tnA', 'keyB')},
             {'key': ('fvTenant|tnA', 'keyC')},
             {'key': ('fvTenant|tnA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('fvTenant|tnA1', 'keyB')},
             {'key': ('fvTenant|tnA1', 'keyC')},
             {'key': ('fvTenant|tnA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('fvTenant|tnA2', 'keyB')},
             {'key': ('fvTenant|tnA2', 'keyC')},
             {'key': ('fvTenant|tnA2', 'keyC', 'keyD')}])
        self.tree_mgr.update_bulk(self.ctx, [data1, data2, data3],
                                  tree=tree_type)

        self.universe.serve(['tn-tnA', 'tn-tnA1', 'tn-tnA2', 'tn-tnA3'])
        # Other state is in sync
        other_state = {
            'tn-tnA': tree.StructuredHashTree().from_string(str(data1)),
            'tn-tnA1': tree.StructuredHashTree().from_string(str(data2)),
            'tn-tnA2': tree.StructuredHashTree().from_string(str(data3))}
        # Optimized state is empty
        self.assertEqual({}, self.universe.get_optimized_state(other_state))

        # Add a new tenant
        data4 = tree.StructuredHashTree().include(
            [{'key': ('fvTenant|tnA3', 'keyB')},
             {'key': ('fvTenant|tnA3', 'keyC')},
             {'key': ('fvTenant|tnA3', 'keyC', 'keyD')}])
        self.tree_mgr.update_bulk(self.ctx, [data4], tree=tree_type)
        self.assertEqual({'tn-tnA3': data4},
                         self.universe.get_optimized_state(other_state))
        # Modify data1
        data1.add(('fvTenant|tnA', 'keyZ'), attribute='something')
        self.tree_mgr.update_bulk(self.ctx, [data1], tree=tree_type)
        # Now Data1 is included too
        self.assertEqual({'tn-tnA3': data4, 'tn-tnA': data1},
                         self.universe.get_optimized_state(other_state))

    def test_get_aim_resources(self, tree_type=tree_manager.CONFIG_TREE):
        tree_mgr = tree_manager.HashTreeManager()
        aim_mgr = aim_manager.AimManager()
        t1 = resource.Tenant(name='t1')
        t2 = resource.Tenant(name='t2')
        t1_fault = aim_status.AciFault(
            fault_code='101', external_identifier='uni/tn-t1/fault-101',
            description='failure101')
        t2_fault = aim_status.AciFault(
            fault_code='102', external_identifier='uni/tn-t2/fault-102',
            description='failure102')
        # Create Resources on a couple of tenants
        bd1 = resource.BridgeDomain(
            tenant_name='t1', name='bd1', display_name='somestuff',
            vrf_name='vrf')
        bd1_fault = aim_status.AciFault(
            fault_code='901', external_identifier='uni/tn-t1/BD-bd1/fault-901',
            description='failure901')
        bd1_fault2 = aim_status.AciFault(
            fault_code='902', external_identifier='uni/tn-t1/BD-bd1/fault-902',
            description='failure902')
        bd2 = resource.BridgeDomain(
            tenant_name='t2', name='bd1', display_name='somestuff',
            vrf_name='vrf2')
        dc1 = aim_service_graph.DeviceCluster(
            tenant_name='t1', name='clus1', devices=[{'name': '1'}])
        dc1_fault = aim_status.AciFault(
            fault_code='901',
            external_identifier='uni/tn-t1/lDevVip-clus1/fault-901',
            description='failure901')
        sg1 = aim_service_graph.ServiceGraph(
            tenant_name='t1', name='gr1',
            linear_chain_nodes=[{'name': 'N1',
                                 'device_cluster_name': 'cl1'}])
        sg1_fault = aim_status.AciFault(
            fault_code='901',
            external_identifier='uni/tn-t1/AbsGraph-gr1/fault-901',
            description='failure901')
        srp1 = aim_service_graph.ServiceRedirectPolicy(
            tenant_name='t1', name='srp1',
            destinations=[{'ip': '1.1.1.1', 'mac': 'aa:bb:cc:dd:ee:ff'}])
        srp1_fault = aim_status.AciFault(
            fault_code='901',
            external_identifier=('uni/tn-t1/svcCont/svcRedirectPol-srp1'
                                 '/fault-901'),
            description='failure901')
        dc_ctx1 = aim_service_graph.DeviceClusterContext(
            tenant_name='t1', contract_name='contract1',
            service_graph_name='graph1', node_name='N1',
            device_cluster_name='cluster1',
            device_cluster_tenant_name='common',
            bridge_domain_name='svc_bd',
            service_redirect_policy_name='srp1')
        dc_ctx1_fault = aim_status.AciFault(
            fault_code='901',
            external_identifier=('uni/tn-t1/ldevCtx-c-contract1-'
                                 'g-graph1-n-N1/fault-901'),
            description='failure901')

        if tree_type == tree_manager.MONITORED_TREE:
            bd1.monitored = True
            bd2.monitored = True
            t1.monitored = True
            t2.monitored = True
            dc1.monitored = True
            sg1.monitored = True
            srp1.monitored = True
            dc_ctx1.monitored = True

        aim_mgr.create(self.ctx, t1)
        aim_mgr.create(self.ctx, t2)
        aim_mgr.create(self.ctx, bd1)
        aim_mgr.set_fault(self.ctx, t1, t1_fault)
        aim_mgr.set_fault(self.ctx, t2, t2_fault)
        aim_mgr.set_fault(self.ctx, bd1, bd1_fault)
        aim_mgr.set_fault(self.ctx, bd1, bd1_fault2)

        aim_mgr.create(self.ctx, bd2)
        aim_mgr.set_resource_sync_synced(self.ctx, t1)
        aim_mgr.set_resource_sync_synced(self.ctx, t2)
        aim_mgr.set_resource_sync_synced(self.ctx, bd2)
        aim_mgr.set_resource_sync_synced(self.ctx, bd1)

        aim_mgr.create(self.ctx, dc1)
        aim_mgr.create(self.ctx, sg1)
        aim_mgr.create(self.ctx, srp1)
        aim_mgr.create(self.ctx, dc_ctx1)
        aim_mgr.set_fault(self.ctx, dc1, dc1_fault)
        aim_mgr.set_fault(self.ctx, sg1, sg1_fault)
        aim_mgr.set_fault(self.ctx, srp1, srp1_fault)
        aim_mgr.set_fault(self.ctx, dc_ctx1, dc_ctx1_fault)
        aim_mgr.set_resource_sync_synced(self.ctx, dc1)
        aim_mgr.set_resource_sync_synced(self.ctx, sg1)
        aim_mgr.set_resource_sync_synced(self.ctx, srp1)
        aim_mgr.set_resource_sync_synced(self.ctx, dc_ctx1)

        # Two trees exist
        trees = tree_mgr.find(self.ctx, tree=tree_type)
        self.assertEqual(2, len(trees))

        # Calculate the different with empty trees to retrieve missing keys
        diff_tn_1 = trees[0].diff(tree.StructuredHashTree())
        diff_tn_2 = trees[1].diff(tree.StructuredHashTree())
        self.universe.get_relevant_state_for_read = mock.Mock(
            return_value=[{'tn-t1': trees[0], 'tn-t2': trees[1]}])
        result = self.universe.get_resources(diff_tn_1.get('add', []) +
                                             diff_tn_1.get('remove', []) +
                                             diff_tn_2.get('add', []) +
                                             diff_tn_2.get('remove', []))
        converted = converter.AciToAimModelConverter().convert(
            converter.AimToAciModelConverter().convert(
                [bd1, bd2, dc1, sg1, srp1, dc_ctx1, t1, t2]))
        if tree_type == tree_manager.MONITORED_TREE:
            for x in converted:
                x.monitored = True
        if tree_type in [tree_manager.CONFIG_TREE,
                         tree_manager.MONITORED_TREE]:
            self.assertEqual(len(converted), len(result))
            for item in converted:
                self.assertTrue(item in result)
        elif tree_type == tree_manager.OPERATIONAL_TREE:
            self.assertEqual(8, len(result))
            self.assertTrue(bd1_fault in result)
            self.assertTrue(bd1_fault2 in result)
            self.assertTrue(dc1_fault in result)
            self.assertTrue(sg1_fault in result)
            self.assertTrue(srp1_fault in result)
            self.assertTrue(dc_ctx1_fault in result)

    def test_cleanup_state(self, tree_type=tree_manager.CONFIG_TREE):
        tree_mgr = tree_manager.HashTreeManager()
        aim_mgr = aim_manager.AimManager()
        aim_mgr.create(self.ctx, resource.Tenant(name='t1'))
        bd1 = resource.BridgeDomain(
            tenant_name='t1', name='bd1', display_name='somestuff',
            vrf_name='vrf')
        bd1_fault = aim_status.AciFault(
            fault_code='901', external_identifier='uni/tn-t1/BD-bd1/fault-901',
            description='failure901')

        aim_mgr.create(self.ctx, bd1)
        aim_mgr.set_fault(self.ctx, bd1, bd1_fault)
        self.universe.cleanup_state('tn-t1')

        trees = tree_mgr.find(self.ctx, tree=tree_type)
        self.assertEqual(0, len(trees))

    def test_push_resources(self):
        aim_mgr = aim_manager.AimManager()
        aim_mgr.create(self.ctx, resource.Tenant(name='t1'))
        ap = self._get_example_aci_app_profile(dn='uni/tn-t1/ap-a1')
        ap_aim = resource.ApplicationProfile(tenant_name='t1', name='a1')
        epg = self._get_example_aci_epg(
            dn='uni/tn-t1/ap-a1/epg-test')
        epg_aim = resource.EndpointGroup(
            tenant_name='t1', app_profile_name='a1', name='test')
        fault = self._get_example_aci_fault(
            dn='uni/tn-t1/ap-a1/epg-test/fault-951')
        faul_aim = aim_status.AciFault(
            fault_code='951',
            external_identifier='uni/tn-t1/ap-a1/epg-test/fault-951')
        self.universe.push_resources({'create': [ap, epg, fault],
                                      'delete': []})
        res = aim_mgr.get(self.ctx, resource.EndpointGroup(
            tenant_name='t1', app_profile_name='a1', name='test'))
        status = aim_mgr.get_status(self.ctx, res)
        self.assertEqual(1, len(status.faults))
        self.assertEqual('951', status.faults[0].fault_code)

        # Unset fault
        self.universe.push_resources({'create': [],
                                      'delete': [faul_aim]})
        status = aim_mgr.get_status(self.ctx, res)
        self.assertEqual(0, len(status.faults))

        # create subject, and faults for subject-to-filter relation
        filter_objs = [
            {'vzBrCP': {'attributes': {'dn': 'uni/tn-t1/brc-c'}}},
            {'vzSubj': {'attributes': {'dn': 'uni/tn-t1/brc-c/subj-s2'}}},
            self._get_example_aci_fault(
                dn='uni/tn-t1/brc-c/subj-s2/intmnl/rsfiltAtt-f/fault-F1111',
                code='F1111'),
            self._get_example_aci_fault(
                dn='uni/tn-t1/brc-c/subj-s2/outtmnl/rsfiltAtt-g/fault-F1112',
                code='F1112'),
            self._get_example_aci_fault(
                dn='uni/tn-t1/brc-c/subj-s2/rssubjFiltAtt-h/fault-F1113',
                code='F1113')]
        self.universe.push_resources({'create': filter_objs,
                                      'delete': []})
        subj = resource.ContractSubject(tenant_name='t1', contract_name='c',
                                        name='s2')
        status = aim_mgr.get_status(self.ctx, subj)
        self.assertEqual(3, len(status.faults))
        self.assertEqual(['F1111', 'F1112', 'F1113'],
                         [f.fault_code for f in status.faults])

        # delete filter faults
        self.universe.push_resources({'create': [],
                                      'delete': status.faults})
        status = aim_mgr.get_status(self.ctx, subj)
        self.assertEqual(0, len(status.faults))
        # Managed epg
        managed_epg = resource.EndpointGroup(
            tenant_name='t1', app_profile_name='a1', name='managed')
        aim_mgr.create(self.ctx, managed_epg)
        # EPG cannot be deleted since is managed
        self.universe.push_resources({'create': [],
                                      'delete': [ap_aim, managed_epg]})
        res = aim_mgr.get(self.ctx, managed_epg)
        if self.monitor_universe:
            self.assertIsNotNone(res)
            aim_mgr.delete(self.ctx, managed_epg)
        else:
            self.assertIsNone(res)
        if self.ctx.store.supports_foreign_keys:
            res = aim_mgr.get(self.ctx, ap_aim)
            self.assertIsNotNone(res)

            # Second time around, AP deletion  with monitored child works
            epg_aim = aim_mgr.get(self.ctx, epg_aim)
            self.universe.push_resources({'create': [],
                                          'delete': [ap_aim, epg_aim]})
            res = aim_mgr.get(self.ctx, ap_aim)
            if epg_aim.monitored:
                self.assertIsNone(res)
            else:
                self.assertIsNotNone(res)
                self.universe.push_resources({'create': [],
                                              'delete': [ap_aim]})
                res = aim_mgr.get(self.ctx, ap_aim)
                self.assertIsNone(res)

    def test_push_resources_service_graph(self):
        aim_mgr = aim_manager.AimManager()
        aim_mgr.create(self.ctx, resource.Tenant(name='t1'))

        def create_delete_object(aim_obj, aci_obj, aci_faults):
            # create object and faults
            to_create = [aci_obj]
            to_create.extend(aci_faults)
            self.universe.push_resources({'create': to_create,
                                          'delete': []})

            self.assertIsNotNone(aim_mgr.get(self.ctx, aim_obj))
            status = aim_mgr.get_status(self.ctx, aim_obj)
            self.assertEqual(len(aci_faults), len(status.faults))
            self.assertEqual(sorted([f['faultInst']['attributes']['code']
                                     for f in aci_faults]),
                             sorted([f.fault_code for f in status.faults]))

            # delete filter faults
            self.universe.push_resources({'create': [],
                                          'delete': status.faults})
            status = aim_mgr.get_status(self.ctx, aim_obj)
            self.assertEqual(0, len(status.faults))

        # Objects with alt_resource
        dc1_aci = {'vnsLDevVip':
                   {'attributes': {'dn': 'uni/tn-t1/lDevVip-cl2'}}}
        dc1_fault_objs = [
            self._get_example_aci_fault(
                dn='uni/tn-t1/lDevVip-cl2/fault-F1110',
                code='F1110'),
            self._get_example_aci_fault(
                dn='uni/tn-t1/lDevVip-cl2/lIf-interface/fault-F1111',
                code='F1111'),
            self._get_example_aci_fault(
                dn='uni/tn-t1/lDevVip-cl2/cDev-n2/cIf-[interface]/fault-F1112',
                code='F1112')]
        dc1 = aim_service_graph.DeviceCluster(tenant_name='t1', name='cl2')

        create_delete_object(dc1, dc1_aci, dc1_fault_objs)

        sg1_aci = {'vnsAbsGraph':
                   {'attributes': {'dn': 'uni/tn-t1/AbsGraph-gr2'}}}
        sg1_fault_objs = [
            self._get_example_aci_fault(
                dn='uni/tn-t1/AbsGraph-gr2/fault-F1110',
                code='F1110'),
            self._get_example_aci_fault(
                dn='uni/tn-t1/AbsGraph-gr2/AbsConnection-C1/fault-F1111',
                code='F1111'),
            self._get_example_aci_fault(
                dn='uni/tn-t1/AbsGraph-gr2/AbsNode-N1/fault-F1112',
                code='F1112')]
        sg1 = aim_service_graph.ServiceGraph(tenant_name='t1', name='gr2')

        srp1_aci = {'vnsSvcRedirectPol':
                    {'attributes':
                     {'dn': 'uni/tn-t1/svcCont/svcRedirectPol-r2'}}}
        srp1_fault_objs = [
            self._get_example_aci_fault(
                dn='uni/tn-t1/svcCont/svcRedirectPol-r2/fault-F1111',
                code='F1111'),
            self._get_example_aci_fault(
                dn=('uni/tn-t1/svcCont/svcRedirectPol-r2/'
                    'RedirectDest_ip-[10.6.1.1]/fault-F1112'),
                code='F1112')]
        srp1 = aim_service_graph.ServiceRedirectPolicy(tenant_name='t1',
                                                       name='r2')

        dcc1_aci = {'vnsLDevCtx':
                    {'attributes':
                     {'dn': 'uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1'}}}
        dcc1_fault_objs = [
            self._get_example_aci_fault(
                dn='uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/fault-F1111',
                code='F1111'),
            self._get_example_aci_fault(
                dn=('uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/lIfCtx-c-consumer/'
                    'fault-F1112'),
                code='F1112')]
        dcc1 = aim_service_graph.DeviceClusterContext(tenant_name='t1',
                                                      contract_name='c1',
                                                      service_graph_name='g1',
                                                      node_name='N1')

        create_delete_object(dc1, dc1_aci, dc1_fault_objs)
        create_delete_object(sg1, sg1_aci, sg1_fault_objs)
        create_delete_object(srp1, srp1_aci, srp1_fault_objs)
        create_delete_object(dcc1, dcc1_aci, dcc1_fault_objs)

    def test_retrieve_fault_parent(self):
        ext_net = aim_status.AciFault(
            fault_code='F0967',
            external_identifier=('uni/tn-common/out-l3out-1/instP-kepg/'
                                 'rscons-service__default_frontend/'
                                 'fault-F0967'))
        self.assertTrue(
            isinstance(self.universe._retrieve_fault_parent(ext_net)[0],
                       resource.ExternalNetwork))
        epg = aim_status.AciFault(
            fault_code='F0967',
            external_identifier=('uni/tn-common/ap-ap1/epg-epg1/'
                                 'rscons-service__default_frontend/'
                                 'fault-F0967'))
        self.assertTrue(
            isinstance(self.universe._retrieve_fault_parent(epg)[0],
                       resource.EndpointGroup))


class TestAimDbUniverse(TestAimDbUniverseBase, base.TestAimDBBase):

    def test_track_universe_actions(self):
        # When AIM is the current state, created objects are in ACI form,
        # deleted objects are in AIM form
        old_cooldown = self.universe.retry_cooldown
        reset_limit = self.universe.reset_retry_limit
        purge_limit = self.universe.purge_retry_limit
        self.assertEqual(2 * self.universe.max_create_retry, reset_limit)
        self.assertEqual(2 * reset_limit, purge_limit)
        self.assertTrue(self.universe.max_create_retry > 0)
        self.universe.retry_cooldown = -1
        actions = {
            'create': [
                self._get_example_aci_object('fvBD', 'uni/tn-t1/BD-b'),
                self._get_example_aci_object('fvBD', 'uni/tn-t1/BD-b'),
                self._get_example_aci_object('fvCtx', 'uni/tn-t2/ctx-c'),
            ],
            'delete': []
        }
        reset, purge = self.universe._track_universe_actions(actions)
        self.assertEqual(set(), reset)
        self.assertEqual([], purge)
        # 2 roots
        self.assertEqual(2, len(self.universe._action_cache['create']))
        # BD counted only once
        self.assertEqual(
            0, self.universe._action_cache['create']['tn-t1'].values()[0][
                'retries'])
        ctrl = resource.VMMController(domain_type='OpenStack',
                                      domain_name='os', name='ctrl')
        actions = {
            'create': [
                self._get_example_aci_object('fvBD', 'uni/tn-t1/BD-b'),
            ],
            'delete': [ctrl]
        }
        reset, purge = self.universe._track_universe_actions(actions)
        self.assertEqual(set(), reset)
        self.assertEqual([], purge)
        # Tenant t2 is off the hook
        self.assertTrue('tn-t2' not in self.universe._action_cache['create'])
        self.assertTrue('tn-t2' not in self.universe._action_cache['delete'])
        # BD count increased
        self.assertEqual(
            1, self.universe._action_cache['create']['tn-t1'].values()[0][
                'retries'])
        self.assertEqual(
            0, self.universe._action_cache['delete'][ctrl.root].values()[0][
                'retries'])
        # Retry the above until t1 needs reset
        for _ in range(reset_limit - 1):
            reset, purge = self.universe._track_universe_actions(actions)
            self.assertEqual(set(), reset)
            self.assertEqual([], purge)
        reset, purge = self.universe._track_universe_actions(actions)
        self.assertEqual({'tn-t1'}, reset)
        self.assertEqual([], purge)
        # with the next run, reset is not required for t1 anymore, but pure
        # countdown starts
        reset, purge = self.universe._track_universe_actions(actions)
        self.assertEqual({ctrl.root}, reset)
        self.assertEqual([], purge)
        for _ in range(purge_limit - reset_limit - 2):
            reset, purge = self.universe._track_universe_actions(actions)
            self.assertEqual(set(), reset)
            self.assertEqual([], purge)
        reset, purge = self.universe._track_universe_actions(actions)
        self.assertEqual(set(), reset)
        self.assertEqual(1, len(purge))
        self.assertEqual('create', purge[0][0])
        self.assertEqual('uni/tn-t1/BD-b', purge[0][1].dn)
        reset, purge = self.universe._track_universe_actions(actions)
        self.assertEqual(set(), reset)
        self.assertEqual(1, len(purge))
        self.assertEqual(ctrl.dn, purge[0][1].dn)
        self.universe.retry_cooldown = old_cooldown


class TestAimDbOperationalUniverse(TestAimDbUniverseBase, base.TestAimDBBase):

    def setUp(self):
        super(TestAimDbOperationalUniverse, self).setUp(
            klass=aim_universe.AimDbOperationalUniverse)

    def test_state(self):
        super(TestAimDbOperationalUniverse, self).test_state(
            tree_type=tree_manager.OPERATIONAL_TREE)

    def test_get_optimized_state(self):
        super(TestAimDbOperationalUniverse, self).test_get_optimized_state(
            tree_type=tree_manager.OPERATIONAL_TREE)

    def test_get_aim_resources(self):
        super(TestAimDbOperationalUniverse, self).test_get_aim_resources(
            tree_type=tree_manager.OPERATIONAL_TREE)

    def test_cleanup_state(self):
        super(TestAimDbOperationalUniverse, self).test_cleanup_state(
            tree_type=tree_manager.OPERATIONAL_TREE)


class TestAimDbMonitoredUniverse(TestAimDbUniverseBase, base.TestAimDBBase):

    def setUp(self):
        super(TestAimDbMonitoredUniverse, self).setUp(
            klass=aim_universe.AimDbMonitoredUniverse)
        self.monitor_universe = True

    def test_state(self):
        super(TestAimDbMonitoredUniverse, self).test_state(
            tree_type=tree_manager.MONITORED_TREE)

    def test_get_optimized_state(self):
        super(TestAimDbMonitoredUniverse, self).test_get_optimized_state(
            tree_type=tree_manager.MONITORED_TREE)

    def test_get_aim_resources(self):
        super(TestAimDbMonitoredUniverse, self).test_get_aim_resources(
            tree_type=tree_manager.MONITORED_TREE)

    def test_cleanup_state(self):
        super(TestAimDbMonitoredUniverse, self).test_cleanup_state(
            tree_type=tree_manager.MONITORED_TREE)
