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
from aim.api import status as aim_status
from aim import config  # noqa
from aim.db import tree_model  # noqa
from aim import exceptions as exc
from aim.tests import base


def getattr_canonical(obj, attr):
    return base.sort_if_list(getattr(obj, attr))


class TestAimManager(base.TestAimDBBase):

    def setUp(self):
        super(TestAimManager, self).setUp()
        self.mgr = aim_manager.AimManager()

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

    def test_bad_aci_resource_definition(self):

        class bad_resource_1(resource.AciResourceBase):
            pass

        class bad_resource_2(bad_resource_1):
            _aci_mo_name = 'fvMagic'

        def create_obj(klass):
            return klass({})

        self.assertRaises(exc.AciResourceDefinitionError, create_obj,
                          bad_resource_1)
        self.assertRaises(exc.AciResourceDefinitionError, create_obj,
                          bad_resource_2)


class TestResourceOpsBase(object):
    test_default_values = {}
    test_dn = None
    prereq_objects = None

    def setUp(self):
        super(TestResourceOpsBase, self).setUp()
        self.mgr = aim_manager.AimManager()
        self.mgr._update_listeners = []

    def _test_resource_ops(self, resource, test_identity_attributes,
                           test_required_attributes, test_search_attributes,
                           test_update_attributes,
                           test_default_values,
                           test_dn):
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
        :param test_default_values: dictionary of default values to verify
        after object has been created
        :param test_dn: expected DN of created resource, if any.
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

        for k, v in test_default_values.iteritems():
            self.assertEqual(v, getattr_canonical(res, k))

        if test_dn:
            self.assertEqual(test_dn, res.dn)

        # Verify successful creation
        r1 = self.mgr.create(self.ctx, res)
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr_canonical(r1, k))
        # Verify get
        r1 = self.mgr.get(self.ctx, res)
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr_canonical(r1, k))

        # Verify overwrite
        for k, v in test_search_attributes.iteritems():
            setattr(res, k, v)
        r2 = self.mgr.create(self.ctx, res, overwrite=True)

        for k, v in test_search_attributes.iteritems():
            self.assertEqual(v, getattr_canonical(r2, k))

        # Test search by identity
        rs1 = self.mgr.find(self.ctx, resource, **test_identity_attributes)
        self.assertEqual(1, len(rs1))
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr_canonical(rs1[0], k))

        # Test search by other attributes
        rs2 = self.mgr.find(self.ctx, resource, **test_search_attributes)
        self.assertEqual(1, len(rs2))
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr_canonical(rs2[0], k))

        # Test update
        r3 = self.mgr.update(self.ctx, res, **test_update_attributes)
        for k, v in test_update_attributes.iteritems():
            self.assertEqual(v, getattr_canonical(r3, k))

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

    def _test_resource_status(self, resource, test_identity_attributes):
        self._create_prerequisite_objects()
        creation_attributes = {}
        creation_attributes.update(test_identity_attributes)
        res = resource(**creation_attributes)

        self.mgr.create(self.ctx, res, overwrite=True)
        status = self.mgr.get_status(self.ctx, res)
        self.assertTrue(isinstance(status, aim_status.AciStatus))
        self.assertFalse(status.is_build())
        self.assertFalse(status.is_error())

        status.sync_message = "some message"
        self.mgr.update_status(self.ctx, res, status)

        # Add a fault
        fault = aim_status.AciFault(
            fault_code='412', external_identifier='dn',
            severity=aim_status.AciFault.SEV_CRITICAL)
        self.mgr.set_fault(self.ctx, res, fault)
        status = self.mgr.get_status(self.ctx, res)
        self.assertEqual(1, len(status.faults))
        self.assertEqual(aim_status.AciFault.SEV_CRITICAL,
                         status.faults[0].severity)

        self.mgr.clear_fault(self.ctx, res, fault)
        status = self.mgr.get_status(self.ctx, res)
        self.assertEqual(0, len(status.faults))

    def _create_prerequisite_objects(self):
        for obj in (self.prereq_objects or []):
            self.mgr.create(self.ctx, obj)

    def test_lifecycle(self):
        self._create_prerequisite_objects()
        self._test_resource_ops(
            self.resource_class,
            self.test_identity_attributes,
            self.test_required_attributes,
            self.test_search_attributes,
            self.test_update_attributes,
            self.test_default_values,
            self.test_dn)

    def test_hooks(self):
        self._create_prerequisite_objects()
        self._test_commit_hook(
            self.resource_class,
            self.test_identity_attributes,
            self.test_required_attributes,
            self.test_update_attributes)


class TestAciResourceOpsBase(TestResourceOpsBase):

    def test_status(self):
        self._test_resource_status(
            self.resource_class, self.test_identity_attributes)


class TestTenant(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.Tenant
    test_identity_attributes = {'name': 'tenant1'}
    test_required_attributes = {'name': 'tenant1'}
    test_search_attributes = {'name': 'tenant1'}
    test_update_attributes = {'display_name': 'pepsi'}
    test_dn = 'uni/tn-tenant1'

    def test_status(self):
        pass


class TestBridgeDomain(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.BridgeDomain
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'net1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'net1'}
    test_search_attributes = {'l2_unknown_unicast_mode': 'proxy'}
    test_update_attributes = {'l2_unknown_unicast_mode': 'private',
                              'display_name': 'pretty-net1',
                              'vrf_name': 'default'}
    test_dn = 'uni/tn-tenant1/BD-net1'


class TestAgent(TestResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.Agent
    test_identity_attributes = {'id': 'myuuid'}
    test_required_attributes = {'agent_type': 'aid',
                                'host': 'h1',
                                'binary_file': 'aid.py',
                                'version': '1.0',
                                'hash_trees': ['t1']}
    test_search_attributes = {'host': 'h1'}
    test_update_attributes = {'host': 'h2',
                              'version': '2.0',
                              'hash_trees': ['t2']}

    def setUp(self):
        super(TestAgent, self).setUp()
        self.ctx.db_session.add(
            tree_model.TenantTree(tenant_rn='t1', root_full_hash='',
                                  tree='{}'))
        self.ctx.db_session.add(
            tree_model.TenantTree(tenant_rn='t2', root_full_hash='',
                                  tree='{}'))

    def test_timestamp(self):
        agent = resource.Agent(id='myuuid', agent_type='aid', host='host',
                               binary_file='binary_file', version='1.0')

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
                               binary_file='binary_file', version='1.0')
        self.assertRaises(AttributeError, agent.is_down)
        agent = self.mgr.create(self.ctx, agent)
        self.assertFalse(agent.is_down())
        config.cfg.CONF.set_override('agent_down_time', 0, 'aim')
        self.assertTrue(agent.is_down())

    def test_status(self):
        pass


class TestSubnet(TestAciResourceOpsBase, base.TestAimDBBase):
    prereq_objects = [
        resource.BridgeDomain(tenant_name='tenant1', name='net1')]
    gw_ip = resource.Subnet.to_gw_ip_mask('192.168.10.1', 28)
    resource_class = resource.Subnet
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'bd_name': 'net1',
                                'gw_ip_mask': gw_ip}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'bd_name': 'net1',
                                'gw_ip_mask': gw_ip}
    test_search_attributes = {'bd_name': 'net1'}
    test_update_attributes = {'display_name': 'sub1',
                              'scope': resource.Subnet.SCOPE_PUBLIC}
    test_default_values = {
        'scope': resource.Subnet.SCOPE_PRIVATE}
    test_dn = 'uni/tn-tenant1/BD-net1/subnet-[192.168.10.1/28]'


class TestVRF(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.VRF
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'shared'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'shared'}
    test_search_attributes = {'name': 'shared'}
    test_update_attributes = {'display_name': 'shared',
                              'policy_enforcement_pref':
                                  resource.VRF.POLICY_UNENFORCED}
    test_default_values = {
        'policy_enforcement_pref': resource.VRF.POLICY_ENFORCED}
    test_dn = 'uni/tn-tenant1/ctx-shared'


class TestApplicationProfile(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.ApplicationProfile
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'lab'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'lab'}
    test_search_attributes = {'name': 'lab'}
    test_update_attributes = {'display_name': 'lab101'}
    test_dn = 'uni/tn-tenant1/ap-lab'


class TestEndpointGroup(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.EndpointGroup
    prereq_objects = [
        resource.ApplicationProfile(tenant_name='tenant1', name='lab')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'app_profile_name': 'lab',
                                'name': 'web'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'app_profile_name': 'lab',
                                'name': 'web',
                                'provided_contract_names': ['k', 'p1', 'p2'],
                                'consumed_contract_names': ['c1', 'c2', 'k']}
    test_search_attributes = {'name': 'web'}
    test_update_attributes = {'bd_name': 'net1',
                              'provided_contract_names': ['c2', 'k', 'p1'],
                              'consumed_contract_names': ['c1', 'k', 'p2']}
    test_dn = 'uni/tn-tenant1/ap-lab/epg-web'
