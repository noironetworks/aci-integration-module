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
from aim.common.hashtree import structured_tree
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

        class bad_resource_3(bad_resource_1):
            _aci_mo_name = 'fvTenant'
            identity_attributes = ['attr1', 'attr2']

        def create_obj(klass):
            return klass({})

        self.assertRaises(exc.AciResourceDefinitionError, create_obj,
                          bad_resource_1)
        self.assertRaises(exc.AciResourceDefinitionError, create_obj,
                          bad_resource_2)
        self.assertRaises(exc.InvalidDNForAciResource,
                          bad_resource_3.from_dn, 'uni/tn-coke')


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
        # check other attributes are unaffected
        for attr in r1.identity_attributes + r1.other_attributes:
            if attr not in test_update_attributes:
                self.assertEqual(getattr_canonical(r1, attr),
                                 getattr_canonical(r3, attr))

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

        if test_update_attributes:
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
        self.assertTrue(status.is_error())
        timestamp = status.faults[0].last_update_timestamp
        self.assertIsNotNone(timestamp)

        # Update the fault
        time.sleep(1)
        fault.severity = aim_status.AciFault.SEV_CLEARED
        self.mgr.set_fault(self.ctx, res, fault)
        status = self.mgr.get_status(self.ctx, res)
        self.assertEqual(1, len(status.faults))
        self.assertEqual(aim_status.AciFault.SEV_CLEARED,
                         status.faults[0].severity)
        new_timestamp = status.faults[0].last_update_timestamp
        self.assertTrue(new_timestamp > timestamp)
        self.assertFalse(status.is_error())

        # Add fault with same code
        fault_2 = aim_status.AciFault(
            fault_code='412', external_identifier='dn-2',
            severity=aim_status.AciFault.SEV_MAJOR)
        self.mgr.set_fault(self.ctx, res, fault_2)
        status = self.mgr.get_status(self.ctx, res)
        self.assertEqual(2, len(status.faults))
        self.assertTrue(status.is_error())

        self.mgr.clear_fault(self.ctx, fault)
        self.mgr.clear_fault(self.ctx, fault_2)
        status = self.mgr.get_status(self.ctx, res)
        self.assertEqual(0, len(status.faults))

        # Delete resource and verify that status is deleted as well
        self.mgr.set_fault(self.ctx, res, fault_2)
        db_res = self.mgr._query_db_obj(self.ctx.db_session, res)
        try:
            aim_id = db_res.aim_id
        except AttributeError:
            # Resource doesn't support Status
            pass
        else:
            self.mgr.delete(self.ctx, res)
            status_db = self.mgr._query_db_obj(
                self.ctx.db_session,
                aim_status.AciStatus(resource_type=type(res).__name__,
                                     resource_id=aim_id))
            self.assertIsNone(status_db)

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

    def test_monitored(self):
        if 'monitored' in self.resource_class.other_attributes:
            self._create_prerequisite_objects()
            creation_attributes = {'monitored': True}
            creation_attributes.update(self.test_required_attributes),
            creation_attributes.update(self.test_identity_attributes)
            res = self.resource_class(**creation_attributes)
            r1 = self.mgr.create(self.ctx, res)
            self.assertTrue(r1.monitored)

            # Can overwrite if monitored is still True
            r1 = self.mgr.create(self.ctx, res, overwrite=True)

            # Cannot create overwrite if monitored is changed
            r1.monitored = False
            self.assertRaises(exc.InvalidMonitoredStateUpdate,
                              self.mgr.create, self.ctx, r1, overwrite=True)

            # Updating the resource fails
            self.assertRaises(exc.InvalidUpdatedOnMonitoredObject,
                              self.mgr.update, self.ctx, res,
                              **self.test_update_attributes)

            # Also updating the monitored attribute itself
            res.monitored = False
            self.assertRaises(exc.InvalidUpdatedOnMonitoredObject,
                              self.mgr.update, self.ctx, res,
                              monitored=False)

            # Deleting it works
            self.mgr.delete(self.ctx, res)
            self.assertIsNone(self.mgr.get(self.ctx, res))


class TestAciResourceOpsBase(TestResourceOpsBase):

    def test_status(self):
        attr = {k: v for k, v in self.test_identity_attributes.iteritems()}
        attr.update(self.test_required_attributes)
        self._test_resource_status(self.resource_class, attr)

    def test_dn_op(self):
        res = self.resource_class(**self.test_required_attributes)
        self.assertEqual(self.test_dn, res.dn)

        res1 = self.resource_class.from_dn(res.dn)
        self.assertEqual(res.identity, res1.identity)

        # invalid dn
        self.assertRaises(exc.InvalidDNForAciResource,
                          self.resource_class.from_dn,
                          res.dn + '/foo')


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
                              'vrf_name': 'default',
                              'l3out_names': ['l3out1', 'out2']}
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
        self.tree_mgr = tree_model.TenantHashTreeManager()
        self.tree_mgr.update_bulk(
            self.ctx, [structured_tree.StructuredHashTree(root_key=('t1', )),
                       structured_tree.StructuredHashTree(root_key=('t2', ))])

        self.addCleanup(self._clean_trees)

    def _clean_trees(self):
        tree_model.TenantHashTreeManager().delete_by_tenant_rn(self.ctx, 't1')
        tree_model.TenantHashTreeManager().delete_by_tenant_rn(self.ctx, 't2')

    def test_timestamp(self):
        agent = resource.Agent(id='myuuid', agent_type='aid', host='host',
                               binary_file='binary_file', version='1.0')

        # Verify successful creation
        agent = self.mgr.create(self.ctx, agent, overwrite=True)
        hbeat = agent.heartbeat_timestamp

        # DB side timestamp has granularity in seconds
        time.sleep(1)
        # Update and verify that timestamp changed
        agent = self.mgr.update(self.ctx, agent,
                                beat_count=agent.beat_count + 1)
        # Hbeat is updated
        self.assertTrue(hbeat < agent.heartbeat_timestamp)

    def test_agent_down(self):
        agent = resource.Agent(agent_type='aid', host='host',
                               binary_file='binary_file', version='1.0')
        self.assertRaises(AttributeError, agent.is_down, self.ctx)
        agent = self.mgr.create(self.ctx, agent)
        self.assertFalse(agent.is_down(self.ctx))
        self.set_override('agent_down_time', 0, 'aim')
        self.assertTrue(agent.is_down(self.ctx))

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
        resource.ApplicationProfile(tenant_name='tenant1', name='lab'),
        resource.VMMDomain(type='OpenStack', name='openstack'),
        resource.PhysicalDomain(name='phys')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'app_profile_name': 'lab',
                                'name': 'web'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'app_profile_name': 'lab',
                                'name': 'web',
                                'provided_contract_names': ['k', 'p1', 'p2'],
                                'consumed_contract_names': ['c1', 'c2', 'k'],
                                'openstack_vmm_domain_names': ['openstack']}
    test_search_attributes = {'name': 'web'}
    test_update_attributes = {'bd_name': 'net1',
                              'provided_contract_names': ['c2', 'k', 'p1'],
                              'consumed_contract_names': ['c1', 'k', 'p2'],
                              'physical_domain_names': ['phys']}
    test_dn = 'uni/tn-tenant1/ap-lab/epg-web'

    def test_update_other_attributes(self):
        self._create_prerequisite_objects()

        res = resource.EndpointGroup(**self.test_required_attributes)
        r0 = self.mgr.create(self.ctx, res)
        self.assertEqual(['k', 'p1', 'p2'],
                         getattr_canonical(r0, 'provided_contract_names'))
        self.assertEqual(['openstack'],
                         getattr_canonical(r0, 'openstack_vmm_domain_names'))

        r1 = self.mgr.update(self.ctx, res, bd_name='net1')
        self.assertEqual('net1', r1.bd_name)
        self.assertEqual(['k', 'p1', 'p2'],
                         getattr_canonical(r1, 'provided_contract_names'))
        self.assertEqual(['c1', 'c2', 'k'],
                         getattr_canonical(r1, 'consumed_contract_names'))

        r2 = self.mgr.update(self.ctx, res, provided_contract_names=[],
                             openstack_vmm_domain_names=[])
        self.assertEqual('net1', r2.bd_name)
        self.assertEqual([], getattr_canonical(r2, 'provided_contract_names'))
        self.assertEqual(['c1', 'c2', 'k'],
                         getattr_canonical(r2, 'consumed_contract_names'))
        self.assertEqual([],
                         getattr_canonical(r2, 'openstack_vmm_domain_names'))


class TestFilter(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.Filter
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'filter1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'filter1'}
    test_search_attributes = {'name': 'filter1'}
    test_update_attributes = {'display_name': 'uv-filter'}
    test_dn = 'uni/tn-tenant1/flt-filter1'


class TestFilterEntry(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.FilterEntry
    prereq_objects = [
        resource.Filter(tenant_name='tenant1', name='filter1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'filter_name': 'filter1',
                                'name': 'entry1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'filter_name': 'filter1',
                                'name': 'entry1',
                                'arp_opcode': 'reply',
                                'ether_type': 'arp',
                                'ip_protocol': '6',
                                'dest_to_port': '443',
                                'source_from_port': 'dns'}
    test_search_attributes = {'ip_protocol': '6'}
    test_update_attributes = {'ether_type': 'ip',
                              'dest_to_port': resource.FilterEntry.UNSPECIFIED,
                              'icmpv4_type': 'echo'}
    test_dn = 'uni/tn-tenant1/flt-filter1/e-entry1'


class TestContract(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.Contract
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'contract1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'contract1',
                                'scope': resource.Contract.SCOPE_TENANT}
    test_search_attributes = {'scope': resource.Contract.SCOPE_TENANT}
    test_update_attributes = {'scope': resource.Contract.SCOPE_CONTEXT}
    test_dn = 'uni/tn-tenant1/brc-contract1'


class TestContractSubject(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.ContractSubject
    prereq_objects = [
        resource.Contract(tenant_name='tenant1', name='contract1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'contract_name': 'contract1',
                                'name': 'subject1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'contract_name': 'contract1',
                                'name': 'subject1',
                                'in_filters': ['f1', 'f2'],
                                'out_filters': ['f2', 'f3'],
                                'bi_filters': ['f1', 'f3', 'f4']}
    test_search_attributes = {'name': 'subject1'}
    test_update_attributes = {'in_filters': ['f1', 'f2', 'f3'],
                              'out_filters': []}
    test_dn = 'uni/tn-tenant1/brc-contract1/subj-subject1'


class TestEndpoint(TestResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.Endpoint
    prereq_objects = [
        resource.ApplicationProfile(tenant_name='t1', name='lab'),
        resource.ApplicationProfile(tenant_name='t1', name='dept'),
        resource.EndpointGroup(tenant_name='t1', app_profile_name='lab',
                               name='g1'),
        resource.EndpointGroup(tenant_name='t1', app_profile_name='dept',
                               name='g20')]
    test_identity_attributes = {'uuid': '1234'}
    test_required_attributes = {'uuid': '1234',
                                'epg_tenant_name': 't1',
                                'epg_app_profile_name': 'lab',
                                'epg_name': 'g1'}
    test_search_attributes = {'epg_name': 'g1'}
    test_update_attributes = {'epg_app_profile_name': 'dept',
                              'epg_name': 'g20'}


class TestVMMDomain(TestResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.VMMDomain
    test_identity_attributes = {'type': 'OpenStack', 'name': 'openstack'}
    test_required_attributes = {'type': 'OpenStack', 'name': 'openstack'}
    test_search_attributes = {'name': 'openstack'}
    test_update_attributes = {}


class TestPhysicalDomain(TestResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.PhysicalDomain
    test_identity_attributes = {'name': 'phys'}
    test_required_attributes = {'name': 'phys'}
    test_search_attributes = {}
    test_update_attributes = {}


class TestL3Outside(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.L3Outside
    test_identity_attributes = {'name': 'l3out1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'l3out1',
                                'vrf_name': 'ctx1',
                                'l3_domain_dn': 'uni/foo'}
    test_search_attributes = {'vrf_name': 'ctx1'}
    test_update_attributes = {'l3_domain_dn': 'uni/bar'}
    test_dn = 'uni/tn-tenant1/out-l3out1'


class TestExternalNetwork(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.ExternalNetwork
    prereq_objects = [
        resource.L3Outside(tenant_name='tenant1', name='l3out1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'l3out_name': 'l3out1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'l3out_name': 'l3out1',
                                'name': 'net1',
                                'nat_epg_dn': 'uni/tn-1/ap-a1/epg-g1',
                                'provided_contract_names': ['k', 'p1', 'p2'],
                                'consumed_contract_names': ['c1', 'c2', 'k']}
    test_search_attributes = {'name': 'net1'}
    test_update_attributes = {'provided_contract_names': ['c2', 'k'],
                              'consumed_contract_names': []}
    test_dn = 'uni/tn-tenant1/out-l3out1/instP-net1'


class TestExternalSubnet(TestAciResourceOpsBase, base.TestAimDBBase):
    resource_class = resource.ExternalSubnet
    prereq_objects = [
        resource.L3Outside(tenant_name='tenant1', name='l3out1'),
        resource.ExternalNetwork(tenant_name='tenant1', l3out_name='l3out1',
                                 name='net1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'l3out_name': 'l3out1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'l3out_name': 'l3out1',
                                'external_network_name': 'net1',
                                'cidr': '200.200.100.0/24'}
    test_search_attributes = {'cidr': '200.200.100.0/24'}
    test_update_attributes = {'display_name': 'home'}
    test_dn = ('uni/tn-tenant1/out-l3out1/instP-net1/'
               'extsubnet-[200.200.100.0/24]')
