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
from aim.api import resource
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim import config as aim_cfg
from aim.tests import base
from aim.tests.unit.agent.aid_universes import test_aci_tenant


def _kill_thread(inst):
    inst.is_dead = mock.Mock(return_value=True)


class TestAciUniverseMixin(test_aci_tenant.TestAciClientMixin):

    def setUp(self, universe_klass=None):
        super(TestAciUniverseMixin, self).setUp()
        self._do_aci_mocks()
        self.backend_state = {}
        self.universe = (universe_klass or
                         aci_universe.AciUniverse)().initialize(
            aim_cfg.ConfigManager(self.ctx, 'h1'), [])
        self.universe.get_relevant_state_for_read = mock.Mock(
            return_value=[self.backend_state])
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

        aci_tenant.AciTenantManager.kill = _kill_thread
        self.addCleanup(self.mock_start.stop)
        self.addCleanup(self.mock_is_dead.stop)
        self.addCleanup(self.mock_is_warm.stop)

    def test_serve(self):
        tenant_list = ['tn-%s' % x for x in range(10)]
        self.universe.serve(self.ctx, tenant_list)
        # List of serving tenant correctly updated
        self.assertEqual(set(tenant_list),
                         set(self.universe.serving_tenants.keys()))
        # Remove some tenants and add more
        tenant_list = tenant_list[5:]
        tenant_list.extend(['tn-%s' % x for x in range(15, 20)])
        self.assertNotEqual(set(tenant_list),
                            set(self.universe.serving_tenants.keys()))
        self.universe.serve(self.ctx, tenant_list)
        self.assertEqual(set(tenant_list),
                         set(self.universe.serving_tenants.keys()))

        # Test same tenants cause a noop
        serving_tenants_copy = dict(
            [(k, v) for k, v in self.universe.serving_tenants.iteritems()])
        self.universe.serve(self.ctx, tenant_list)
        for k, v in serving_tenants_copy.iteritems():
            # Serving tenant values are the same
            self.assertIs(v, self.universe.serving_tenants[k])

        # Kill one of the values, and verify that it gets restored on next
        # serve
        self.universe.serving_tenants['tn-19'].is_dead = mock.Mock(
            return_value=True)
        self.universe.serve(self.ctx, tenant_list)
        for k, v in serving_tenants_copy.iteritems():
            if k != 'tn-19':
                # Serving tenant values are the same
                self.assertIs(v, self.universe.serving_tenants[k])
            else:
                # This was replaced fresh
                self.assertIsNot(v, self.universe.serving_tenants[k])

    def test_observe(self):
        tenant_list = ['tn-%s' % x for x in range(10)]
        self.universe.serve(self.ctx, tenant_list)
        self.assertEqual({}, self.universe.state)
        self.universe.observe(self.ctx)
        for tenant in tenant_list:
            self.assertTrue(tenant in self.universe.state)
            self.assertTrue(isinstance(self.universe.state[tenant],
                                       structured_tree.StructuredHashTree))
        # Remove some tenants and add more
        tenant_list = tenant_list[5:]
        tenant_list.extend(['tn-%s' % x for x in range(15, 20)])
        self.universe.serve(self.ctx, tenant_list)
        # Old state is popped
        for tenant in ['tn-%s' % x for x in range(5)]:
            self.assertFalse(tenant in self.universe.state)
        # New state not present yet
        for tenant in ['tn-%s' % x for x in range(15, 20)]:
            self.assertFalse(tenant in self.universe.state)
        self.universe.observe(self.ctx)
        # Now the new state is fully there
        for tenant in tenant_list:
            self.assertTrue(tenant in self.universe.state)
            self.assertTrue(isinstance(self.universe.state[tenant],
                                       structured_tree.StructuredHashTree))

    def test_serve_exception(self):
        tenant_list = ['tn-%s' % x for x in range(10)]
        self.universe.serve(self.ctx, tenant_list)
        # Remove some tenants
        tenant_list_new = tenant_list[5:]
        old = self.universe.serving_tenants['tn-9'].is_dead
        self.universe.serving_tenants['tn-9'].is_dead = mock.Mock(
            side_effect=KeyError)
        self.assertRaises(KeyError, self.universe.serve, self.ctx,
                          tenant_list_new)
        self.universe.serving_tenants['tn-9'].is_dead = old
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
        self.universe.serve(self.ctx, tenant_list)
        for tenant in tenant_list:
            self.assertFalse(self.universe.serving_tenants[tenant].is_dead())

        # Kill raises exception
        self.universe.serving_tenants['tn-1'].kill = mock.Mock(
            side_effect=ValueError)
        # Serve happens without problems
        self.universe.serve(self.ctx, tenant_list_new)
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

        self.universe.serve(self.ctx, ['tn-tn1', 'tn-tn2'])
        self.universe.push_resources(
            self.ctx, {'create': [bd1_tn1, bd2_tn1, bd2_tn2],
                       'delete': [bd1_tn2]})
        # Verify that the requests are filled properly
        tn1 = self.universe.serving_tenants[
            'tn-tn1'].object_backlog.get_nowait()
        tn2 = self.universe.serving_tenants[
            'tn-tn2'].object_backlog.get_nowait()
        self.assertEqual({'create': [bd1_tn1, bd2_tn1]}, tn1)
        self.assertEqual({'create': [bd2_tn2], 'delete': [bd1_tn2]}, tn2)

        self.assertTrue(
            self.universe.serving_tenants['tn-tn1'].object_backlog.empty())
        self.assertTrue(
            self.universe.serving_tenants['tn-tn2'].object_backlog.empty())

    def test_get_resource_fault(self):
        fault = self._get_example_aci_fault()
        self._add_data_to_tree([fault], self.backend_state)
        key = ('fvTenant|t1', 'fvAp|a1', 'fvAEPg|test', 'faultInst|951')
        result = self.universe.get_resource(key)
        self.assertEqual(fault, result[0])

    def test_get_resources(self):
        objs = [
            self._get_example_aci_fault(),
            {'fvBD': {
                'attributes': {'arpFlood': 'no',
                               'dn': 'uni/tn-test-tenant/BD-test',
                               'epMoveDetectMode': '',
                               'ipLearning': 'yes',
                               'limitIpLearnToSubnets': 'no',
                               'nameAlias': '',
                               'unicastRoute': 'yes',
                               'unkMacUcastAct': 'proxy'}}},
            {'fvRsCtx': {'attributes': {
                'dn': 'uni/tn-test-tenant/BD-test/rsctx', 'tnFvCtxName': ''}}},
            {'vzSubj': {'attributes': {'dn': 'uni/tn-t1/brc-c/subj-s',
                                       'nameAlias': ''}}},
            {'vzInTerm': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/intmnl'}}},
            {'vzOutTerm': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/outtmnl'}}},
            {'vzRsSubjFiltAtt': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/rssubjFiltAtt-f',
                'tnVzFilterName': 'f'}}},
            {'vzRsFiltAtt': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/intmnl/rsfiltAtt-g',
                'tnVzFilterName': 'g'}}},
            {'vzRsFiltAtt': {'attributes': {
                'dn': 'uni/tn-t1/brc-c/subj-s/outtmnl/rsfiltAtt-h',
                'tnVzFilterName': 'h'}}}]
        self._add_data_to_tree(objs, self.backend_state)
        keys = [('fvTenant|t1', 'fvAp|a1', 'fvAEPg|test', 'faultInst|951'),
                ('fvTenant|test-tenant', 'fvBD|test'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s', 'vzRsSubjFiltAtt|f'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s', 'vzOutTerm|outtmnl'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s', 'vzInTerm|intmnl',
                 'vzRsFiltAtt|g'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s', 'vzOutTerm|outtmnl',
                 'vzRsFiltAtt|h'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s')]
        result = self.universe.get_resources(keys)
        self.assertEqual(sorted(objs), sorted(result))

    @base.requires(['skip'])
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
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s',
                 'vzRsSubjFiltAtt|f'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s',
                 'vzInTerm|intmnl', 'vzRsFiltAtt|g'),
                ('fvTenant|t1', 'vzBrCP|c', 'vzSubj|s',
                 'vzOutTerm|outtmnl', 'vzRsFiltAtt|h')]
        result = self.universe.get_resources_for_delete(keys)
        self.assertEqual(sorted(objs), sorted(result))
        # Create a pending monitored object
        tn1 = resource.Tenant(name='tn1', monitored=True)
        monitored_bd = resource.BridgeDomain(
            tenant_name='tn1', name='monitoredBD', monitored=True)
        self.universe.manager.create(self.ctx, tn1)
        self.universe.manager.set_resource_sync_pending(self.ctx, tn1)
        self.universe.manager.create(self.ctx, monitored_bd)
        self.universe.manager.set_resource_sync_pending(self.ctx, monitored_bd)

        self.universe.multiverse = []
        result = self.universe.get_resources_for_delete(
            [('fvTenant|tn1', 'fvBD|monitoredBD')])
        self.assertEqual(1, len(result))
        result = result[0]
        self.assertEqual('tagInst', result.keys()[0])
        self.assertEqual('uni/tn-tn1/BD-monitoredBD/tag-openstack_aid',
                         result.values()[0]['attributes']['dn'])

        # Delete an RS-node of a monitored object
        self.universe.manager.create(self.ctx, resource.L3Outside(
            tenant_name='tn1', name='out', monitored=True))
        ext_net = self.universe.manager.create(
            self.ctx,
            resource.ExternalNetwork(tenant_name='tn1', l3out_name='out',
                                     name='inet',
                                     provided_contract_names=['p1'],
                                     monitored=True))
        self.universe.manager.set_resource_sync_synced(self.ctx, ext_net)
        result = self.universe.get_resources_for_delete(
            [('fvTenant|tn1', 'l3extOut|out', 'l3extInstP|inet',
              'fvRsProv|p1')])
        self.assertEqual(1, len(result))
        result = result[0]
        self.assertEqual('fvRsProv', result.keys()[0])
        self.assertEqual('uni/tn-tn1/out-out/instP-inet/rsprov-p1',
                         result.values()[0]['attributes']['dn'])

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

    def test_thread_monitor(self):
        self.set_override('apic_hosts', ['3.1.1.1', '3.1.1.2', '3.1.1.3'],
                          'apic')
        self.universe.ws_context._reload_websocket_config()
        self.universe.ws_context.monitor_max_backoff = 0
        self.universe.ws_context.monitor_sleep_time = 0
        t = mock.Mock()
        t.isAlive = mock.Mock(return_value=False)
        self.universe.ws_context.subs_thread = t
        with mock.patch.object(utils, 'perform_harakiri') as harakiri:
            self.universe.ws_context._thread_monitor({'monitor_runs': 4})
            self.assertEqual(4, t.isAlive.call_count)
            harakiri.assert_called_once_with(mock.ANY, mock.ANY)
            harakiri.reset_mock()
            t.isAlive = mock.Mock(return_value=True)
            self.universe.ws_context._thread_monitor({'monitor_runs': 4})
            self.assertEqual(0, harakiri.call_count)

    def test_track_universe_actions(self):
        # When AIM is the current state, created objects are in ACI form,
        # deleted objects are in AIM form
        reset_limit = self.universe.reset_retry_limit
        purge_limit = self.universe.purge_retry_limit
        old_backoff_time = self.universe.max_backoff_time
        self.assertEqual(2 * self.universe.max_create_retry, reset_limit)
        self.assertEqual(2 * reset_limit, purge_limit)
        self.assertTrue(self.universe.max_create_retry > 0)
        self.universe.max_backoff_time = 0
        actions = {
            'create': [
                resource.BridgeDomain(tenant_name='t1', name='b'),
                resource.BridgeDomain(tenant_name='t1', name='b'),
            ],
            'delete': []
        }
        reset, purge, skip = self.universe._track_universe_actions(actions,
                                                                   'tn-t1')
        self.assertEqual(False, reset)
        self.assertEqual([], purge)
        # 1 root
        self.assertEqual(1, len(self.universe._sync_log['tn-t1']['create']))
        actions = {
            'create': [
                resource.VRF(tenant_name='t2', name='c'),
            ],
            'delete': []
        }
        reset, purge, skip = self.universe._track_universe_actions(actions,
                                                                   'tn-t2')
        # 2 roots
        self.assertEqual(1, len(self.universe._sync_log['tn-t2']['create']))
        # BD counted only once
        self.assertEqual(
            0, self.universe._sync_log['tn-t1']['create'].values()[0][
                'retries'])
        ctrl = resource.VMMController(domain_type='OpenStack',
                                      domain_name='os', name='ctrl')
        actions = {
            'create': [],
            'delete': [
                self._get_example_aci_object('vmmCtrlrP', ctrl.dn)
            ]
        }
        reset, purge, skip = self.universe._track_universe_actions(
            actions, 'vmmp-OpenStack')
        self.assertEqual(False, reset)
        self.assertEqual([], purge)
        reset, purge, skip = self.universe._track_universe_actions(
            {'create': [], 'delete': []}, 'tn-t2')
        # Tenant t2 is off the hook
        self.assertTrue('tn-t2' not in
                        self.universe._sync_log['tn-t2']['create'])
        self.assertTrue('tn-t2' not in
                        self.universe._sync_log['tn-t2']['delete'])
        actions = {
            'create': [
                resource.BridgeDomain(tenant_name='t1', name='b'),
            ],
            'delete': []
        }
        reset, purge, skip = self.universe._track_universe_actions(actions,
                                                                   'tn-t1')
        # BD count increased
        self.assertEqual(
            1, self.universe._sync_log['tn-t1']['create'].values()[0][
                'retries'])
        self.assertEqual(
            0, self.universe._sync_log[ctrl.root]['delete'].values()[0][
                'retries'])
        # Retry the above until t1 needs reset
        for _ in range(reset_limit - 1):
            reset, purge, skip = self.universe._track_universe_actions(actions,
                                                                       'tn-t1')
            self.assertEqual(False, reset)
            self.assertEqual([], purge)
        reset, purge, skip = self.universe._track_universe_actions(actions,
                                                                   'tn-t1')
        self.assertEqual(True, reset)
        self.assertEqual([], purge)
        # with the next run, reset is not required for t1 anymore, but pure
        # countdown starts
        reset, purge, skip = self.universe._track_universe_actions(actions,
                                                                   'tn-t1')
        self.assertEqual([], purge)
        for _ in range(purge_limit - reset_limit - 2):
            reset, purge, skip = self.universe._track_universe_actions(actions,
                                                                       'tn-t1')
            self.assertEqual(False, reset)
            self.assertEqual([], purge)
        reset, purge, skip = self.universe._track_universe_actions(actions,
                                                                   'tn-t1')
        self.assertEqual(False, reset)
        self.assertEqual(1, len(purge))
        self.assertEqual('create', purge[0][0])
        self.assertEqual('uni/tn-t1/BD-b', purge[0][1].dn)
        self.universe.max_backoff_time = old_backoff_time


class TestAciUniverse(TestAciUniverseMixin, base.TestAimDBBase):

    def setUp(self):
        super(TestAciUniverse, self).setUp(
            aci_universe.AciOperationalUniverse)

    def test_shared_served_tenants(self):
        operational = aci_universe.AciOperationalUniverse().initialize(
            aim_cfg.ConfigManager(self.ctx, ''), [])
        tenant_list = ['tn-%s' % x for x in range(10)]
        self.universe.serve(self.ctx, tenant_list)
        self.assertIs(self.universe.serving_tenants,
                      operational.serving_tenants)
        for key, value in self.universe.serving_tenants.iteritems():
            self.assertIs(operational.serving_tenants[key], value)

    def test_track_universe_actions(self):
        pass


class TestAciOperationalUniverse(TestAciUniverseMixin, base.TestAimDBBase):

    def setUp(self):
        super(TestAciOperationalUniverse, self).setUp(
            aci_universe.AciOperationalUniverse)


class TestAciMonitoredUniverse(TestAciUniverseMixin, base.TestAimDBBase):

    def setUp(self):
        super(TestAciMonitoredUniverse, self).setUp(
            aci_universe.AciMonitoredUniverse)
