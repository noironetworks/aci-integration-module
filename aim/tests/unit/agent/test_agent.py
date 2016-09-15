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
import time

from apicapi import apic_client
import mock
from oslo_db import exception

from aim.agent.aid import service
from aim.agent.aid.universes.aci import aci_universe
from aim import aim_manager
from aim.api import resource
from aim.api import status as aim_status
from aim.common.hashtree import structured_tree as tree
from aim import config
from aim.db import tree_model
from aim.tests import base
from aim.tests.unit.agent.aid_universes import test_aci_tenant


class TestAgent(base.TestAimDBBase, test_aci_tenant.TestAciClientMixin):

    def setUp(self):
        super(TestAgent, self).setUp()
        self.set_override('agent_down_time', 3600, 'aim')
        self.set_override('agent_polling_interval', 0, 'aim')
        self.set_override('aci_tenant_polling_yield', 0, 'aim')
        self.aim_manager = aim_manager.AimManager()
        self.tree_manager = tree_model.TenantTreeManager(
            tree.StructuredHashTree)
        self.old_post = apic_client.ApicSession.post_body

        self.addCleanup(self._reset_apic_client)
        self._do_aci_mocks()
        self.tenant_thread = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager._run')
        self.tenant_thread.start()

        self.thread_dead = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager.is_dead',
            return_value=False)
        self.thread_dead.start()

        self.thread_warm = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager.is_warm',
            return_value=True)
        self.thread_warm.start()

        self.thread_health = mock.patch(
            'aim.agent.aid.universes.aci.tenant.AciTenantManager.health_state',
            return_value=True)
        self.thread_health.start()

        self.addCleanup(self.tenant_thread.stop)
        self.addCleanup(self.thread_dead.stop)
        self.addCleanup(self.thread_warm.stop)
        self.addCleanup(self.thread_health.stop)

    def _reset_apic_client(self):
        apic_client.ApicSession.post_body = self.old_post

    def _mock_current_manager_post(self, mo, data, *params):
        # Each post, generates the same set of events for the WS interface
        data = json.loads(data)
        events = []
        base = 'uni'
        container = mo.container
        if container:
            base = apic_client.ManagedObjectClass(container).dn(*params[:-1])
        self._tree_to_event(data, events, base, self._current_manager)
        # Tagging is done by the tenant manager
        self._set_events(events, manager=self._current_manager, tag=False)

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
        self.set_override('host', host)
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

    def test_send_heartbeat(self):
        agent = self._create_agent()
        current_tstamp = agent.agent.heartbeat_timestamp
        time.sleep(1)
        agent._send_heartbeat()
        self.assertTrue(current_tstamp < agent.agent.heartbeat_timestamp)

    def test_calculate_tenants(self):
        # One agent, zero tenants
        agent = self._create_agent()
        result = agent._calculate_tenants(agent.context)
        self.assertEqual([], result)
        self.assertEqual([], agent.agent.hash_trees)

        # Same agent, one tenant
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        self.tree_manager.update_bulk(self.ctx, [data])
        result = agent._calculate_tenants(agent.context)
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
        result = agent._calculate_tenants(agent.context)
        # All tenants are served by this agent since he's the only one
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']), set(result))
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(agent.agent.hash_trees))

        # Multiple Agents
        agent2 = self._create_agent(host='h2')
        agent3 = self._create_agent(host='h3')
        # Recalculate
        result = agent._calculate_tenants(agent.context)
        result2 = agent2._calculate_tenants(agent2.context)
        result3 = agent3._calculate_tenants(agent3.context)
        # All the tenants must be served
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result + result2))
        self.assertNotEqual([], result)
        self.assertNotEqual([], result2)
        self.assertNotEqual([], result3)
        # Each tenant has 2 agents
        self.assertEqual(
            2, len([x for x in result + result2 + result3 if x == 'keyA']))
        self.assertEqual(
            2, len([x for x in result + result2 + result3 if x == 'keyA1']))
        self.assertEqual(
            2, len([x for x in result + result2 + result3 if x == 'keyA2']))

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
        self.aim_manager.create(agent.context, agent.agent, overwrite=True)
        result = agent._calculate_tenants(agent.context)
        result2 = agent2._calculate_tenants(agent2.context)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result2))
        # Agent one has no tenant assigned
        self.assertEqual([], result)

        # Fix agent1
        agent.agent.admin_state_up = True
        self.aim_manager.create(agent.context, agent.agent, overwrite=True)
        result = agent._calculate_tenants(agent.context)
        result2 = agent2._calculate_tenants(agent2.context)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result + result2))
        # neither agent has empty configuration
        self.assertNotEqual([], result)
        self.assertNotEqual([], result2)

        # Upgrade agent2 version
        agent2.agent.version = "2.0.0"
        self.aim_manager.create(agent2.context, agent2.agent, overwrite=True)
        result = agent._calculate_tenants(agent.context)
        result2 = agent2._calculate_tenants(agent2.context)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result2))
        # Agent one has no tenant assigned
        self.assertEqual([], result)

        # Upgrade agent1 version
        agent.agent.version = "2.0.0"
        self.aim_manager.create(agent.context, agent.agent, overwrite=True)
        result = agent._calculate_tenants(agent.context)
        result2 = agent2._calculate_tenants(agent2.context)
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
                                        vrf_name='vrf2')
        self.aim_manager.create(self.ctx, bd1_tn2)
        self.aim_manager.create(self.ctx, bd1_tn1)
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
        agent._daemon_loop()

        for tenant in agent.current_universe.serving_tenants.values():
            tenant._subscribe_tenant()
            tenant.health_state = True
        # The ACI universe will not push the configuration unless explicitly
        # called
        self.assertFalse(
            agent.current_universe.serving_tenants[tenant_name1].
            object_backlog.empty())
        self.assertFalse(
            agent.current_universe.serving_tenants[tenant_name2].
            object_backlog.empty())

        # Meanwhile, Operational state has been cleaned from AIM
        status = self.aim_manager.get_status(self.ctx, bd1_tn1)
        self.assertEqual(0, len(status.faults))

        # Events around the BD creation are now sent to the ACI universe, add
        # them to the observed tree
        apic_client.ApicSession.post_body = self._mock_current_manager_post
        for tenant in agent.current_universe.serving_tenants.values():
            self._current_manager = tenant
            tenant._event_loop()

        # Now, the two trees are in sync
        agent._daemon_loop()
        self._assert_universe_sync(agent.desired_universe,
                                   agent.current_universe)

        self.assertTrue(
            agent.current_universe.serving_tenants[tenant_name1].
            object_backlog.empty())
        self.assertTrue(
            agent.current_universe.serving_tenants[tenant_name2].
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
        agent._daemon_loop()
        self.assertIs(agent.current_universe.serving_tenants[tenant_name1],
                      currentserving_tenants[tenant_name1])
        self.assertIs(agent.current_universe.serving_tenants[tenant_name2],
                      currentserving_tenants[tenant_name2])
        # There are changes on tn1 only
        self.assertFalse(
            agent.current_universe.serving_tenants[tenant_name1].
            object_backlog.empty())
        self.assertTrue(
            agent.current_universe.serving_tenants[tenant_name2].
            object_backlog.empty())
        # Get events
        for tenant in agent.current_universe.serving_tenants.values():
            self._current_manager = tenant
            tenant._event_loop()
        agent._daemon_loop()
        # Everything is in sync again
        self._assert_universe_sync(agent.desired_universe,
                                   agent.current_universe)

        # Delete a tenant
        self.aim_manager.delete(self.ctx, bd2_tn1)
        self.aim_manager.delete(self.ctx, tn1)

        agent._daemon_loop()
        # There are changes on tn1 only
        self.assertFalse(
            agent.current_universe.serving_tenants[tenant_name1].
            object_backlog.empty())
        self.assertTrue(
            agent.current_universe.serving_tenants[tenant_name2].
            object_backlog.empty())
        self.assertIs(agent.current_universe.serving_tenants[tenant_name1],
                      currentserving_tenants[tenant_name1])
        self.assertIs(agent.current_universe.serving_tenants[tenant_name2],
                      currentserving_tenants[tenant_name2])
        # Get events
        for tenant in agent.current_universe.serving_tenants.values():
            self._current_manager = tenant
            tenant._event_loop()
        # Depending on the order of operation, we might need another
        # iteration to cleanup the tree completely
        if agent.current_universe.serving_tenants[tenant_name1]._state.root:
            agent._daemon_loop()
            for tenant in agent.current_universe.serving_tenants.values():
                self._current_manager = tenant
                tenant._event_loop()
        # Tenant still exist on AIM because observe didn't run yet
        self.assertIsNone(
            agent.current_universe.serving_tenants[tenant_name1]._state.root)
        tn1 = agent.tree_manager.find(self.ctx, tenant_rn=[tenant_name1])
        self.assertEqual(1, len(tn1))
        # Now tenant will be deleted (still served)
        agent._daemon_loop()
        self.assertIsNone(agent.current_universe.state[tenant_name1].root)
        tn1 = agent.tree_manager.find(self.ctx, tenant_rn=[tenant_name1])
        self.assertEqual(0, len(tn1))

        # Agent not served anymore
        agent._daemon_loop()
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
        apic_client.ApicSession.post_body = self._mock_current_manager_post
        # start by managing a single tenant (non-monitored)
        tn1 = resource.Tenant(name=tenant_name, monitored=True)
        aci_tn = self._get_example_aci_tenant(
            name=tenant_name, dn='uni/tn-%s' % tenant_name)
        self.aim_manager.create(self.ctx, tn1)
        # Run loop for serving tenant
        agent._daemon_loop()
        self._set_events(
            [aci_tn], manager=desired_monitor.serving_tenants[tenant_name],
            tag=False)
        self._observe_aci_events(current_config)
        # Simulate an external actor creating a BD
        aci_bd = self._get_example_aci_bd(
            tenant_name=tenant_name, name='default',
            dn='uni/tn-%s/BD-default' % tenant_name)
        self._set_events(
            [aci_bd], manager=desired_monitor.serving_tenants[tenant_name],
            tag=False)
        apic_client.ApicSession.post_body = self._mock_current_manager_post

        # Observe ACI events
        self._observe_aci_events(current_config)

        # Run the loop for reconciliation
        agent._daemon_loop()
        # A monitored BD should now exist in AIM
        aim_bd = self.aim_manager.get(self.ctx, resource.BridgeDomain(
            tenant_name=tenant_name, name='default'))
        self.assertTrue(aim_bd.monitored)
        # Trees are in sync
        self._assert_universe_sync(desired_monitor, current_monitor)

        # Delete the monitored BD, will be re-created
        self.aim_manager.delete(self.ctx, aim_bd)
        agent._daemon_loop()
        # It's reconciled
        aim_bd = self.aim_manager.get(self.ctx, resource.BridgeDomain(
            tenant_name=tenant_name, name='default'))
        self.assertTrue(aim_bd.monitored)
        # Send delete event
        aci_bd['fvBD']['attributes']['status'] = 'deleted'
        self._set_events(
            [aci_bd], manager=desired_monitor.serving_tenants[tenant_name],
            tag=False)
        # Observe ACI events
        self._observe_aci_events(current_config)
        # Run the loop for reconciliation
        agent._daemon_loop()
        # BD is deleted
        aim_bd = self.aim_manager.get(self.ctx, resource.BridgeDomain(
            tenant_name=tenant_name, name='default'))
        self.assertIsNone(aim_bd)
        self._assert_universe_sync(desired_monitor, current_monitor)

    def test_monitored_tree_fk_semantics(self):
        agent = self._create_agent()

        current_config = agent.multiverse[0]['current']
        desired_monitor = agent.multiverse[2]['desired']
        tenant_name = 'test_monitored_tree_fk_semantics'
        apic_client.ApicSession.post_body = self._mock_current_manager_post
        # start by managing a single monitored tenant
        tn1 = resource.Tenant(name=tenant_name, monitored=True)
        aci_tn = self._get_example_aci_tenant(
            name=tenant_name, dn='uni/tn-%s' % tenant_name)
        # Create tenant in AIM to start serving it
        self.aim_manager.create(self.ctx, tn1)
        # Run loop for serving tenant
        agent._daemon_loop()
        # we need this tenant to exist in ACI
        self._set_events(
            [aci_tn], manager=desired_monitor.serving_tenants[tenant_name],
            tag=False)
        # Observe ACI events
        self._observe_aci_events(current_config)
        # Create a managed BD
        bd1 = resource.BridgeDomain(name='bd1', tenant_name=tenant_name)
        self.aim_manager.create(self.ctx, bd1)
        # Make BD appear on ACI
        agent._daemon_loop()
        self._observe_aci_events(current_config)
        # Create a monitored subnet in the BD
        aci_sub = self._get_example_aci_subnet(
            dn='uni/tn-%s/BD-bd1/subnet-[10.10.10.1/28]' % tenant_name)
        self._set_events(
            [aci_sub], manager=desired_monitor.serving_tenants[tenant_name],
            tag=False)
        # Observe the event
        self._observe_aci_events(current_config)
        # Reconcile
        agent._daemon_loop()
        # Monitored sub is created
        aim_sub = resource.Subnet(tenant_name=tenant_name, bd_name='bd1',
                                  gw_ip_mask='10.10.10.1/28')
        aim_sub = self.aim_manager.get(self.ctx, aim_sub)
        self.assertTrue(aim_sub.monitored)
        # deleting the BD from aim fails because of FK
        self.assertRaises(exception.DBReferenceError, self.aim_manager.delete,
                          self.ctx, bd1)

    def test_monitored_tree_serve_semantics(self):
        agent = self._create_agent()

        current_config = agent.multiverse[0]['current']
        desired_config = agent.multiverse[0]['desired']

        desired_monitor = agent.multiverse[2]['desired']
        apic_client.ApicSession.post_body = self._mock_current_manager_post
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
        agent._daemon_loop()
        # we need this tenant to exist in ACI
        self._set_events(
            [aci_tn, aci_bd],
            manager=desired_monitor.serving_tenants[tenant_name], tag=False)
        self._observe_aci_events(current_config)
        agent._daemon_loop()
        bd1 = resource.BridgeDomain(name='bd1', tenant_name=tenant_name)
        self.aim_manager.create(self.ctx, bd1)
        # Push BD in ACI
        agent._daemon_loop()
        # Feedback loop
        self._observe_aci_events(current_config)
        # Observe
        agent._daemon_loop()
        # Config universes in sync
        self._assert_universe_sync(desired_config, current_config)
        # Detele the only managed item
        self.aim_manager.delete(self.ctx, bd1)
        # Delete on ACI
        agent._daemon_loop()
        # Feedback loop
        self._observe_aci_events(current_config)
        # Observe
        agent._daemon_loop()
        # Delete the tenant on AIM, agents should stop watching it
        self.aim_manager.delete(self.ctx, tn1)
        # This loop will have a consensus for deleting Tenant tn1
        agent._daemon_loop()
        # Agent will not serve such tenant anymore
        agent._daemon_loop()
        self.assertTrue(tenant_name not in desired_monitor.serving_tenants)

    # TODO(ivar): need to implement delete-error semantics for all the
    # universes

    # def test_monitored_tree_relationship(self):
    #    agent = self._create_agent()

    #    current_config = agent.multiverse[0]['current']
    #    desired_config = agent.multiverse[0]['desired']

    #    desired_monitor = agent.multiverse[2]['desired']
    #    current_monitor = agent.multiverse[2]['current']

    #    tenant_name = 'test_monitored_tree_relationship'
    #    self.assertEqual({}, desired_monitor.aci_session._data_stash)
    #    apic_client.ApicSession.post_body = self._mock_current_manager_post

    #    tn1 = resource.Tenant(name=tenant_name)
    #    # Create tenant in AIM to start serving it
    #    self.aim_manager.create(self.ctx, tn1)
    #    # Run loop for serving tenant
    #    agent._daemon_loop()
    #    self._observe_aci_events(current_config)
    #    # Create a BD manually on this tenant
    #    aci_bd = self._get_example_aci_bd(
    #        tenant_name=tenant_name, name='mybd',
    #        dn='uni/tn-%s/BD-mybd' % tenant_name,
    #        limitIpLearnToSubnets='yes')
    #    self._set_events(
    #        [aci_bd], manager=desired_monitor.serving_tenants[tenant_name],
    #        tag=False)
    #    self._observe_aci_events(current_config)
    #    # Reconcile
    #    agent._daemon_loop()
    #    # Create a managed subnet in the BD
    #    sub = resource.Subnet(tenant_name=tenant_name, bd_name='mybd',
    #                          gw_ip_mask='10.10.10.1/28')
    #    self.aim_manager.create(self.ctx, sub)
    #    bd = resource.BridgeDomain(name='mybd', tenant_name=tenant_name)
    #    bd = self.aim_manager.get(self.ctx, bd)
    #    self.assertTrue(bd.limit_ip_learn_to_subnets)
    #    # Delete the ACI BD manually
    #    aci_bd['fvBD']['attributes']['status'] = 'deleted'
    #    self._set_events(
    #        [aci_bd], manager=desired_monitor.serving_tenants[tenant_name],
    #        tag=False)
    #    # Observe
    #    self._observe_aci_events(current_config)
    #    # Reconcile
    #    agent._daemon_loop()
    #    # Observe
    #    self._observe_aci_events(current_config)
    #    agent._daemon_loop()
    #    # Verify all tree converged
    #    self._assert_universe_sync(desired_config, current_config)
    #    self._assert_universe_sync(desired_monitor, current_monitor)#

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
        apic_client.ApicSession.post_body = self._mock_current_manager_post

        tn1 = resource.Tenant(name=tenant_name)
        # Create tenant in AIM to start serving it
        self.aim_manager.create(self.ctx, tn1)
        # Run loop for serving tenant
        agent._daemon_loop()
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
            manager=desired_monitor.serving_tenants[tenant_name], tag=False)
        self._observe_aci_events(current_config)
        # Reconcile
        agent._daemon_loop()
        # Verify AIM ext net doesn't have contracts set
        ext_net = resource.ExternalNetwork(
            tenant_name=tenant_name, name='extnet', l3out_name='default')
        ext_net = self.aim_manager.get(self.ctx, ext_net)
        self.assertEqual([], ext_net.provided_contract_names)
        self.assertEqual([], ext_net.consumed_contract_names)
        self._observe_aci_events(current_config)
        # Observe
        agent._daemon_loop()

        self._assert_universe_sync(desired_monitor, current_monitor)
        self._assert_universe_sync(desired_config, current_config)

        # Updare ext_net to provide some contract
        self.aim_manager.update(self.ctx, ext_net,
                                provided_contract_names=['c1'])
        # Reconcile
        agent._daemon_loop()
        self._observe_aci_events(current_config)
        # Observe
        agent._daemon_loop()

        # Verify all tree converged
        self._assert_universe_sync(desired_monitor, current_monitor)
        self._assert_universe_sync(desired_config, current_config)

    def _observe_aci_events(self, aci_universe):
        for tenant in aci_universe.serving_tenants.values():
            self._current_manager = tenant
            tenant._event_loop()

    def _assert_universe_sync(self, desired, current):
        self.assertEqual(current.state, desired.state,
                         'Not in sync:\n current\n: %s \n\n desired\n: %s' %
                         ({x: str(y) for x, y in
                           current.state.iteritems()},
                          {x: str(y) for x, y in
                           desired.state.iteritems()}))
