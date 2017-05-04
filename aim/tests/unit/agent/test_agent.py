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

import json
from requests import exceptions as rexc
import time

from apicapi import apic_client
from apicapi import exceptions as aexc
import mock
from oslo_db import exception

from aim.agent.aid import service
from aim.agent.aid.universes.aci import aci_universe
from aim.aim_lib import nat_strategy
from aim import aim_manager
from aim.api import resource
from aim.api import service_graph
from aim.api import status as aim_status
from aim.common.hashtree import structured_tree as tree
from aim.common import utils
from aim import config
from aim import context
from aim.tests import base
from aim.tests.unit.agent.aid_universes import test_aci_tenant
from aim.tools.cli.debug import hashtree as treecli
from aim import tree_manager


def run_once_loop(agent):
    def _run_once_loop(ctx, serve=True):
        agent.run_daemon_loop = False
        try:
            agent._run_arguments
        except AttributeError:
            agent._run_arguments = []
        agent._run_arguments = agent._run_arguments + [ctx, serve]
    return _run_once_loop


class TestAgent(base.TestAimDBBase, test_aci_tenant.TestAciClientMixin):

    def setUp(self):
        super(TestAgent, self).setUp()
        self.set_override('agent_down_time', 3600, 'aim')
        self.set_override('agent_polling_interval', 0, 'aim')
        self.set_override('aci_tenant_polling_yield', 0, 'aim')
        self.aim_manager = aim_manager.AimManager()
        self.tree_manager = tree_manager.TreeManager(tree.StructuredHashTree)
        self.old_post = apic_client.ApicSession.post_body_dict

        self.addCleanup(self._reset_apic_client)
        self._do_aci_mocks()
        self.tenant_thread = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager.run')
        self.tenant_thread.start()

        self.thread_dead = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager.is_dead',
            return_value=False)
        self.thread_dead.start()

        self.thread_warm = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager.is_warm',
            return_value=True)
        self.thread_warm.start()

        self.events_thread = mock.patch(
            'aim.agent.aid.event_handler.EventHandler._spawn_listener')
        self.events_thread.start()

        self.watcher_threads = mock.patch(
            'aim.agent.aid.universes.k8s.k8s_watcher.K8sWatcher.run')
        self.watcher_threads.start()

        self.stop_watcher_threads = mock.patch(
            'aim.agent.aid.universes.k8s.k8s_watcher.K8sWatcher.stop_threads')
        self.stop_watcher_threads.start()

        self.hb_loop = mock.patch(
            'aim.agent.aid.service.AID._spawn_heartbeat_loop')
        self.hb_loop.start()

        self.addCleanup(self.tenant_thread.stop)
        self.addCleanup(self.thread_dead.stop)
        self.addCleanup(self.thread_warm.stop)
        self.addCleanup(self.events_thread.stop)
        self.addCleanup(self.watcher_threads.stop)
        self.addCleanup(self.stop_watcher_threads.stop)
        self.addCleanup(self.hb_loop.stop)

    def _reset_apic_client(self):
        apic_client.ApicSession.post_body_dict = self.old_post

    def _mock_current_manager_post(self, mo, data, *params):
        # Each post, generates the same set of events for the WS interface
        events = []
        base = 'uni'
        container = mo.container
        if container:
            base = apic_client.ManagedObjectClass(container).dn(*params[:-1])
        self._tree_to_event(data, events, base, self._current_manager)
        # pre-create Kubernetes VMM domain so that implicitly
        # created Kubernetes objects can be handled
        k8s_ctrlr = {'vmmInjectedCont':
                     {'attributes':
                      {'dn': ('uni/vmmp-Kubernetes/dom-kubernetes/'
                              'ctrlr-kube-cluster/injcont')}}}
        self._set_events([k8s_ctrlr], manager=self._current_manager,
                         tag=False, create_parents=True)
        # Tagging is done by the tenant manager
        self._set_events(events, manager=self._current_manager, tag=False)

    def _mock_current_manager_delete(self, dn, **kwargs):
        # remove /mo/ and .json
        decomposed = test_aci_tenant.decompose_aci_dn(dn[4:-5])
        data = [{decomposed[-1][0]: {'attributes': {'dn': dn[4:-5],
                                                    'status': 'deleted'}}}]
        self._set_events(data, manager=self._current_manager, tag=False)

    def _tree_to_event(self, root, result, dn, manager):
        if not root:
            return
        children = root.values()[0]['children']
        root.values()[0]['children'] = []
        dn += '/' + root.values()[0]['attributes']['rn']
        root.values()[0]['attributes']['dn'] = dn
        status = root.values()[0]['attributes'].get('status')
        if status is None:
            root.values()[0]['attributes']['status'] = 'created'
        elif status == 'deleted':
            # API call fails in case the item doesn't exist
            if not test_aci_tenant.mock_get_data(manager.aci_session,
                                                 'mo/' + dn):
                raise apic_client.cexc.ApicResponseNotOk(
                    request='delete', status='404',
                    reason='not found', err_text='not', err_code='404')
        result.append(root)
        for child in children:
            self._tree_to_event(child, result, dn, manager)

    def _create_agent(self, host='h1'):
        self.set_override('aim_service_identifier', host, 'aim')
        aid = service.AID(config.CONF)
        session = aci_universe.AciUniverse.establish_aci_session(
            self.cfg_manager)
        for pair in aid.multiverse:
            for universe in pair.values():
                if getattr(universe, 'aci_session', None):
                    universe.aci_session = session
                    session._data_stash = {}
        return aid

    def test_init(self):
        agent = self._create_agent()
        self.assertEqual('h1', agent.host)
        # Agent is registered
        agents = self.aim_manager.find(self.ctx, resource.Agent)
        self.assertEqual(1, len(agents))
        self.assertEqual('aid-h1', agents[0].id)

    @base.requires(['timestamp'])
    def test_send_heartbeat(self):
        agent = self._create_agent()
        current_tstamp = agent.agent.heartbeat_timestamp
        time.sleep(1)
        agent._send_heartbeat(self.ctx)
        self.assertTrue(current_tstamp < agent.agent.heartbeat_timestamp)

    def test_calculate_tenants(self):
        # One agent, zero tenants
        agent = self._create_agent()
        result = agent._calculate_tenants(self.ctx)
        self.assertEqual([], result)
        self.assertEqual([], agent.agent.hash_trees)

        # Same agent, one tenant
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        self.tree_manager.update_bulk(self.ctx, [data])
        result = agent._calculate_tenants(self.ctx)
        self.assertEqual(['keyA'], result)
        self.assertEqual(['keyA'], agent.agent.hash_trees)

        # Same agent, N Tenants
        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA1', 'keyB')}, {'key': ('keyA1', 'keyC')},
             {'key': ('keyA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('keyA2', 'keyB')}, {'key': ('keyA2', 'keyC')},
             {'key': ('keyA2', 'keyC', 'keyD')}])
        self.tree_manager.update_bulk(self.ctx, [data2, data3])
        result = agent._calculate_tenants(self.ctx)
        # All tenants are served by this agent since he's the only one
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']), set(result))
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(agent.agent.hash_trees))

        # Multiple Agents
        agent2 = self._create_agent(host='h2')
        agent3 = self._create_agent(host='h3')
        # Recalculate
        result = agent._calculate_tenants(self.ctx)
        result2 = agent2._calculate_tenants(self.ctx)
        result3 = agent3._calculate_tenants(self.ctx)
        # All the tenants must be served
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result + result2))
        self.assertNotEqual([], result)
        self.assertNotEqual([], result2)
        self.assertNotEqual([], result3)
        if not agent.single_aid:
            # Each tenant has 2 agents
            self.assertEqual(
                2,
                len([x for x in result + result2 + result3 if x == 'keyA']))
            self.assertEqual(
                2,
                len([x for x in result + result2 + result3 if x == 'keyA1']))
            self.assertEqual(
                2,
                len([x for x in result + result2 + result3 if x == 'keyA2']))
        else:
            self.assertEqual(set(['keyA', 'keyA1', 'keyA2']), set(result))
            self.assertEqual(set(['keyA', 'keyA1', 'keyA2']), set(result2))
            self.assertEqual(set(['keyA', 'keyA1', 'keyA2']), set(result3))

    @base.requires(['timestamp'])
    def test_down_time_suicide(self):
        with mock.patch.object(service.utils, 'perform_harakiri') as hara:
            agent = self._create_agent()
            agent._calculate_tenants(self.ctx)
            agent.max_down_time = -1
            agent._calculate_tenants(self.ctx)
            hara.assert_called_once_with(service.LOG, mock.ANY)

    @base.requires(['timestamp'])
    def test_tenant_association_fail(self):
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA1', 'keyB')}, {'key': ('keyA1', 'keyC')},
             {'key': ('keyA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('keyA2', 'keyB')}, {'key': ('keyA2', 'keyC')},
             {'key': ('keyA2', 'keyC', 'keyD')}])
        self.tree_manager.update_bulk(self.ctx, [data, data2, data3])
        agent = self._create_agent()
        agent2 = self._create_agent(host='h2')

        # Bring agent administratively down
        agent.agent.admin_state_up = False
        self.aim_manager.create(self.ctx, agent.agent, overwrite=True)
        result = agent._calculate_tenants(self.ctx)
        result2 = agent2._calculate_tenants(self.ctx)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result2))
        # Agent one has no tenant assigned
        self.assertEqual([], result)

        # Fix agent1
        agent.agent.admin_state_up = True
        self.aim_manager.create(self.ctx, agent.agent, overwrite=True)
        result = agent._calculate_tenants(self.ctx)
        result2 = agent2._calculate_tenants(self.ctx)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result + result2))
        # neither agent has empty configuration
        self.assertNotEqual([], result)
        self.assertNotEqual([], result2)

        # Upgrade agent2 version
        agent2.agent.version = "2.0.0"
        self.aim_manager.create(self.ctx, agent2.agent, overwrite=True)
        result = agent._calculate_tenants(self.ctx)
        result2 = agent2._calculate_tenants(self.ctx)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result2))
        # Agent one has no tenant assigned
        self.assertEqual([], result)

        # Upgrade agent1 version
        agent.agent.version = "2.0.0"
        self.aim_manager.create(self.ctx, agent.agent, overwrite=True)
        result = agent._calculate_tenants(self.ctx)
        result2 = agent2._calculate_tenants(self.ctx)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result + result2))
        # neither agent has empty configuration
        self.assertNotEqual([], result)
        self.assertNotEqual([], result2)

    def test_main_loop(self):
        agent = self._create_agent()
        # Keep test compatibility with monitred universe introduction
        agent.current_universe = agent.multiverse[0]['current']
        agent.desired_universe = agent.multiverse[0]['desired']

        tenant_name1 = 'test_main_loop1'
        tenant_name2 = 'test_main_loop2'
        # Create 2 tenants by initiating their objects
        tn1 = resource.Tenant(name=tenant_name1)
        tn2 = resource.Tenant(name=tenant_name2)
        self.aim_manager.create(self.ctx, tn1)
        self.aim_manager.create(self.ctx, tn2)

        bd1_tn1 = resource.BridgeDomain(tenant_name=tenant_name1, name='bd1',
                                        vrf_name='vrf1')
        bd1_tn2 = resource.BridgeDomain(tenant_name=tenant_name2, name='bd1',
                                        vrf_name='vrf2', display_name='nice')
        self.aim_manager.create(self.ctx, bd1_tn2)
        self.aim_manager.create(self.ctx, bd1_tn1)
        bd1_tn1_status = self.aim_manager.get_status(self.ctx, bd1_tn1)
        bd1_tn2_status = self.aim_manager.get_status(self.ctx, bd1_tn2)
        self.aim_manager.set_fault(
            self.ctx, bd1_tn1, aim_status.AciFault(
                fault_code='516',
                external_identifier='uni/tn-%s/BD-bd1/'
                                    'fault-516' % tenant_name1))
        # Fault has been registered in the DB
        status = self.aim_manager.get_status(self.ctx, bd1_tn1)
        self.assertEqual(1, len(status.faults))

        # ACI universe is empty right now, one cycle of the main loop will
        # reconcile the state
        agent._daemon_loop(self.ctx)

        for tenant in agent.current_universe.serving_tenants.values():
            tenant._subscribe_tenant()
        # The ACI universe will not push the configuration unless explicitly
        # called
        self.assertFalse(
            agent.current_universe.serving_tenants[tn1.rn].
            object_backlog.empty())
        self.assertFalse(
            agent.current_universe.serving_tenants[tn2.rn].
            object_backlog.empty())

        # Meanwhile, Operational state has been cleaned from AIM
        status = self.aim_manager.get_status(self.ctx, bd1_tn1)
        self.assertEqual(0, len(status.faults))

        # Events around the BD creation are now sent to the ACI universe, add
        # them to the observed tree
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete
        for tenant in agent.current_universe.serving_tenants.values():
            self._current_manager = tenant
            tenant._event_loop()

        # Now, the two trees are in sync
        agent._daemon_loop(self.ctx)
        self._assert_universe_sync(agent.desired_universe,
                                   agent.current_universe,
                                   tenants=[tn1.root, tn2.root])
        self._assert_reset_consistency()

        # Status for the two BDs is now synced
        bd1_tn1_status = self.aim_manager.get_status(self.ctx, bd1_tn1)
        bd1_tn2_status = self.aim_manager.get_status(self.ctx, bd1_tn2)
        self.assertEqual(aim_status.AciStatus.SYNCED,
                         bd1_tn1_status.sync_status)
        self.assertEqual(aim_status.AciStatus.SYNCED,
                         bd1_tn2_status.sync_status)

        self.assertTrue(
            agent.current_universe.serving_tenants[tn1.rn].
            object_backlog.empty())
        self.assertTrue(
            agent.current_universe.serving_tenants[tn2.rn].
            object_backlog.empty())

        # Delete object and create a new one on tn1
        self.aim_manager.delete(self.ctx, bd1_tn1)
        bd2_tn1 = resource.BridgeDomain(tenant_name=tenant_name1, name='bd2',
                                        vrf_name='vrf3')
        self.aim_manager.create(self.ctx, bd2_tn1)
        # Push state
        currentserving_tenants = {
            k: v for k, v in
            agent.current_universe.serving_tenants.iteritems()}
        agent._daemon_loop(self.ctx)
        self.assertIs(agent.current_universe.serving_tenants[tn1.rn],
                      currentserving_tenants[tn1.rn])
        self.assertIs(agent.current_universe.serving_tenants[tn2.rn],
                      currentserving_tenants[tn2.rn])
        # There are changes on tn1 only
        self.assertFalse(
            agent.current_universe.serving_tenants[tn1.rn].
            object_backlog.empty())
        self.assertTrue(
            agent.current_universe.serving_tenants[tn2.rn].
            object_backlog.empty())
        # Get events
        for tenant in agent.current_universe.serving_tenants.values():
            self._current_manager = tenant
            tenant._event_loop()
        agent._daemon_loop(self.ctx)
        # Everything is in sync again
        self._assert_universe_sync(agent.desired_universe,
                                   agent.current_universe,
                                   tenants=[tn1.root, tn2.root])
        self._assert_reset_consistency(tn1.rn)
        self._assert_reset_consistency(tn2.rn)

        # Delete a tenant
        self.aim_manager.delete(self.ctx, bd2_tn1)
        self.aim_manager.delete(self.ctx, tn1)

        agent._daemon_loop(self.ctx)
        # There are changes on tn1 only
        self.assertFalse(
            agent.current_universe.serving_tenants[tn1.rn].
            object_backlog.empty())
        self.assertTrue(
            agent.current_universe.serving_tenants[tn2.rn].
            object_backlog.empty())
        self.assertIs(agent.current_universe.serving_tenants[tn1.rn],
                      currentserving_tenants[tn1.rn])
        self.assertIs(agent.current_universe.serving_tenants[tn2.rn],
                      currentserving_tenants[tn2.rn])
        # Get events
        for tenant in agent.current_universe.serving_tenants.values():
            self._current_manager = tenant
            tenant._event_loop()
        # Depending on the order of operation, we might need another
        # iteration to cleanup the tree completely
        if agent.current_universe.serving_tenants[tn1.rn]._state.root:
            agent._daemon_loop(self.ctx)
            for tenant in agent.current_universe.serving_tenants.values():
                self._current_manager = tenant
                tenant._event_loop()
        # Tenant still exist on AIM because observe didn't run yet
        self.assertIsNone(
            agent.current_universe.serving_tenants[tn1.rn]._state.root)
        tree1 = agent.tree_manager.find(self.ctx, root_rn=[tn1.rn])
        self.assertEqual(1, len(tree1))
        # Now tenant will be deleted (still served)
        agent._daemon_loop(self.ctx)
        self.assertIsNone(agent.current_universe.state[tn1.rn].root)
        tree1 = agent.tree_manager.find(self.ctx, root_rn=[tn1.rn])
        self.assertEqual(0, len(tree1))

        # Agent not served anymore
        agent._daemon_loop(self.ctx)
        self.assertFalse(tenant_name1 in agent.current_universe.state)

    def test_handle_sigterm(self):
        agent = self._create_agent()
        self.assertTrue(agent.run_daemon_loop)
        agent._handle_sigterm(mock.Mock(), mock.Mock())
        self.assertFalse(agent.run_daemon_loop)

    def test_change_polling_interval(self):
        agent = self._create_agent()
        self.set_override('agent_polling_interval', 130, 'aim')
        self.assertNotEqual(130, agent.polling_interval)
        agent.conf_manager.subs_mgr._poll_and_execute()
        self.assertEqual(130, agent.polling_interval)

    def test_change_report_interval(self):
        agent = self._create_agent()
        self.set_override('agent_report_interval', 130, 'aim')
        self.assertNotEqual(130, agent.report_interval)
        agent.conf_manager.subs_mgr._poll_and_execute()
        self.assertEqual(130, agent.report_interval)

    def test_monitored_tree_lifecycle(self):
        agent = self._create_agent()

        current_config = agent.multiverse[0]['current']
        tenant_name = 'test_monitored_tree_lifecycle'
        current_monitor = agent.multiverse[2]['current']
        desired_monitor = agent.multiverse[2]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete
        # start by managing a single tenant (non-monitored)
        tn1 = resource.Tenant(name=tenant_name, monitored=True)
        aci_tn = self._get_example_aci_tenant(
            name=tenant_name, dn='uni/tn-%s' % tenant_name, nameAlias='nice')
        self.aim_manager.create(self.ctx, tn1)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        self._set_events(
            [aci_tn], manager=desired_monitor.serving_tenants[tn1.rn],
            tag=False)
        self._observe_aci_events(current_config)
        # Simulate an external actor creating a BD
        aci_bd = self._get_example_aci_bd(
            tenant_name=tenant_name, name='default',
            dn='uni/tn-%s/BD-default' % tenant_name)
        aci_rsctx = self._get_example_aci_rs_ctx(
            dn='uni/tn-%s/BD-default/rsctx' % tenant_name)
        self._set_events(
            [aci_bd, aci_rsctx],
            manager=desired_monitor.serving_tenants[tn1.rn],
            tag=False)
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete

        # Observe ACI events
        self._observe_aci_events(current_config)

        # Run the loop for reconciliation
        agent._daemon_loop(self.ctx)

        # Run loop again to set SYNCED state
        self._observe_aci_events(current_config)
        agent._daemon_loop(self.ctx)

        # A monitored BD should now exist in AIM
        aim_bd = self.aim_manager.get(self.ctx, resource.BridgeDomain(
            tenant_name=tenant_name, name='default'))
        self.assertTrue(aim_bd.monitored)
        self.assertEqual('default', aim_bd.vrf_name)
        # This BD's sync state should be OK
        aim_bd_status = self.aim_manager.get_status(self.ctx, aim_bd)
        self.assertEqual(aim_status.AciStatus.SYNCED,
                         aim_bd_status.sync_status)
        # Trees are in sync
        self._assert_universe_sync(desired_monitor, current_monitor,
                                   tenants=[tn1.root])
        self._assert_reset_consistency()

        # Delete the monitored BD, will be re-created
        self.aim_manager.delete(self.ctx, aim_bd)
        agent._daemon_loop(self.ctx)
        # It's reconciled
        aim_bd = self.aim_manager.get(self.ctx, resource.BridgeDomain(
            tenant_name=tenant_name, name='default'))
        self.assertTrue(aim_bd.monitored)
        # Send delete event
        aci_bd['fvBD']['attributes']['status'] = 'deleted'
        aci_rsctx['fvRsCtx']['attributes']['status'] = 'deleted'
        ac_bd_tag = {'tagInst': {'attributes': {
            'dn': aci_bd['fvBD']['attributes']['dn'] + '/tag-' + self.sys_id,
            'status': 'deleted'}}}
        self._set_events(
            [ac_bd_tag, aci_rsctx, aci_bd],
            manager=desired_monitor.serving_tenants[tn1.rn], tag=False)
        # Observe ACI events
        self._observe_aci_events(current_config)
        # Run the loop for reconciliation
        agent._daemon_loop(self.ctx)
        # BD is deleted
        aim_bd = self.aim_manager.get(self.ctx, resource.BridgeDomain(
            tenant_name=tenant_name, name='default'))
        self.assertIsNone(aim_bd)
        self._assert_universe_sync(desired_monitor, current_monitor,
                                   tenants=[tn1.root])
        self._assert_reset_consistency(tn1.rn)

    @base.requires(['foreign_keys'])
    def test_monitored_tree_fk_semantics(self):
        agent = self._create_agent()

        current_config = agent.multiverse[0]['current']
        desired_monitor = agent.multiverse[2]['desired']
        tenant_name = 'test_monitored_tree_fk_semantics'
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete
        # start by managing a single monitored tenant
        tn1 = resource.Tenant(name=tenant_name, monitored=True)
        aci_tn = self._get_example_aci_tenant(
            name=tenant_name, dn='uni/tn-%s' % tenant_name)
        # Create tenant in AIM to start serving it
        self.aim_manager.create(self.ctx, tn1)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        # we need this tenant to exist in ACI
        self._set_events(
            [aci_tn], manager=desired_monitor.serving_tenants[tn1.rn],
            tag=False)
        # Observe ACI events
        self._observe_aci_events(current_config)
        # Create a managed BD
        bd1 = resource.BridgeDomain(name='bd1', tenant_name=tenant_name)
        self.aim_manager.create(self.ctx, bd1)
        # Make BD appear on ACI
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        # Create a monitored subnet in the BD
        aci_sub = self._get_example_aci_subnet(
            dn='uni/tn-%s/BD-bd1/subnet-[10.10.10.1/28]' % tenant_name)
        self._set_events(
            [aci_sub], manager=desired_monitor.serving_tenants[tn1.rn],
            tag=False)
        # Observe the event
        self._observe_aci_events(current_config)
        # Reconcile
        agent._daemon_loop(self.ctx)
        # Monitored sub is created
        aim_sub = resource.Subnet(tenant_name=tenant_name, bd_name='bd1',
                                  gw_ip_mask='10.10.10.1/28')
        aim_sub = self.aim_manager.get(self.ctx, aim_sub)
        # Create a managed sub
        aim_sub2 = resource.Subnet(tenant_name=tenant_name, bd_name='bd1',
                                   gw_ip_mask='10.10.11.1/28')
        aim_sub2 = self.aim_manager.create(self.ctx, aim_sub2)
        self.assertTrue(aim_sub.monitored)
        self.assertFalse(aim_sub2.monitored)
        # deleting the BD from aim fails because of FK
        self.assertRaises(exception.DBReferenceError, self.aim_manager.delete,
                          self.ctx, bd1)
        # now delete managed sub
        self.aim_manager.delete(self.ctx, aim_sub2)
        # Deleting BD will now work
        self.aim_manager.delete(self.ctx, bd1)

    def test_monitored_tree_serve_semantics(self):
        agent = self._create_agent()

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']

        desired_monitor = agent.multiverse[2]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete
        tenant_name = 'test_monitored_tree_serve_semantics'
        self.assertEqual({}, desired_monitor.aci_session._data_stash)

        # start by managing a single monitored tenant
        tn1 = resource.Tenant(name=tenant_name, monitored=True)
        aci_tn = self._get_example_aci_tenant(
            name=tenant_name, dn='uni/tn-%s' % tenant_name)
        aci_bd = self._get_example_aci_bd(
            tenant_name=tenant_name, name='mybd',
            dn='uni/tn-%s/BD-mybd' % tenant_name)
        # Create tenant in AIM to start serving it
        self.aim_manager.create(self.ctx, tn1)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        # we need this tenant to exist in ACI
        self._set_events(
            [aci_tn, aci_bd],
            manager=desired_monitor.serving_tenants[tn1.rn], tag=False)
        self._observe_aci_events(current_config)
        agent._daemon_loop(self.ctx)
        bd1 = resource.BridgeDomain(name='bd1', tenant_name=tenant_name)
        self.aim_manager.create(self.ctx, bd1)
        # Push BD in ACI
        agent._daemon_loop(self.ctx)
        # Feedback loop
        self._observe_aci_events(current_config)
        # Observe
        agent._daemon_loop(self.ctx)
        # Config universes in sync
        self._assert_universe_sync(desired_config, current_config,
                                   tenants=[tn1.root])
        self._assert_reset_consistency()
        # Detele the only managed item
        self.aim_manager.delete(self.ctx, bd1)
        # Delete on ACI
        agent._daemon_loop(self.ctx)
        # Feedback loop
        self._observe_aci_events(current_config)
        # Observe
        agent._daemon_loop(self.ctx)
        # Delete the tenant on AIM, agents should stop watching it
        self.aim_manager.delete(self.ctx, tn1)
        # This loop will have a consensus for deleting Tenant tn1
        agent._daemon_loop(self.ctx)
        # Agent will not serve such tenant anymore
        agent._daemon_loop(self.ctx)
        self.assertTrue(tn1.rn not in desired_monitor.serving_tenants)

    def test_monitored_tree_relationship(self):
        # Set retry to 1 to cause immediate creation surrender
        self.set_override('max_operation_retry', 1, 'aim')
        agent = self._create_agent()
        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']

        desired_monitor = agent.multiverse[2]['desired']
        current_monitor = agent.multiverse[2]['current']

        tenant_name = 'test_monitored_tree_relationship'
        self.assertEqual({}, desired_monitor.aci_session._data_stash)
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete

        tn1 = resource.Tenant(name=tenant_name)
        # Create tenant in AIM to start serving it
        self.aim_manager.create(self.ctx, tn1)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        # Create a BD manually on this tenant
        aci_bd = self._get_example_aci_bd(
            tenant_name=tenant_name, name='mybd',
            dn='uni/tn-%s/BD-mybd' % tenant_name,
            limitIpLearnToSubnets='yes')
        self._set_events(
            [aci_bd], manager=desired_monitor.serving_tenants[tn1.rn],
            tag=False)
        self._observe_aci_events(current_config)
        # Reconcile
        agent._daemon_loop(self.ctx)
        # Create a managed subnet in the BD
        sub = resource.Subnet(tenant_name=tenant_name, bd_name='mybd',
                              gw_ip_mask='10.10.10.1/28')
        self.aim_manager.create(self.ctx, sub)
        bd = resource.BridgeDomain(name='mybd', tenant_name=tenant_name)
        bd = self.aim_manager.get(self.ctx, bd)
        self.assertTrue(bd.limit_ip_learn_to_subnets)
        self.assertTrue(bd.monitored)
        # Observe
        self._observe_aci_events(current_config)
        # Reconcile
        agent._daemon_loop(self.ctx)
        # Observe
        self._observe_aci_events(current_config)
        agent._daemon_loop(self.ctx)
        # Verify all trees converged
        self._assert_universe_sync(desired_config, current_config,
                                   tenants=[tn1.root])
        self._assert_universe_sync(desired_monitor, current_monitor,
                                   tenants=[tn1.root])
        self._assert_reset_consistency()
        # Delete the ACI BD manually
        aci_bd['fvBD']['attributes']['status'] = 'deleted'
        self._set_events(
            [aci_bd], manager=desired_monitor.serving_tenants[tn1.rn],
            tag=False)
        # Observe
        self._observe_aci_events(current_config)
        # Reconcile
        agent._daemon_loop(self.ctx)
        # Observe
        self._observe_aci_events(current_config)
        agent._daemon_loop(self.ctx)
        # Verify sync status of BD
        if self.ctx.store.supports_foreign_keys:
            bd = self.aim_manager.get(self.ctx, bd)
            bd_status = self.aim_manager.get_status(self.ctx, bd)
            self.assertEqual(aim_status.AciStatus.SYNC_FAILED,
                             bd_status.sync_status)
            self.assertNotEqual('', bd_status.sync_message)
        else:
            self.assertIsNone(self.aim_manager.get(self.ctx, bd))
        # Same for subnet
        sub = self.aim_manager.get(self.ctx, sub)
        sub_status = self.aim_manager.get_status(self.ctx, sub)
        self.assertEqual(aim_status.AciStatus.SYNC_FAILED,
                         sub_status.sync_status)
        self.assertNotEqual('', sub_status.sync_message)
        # Verify all tree converged
        self._assert_universe_sync(desired_config, current_config,
                                   tenants=[tn1.root])
        self._assert_universe_sync(desired_monitor, current_monitor,
                                   tenants=[tn1.root])
        self._assert_reset_consistency()

    def test_monitored_tree_rs_objects(self):
        """Verify that RS objects can be synced for monitored objects

        :return:
        """
        agent = self._create_agent()

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']

        desired_monitor = agent.multiverse[2]['desired']
        current_monitor = agent.multiverse[2]['current']

        tenant_name = 'test_monitored_tree_rs_objects'
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)

        tn1 = resource.Tenant(name=tenant_name)
        # Create tenant in AIM to start serving it
        self.aim_manager.create(self.ctx, tn1)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        # Create a BD manually on this tenant
        aci_l3o = self._get_example_aci_l3_out(
            dn='uni/tn-%s/out-default' % tenant_name, name='default')
        aci_ext_net = self._get_example_aci_ext_net(
            dn='uni/tn-%s/out-default/instP-extnet' % tenant_name)
        aci_ext_net_rs_prov = self._get_example_aci_ext_net_rs_prov(
            dn='uni/tn-%s/out-default/instP-extnet/'
               'rsprov-default' % tenant_name)
        self._set_events(
            [aci_l3o, aci_ext_net, aci_ext_net_rs_prov],
            manager=desired_monitor.serving_tenants[tn1.rn], tag=False)
        self._observe_aci_events(current_config)
        # Reconcile
        agent._daemon_loop(self.ctx)
        # Verify AIM ext net doesn't have contracts set
        ext_net = resource.ExternalNetwork(
            tenant_name=tenant_name, name='extnet', l3out_name='default')
        ext_net = self.aim_manager.get(self.ctx, ext_net)
        self.assertEqual([], ext_net.provided_contract_names)
        self.assertEqual([], ext_net.consumed_contract_names)
        self._observe_aci_events(current_config)
        # Observe
        agent._daemon_loop(self.ctx)

        self._assert_universe_sync(desired_monitor, current_monitor,
                                   tenants=[tn1.root])
        self._assert_universe_sync(desired_config, current_config,
                                   tenants=[tn1.root])
        self._assert_reset_consistency()
        # Update ext_net to provide some contract
        self.aim_manager.update(self.ctx, ext_net,
                                provided_contract_names=['c1'])
        # Reconcile
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        # Observe
        agent._daemon_loop(self.ctx)
        ext_net = self.aim_manager.get(self.ctx, ext_net)
        self.assertEqual(['c1'], ext_net.provided_contract_names)
        # Verify contract is provided in ACI
        prov = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn1.rn].aci_session,
            'mo/uni/tn-%s/out-default/instP-extnet/rsprov-c1' % tenant_name)
        self.assertIsNotNone(prov[0])
        # Also its tag exists
        prov_tag = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn1.rn].aci_session,
            'mo/uni/tn-%s/out-default/instP-extnet/rsprov-c1/'
            'tag-openstack_aid' % tenant_name)
        self.assertIsNotNone(prov_tag[0])
        # Old contract still exists
        prov_def = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn1.rn].aci_session,
            'mo/uni/tn-%s/out-default/instP-extnet/rsprov-default' %
            tenant_name)
        self.assertIsNotNone(prov_def[0])
        # Verify all tree converged
        self._assert_universe_sync(desired_monitor, current_monitor,
                                   tenants=[tn1.root])
        self._assert_universe_sync(desired_config, current_config,
                                   tenants=[tn1.root])
        self._assert_reset_consistency()

    def test_daemon_loop(self):
        agent = self._create_agent()
        agent._daemon_loop = run_once_loop(agent)
        # Calling the first time with a reconcile event, still calls serve=True
        agent.events.q.put_nowait('reconcile')
        agent.daemon_loop()
        # Called 2 times with 2 arguments each time
        self.assertEqual(4, len(agent._run_arguments))
        # Served new tenants
        self.assertTrue(agent._run_arguments[1])
        self.assertFalse(agent._run_arguments[3])

        # Call again with serve event
        agent.run_daemon_loop = True
        agent.events.q.put_nowait('reconcile')
        agent.events.q.put_nowait('serve')
        agent.daemon_loop()
        self.assertEqual(8, len(agent._run_arguments))
        self.assertTrue(agent._run_arguments[5])
        self.assertTrue(agent._run_arguments[7])

    def test_manual_rs(self):
        agent = self._create_agent()
        tenant_name = 'test_manual_rs'

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']
        current_monitor = agent.multiverse[2]['current']
        desired_monitor = agent.multiverse[2]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete
        # start by managing a single tenant (non-monitored)
        tn = resource.Tenant(name=tenant_name)
        self.aim_manager.create(self.ctx, tn)
        # Create a APP profile in such tenant
        self.aim_manager.create(
            self.ctx, resource.ApplicationProfile(
                tenant_name=tenant_name, name='app'))
        # Create an EPG
        epg = resource.EndpointGroup(
            tenant_name=tenant_name, app_profile_name='app', name='epg')
        self.aim_manager.create(self.ctx, epg)
        # Add 2 contracts
        self.aim_manager.create(
            self.ctx, resource.Contract(
                tenant_name=tenant_name, name='c1'))
        self.aim_manager.create(
            self.ctx, resource.Contract(
                tenant_name=tenant_name, name='c2'))
        # Serve
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        # Reconcile
        agent._daemon_loop(self.ctx)
        # Verify everything is fine
        self._assert_universe_sync(desired_monitor, current_monitor,
                                   tenants=[tn.root])
        self._assert_universe_sync(desired_config, current_config,
                                   tenants=[tn.root])
        self._assert_reset_consistency()

        # Now add a contract to the EPG through AIM
        self.aim_manager.update(self.ctx, epg, provided_contract_names=['c1'])

        # Observe, Reconcile, Verify
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        agent._daemon_loop(self.ctx)
        self._assert_universe_sync(desired_monitor, current_monitor,
                                   tenants=[tn.root])
        self._assert_universe_sync(desired_config, current_config,
                                   tenants=[tn.root])
        self._assert_reset_consistency()

        # Add the contract manually (should be removed)

        aci_contract_rs = {
            "fvRsProv": {
                "attributes": {
                    "dn": "uni/tn-%s/ap-%s/epg-%s/rsprov-%s" % (
                        tenant_name, 'app', 'epg', 'c2'),
                    "status": "created",
                    "tnVzBrCPName": "c2"
                }
            }
        }
        self._set_events(
            [aci_contract_rs],
            manager=desired_monitor.serving_tenants[tn.rn], tag=False)
        self._observe_aci_events(current_config)
        # Observe, Reconcile, Verify
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        agent._daemon_loop(self.ctx)
        self._assert_universe_sync(desired_monitor, current_monitor,
                                   tenants=[tn.root])
        self._assert_universe_sync(desired_config, current_config,
                                   tenants=[tn.root])
        self._assert_reset_consistency()

        # C2 RS is not to be found
        self.assertRaises(
            apic_client.cexc.ApicResponseNotOk, test_aci_tenant.mock_get_data,
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + aci_contract_rs['fvRsProv']['attributes']['dn'])

    def test_monitored_state_change(self):
        agent = self._create_agent()
        tenant_name = 'test_monitored_state_change'

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']
        current_monitor = agent.multiverse[2]['current']
        desired_monitor = agent.multiverse[2]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete
        tn = resource.Tenant(name=tenant_name, monitored=True)
        # Create tenant in AIM to start serving it
        self.aim_manager.create(self.ctx, tn)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        # Create some manual stuff
        aci_tn = self._get_example_aci_tenant(
            name=tenant_name, dn='uni/tn-%s' % tenant_name)
        aci_ap = self._get_example_aci_app_profile(
            dn='uni/tn-%s/ap-ap1' % tenant_name, name='ap1')
        aci_epg = self._get_example_aci_epg(
            dn='uni/tn-%s/ap-ap1/epg-epg1' % tenant_name)
        aci_contract = self._get_example_aci_contract(
            dn='uni/tn-%s/brc-c' % tenant_name)
        aci_prov_contract = self._get_example_provided_contract(
            dn='uni/tn-%s/ap-ap1/epg-epg1/rsprov-c' % tenant_name)

        self._set_events(
            [aci_tn, aci_ap, aci_epg, aci_contract, aci_prov_contract],
            manager=desired_monitor.serving_tenants[tn.rn], tag=False)

        self._sync_and_verify(agent, current_config,
                              [(current_config, desired_config),
                               (current_monitor, desired_monitor)],
                              tenants=[tn.root])
        # retrieve the corresponding AIM objects
        ap = self.aim_manager.get(self.ctx, resource.ApplicationProfile(
            tenant_name=tenant_name, name='ap1'))
        epg = self.aim_manager.get(self.ctx, resource.EndpointGroup(
            tenant_name=tenant_name, app_profile_name='ap1', name='epg1'))
        contract = self.aim_manager.get(self.ctx, resource.Contract(
            tenant_name=tenant_name, name='c'))
        self.assertTrue(bool(ap.monitored and epg.monitored and
                             contract.monitored))
        self.assertEqual(['c'], epg.provided_contract_names)

        # Now take control of the EPG
        self.aim_manager.update(self.ctx, epg, monitored=False)
        epg = self.aim_manager.get(self.ctx, resource.EndpointGroup(
            tenant_name=tenant_name, app_profile_name='ap1', name='epg1'))
        self.assertFalse(epg.monitored)
        # We keep and own the contracts
        self.assertEqual(['c'], epg.provided_contract_names)
        self._sync_and_verify(agent, current_config,
                              [(desired_config, current_config),
                               (desired_monitor, current_monitor)],
                              tenants=[tn.root])
        # Tag exists in ACI
        tag = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + epg.dn + '/tag-openstack_aid')
        self.assertIsNotNone(tag)
        tag = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + epg.dn + '/rsprov-c/tag-openstack_aid')
        self.assertIsNotNone(tag)
        # Run an empty change on the EPG, bringing it to sync pending
        self.aim_manager.update(self.ctx, epg)
        self._sync_and_verify(agent, current_config,
                              [(desired_config, current_config),
                               (desired_monitor, current_monitor)],
                              tenants=[tn.root])
        # Put back EPG into monitored state
        epg = self.aim_manager.update(self.ctx, epg, monitored=True)
        self.assertTrue(epg.monitored)
        self._sync_and_verify(agent, current_config,
                              [(desired_config, current_config),
                               (desired_monitor, current_monitor)],
                              tenants=[tn.root])
        # Tag doesn't exist anymore
        self.assertRaises(
            apic_client.cexc.ApicResponseNotOk, test_aci_tenant.mock_get_data,
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + epg.dn + '/rsprov-c/tag-openstack_aid')
        self.assertRaises(
            apic_client.cexc.ApicResponseNotOk, test_aci_tenant.mock_get_data,
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + epg.dn + '/tag-openstack_aid')
        # Object is in monitored universe and in good shape
        epg = self.aim_manager.get(self.ctx, epg)
        self.assertTrue(epg.monitored)
        # Still keeping whatever contract we had, but monitored this time
        self.assertEqual(['c'], epg.provided_contract_names)
        status = self.aim_manager.get_status(self.ctx, epg)
        self.assertEqual(status.SYNCED, status.sync_status)

    @base.requires(['foreign_keys'])
    def test_no_nat_strategy_lifecycle(self):
        """Test ownership changes made by no-NAT strategy."""
        agent = self._create_agent()
        tenant_name = 'test_no_nat_strategy_lifecycle'

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']
        desired_config.max_create_retry = float("inf")
        current_monitor = agent.multiverse[2]['current']
        desired_monitor = agent.multiverse[2]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete

        tn = resource.Tenant(name=tenant_name, monitored=True)
        self.aim_manager.create(self.ctx, tn)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)

        # simulate pre-existing VRF, L3Out and ExternalNetwork
        aci_tn = self._get_example_aci_tenant(
            name=tenant_name, dn='uni/tn-%s' % tenant_name)
        aci_vrf = self._get_example_aci_vrf(
            dn='uni/tn-%s/ctx-shared' % tenant_name, name='shared')
        aci_l3out = {'l3extOut':
                     {'attributes':
                      {'dn': 'uni/tn-%s/out-l3out' % tenant_name,
                       'name': 'l3out'}}}
        aci_ctxRs = {'l3extRsEctx':
                     {'attributes':
                      {'dn': 'uni/tn-%s/out-l3out/rsectx' % tenant_name,
                       'tnFvCtxName': 'shared'}}}
        aci_instP = {'l3extInstP':
                     {'attributes':
                      {'dn': 'uni/tn-%s/out-l3out/instP-inet' % tenant_name,
                       'name': 'inet'}}}
        self._set_events(
            [aci_tn, aci_vrf, aci_l3out, aci_ctxRs, aci_instP],
            manager=desired_monitor.serving_tenants[tn.rn], tag=False)
        self._sync_and_verify(agent, current_config,
                              [(desired_config, current_config),
                               (desired_monitor, current_monitor)],
                              tenants=[tn.root])
        # retrieve the corresponding AIM objects
        l3out = self.aim_manager.get(self.ctx, resource.L3Outside(
            tenant_name=tenant_name, name='l3out'))
        ext_net = self.aim_manager.get(self.ctx, resource.ExternalNetwork(
            tenant_name=tenant_name, l3out_name='l3out', name='inet'))
        self.assertTrue(bool(l3out.monitored and ext_net.monitored))

        ns = nat_strategy.NoNatStrategy(self.aim_manager)
        # Start using L3out from NAT strategy -> take ownership
        ns.create_l3outside(self.ctx, l3out)
        ns.create_external_network(self.ctx, ext_net)

        l3out = self.aim_manager.get(self.ctx, resource.L3Outside(
            tenant_name=tenant_name, name='l3out'))
        self.assertFalse(l3out.monitored)
        self._sync_and_verify(agent, current_config,
                              [(desired_config, current_config),
                               (desired_monitor, current_monitor)],
                              tenants=[tn.root])
        tag = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + l3out.dn + '/tag-openstack_aid')
        self.assertIsNotNone(tag)
        tag = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + l3out.dn + '/rsectx/tag-openstack_aid')
        self.assertIsNotNone(tag)

        # Use l3out with VRF
        vrf1 = resource.VRF(tenant_name=tenant_name, name='foo')
        self.aim_manager.create(self.ctx, vrf1)
        ns.connect_vrf(self.ctx, ext_net, vrf1)
        self._sync_and_verify(agent, current_config,
                              [(desired_config, current_config),
                               (desired_monitor, current_monitor)],
                              tenants=[tn.root])
        tag = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + l3out.dn + '/rsectx/tag-openstack_aid')
        self.assertIsNotNone(tag)
        ctxRs = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + l3out.dn + '/rsectx')
        self.assertEqual('foo',
                         ctxRs[0].values()[0]['attributes']['tnFvCtxName'])

        # Disconnect VRF
        ns.disconnect_vrf(self.ctx, ext_net, vrf1)
        self._sync_and_verify(agent, current_config,
                              [(desired_config, current_config),
                               (desired_monitor, current_monitor)],
                              tenants=[tn.root])
        tag = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + l3out.dn + '/rsectx/tag-openstack_aid')
        self.assertIsNotNone(tag)
        ctxRs = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + l3out.dn + '/rsectx')
        self.assertEqual('shared',
                         ctxRs[0].values()[0]['attributes']['tnFvCtxName'])

        # Stop using L3Out -> give back ownership
        ns.delete_l3outside(self.ctx, l3out)
        l3out = self.aim_manager.get(self.ctx, resource.L3Outside(
            tenant_name=tenant_name, name='l3out'))
        self.assertTrue(l3out.monitored)
        # Given the order in which the universes are processed, removing
        # ownership of an AIM resource needs an extra AID iteration. More
        # specifically, the first iteration will delete the Tags from ACI
        # which then needs to send back an event in order for the Monitored
        # universe to eventually sync up.
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        self._sync_and_verify(agent, current_config,
                              [(desired_config, current_config),
                               (desired_monitor, current_monitor)],
                              tenants=[tn.root])
        ctxRs = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + l3out.dn + '/rsectx')
        self.assertIsNotNone(ctxRs)
        self.assertRaises(
            apic_client.cexc.ApicResponseNotOk, test_aci_tenant.mock_get_data,
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + l3out.dn + '/tag-openstack_aid')
        self.assertRaises(
            apic_client.cexc.ApicResponseNotOk, test_aci_tenant.mock_get_data,
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + l3out.dn + '/rsectx/tag-openstack_aid')

    def test_monitored_l3out_vrf_rs(self):
        agent = self._create_agent()
        tenant_name = 'test_monitored_l3out_vrf_rs'

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']
        current_monitor = agent.multiverse[2]['current']
        desired_monitor = agent.multiverse[2]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete
        tn = resource.Tenant(name=tenant_name, monitored=True)
        # Create tenant in AIM to start serving it
        self.aim_manager.create(self.ctx, tn)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        # Create some manual stuff
        aci_tn = self._get_example_aci_tenant(
            name=tenant_name, dn='uni/tn-%s' % tenant_name)
        aci_l3o = self._get_example_aci_l3_out(
            dn='uni/tn-%s/out-out' % tenant_name, name='out')
        aci_l3o_vrf_rs = self._get_example_aci_l3_out_vrf_rs(
            dn='uni/tn-%s/out-out/rsectx' % tenant_name, tnFvCtxName='foo')

        self._set_events(
            [aci_tn, aci_l3o, aci_l3o_vrf_rs],
            manager=desired_monitor.serving_tenants[tn.rn], tag=False)

        self._sync_and_verify(agent, current_config,
                              [(current_config, desired_config),
                               (current_monitor, desired_monitor)],
                              tenants=[tn.root])
        l3o = self.aim_manager.get(self.ctx, resource.L3Outside(
            tenant_name=tenant_name, name='out'))
        self.assertIsNotNone(l3o)
        self.assertTrue(l3o.monitored)
        self.assertEqual('foo', l3o.vrf_name)

    def test_monitored_ext_net_contract_rs(self):
        agent = self._create_agent()
        tenant_name = 'test_monitored_ext_net_contract_rs'

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']
        current_monitor = agent.multiverse[2]['current']
        desired_monitor = agent.multiverse[2]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete
        tn = resource.Tenant(name=tenant_name, monitored=True)
        # Create tenant in AIM to start serving it
        self.aim_manager.create(self.ctx, tn)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        # Create some manual stuff
        aci_tn = self._get_example_aci_tenant(
            name=tenant_name, dn='uni/tn-%s' % tenant_name)
        aci_l3o = self._get_example_aci_l3_out(
            dn='uni/tn-%s/out-out' % tenant_name, name='out')
        aci_ext_net = {'l3extInstP':
                       {'attributes':
                        {'dn': 'uni/tn-%s/out-out/instP-inet' % tenant_name,
                         'name': 'inet'}}}

        self._set_events(
            [aci_tn, aci_l3o, aci_ext_net],
            manager=desired_monitor.serving_tenants[tn.rn], tag=False)

        self._sync_and_verify(agent, current_config,
                              [(current_config, desired_config),
                               (current_monitor, desired_monitor)],
                              tenants=[tn.root])
        ext_net = self.aim_manager.get(self.ctx, resource.ExternalNetwork(
            tenant_name=tenant_name, l3out_name='out', name='inet'))
        self.assertIsNotNone(ext_net)
        self.assertTrue(ext_net.monitored)
        self.assertEqual([], ext_net.provided_contract_names)

        self.aim_manager.update(self.ctx, ext_net,
                                provided_contract_names=['p1'])
        ext_net = self.aim_manager.get(self.ctx, ext_net)
        self.assertEqual(['p1'], ext_net.provided_contract_names)

        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        tag = test_aci_tenant.mock_get_data(
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + ext_net.dn + '/rsprov-p1/tag-openstack_aid')
        self.assertIsNotNone(tag)

        self.aim_manager.update(self.ctx, ext_net,
                                provided_contract_names=[])
        ext_net = self.aim_manager.get(self.ctx, ext_net)
        self.assertEqual([], ext_net.provided_contract_names)
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(current_config)
        self.assertRaises(
            apic_client.cexc.ApicResponseNotOk,
            test_aci_tenant.mock_get_data,
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + ext_net.dn + '/rsprov-p1')
        self.assertRaises(
            apic_client.cexc.ApicResponseNotOk,
            test_aci_tenant.mock_get_data,
            desired_monitor.serving_tenants[tn.rn].aci_session,
            'mo/' + ext_net.dn + '/rsprov-p1/tag-openstack_aid')

    def test_aci_errors(self):
        self.set_override('max_operation_retry', 2, 'aim')
        self.set_override('retry_cooldown', -1, 'aim')
        agent = self._create_agent()
        tenant_name = 'test_manual_rs'
        current_config = agent.multiverse[0]['current']
        tn = resource.Tenant(name=tenant_name)
        tn = self.aim_manager.create(self.ctx, tn)
        # Serve tenant
        agent._daemon_loop(self.ctx)
        # Try to create the tenant in multiple iterations and test different
        # errors
        with mock.patch.object(utils, 'perform_harakiri') as harakiri:
            # OPERATION_CRITICAL (fail object immediately)
            apic_client.ApicSession.post_body_dict = mock.Mock(
                side_effect=aexc.ApicResponseNotOk(
                    request='', status='400', reason='',
                    err_text='', err_code='122'))
            # Observe and Reconcile
            self._observe_aci_events(current_config)
            agent._daemon_loop(self.ctx)
            # Tenant object should be in sync_error state
            self.assertEqual(
                aim_status.AciStatus.SYNC_FAILED,
                self.aim_manager.get_status(self.ctx, tn).sync_status)
            # Put tenant back in pending state
            self.aim_manager.update(self.ctx, tn)
            agent._daemon_loop(self.ctx)

            # OPERATION_TRANSIENT (fail object after max retries)
            apic_client.ApicSession.post_body_dict = mock.Mock(
                side_effect=aexc.ApicResponseNotOk(
                    request='', status='400', reason='',
                    err_text='', err_code='102'))
            # Observe and Reconcile
            self._observe_aci_events(current_config)
            agent._daemon_loop(self.ctx)
            # Tenant is still in SYNC_PENDING state
            self.assertEqual(
                aim_status.AciStatus.SYNC_PENDING,
                self.aim_manager.get_status(self.ctx, tn).sync_status)
            # Another tentative, however, will fail the object
            self._observe_aci_events(current_config)
            agent._daemon_loop(self.ctx)
            # Tenant is still in SYNC_PENDING state
            self.assertEqual(
                aim_status.AciStatus.SYNC_FAILED,
                self.aim_manager.get_status(self.ctx, tn).sync_status)
            # Put tenant back in pending state
            self.aim_manager.update(self.ctx, tn)

            # SYSTEM_TRANSIENT (never fail the object)
            apic_client.ApicSession.post_body_dict = mock.Mock(
                side_effect=rexc.Timeout())
            # This will not fail the object
            for x in range(3):
                # Observe and Reconcile
                self._observe_aci_events(current_config)
                agent._daemon_loop(self.ctx)
                # Tenant is still in SYNC_PENDING state
                self.assertEqual(
                    aim_status.AciStatus.SYNC_PENDING,
                    self.aim_manager.get_status(self.ctx, tn).sync_status)

            # SYSTEM_CRITICAL perform harakiri
            apic_client.ApicSession.post_body_dict = mock.Mock(
                side_effect=aexc.ApicResponseNoCookie(request=''))
            self.assertEqual(0, harakiri.call_count)
            self._observe_aci_events(current_config)
            agent._daemon_loop(self.ctx)
            self.assertEqual(1, harakiri.call_count)

            # UNKNOWN (fail after max retries)
            apic_client.ApicSession.post_body_dict = mock.Mock(
                side_effect=Exception())
            # Observe and Reconcile
            self._observe_aci_events(current_config)
            agent._daemon_loop(self.ctx)
            # Tenant is still in SYNC_PENDING state
            self.assertEqual(
                aim_status.AciStatus.SYNC_PENDING,
                self.aim_manager.get_status(self.ctx, tn).sync_status)
            # Another tentative, however, will fail the object
            self._observe_aci_events(current_config)
            agent._daemon_loop(self.ctx)
            # Tenant is still in SYNC_PENDING state
            self.assertEqual(
                aim_status.AciStatus.SYNC_FAILED,
                self.aim_manager.get_status(self.ctx, tn).sync_status)

    @base.requires(['hooks'])
    def test_multi_context_session(self):
        tenant_name = 'test_transaction'
        tenant_name2 = 'test_transaction2'
        self.aim_manager.create(self.ctx, resource.Tenant(name=tenant_name))
        ctx1 = context.AimContext(self.ctx.db_session)
        self.aim_manager.create(ctx1, resource.Tenant(name=tenant_name2))

    def test_non_tenant_roots(self):
        agent = self._create_agent()
        vmm = resource.VMMDomain(type='OpenStack', name='ostack')
        vmmp = resource.VMMPolicy(type='OpenStack')
        phys = resource.PhysicalDomain(name='physdomain')
        topology = resource.Topology()
        pod = resource.Pod(name='1')
        self.aim_manager.create(self.ctx, vmmp)
        self.aim_manager.create(self.ctx, vmm)
        self.aim_manager.create(self.ctx, phys)
        self.aim_manager.create(self.ctx, topology)
        self.aim_manager.create(self.ctx, pod)

        current_config = agent.multiverse[0]['current']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        # Run loop for serving tenant
        agent._daemon_loop(self.ctx)
        pod_parent = {
            'fabricTopology': {'attributes': {'dn': 'topology'}}}
        self._set_events(
            [pod_parent], manager=current_config.serving_tenants[topology.rn],
            tag=False)
        self._observe_aci_events(current_config)

        vmm = test_aci_tenant.mock_get_data(
            current_config.serving_tenants['vmmp-OpenStack'].aci_session,
            'mo/' + vmm.dn)
        self.assertIsNotNone(vmm)
        phys = test_aci_tenant.mock_get_data(
            current_config.serving_tenants[phys.rn].aci_session,
            'mo/' + phys.dn)
        self.assertIsNotNone(phys)
        self.assertEqual('topology/pod-1', pod.dn)
        pod = test_aci_tenant.mock_get_data(
            current_config.serving_tenants[topology.rn].aci_session,
            'mo/' + pod.dn)
        self.assertIsNotNone(pod)

    def test_non_rs_nested_objects(self):
        agent = self._create_agent()
        tenant_name = 'test_non_rs_nested_objects'

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']
        current_monitor = agent.multiverse[2]['current']
        desired_monitor = agent.multiverse[2]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        apic_client.ApicSession.DELETE = self._mock_current_manager_delete
        tn = resource.Tenant(name=tenant_name)
        tn = self.aim_manager.create(self.ctx, tn)
        # Serve tenant
        agent._daemon_loop(self.ctx)
        self._sync_and_verify(agent, current_config,
                              [(current_config, desired_config),
                               (current_monitor, desired_monitor)],
                              tenants=[tn.root])
        # Create SRP parent
        srp_parent = {
            'vnsSvcCont': {
                'attributes': {'dn': 'uni/tn-%s/svcCont' % tenant_name}}}
        self._set_events(
            [srp_parent], manager=current_config.serving_tenants[tn.rn],
            tag=False)
        self._sync_and_verify(agent, current_config,
                              [(current_config, desired_config),
                               (current_monitor, desired_monitor)],
                              tenants=[tn.root])
        srp = service_graph.ServiceRedirectPolicy(
            tenant_name=tenant_name, name='name')
        self.aim_manager.create(self.ctx, srp)
        self._sync_and_verify(agent, current_config,
                              [(current_config, desired_config),
                               (current_monitor, desired_monitor)],
                              tenants=[tn.root])
        # Create dest policy
        self.aim_manager.update(self.ctx, srp,
                                destinations=[{'ip': '1.1.1.1',
                                               'mac': 'aa:aa:aa:aa:aa'}])
        self._sync_and_verify(agent, current_config,
                              [(current_config, desired_config),
                               (current_monitor, desired_monitor)],
                              tenants=[tn.root])
        dest = test_aci_tenant.mock_get_data(
            current_config.serving_tenants[tn.rn].aci_session,
            'mo/' + srp.dn + '/RedirectDest_ip-[1.1.1.1]')
        self.assertIsNotNone(dest)
        # Create one manually
        aci_dst = {
            'vnsRedirectDest': {
                'attributes': {'dn': srp.dn + '/RedirectDest_ip-[1.1.1.2]',
                               'ip': '1.1.1.2', 'mac': 'aa:aa:aa:aa:ab'}}}
        self._set_events(
            [aci_dst], manager=current_config.serving_tenants[tn.rn],
            tag=False)
        self._observe_aci_events(current_config)
        self._sync_and_verify(agent, current_config,
                              [(current_config, desired_config),
                               (current_monitor, desired_monitor)],
                              tenants=[tn.root])
        # Dest deleted
        self.assertRaises(
            apic_client.cexc.ApicResponseNotOk,
            test_aci_tenant.mock_get_data,
            current_config.serving_tenants[tn.rn].aci_session,
            'mo/' + srp.dn + '/RedirectDest_ip-[1.1.1.2]')
        self._sync_and_verify(agent, current_config,
                              [(current_config, desired_config),
                               (current_monitor, desired_monitor)],
                              tenants=[tn.root])

    def test_monitored_objects_sync_state(self):
        agent = self._create_agent()
        tenant_name = 'test_monitored_objects_sync_state'

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        tn = resource.Tenant(name=tenant_name, monitored=True)
        tn = self.aim_manager.create(self.ctx, tn)
        tenants = agent._calculate_tenants(self.ctx)
        current_config.serve(tenants)
        desired_config.serve(tenants)
        tenant = {
            'fvTenant': {
                'attributes': {'dn': 'uni/tn-%s' % tenant_name,
                               'nameAlias': 'test'}}}
        self._set_events(
            [tenant], manager=current_config.serving_tenants[tn.rn],
            tag=False)
        self.aim_manager.create(self.ctx, resource.ApplicationProfile(
            tenant_name=tenant_name, name='ap-name'))
        self._observe_aci_events(current_config)
        agent._daemon_loop(self.ctx)
        self.assertEqual(aim_status.AciStatus.SYNC_NA,
                         self.aim_manager.get_status(self.ctx, tn).sync_status)
        self._observe_aci_events(current_config)
        agent._daemon_loop(self.ctx)
        self.assertEqual(aim_status.AciStatus.SYNCED,
                         self.aim_manager.get_status(self.ctx, tn).sync_status)

    @base.requires(['k8s'])
    def test_k8s_node_faults(self):
        agent = self._create_agent()

        desired_oper = agent.multiverse[1]['desired']
        apic_client.ApicSession.post_body_dict = (
            self._mock_current_manager_post)
        vmm = resource.VMMDomain(type='Kubernetes', name='kubernetes',
                                 monitored=True)
        self.aim_manager.create(self.ctx, vmm)
        agent._daemon_loop(self.ctx)
        f1 = aim_status.AciFault(
            fault_code='F609007',
            external_identifier='uni/vmmp-Kubernetes/dom-kubernetes/'
                                'ctrlr-kubernetes/injcont/ns-[default]/'
                                'svc-[frontend]/p-http-prot-tcp-t-80/'
                                'fault-F609007')
        self.assertIsNotNone(self.aim_manager.create(self.ctx, f1))
        # see if it gets deleted
        self._observe_aci_events(desired_oper)
        agent._daemon_loop(self.ctx)
        self.assertIsNone(self.aim_manager.get(self.ctx, f1))

    def _observe_aci_events(self, aci_universe):
        for tenant in aci_universe.serving_tenants.values():
            self._current_manager = tenant
            tenant._event_loop()

    def _assert_universe_sync(self, desired, current, tenants=None):

        def printable_state(universe):
            return json.dumps({x: y.root.to_dict() if y.root else {}
                               for x, y in universe.state.iteritems()},
                              indent=2)
        # Because of the possible error nodes, we need to verify that the
        # diff is empty
        self.assertEqual(current.state.keys(), desired.state.keys(),
                         'Not in sync:\n current\n: %s \n\n desired\n: %s' %
                         (printable_state(current), printable_state(desired)))
        for tenant in (tenants or current.state):
            self.assertEqual(
                {"add": [], "remove": []},
                desired.state[tenant].diff(current.state[tenant]),
                'Not in sync:\n current\n: %s \n\n desired\n: %s' %
                (printable_state(current), printable_state(desired)))

    def _assert_reset_consistency(self, tenant=None):
        ctx = mock.Mock()
        ctx.obj = {'manager': self.aim_manager, 'aim_ctx': self.ctx}
        # get current tree(s)
        filters = {}
        if tenant:
            filters = {'name': tenant}
        # for each tenant, save their trees
        old = self._get_aim_trees_by_tenant(filters)

        # Now reset trees
        treecli._reset(ctx, tenant)
        # Check if they are still the same
        current = self._get_aim_trees_by_tenant(filters)
        self.assertEqual(old, current)

    def _get_aim_trees_by_tenant(self, filters):
        tenants = self.aim_manager.find(self.ctx, resource.Tenant, **filters)
        result = {}
        for tenant in tenants:
            result[tenant.name] = {}
            for type in tree_manager.SUPPORTED_TREES:
                result[tenant.name][type] = (
                    self.tt_mgr.get(self.ctx, tenant.rn, tree=type))
        return result

    def _sync_and_verify(self, agent, to_observe, couples, tenants=None):
        agent._daemon_loop(self.ctx)
        self._observe_aci_events(to_observe)
        agent._daemon_loop(self.ctx)
        # Verify everything is fine
        for couple in couples:
            self._assert_universe_sync(couple[0], couple[1], tenants=tenants)
        self._assert_reset_consistency()
