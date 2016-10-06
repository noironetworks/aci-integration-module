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

from aim.agent.aid.universes.aci import aci_universe
from aim.agent.aid.universes.aci import tenant as aci_tenant
from aim.common.hashtree import structured_tree
from aim import config as aim_cfg
from aim.tests import base
from aim.tests.unit.agent.aid_universes import test_aci_tenant


def _kill_thread(inst):
    inst.is_dead = mock.Mock(return_value=True)


class TestAciUniverseMixin(test_aci_tenant.TestAciClientMixin):

    def setUp(self, universe_klass=None):
        super(TestAciUniverseMixin, self).setUp()
        self._do_aci_mocks()
        self.universe = (universe_klass or
                         aci_universe.AciUniverse)().initialize(
            self.ctx, aim_cfg.ConfigManager(self.ctx, 'h1'))
        # Mock ACI tenant manager
        self.mock_start = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager.start')
        self.mock_start.start()
        self.mock_is_dead = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager.is_dead',
            return_value=False)
        self.mock_is_dead.start()
        self.mock_is_warm = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager.is_warm',
            return_value=True)
        self.mock_is_warm.start()
        aci_tenant.AciTenantManager.health_state = True
        aci_tenant.AciTenantManager.kill = _kill_thread
        self.addCleanup(self.mock_start.stop)
        self.addCleanup(self.mock_is_dead.stop)
        self.addCleanup(self.mock_is_warm.stop)

    def test_serve(self):
        tenant_list = ['tn%s' % x for x in range(10)]
        self.universe.serve(tenant_list)
        # List of serving tenant correctly updated
        self.assertEqual(set(tenant_list),
                         set(self.universe.serving_tenants.keys()))
        # Remove some tenants and add more
        tenant_list = tenant_list[5:]
        tenant_list.extend(['tn%s' % x for x in range(15, 20)])
        self.assertNotEqual(set(tenant_list),
                            set(self.universe.serving_tenants.keys()))
        self.universe.serve(tenant_list)
        self.assertEqual(set(tenant_list),
                         set(self.universe.serving_tenants.keys()))

        # Test same tenants cause a noop
        serving_tenants_copy = dict(
            [(k, v) for k, v in self.universe.serving_tenants.iteritems()])
        # Health state has to be True
        for k, v in self.universe.serving_tenants.iteritems():
            v.health_state = True
        self.universe.serve(tenant_list)
        for k, v in serving_tenants_copy.iteritems():
            # Serving tenant values are the same
            self.assertIs(v, self.universe.serving_tenants[k])

        # Kill one of the values, and verify that it gets restored on next
        # serve
        self.universe.serving_tenants['tn19'].is_dead = mock.Mock(
            return_value=True)
        self.universe.serve(tenant_list)
        for k, v in serving_tenants_copy.iteritems():
            if k != 'tn19':
                # Serving tenant values are the same
                self.assertIs(v, self.universe.serving_tenants[k])
            else:
                # This was replaced fresh
                self.assertIsNot(v, self.universe.serving_tenants[k])

    def test_observe(self):
        tenant_list = ['tn%s' % x for x in range(10)]
        self.universe.serve(tenant_list)
        self.assertEqual({}, self.universe.state)
        self.universe.observe()
        for tenant in tenant_list:
            self.assertTrue(tenant in self.universe.state)
            self.assertTrue(isinstance(self.universe.state[tenant],
                                       structured_tree.StructuredHashTree))
        # Remove some tenants and add more
        tenant_list = tenant_list[5:]
        tenant_list.extend(['tn%s' % x for x in range(15, 20)])
        self.universe.serve(tenant_list)
        # Old state is popped
        for tenant in ['tn%s' % x for x in range(5)]:
            self.assertFalse(tenant in self.universe.state)
        # New state not present yet
        for tenant in ['tn%s' % x for x in range(15, 20)]:
            self.assertFalse(tenant in self.universe.state)
        self.universe.observe()
        # Now the new state is fully there
        for tenant in tenant_list:
            self.assertTrue(tenant in self.universe.state)
            self.assertTrue(isinstance(self.universe.state[tenant],
                                       structured_tree.StructuredHashTree))

    def test_serve_exception(self):
        tenant_list = ['tn%s' % x for x in range(10)]
        self.universe.serve(tenant_list)
        # Health state has to be True for served tenants
        for k, v in self.universe.serving_tenants.iteritems():
            v.health_state = True
        # Remove some tenants
        tenant_list_new = tenant_list[5:]
        old = self.universe.serving_tenants['tn9'].is_dead
        self.universe.serving_tenants['tn9'].is_dead = mock.Mock(
            side_effect=KeyError)
        self.assertRaises(KeyError, self.universe.serve, tenant_list_new)
        self.universe.serving_tenants['tn9'].is_dead = old
        # List of serving tenant back to the initial one
        self.assertEqual(set(tenant_list),
                         set(self.universe.serving_tenants.keys()))
        # Thread that were once removed are now dead
        for tenant in tenant_list[:5]:
            self.assertTrue(self.universe.serving_tenants[tenant].is_dead())
        # Others are not
        for tenant in tenant_list[5:]:
            self.assertFalse(self.universe.serving_tenants[tenant].is_dead())
        # With a new serve, dead ones are regenerated
        self.universe.serve(tenant_list)
        for tenant in tenant_list:
            self.assertFalse(self.universe.serving_tenants[tenant].is_dead())

        # Kill raises exception
        self.universe.serving_tenants['tn1'].kill = mock.Mock(
            side_effect=ValueError)
        # Serve happens without problems
        self.universe.serve(tenant_list_new)
        self.assertEqual(set(tenant_list_new),
                         set(self.universe.serving_tenants.keys()))

    def test_push_aim_resources(self):
        # Create some resources
        bd1_tn1 = self._get_example_aim_bd(tenant_name='tn1',
                                           name='bd1')
        bd2_tn1 = self._get_example_aim_bd(tenant_name='tn1',
                                           name='bd2')
        bd1_tn2 = self._get_example_aim_bd(tenant_name='tn2',
                                           name='bd1')
        bd2_tn2 = self._get_example_aim_bd(tenant_name='tn2',
                                           name='bd2')

        self.universe.serve(['tn1', 'tn2'])
        self.universe.push_resources(
            {'create': [bd1_tn1, bd2_tn1, bd2_tn2],
             'delete': [bd1_tn2]})
        # Verify that the requests are filled properly
        tn1 = self.universe.serving_tenants['tn1'].object_backlog.get()
        tn2 = self.universe.serving_tenants['tn2'].object_backlog.get()
        self.assertEqual({'create': [bd1_tn1, bd2_tn1]}, tn1)
        self.assertEqual({'create': [bd2_tn2], 'delete': [bd1_tn2]}, tn2)

        self.assertTrue(
            self.universe.serving_tenants['tn1'].object_backlog.empty())
        self.assertTrue(
            self.universe.serving_tenants['tn2'].object_backlog.empty())

    def test_get_resource_fault(self):
        fault = self._get_example_aci_fault()
        self._add_server_data([fault], self.universe, create_parents=True)
        key = ('fvTenant|t1', 'fvAp|a1', 'fvAEPg|test', 'faultInst|951')
        result = self.universe.get_resource(key)
        self.assertEqual(fault, result[0])

    def test_get_resources(self):
        objs = [
            self._get_example_aci_fault(),
            self._get_example_aci_bd(),
            {'vzSubj': {'attributes': {'dn': u'uni/tn-t1/brc-c/subj-s'}}},
            {'vzRsSubjFiltAtt': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/rssubjFiltAtt-f'}}},
            {'vzRsFiltAtt': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/intmnl/rsfiltAtt-g'}}},
            {'vzRsFiltAtt': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/outtmnl/rsfiltAtt-h'}}}]
        self._add_server_data(objs, self.universe, create_parents=True)
        keys = [('fvTenant|t1', 'fvAp|a1', 'fvAEPg|test', 'faultInst|951'),
                ('fvTenant|test-tenant', 'fvBD|test'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s', 'vzRsSubjFiltAtt|f'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s',
                 'vzInTerm|intmnl', 'vzRsFiltAtt|g'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s',
                 'vzOutTerm|outtmnl', 'vzRsFiltAtt|h'), ]
        result = self.universe.get_resources(keys)
        self.assertEqual(sorted(objs), sorted(result))

    def test_get_resources_for_delete(self):
        objs = [
            {'fvBD': {'attributes': {
                'dn': 'uni/tn-t1/BD-test'}}},
            {'vzRsSubjFiltAtt': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/rssubjFiltAtt-f'}}},
            {'vzRsFiltAtt': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/intmnl/rsfiltAtt-g'}}},
            {'vzRsFiltAtt': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/outtmnl/rsfiltAtt-h'}}}]
        keys = [('fvTenant|t1', 'fvBD|test'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s', 'vzRsSubjFiltAtt|f'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s',
                 'vzInTerm|intmnl', 'vzRsFiltAtt|g'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s',
                 'vzOutTerm|outtmnl', 'vzRsFiltAtt|h'), ]
        result = self.universe.get_resources_for_delete(keys)
        self.assertEqual(sorted(objs), sorted(result))

    def test_ws_config_changed(self):
        # Refresh subscriptions
        self.universe.ws_context = aci_universe.WebSocketContext(
            aim_cfg.ConfigManager(self.ctx, 'h1'))
        current_ws = self.universe.ws_context.session
        self.set_override('apic_hosts', ['3.1.1.1'], 'apic', poll=True)
        # Callback modified parameters
        self.assertTrue(current_ws is not self.universe.ws_context.session)
        self.assertEqual(['3.1.1.1'], self.universe.ws_context.apic_hosts)
        self.assertTrue('3.1.1.1' in self.universe.ws_context.session.api)

        # Change again to same value, there'll be no effect
        current_ws = self.universe.ws_context.session
        self.set_override('apic_hosts', ['3.1.1.1'], 'apic')
        self.assertTrue(current_ws is self.universe.ws_context.session)


class TestAciUniverse(TestAciUniverseMixin, base.TestAimDBBase):

    def setUp(self):
        super(TestAciUniverse, self).setUp(
            aci_universe.AciOperationalUniverse)

    def test_shared_served_tenants(self):
        operational = aci_universe.AciOperationalUniverse().initialize(
            self.ctx, aim_cfg.ConfigManager(self.ctx, ''))
        tenant_list = ['tn%s' % x for x in range(10)]
        self.universe.serve(tenant_list)
        self.assertIs(self.universe.serving_tenants,
                      operational.serving_tenants)
        for key, value in self.universe.serving_tenants.iteritems():
            self.assertIs(operational.serving_tenants[key], value)


class TestAciOperationalUniverse(TestAciUniverseMixin, base.TestAimDBBase):

    def setUp(self):
        super(TestAciOperationalUniverse, self).setUp(
            aci_universe.AciOperationalUniverse)


class TestAciMonitoredUniverse(TestAciUniverseMixin, base.TestAimDBBase):

    def setUp(self):
        super(TestAciMonitoredUniverse, self).setUp(
            aci_universe.AciMonitoredUniverse)
