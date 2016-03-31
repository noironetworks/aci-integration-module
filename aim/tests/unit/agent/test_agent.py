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

import time

from aim.agent.aid import service
from aim import aim_manager
from aim.api import resource
from aim.common.hashtree import structured_tree as tree
from aim import config
from aim.db import tree_model
from aim.tests import base


class TestAgent(base.TestAimDBBase):

    def setUp(self):
        super(TestAgent, self).setUp()
        self.manager = aim_manager.AimManager()
        self.tree_manager = tree_model.TREE_MANAGER

    def _create_agent(self, host='h1'):
        config.CONF.set_override('host', host)
        return service.AID(config.CONF)

    def test_init(self):
        agent = self._create_agent()
        self.assertEqual('h1', agent.host)
        # Agent is registered
        agents = self.manager.find(self.ctx, resource.Agent)
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
        self.manager.create(agent.context, agent.agent, overwrite=True)
        result = agent._calculate_tenants(agent.context)
        result2 = agent2._calculate_tenants(agent2.context)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result2))
        # Agent one has no tenant assigned
        self.assertEqual([], result)

        # Fix agent1
        agent.agent.admin_state_up = True
        self.manager.create(agent.context, agent.agent, overwrite=True)
        result = agent._calculate_tenants(agent.context)
        result2 = agent2._calculate_tenants(agent2.context)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result + result2))
        # neither agent has empty configuration
        self.assertNotEqual([], result)
        self.assertNotEqual([], result2)

        # Upgrade agent2 version
        agent2.agent.version = "2.0.0"
        self.manager.create(agent2.context, agent2.agent, overwrite=True)
        result = agent._calculate_tenants(agent.context)
        result2 = agent2._calculate_tenants(agent2.context)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result2))
        # Agent one has no tenant assigned
        self.assertEqual([], result)

        # Upgrade agent1 version
        agent.agent.version = "2.0.0"
        self.manager.create(agent.context, agent.agent, overwrite=True)
        result = agent._calculate_tenants(agent.context)
        result2 = agent2._calculate_tenants(agent2.context)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(result + result2))
        # neither agent has empty configuration
        self.assertNotEqual([], result)
        self.assertNotEqual([], result2)
