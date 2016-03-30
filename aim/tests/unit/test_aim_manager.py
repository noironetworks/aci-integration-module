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

"""
test_aim_manager
----------------------------------

Tests for `aim_manager` module.
"""

import mock
import time

from aim import aim_manager
from aim.api import resource
from aim import config  # noqa
from aim.db import tree_model  # noqa
from aim import exceptions as exc
from aim.tests import base


class TestAimManager(base.TestAimDBBase):

    def setUp(self):
        super(TestAimManager, self).setUp()
        self.mgr = aim_manager.AimManager()

    def _test_resource_ops(self, resource, test_identity_attributes,
                           test_required_attributes, test_search_attributes,
                           test_update_attributes):
        """Test basic operations for resources

        :param resource: resource type, eg: BridgeDomain
        :param test_identity_attributes: dictionary with test identity values
        eg: {'tenant_rn': 'foo', 'rn': 'bar'}
        :param test_required_attributes: dictionary with attributes required
        by the DB for successful object creation.
        :param test_search_attributes: dictionary with test search attributes,
        needs to be one/more of the resource's other_attributes suitable for
        search. eg: {'vrf_rn': 'shared'}
        :param test_update_attributes: some attributes already present in
        one of the previously specified ones that hold a different value.
        :return:
        """
        # Run the following only if ID attributes are also required
        if not (set(test_identity_attributes.keys()) -
                set(test_required_attributes.keys())):
            self.assertRaises(
                exc.IdentityAttributesMissing, resource, **{})

        # Create with identity attributes
        creation_attributes = {}
        creation_attributes.update(test_required_attributes),
        creation_attributes.update(test_identity_attributes)
        res = resource(**creation_attributes)

        # Verify successful creation
        r1 = self.mgr.create(self.ctx, res)
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr(r1, k))
        # Verify get
        r1 = self.mgr.get(self.ctx, res)
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr(r1, k))

        # Verify overwrite
        for k, v in test_search_attributes.iteritems():
            setattr(res, k, v)
        r2 = self.mgr.create(self.ctx, res, overwrite=True)

        for k, v in test_search_attributes.iteritems():
            self.assertEqual(v, getattr(r2, k))

        # Test search by identity
        rs1 = self.mgr.find(self.ctx, resource, **test_identity_attributes)
        self.assertEqual(1, len(rs1))
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr(rs1[0], k))

        # Test search by other attributes
        rs2 = self.mgr.find(self.ctx, resource, **test_search_attributes)
        self.assertEqual(1, len(rs2))
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr(rs2[0], k))

        # Test update
        r3 = self.mgr.update(self.ctx, res, **test_update_attributes)
        for k, v in test_update_attributes.iteritems():
            self.assertEqual(v, getattr(r3, k))

        # Test empty update
        r31 = self.mgr.update(self.ctx, res, **{})
        self.assertEqual(r3, r31)

        # Test delete
        self.mgr.delete(self.ctx, res)
        self.assertIsNone(self.mgr.get(self.ctx, res))
        self.assertEqual([], self.mgr.find(self.ctx, resource))

        # Test update nonexisting object
        r4 = self.mgr.update(self.ctx, res, **{})
        self.assertIsNone(r4)
        r4 = self.mgr.update(self.ctx, res, something='foo')
        self.assertIsNone(r4)

        # Test delete nonexisting object (no error)
        self.mgr.delete(self.ctx, res)

    def test_resource_negative(self):

        class bad_resource(object):
            pass

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.create, self.ctx, bad_resource())

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.update, self.ctx, bad_resource())

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.delete, self.ctx, bad_resource())

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.get, self.ctx, bad_resource())

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.find, self.ctx, bad_resource)

    def _test_commit_hook(self, resource, test_identity_attributes,
                          test_required_attributes, test_update_attributes):
        """Test basic commit hooks for resources

        :param resource: resource type, eg: BridgeDomain
        :param test_identity_attributes: dictionary with test identity values
        eg: {'tenant_rn': 'foo', 'rn': 'bar'}
        :param test_required_attributes: dictionary with attributes required
        by the DB for successful object creation.
        :param test_search_attributes: dictionary with test search attributes,
        needs to be one/more of the resource's other_attributes suitable for
        search. eg: {'vrf_rn': 'shared'}
        :param test_update_attributes: some attributes already present in
        one of the previously specified ones that hold a different value.
        :return:
        """
        listener = mock.Mock()
        listener.__name__ = 'mock-listener'
        self.mgr.register_update_listener(listener)

        creation_attributes = {}
        creation_attributes.update(test_required_attributes),
        creation_attributes.update(test_identity_attributes)

        res = resource(**creation_attributes)
        res = self.mgr.create(self.ctx, res)
        listener.assert_called_with(mock.ANY, [res], [], [])

        listener.reset_mock()
        res = self.mgr.update(self.ctx, res, **test_update_attributes)
        listener.assert_called_with(mock.ANY, [], [res], [])

        listener.reset_mock()
        self.mgr.delete(self.ctx, res)
        listener.assert_called_with(mock.ANY, [], [], [res])

        self.mgr.unregister_update_listener(listener)

        listener.reset_mock()
        self.mgr.create(self.ctx, res)
        self.assertFalse(listener.called)

        self.mgr.delete(self.ctx, res)
        self.assertFalse(listener.called)

    def test_bridge_domain_ops(self):
        self._test_resource_ops(
            resource.BridgeDomain,
            test_identity_attributes={'tenant_rn': 'tenant1', 'rn': 'net1'},
            test_required_attributes={'tenant_rn': 'tenant1', 'rn': 'net1'},
            test_search_attributes={'l2_unknown_unicast_mode': 'proxy'},
            test_update_attributes={'l2_unknown_unicast_mode': 'private',
                                    'vrf_rn': 'default'})

    def test_bridge_domain_hooks(self):
        self._test_commit_hook(
            resource.BridgeDomain,
            test_identity_attributes={'tenant_rn': 'tenant1', 'rn': 'net1'},
            test_required_attributes={'tenant_rn': 'tenant1', 'rn': 'net1'},
            test_update_attributes={'l2_unknown_unicast_mode': 'private',
                                    'vrf_rn': 'private'})

    def test_agent_ops(self):
        self._test_resource_ops(
            resource.Agent,
            test_identity_attributes={'id': 'myuuid'},
            test_required_attributes={'agent_type': 'aid',
                                      'host': 'h1',
                                      'binary_file': 'aid.py'},
            test_search_attributes={'host': 'h1'},
            test_update_attributes={'host': 'h2'})

    def test_agent_commit_hook(self):
        self._test_commit_hook(
            resource.Agent,
            test_identity_attributes={'id': 'myuuid'},
            test_required_attributes={'agent_type': 'aid',
                                      'host': 'h1',
                                      'binary_file': 'aid.py'},
            test_update_attributes={'host': 'h2'})

    def test_agent_timestamp(self):
        agent = resource.Agent(id='myuuid', agent_type='aid', host='host',
                               binary_file='binary_file')

        # Verify successful creation
        agent = self.mgr.create(self.ctx, agent, overwrite=True)
        created = agent.created_at
        hbeat = agent.heartbeat_timestamp

        # DB side timestamp has granularity in seconds
        time.sleep(1)
        # Update and verify that timestamp changed
        agent = self.mgr.update(self.ctx, agent,
                                beat_count=agent.beat_count + 1)
        # Create didn't change
        self.assertEqual(created, agent.created_at)
        # Hbeat is updated
        self.assertTrue(hbeat < agent.heartbeat_timestamp)

    def test_agent_down(self):
        agent = resource.Agent(agent_type='aid', host='host',
                               binary_file='binary_file')
        self.assertRaises(AttributeError, agent.is_down)
        agent = self.mgr.create(self.ctx, agent)
        self.assertFalse(agent.is_down())
        config.cfg.CONF.set_override('agent_down_time', 0, 'aim')
        self.assertTrue(agent.is_down())
