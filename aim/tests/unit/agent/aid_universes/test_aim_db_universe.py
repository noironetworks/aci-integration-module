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


from aim.agent.aid.universes import aim_universe
from aim import aim_manager
from aim.api import resource
from aim.api import status as aim_status
from aim.common.hashtree import structured_tree as tree
from aim import config as aim_cfg
from aim.db import agent_model  # noqa
from aim.db import tree_model
from aim.tests import base


class TestAimDbUniverseBase(object):

    def setUp(self, klass=aim_universe.AimDbUniverse):
        super(TestAimDbUniverseBase, self).setUp()
        self.universe = klass().initialize(
            self.session, aim_cfg.ConfigManager(self.ctx, ''))
        self.tree_mgr = tree_model.TenantTreeManager(tree.StructuredHashTree)

    def test_serve(self):
        # Serve the first batch of tenants
        tenants = ['tn%s' % x for x in range(10)]
        self.universe.serve(tenants)
        self.assertEqual(set(tenants), set(self.universe._served_tenants))

    def test_state(self, tree_type=tree_model.CONFIG_TREE):
        # Create some trees in the AIM DB
        data1 = tree.StructuredHashTree().include(
            [{'key': ('tnA', 'keyB')}, {'key': ('tnA', 'keyC')},
             {'key': ('tnA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('tnA1', 'keyB')}, {'key': ('tnA1', 'keyC')},
             {'key': ('tnA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('tnA2', 'keyB')}, {'key': ('tnA2', 'keyC')},
             {'key': ('tnA2', 'keyC', 'keyD')}])
        self.tree_mgr.update_bulk(self.ctx, [data1, data2, data3],
                                  tree=tree_type)
        # Serve tnA, tnA2 and tnExtra
        self.universe.serve(['tnA', 'tnA2', 'tnExtra'])
        # Now observe
        state = self.universe.state
        # tnA and tnA2 have updated values, tnExtra is still empty
        self.assertEqual(data1, state['tnA'])
        self.assertEqual(data3, state['tnA2'])
        self.assertIsNone(state.get('tnExtra'))

        # Change tree in the DB
        data1.add(('tnA', 'keyB'), attribute='something')
        self.tree_mgr.update_bulk(self.ctx, [data1], tree=tree_type)
        # Observe and verify that trees are back in sync
        self.assertNotEqual(data1, state['tnA'])
        state = self.universe.state
        self.assertEqual(data1, state['tnA'])

    def test_get_optimized_state(self, tree_type=tree_model.CONFIG_TREE):
        data1 = tree.StructuredHashTree().include(
            [{'key': ('tnA', 'keyB')}, {'key': ('tnA', 'keyC')},
             {'key': ('tnA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('tnA1', 'keyB')}, {'key': ('tnA1', 'keyC')},
             {'key': ('tnA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('tnA2', 'keyB')}, {'key': ('tnA2', 'keyC')},
             {'key': ('tnA2', 'keyC', 'keyD')}])
        self.tree_mgr.update_bulk(self.ctx, [data1, data2, data3],
                                  tree=tree_type)

        self.universe.serve(['tnA', 'tnA1', 'tnA2', 'tnA3'])
        # Other state is in sync
        other_state = {
            'tnA': tree.StructuredHashTree().from_string(str(data1)),
            'tnA1': tree.StructuredHashTree().from_string(str(data2)),
            'tnA2': tree.StructuredHashTree().from_string(str(data3))}
        # Optimized state is empty
        self.assertEqual({}, self.universe.get_optimized_state(other_state))

        # Add a new tenant
        data4 = tree.StructuredHashTree().include(
            [{'key': ('tnA3', 'keyB')}, {'key': ('tnA3', 'keyC')},
             {'key': ('tnA3', 'keyC', 'keyD')}])
        self.tree_mgr.update_bulk(self.ctx, [data4], tree=tree_type)
        self.assertEqual({'tnA3': data4},
                         self.universe.get_optimized_state(other_state))
        # Modify data1
        data1.add(('tnA', 'keyZ'), attribute='something')
        self.tree_mgr.update_bulk(self.ctx, [data1], tree=tree_type)
        # Now Data1 is included too
        self.assertEqual({'tnA3': data4, 'tnA': data1},
                         self.universe.get_optimized_state(other_state))

    def test_get_aim_resources(self, tree_type=tree_model.CONFIG_TREE):
        tree_mgr = tree_model.TenantHashTreeManager()
        aim_mgr = aim_manager.AimManager()
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
        if tree_type == tree_model.MONITORED_TREE:
            bd1.monitored = True
            bd2.monitored = True

        aim_mgr.create(self.ctx, bd1)
        aim_mgr.set_fault(self.ctx, bd1, bd1_fault)
        aim_mgr.set_fault(self.ctx, bd1, bd1_fault2)

        aim_mgr.create(self.ctx, bd2)

        # Two trees exist
        trees = tree_mgr.find(self.ctx, tree=tree_type)
        self.assertEqual(2, len(trees))

        # Calculate the different with empty trees to retrieve missing keys
        diff_tn_1 = trees[0].diff(tree.StructuredHashTree())
        diff_tn_2 = trees[1].diff(tree.StructuredHashTree())

        result = self.universe.get_resources(diff_tn_1.get('add', []) +
                                             diff_tn_1.get('remove', []) +
                                             diff_tn_2.get('add', []) +
                                             diff_tn_2.get('remove', []))
        self.assertEqual(2, len(result))
        if tree_type in [tree_model.CONFIG_TREE, tree_model.MONITORED_TREE]:
            self.assertTrue(bd1 in result)
            self.assertTrue(bd2 in result)
        elif tree_type == tree_model.OPERATIONAL_TREE:
            self.assertTrue(bd1_fault in result)
            self.assertTrue(bd1_fault2 in result)

    def test_cleanup_state(self, tree_type=tree_model.CONFIG_TREE):
        tree_mgr = tree_model.TenantHashTreeManager()
        aim_mgr = aim_manager.AimManager()
        bd1 = resource.BridgeDomain(
            tenant_name='t1', name='bd1', display_name='somestuff',
            vrf_name='vrf')
        bd1_fault = aim_status.AciFault(
            fault_code='901', external_identifier='uni/tn-t1/bd-bd1/fault-901',
            description='failure901')

        aim_mgr.create(self.ctx, bd1)
        aim_mgr.set_fault(self.ctx, bd1, bd1_fault)
        self.universe.cleanup_state('t1')

        trees = tree_mgr.find(self.ctx, tree=tree_type)
        self.assertEqual(0, len(trees))

    def test_push_resources(self):
        aim_mgr = aim_manager.AimManager()
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

        # Delete AP before EPG (AP can't be deleted)
        self.universe.push_resources({'create': [],
                                      'delete': [ap_aim, epg_aim]})
        res = aim_mgr.get(self.ctx, epg_aim)
        self.assertIsNone(res)
        res = aim_mgr.get(self.ctx, ap_aim)
        self.assertIsNotNone(res)

        # Second time around, AP deletion works
        self.universe.push_resources({'create': [],
                                      'delete': [ap_aim]})
        res = aim_mgr.get(self.ctx, ap_aim)
        self.assertIsNone(res)


class TestAimDbUniverse(TestAimDbUniverseBase, base.TestAimDBBase):
    pass


class TestAimDbOperationalUniverse(TestAimDbUniverseBase, base.TestAimDBBase):

    def setUp(self):
        super(TestAimDbOperationalUniverse, self).setUp(
            klass=aim_universe.AimDbOperationalUniverse)

    def test_state(self):
        super(TestAimDbOperationalUniverse, self).test_state(
            tree_type=tree_model.OPERATIONAL_TREE)

    def test_get_optimized_state(self):
        super(TestAimDbOperationalUniverse, self).test_get_optimized_state(
            tree_type=tree_model.OPERATIONAL_TREE)

    def test_get_aim_resources(self):
        super(TestAimDbOperationalUniverse, self).test_get_aim_resources(
            tree_type=tree_model.OPERATIONAL_TREE)

    def test_cleanup_state(self):
        super(TestAimDbOperationalUniverse, self).test_cleanup_state(
            tree_type=tree_model.OPERATIONAL_TREE)


class TestAimDbMonitoredUniverse(TestAimDbUniverseBase, base.TestAimDBBase):

    def setUp(self):
        super(TestAimDbMonitoredUniverse, self).setUp(
            klass=aim_universe.AimDbMonitoredUniverse)

    def test_state(self):
        super(TestAimDbMonitoredUniverse, self).test_state(
            tree_type=tree_model.MONITORED_TREE)

    def test_get_optimized_state(self):
        super(TestAimDbMonitoredUniverse, self).test_get_optimized_state(
            tree_type=tree_model.MONITORED_TREE)

    def test_get_aim_resources(self):
        super(TestAimDbMonitoredUniverse, self).test_get_aim_resources(
            tree_type=tree_model.MONITORED_TREE)

    def test_cleanup_state(self):
        super(TestAimDbMonitoredUniverse, self).test_cleanup_state(
            tree_type=tree_model.MONITORED_TREE)
