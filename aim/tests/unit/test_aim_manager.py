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

import copy
import time

import jsonschema
from jsonschema import exceptions as schema_exc
import mock

from aim import aim_manager
from aim.api import infra
from aim.api import resource
from aim.api import resource as aim_res
from aim.api import schema
from aim.api import service_graph as aim_service_graph
from aim.api import status as aim_status
from aim.api import tree as api_tree
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim import config  # noqa
from aim.db import hashtree_db_listener
from aim.db import tree_model  # noqa
from aim import exceptions as exc
from aim.tests import base
from aim import tree_manager


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
    test_dn = None
    prereq_objects = None

    def setUp(self):
        super(TestResourceOpsBase, self).setUp()
        attr = self.resource_class.attributes()
        self.test_default_values = {}
        if 'monitored' in attr:
            self.test_default_values.setdefault('monitored', False)
        if 'display_name' in attr:
            self.test_default_values.setdefault('display_name', '')
        self.mgr = aim_manager.AimManager()
        self.mgr._update_listeners = []
        self.schema_dict = schema.generate_schema()

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
        if (not (set(test_identity_attributes.keys()) -
                 set(test_required_attributes.keys())) and
                test_identity_attributes):
            self.assertRaises(
                exc.IdentityAttributesMissing, resource, **{})

        # Create with identity attributes
        creation_attributes = {}
        creation_attributes.update(test_identity_attributes)
        res = resource(**creation_attributes)

        for k, v in test_default_values.iteritems():
            self.assertEqual(v, getattr_canonical(res, k))

        if test_dn:
            self.assertEqual(test_dn, res.dn)

        creation_attributes.update(test_required_attributes)
        res = resource(**creation_attributes)
        # Verify successful creation
        r1 = self.mgr.create(self.ctx, res)
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr_canonical(r1, k))
        self.assertEqual(len(self.mgr.find(self.ctx, resource)),
                         self.mgr.count(self.ctx, resource))
        # Verify get
        r1 = self.mgr.get(self.ctx, res)
        for k, v in creation_attributes.iteritems():
            self.assertEqual(v, getattr_canonical(r1, k))

        if ('object_uid' in self.ctx.store.features and
                'guid' in resource.db_attributes):
            self.assertTrue(bool(r1.guid))

        # Verify overwrite
        for k, v in test_search_attributes.iteritems():
            setattr(res, k, v)
        if not getattr(self, 'skip_overwrite', False):
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
        for attr in r1.attributes():
            if attr not in (test_update_attributes.keys() +
                            res.db_attributes.keys()):
                self.assertEqual(getattr_canonical(r1, attr),
                                 getattr_canonical(r3, attr))

        # Test empty update
        r31 = self.mgr.update(self.ctx, res, **{})
        self.assertEqual(r3, r31)

        # Test delete
        self.mgr.delete(self.ctx, res)
        self.assertIsNone(self.mgr.get(self.ctx, res))
        # TODO(ivar): Avoid config creation form AIM resources
        if not isinstance(res, aim_res.Configuration):
            self.assertNotIn(res, self.mgr.find(self.ctx, resource))
        self.assertEqual(len(self.mgr.find(self.ctx, resource)),
                         self.mgr.count(self.ctx, resource))
        # Test update nonexisting object
        r4 = self.mgr.update(self.ctx, res, **{})
        self.assertIsNone(r4)
        r4 = self.mgr.update(self.ctx, res, something='foo')
        self.assertIsNone(r4)

        # Test jsonschema
        klass_name = res.__class__.__name__
        snake_name = utils.camel_to_snake(klass_name)
        jsonschema.validate({'type': snake_name, snake_name: res.__dict__},
                            self.schema_dict)
        if res.identity_attributes:
            attributes = copy.deepcopy(res.__dict__)
            attributes.pop(res.identity_attributes.keys()[0])
            # Verify that removing a required attribute will fail
            self.assertRaises(
                schema_exc.ValidationError, jsonschema.validate,
                {'type': klass_name,
                 utils.camel_to_snake(klass_name): attributes},
                self.schema_dict)
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
        self.ctx.store.register_update_listener('mock-listener', listener)

        creation_attributes = {}
        creation_attributes.update(test_required_attributes),
        creation_attributes.update(test_identity_attributes)

        res = resource(**creation_attributes)
        res = self.mgr.create(self.ctx, res)
        status = self.mgr.get_status(self.ctx, res)
        if status:
            initial_status = copy.deepcopy(status)
            initial_status.id = None
            exp_calls = [
                mock.call(mock.ANY, [res], [], []),
                mock.call(mock.ANY, [initial_status], [res], [])]
            self._check_call_list(exp_calls, listener)
        else:
            listener.assert_called_with(mock.ANY, [res], [], [])

        # trigger status creation
        if test_update_attributes:
            listener.reset_mock()
            res = self.mgr.update(self.ctx, res, **test_update_attributes)
            status = self.mgr.get_status(self.ctx, res)
            if status:
                exp_calls = [
                    mock.call(mock.ANY, [], [res], [])]
                self._check_call_list(exp_calls, listener)
            else:
                # TODO(ivar): Agent object gets 2 calls to the hook on an
                # update, figure out why
                listener.assert_called_with(mock.ANY, [], [res], [])

        listener.reset_mock()
        self.mgr.delete(self.ctx, res)
        listener.assert_called_with(mock.ANY, [], [], [res])

        self.ctx.store.unregister_update_listener('mock-listener')

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

        res = self.mgr.create(self.ctx, res, overwrite=True)
        status = self.mgr.get_status(self.ctx, res)
        self.assertTrue(isinstance(status, aim_status.AciStatus))
        # Sync status not available
        self.assertEqual(status.SYNC_NA, status.sync_status)
        self.assertTrue(status.is_build())
        self.assertFalse(status.is_error())
        # Sync object
        self.mgr.set_resource_sync_synced(self.ctx, res)
        status = self.mgr.get_status(self.ctx, res)
        self.assertFalse(status.is_build())

        status.sync_message = "some message"
        self.mgr.update_status(self.ctx, res, status)

        # Add a fault
        fault = aim_status.AciFault(
            fault_code='412', external_identifier=res.dn,
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
        # Test parent class from status, and the ability to retrieve the
        # original object from there
        self.assertTrue(isinstance(res, status.parent_class))
        res_from_status = self.mgr.get_by_id(self.ctx, status.parent_class,
                                             status.resource_id)
        # get by ID with non-existing ID will return None
        self.assertIsNone(
            self.mgr.get_by_id(self.ctx, status.parent_class,
                               'nope'))
        self.assertEqual(res, res_from_status)
        # Get resource with aim_id included
        res_with_id = self.mgr.get(self.ctx, res, include_aim_id=True)
        self.assertEqual(res_with_id._aim_id, status.resource_id)
        res_with_id = self.mgr.find(self.ctx, type(res),
                                    include_aim_id=True)[0]
        self.assertEqual(res_with_id._aim_id, status.resource_id)
        res_with_id = self.mgr.get_by_id(self.ctx, status.parent_class,
                                         status.resource_id,
                                         include_aim_id=True)
        self.assertEqual(res_with_id._aim_id, status.resource_id)
        new_timestamp = status.faults[0].last_update_timestamp
        if self.ctx.store.current_timestamp:
            self.assertTrue(new_timestamp > timestamp)
        self.assertFalse(status.is_error())

        # Add fault with same code
        fault_2 = aim_status.AciFault(
            fault_code='412', external_identifier=res.dn + '/fault-412',
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
        db_res = self.mgr._query_db_obj(self.ctx.store, res)
        try:
            aim_id = db_res.aim_id
        except AttributeError:
            # Resource doesn't support Status
            pass
        else:
            self.mgr.delete(self.ctx, res)
            status_db = self.mgr._query_db_obj(
                self.ctx.store,
                aim_status.AciStatus(resource_type=type(res).__name__,
                                     resource_id=aim_id,
                                     resource_root=res.root))
            self.assertIsNone(status_db)

    def _create_prerequisite_objects(self):
        prereq = []
        for obj in (self.prereq_objects or []):
            prereq.append(self.mgr.create(self.ctx, obj))
        return prereq

    def test_lifecycle(self):
        prereq = self._create_prerequisite_objects()
        self._test_resource_ops(
            self.resource_class,
            self.test_identity_attributes,
            self.test_required_attributes,
            self.test_search_attributes,
            self.test_update_attributes,
            self.test_default_values,
            self.test_dn)
        if prereq:
            if len(prereq) > 2:
                self.mgr.delete(self.ctx, prereq[1])
            self.mgr.delete(self.ctx, prereq[0], cascade=True)
            for res in prereq:
                self.assertIsNone(self.mgr.get(self.ctx, res))

    # REVISIT(ivar): now that the listeners are all mocked this test
    # doesn't look very helpful
    @base.requires(['skip'])
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
                              self.mgr.create, self.ctx, r1,
                              fix_ownership=True, overwrite=True)

            # Updating the monitored attribute fails
            res.monitored = False
            self.assertRaises(exc.InvalidMonitoredStateUpdate,
                              self.mgr.update, self.ctx, res,
                              fix_ownership=True, monitored=False)

            r1 = self.mgr.create(self.ctx, r1, overwrite=True)
            self.assertFalse(r1.monitored)
            r1 = self.mgr.update(self.ctx, r1, monitored=True)
            self.assertTrue(r1.monitored)

            self.mgr.set_resource_sync_pending(self.ctx, res)
            # Deleting doesn't work because status is pending
            self.assertRaises(exc.InvalidMonitoredObjectDelete,
                              self.mgr.delete, self.ctx, res)
            # Now delete works
            self.mgr.delete(self.ctx, res, force=True)
            self.assertIsNone(self.mgr.get(self.ctx, res))

    def test_class_root_type(self):
        if issubclass(self.resource_class, resource.AciResourceBase):
            klass_type = hashtree_db_listener.HashTreeDbListener(
                self.mgr)._retrieve_class_root_type(self.resource_class)
            self.assertEqual(self.resource_root_type, klass_type)


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

    def _get_hash_trees(self):
        tenants = self.mgr.find(self.ctx, resource.Tenant)
        result = {}
        for tenant in tenants:
            result[tenant.name] = {}
            for typ in tree_manager.SUPPORTED_TREES:
                result[tenant.name][typ] = (
                    self.tt_mgr.get(self.ctx, tenant.rn, tree=typ))

    def test_tree_reset(self):
        self._create_prerequisite_objects()

        res = self.resource_class(**self.test_required_attributes)
        self.mgr.create(self.ctx, res)

        old = self._get_hash_trees()
        listener = hashtree_db_listener.HashTreeDbListener(self.mgr)
        listener.reset(self.ctx.store)
        new = self._get_hash_trees()
        self.assertEqual(old, new)


class TestTenantMixin(object):
    resource_class = resource.Tenant
    resource_root_type = resource.Tenant._aci_mo_name
    test_identity_attributes = {'name': 'tenant1'}
    test_required_attributes = {'name': 'tenant1'}
    test_search_attributes = {'name': 'tenant1', 'descr': 'openstack_id'}
    test_update_attributes = {'display_name': 'pepsi', 'descr': 'id2'}
    test_default_values = {}
    test_dn = 'uni/tn-tenant1'
    res_command = 'tenant'


class TestBridgeDomainMixin(object):
    prereq_objects = [resource.Tenant(name='tenant-1')]
    resource_class = resource.BridgeDomain
    resource_root_type = resource.Tenant._aci_mo_name
    test_identity_attributes = {'tenant_name': 'tenant-1',
                                'name': 'net1'}
    test_required_attributes = {'tenant_name': 'tenant-1',
                                'name': 'net1',
                                'ip_learning': False}
    test_search_attributes = {'l2_unknown_unicast_mode': 'proxy'}
    test_update_attributes = {'l2_unknown_unicast_mode': 'private',
                              'display_name': 'pretty-net1',
                              'vrf_name': 'default',
                              'ip_learning': True,
                              'l3out_names': ['l3out1', 'out2']}
    test_default_values = {'vrf_name': '',
                           'enable_arp_flood': True,
                           'enable_routing': True,
                           'limit_ip_learn_to_subnets': False,
                           'ip_learning': True,
                           'l2_unknown_unicast_mode': 'proxy',
                           'ep_move_detect_mode': 'garp',
                           'l3out_names': []}
    test_dn = 'uni/tn-tenant-1/BD-net1'
    res_command = 'bridge-domain'


class TestAgentMixin(object):
    resource_class = resource.Agent
    test_identity_attributes = {'id': 'myuuid'}
    test_required_attributes = {'agent_type': 'aid',
                                'host': 'h1',
                                'binary_file': 'aid.py',
                                'version': '1.0',
                                'hash_trees': ['tn-t1']}
    test_search_attributes = {'host': 'h1'}
    test_update_attributes = {'host': 'h2',
                              'version': '2.0',
                              'hash_trees': ['tn-t2']}
    test_default_values = {}
    res_command = 'agent'


class TestSubnetMixin(object):
    prereq_objects = [
        resource.Tenant(name='tenant1'),
        resource.BridgeDomain(tenant_name='tenant1', name='net1')]
    gw_ip = resource.Subnet.to_gw_ip_mask('192.168.10.1', 28)
    resource_class = resource.Subnet
    resource_root_type = resource.Tenant._aci_mo_name
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'bd_name': 'net1',
                                'gw_ip_mask': gw_ip}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'bd_name': 'net1',
                                'gw_ip_mask': gw_ip}
    test_search_attributes = {'bd_name': 'net1'}
    test_update_attributes = {'display_name': 'sub1',
                              'scope': resource.Subnet.SCOPE_PRIVATE}
    test_default_values = {
        'scope': resource.Subnet.SCOPE_PUBLIC}
    test_dn = 'uni/tn-tenant1/BD-net1/subnet-[192.168.10.1/28]'
    res_command = 'subnet'


class TestVRFMixin(object):
    resource_class = resource.VRF
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1')]
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
    res_command = 'vrf'


class TestApplicationProfileMixin(object):
    resource_class = resource.ApplicationProfile
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'lab'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'lab'}
    test_search_attributes = {'name': 'lab'}
    test_update_attributes = {'display_name': 'lab101'}
    test_default_values = {}
    test_dn = 'uni/tn-tenant1/ap-lab'
    res_command = 'application-profile'


class TestEndpointGroupMixin(object):
    resource_class = resource.EndpointGroup
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [
        resource.Tenant(name='tenant1'),
        resource.ApplicationProfile(tenant_name='tenant1', name='lab')]

    test_identity_attributes = {'tenant_name': 'tenant1',
                                'app_profile_name': 'lab',
                                'name': 'web'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'app_profile_name': 'lab',
                                'name': 'web',
                                'provided_contract_names': ['k', 'p1', 'p2'],
                                'consumed_contract_names': ['c1', 'c2', 'k'],
                                'openstack_vmm_domain_names': ['openstack'],
                                'static_paths': [{'path': 'topology/pod-1/'
                                                          'paths-101/pathep-'
                                                          '[eth1/2]',
                                                  'encap': 'vlan-2'},
                                                 {'path': 'topology/pod-1/'
                                                          'paths-102/pathep-'
                                                          '[eth1/5]',
                                                  'encap': 'vlan-5'}],
                                'physical_domains': [{'name': 'phys'}],
                                'epg_contract_masters': [
                                    {'app_profile_name': 'masterap1',
                                     'name': 'masterepg1'},
                                    {'app_profile_name': 'masterap2',
                                     'name': 'masterepg2'}]}
    test_search_attributes = {'name': 'web'}
    test_update_attributes = {'bd_name': 'net1',
                              'policy_enforcement_pref':
                              resource.EndpointGroup.POLICY_ENFORCED,
                              'provided_contract_names': ['c2', 'k', 'p1'],
                              'consumed_contract_names': ['c1', 'k', 'p2'],
                              'physical_domain_names': ['phys'],
                              'static_paths': [{'path': ('topology/pod-1/'
                                                         'paths-101/pathep-'
                                                         '[eth1/2]'),
                                                'encap': 'vlan-22'}],
                              'epg_contract_masters': [
                                  {'app_profile_name': 'masterap1',
                                   'name': 'masterepg1'}]}
    test_default_values = {'bd_name': '',
                           'provided_contract_names': [],
                           'consumed_contract_names': [],
                           'openstack_vmm_domain_names': [],
                           'physical_domain_names': [],
                           'policy_enforcement_pref':
                           resource.EndpointGroup.POLICY_UNENFORCED,
                           'static_paths': [],
                           'epg_contract_masters': []}
    test_dn = 'uni/tn-tenant1/ap-lab/epg-web'
    res_command = 'endpoint-group'


class TestFilterMixin(object):
    resource_class = resource.Filter
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'filter1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'filter1'}
    test_search_attributes = {'name': 'filter1'}
    test_update_attributes = {'display_name': 'uv-filter'}
    test_default_values = {}
    test_dn = 'uni/tn-tenant1/flt-filter1'
    res_command = 'filter'


class TestFilterEntryMixin(object):
    resource_class = resource.FilterEntry
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [
        resource.Tenant(name='tenant1'),
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
    test_default_values = {
        'arp_opcode': resource.FilterEntry.UNSPECIFIED,
        'ether_type': resource.FilterEntry.UNSPECIFIED,
        'ip_protocol': resource.FilterEntry.UNSPECIFIED,
        'icmpv4_type': resource.FilterEntry.UNSPECIFIED,
        'icmpv6_type': resource.FilterEntry.UNSPECIFIED,
        'source_from_port': resource.FilterEntry.UNSPECIFIED,
        'source_to_port': resource.FilterEntry.UNSPECIFIED,
        'dest_from_port': resource.FilterEntry.UNSPECIFIED,
        'dest_to_port': resource.FilterEntry.UNSPECIFIED,
        'tcp_flags': resource.FilterEntry.UNSPECIFIED,
        'stateful': False,
        'fragment_only': False}
    test_dn = 'uni/tn-tenant1/flt-filter1/e-entry1'
    res_command = 'filter-entry'


class TestContractMixin(object):
    resource_class = resource.Contract
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'contract1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'contract1',
                                'scope': resource.Contract.SCOPE_TENANT}
    test_search_attributes = {'scope': resource.Contract.SCOPE_TENANT}
    test_update_attributes = {'scope': resource.Contract.SCOPE_CONTEXT}
    test_default_values = {'scope': resource.Contract.SCOPE_CONTEXT}
    test_dn = 'uni/tn-tenant1/brc-contract1'
    res_command = 'contract'


class TestContractSubjectMixin(object):
    resource_class = resource.ContractSubject
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [
        resource.Tenant(name='tenant1'),
        resource.Contract(tenant_name='tenant1', name='contract1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'contract_name': 'contract1',
                                'name': 'subject1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'contract_name': 'contract1',
                                'name': 'subject1',
                                'in_filters': ['f1', 'f2'],
                                'out_filters': ['f2', 'f3'],
                                'bi_filters': ['f1', 'f3', 'f4'],
                                'service_graph_name': 'g1',
                                'in_service_graph_name': 'g2',
                                'out_service_graph_name': 'g3'}
    test_search_attributes = {'name': 'subject1'}
    test_update_attributes = {'in_filters': ['f1', 'f2', 'f3'],
                              'out_filters': [],
                              'service_graph_name': 'g11',
                              'in_service_graph_name': 'g21',
                              'out_service_graph_name': 'g31'}
    test_default_values = {'in_filters': [],
                           'out_filters': [],
                           'bi_filters': [],
                           'service_graph_name': '',
                           'in_service_graph_name': '',
                           'out_service_graph_name': ''}
    test_dn = 'uni/tn-tenant1/brc-contract1/subj-subject1'
    res_command = 'contract-subject'


class TestEndpointMixin(object):
    resource_class = resource.Endpoint
    prereq_objects = [
        resource.Tenant(name='t1'),
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
    test_default_values = {'epg_name': None,
                           'epg_tenant_name': None,
                           'epg_app_profile_name': None}
    res_command = 'endpoint'


class TestVMMDomainMixin(object):
    resource_class = resource.VMMDomain
    resource_root_type = resource.VMMPolicy._aci_mo_name
    prereq_objects = [resource.VMMPolicy(type='OpenStack')]
    test_identity_attributes = {'type': 'OpenStack',
                                'name': 'openstack',
                                'encap_mode': 'vxlan'}
    test_required_attributes = {'type': 'OpenStack',
                                'name': 'openstack',
                                'enforcement_pref': 'hw',
                                'mode': 'k8s',
                                'mcast_address': '255.3.2.1',
                                'encap_mode': 'vlan',
                                'encap_mode': 'vxlan',
                                'vlan_pool_name': 'vlan_pool_1',
                                'vlan_pool_type': 'static',
                                'mcast_addr_pool_name': 'mcast_pool_1'}
    test_search_attributes = {'name': 'openstack'}
    test_update_attributes = {'mode': 'ovs',
                              'vlan_pool_name': 'pool2'}
    test_default_values = {'enforcement_pref': 'sw',
                           'mode': 'ovs',
                           'mcast_address': '0.0.0.0',
                           'pref_encap_mode': 'vxlan',
                           'vlan_pool_name': '',
                           'mcast_addr_pool_name': '',
                           'vlan_pool_type': 'dynamic'}
    res_command = 'vmm-domain'
    test_dn = 'uni/vmmp-OpenStack/dom-openstack'


class TestPhysicalDomainMixin(object):
    resource_class = resource.PhysicalDomain
    resource_root_type = resource.PhysicalDomain._aci_mo_name
    test_identity_attributes = {'name': 'phys'}
    test_required_attributes = {'name': 'phys'}
    test_search_attributes = {}
    test_update_attributes = {}
    test_default_values = {}
    res_command = 'physical-domain'
    test_dn = 'uni/phys-phys'


class TestL3OutsideMixin(object):
    resource_class = resource.L3Outside
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'l3out1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'l3out1',
                                'vrf_name': 'ctx1',
                                'l3_domain_dn': 'uni/foo'}
    test_search_attributes = {'vrf_name': 'ctx1'}
    test_update_attributes = {'l3_domain_dn': 'uni/bar'}
    test_default_values = {'vrf_name': '', 'l3_domain_dn': ''}
    test_dn = 'uni/tn-tenant1/out-l3out1'
    res_command = 'l3-outside'


class TestExternalNetworkMixin(object):
    resource_class = resource.ExternalNetwork
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [
        resource.Tenant(name='tenant1'),
        resource.L3Outside(tenant_name='tenant1', name='l3out1',
                           vrf_name='ctx1', l3_domain_dn='uni/foo')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'l3out_name': 'l3out1',
                                'name': 'net1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'l3out_name': 'l3out1',
                                'name': 'net1',
                                'nat_epg_dn': 'uni/tn-1/ap-a1/epg-g1',
                                'provided_contract_names': ['k', 'p1', 'p2'],
                                'consumed_contract_names': ['c1', 'c2', 'k']}
    test_search_attributes = {'name': 'net1'}
    test_update_attributes = {'provided_contract_names': ['c2', 'k'],
                              'consumed_contract_names': []}
    test_default_values = {'nat_epg_dn': '',
                           'provided_contract_names': [],
                           'consumed_contract_names': []}
    test_dn = 'uni/tn-tenant1/out-l3out1/instP-net1'
    res_command = 'external-network'


class TestExternalSubnetMixin(object):
    resource_class = resource.ExternalSubnet
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [
        resource.Tenant(name='tenant1'),
        resource.L3Outside(tenant_name='tenant1', name='l3out1'),
        resource.ExternalNetwork(tenant_name='tenant1', l3out_name='l3out1',
                                 name='net1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'l3out_name': 'l3out1',
                                'external_network_name': 'net1',
                                'cidr': '200.200.100.0/24'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'l3out_name': 'l3out1',
                                'external_network_name': 'net1',
                                'cidr': '200.200.100.0/24'}
    test_search_attributes = {'cidr': '200.200.100.0/24'}
    test_update_attributes = {'display_name': 'home'}
    test_default_values = {}
    test_dn = ('uni/tn-tenant1/out-l3out1/instP-net1/'
               'extsubnet-[200.200.100.0/24]')
    res_command = 'external-subnet'


class TestHostLinkMixin(object):
    resource_class = infra.HostLink
    test_identity_attributes = {'host_name': 'h0',
                                'interface_name': 'eth0'}
    test_required_attributes = {'host_name': 'h0',
                                'interface_name': 'eth0',
                                'interface_mac': 'aa:bb:cc:dd:ee:ff',
                                'switch_id': '201',
                                'module': 'vpc-1-33',
                                'port': 'bundle-201-1-33-and-202-1-33',
                                'path': 'topology/pod-1/protpaths-201-202/'
                                        'pathep-[bundle-201-1-33-and-'
                                        '202-1-33]'}
    test_search_attributes = {'host_name': 'h0'}
    test_update_attributes = {'switch_id': '101',
                              'module': '1',
                              'port': '33',
                              'path': 'topology/pod-1/paths-101/pathep-'
                                      '[eth1/33]'}
    test_default_values = {}
    res_command = 'host-link'


class TestHostDomainMappingMixin(object):
    resource_class = infra.HostDomainMapping
    test_identity_attributes = {'host_name': 'host1.example.com'}
    test_required_attributes = {'host_name': 'host1.example.com',
                                'vmm_domain_name': 'ostack1',
                                'physical_domain_name': 'physdom1'}
    test_search_attributes = {'host_name': 'host1.example.com'}
    test_update_attributes = {'vmm_domain_name': 'ostack2',
                              'physical_domain_name': 'physdom2'}
    test_default_values = {'vmm_domain_name': '',
                           'physical_domain_name': ''}
    res_command = 'host-domain-mapping'


class TestHostLinkNetworkLabelMixin(object):
    resource_class = infra.HostLinkNetworkLabel
    test_identity_attributes = {'host_name': 'host1.example.com',
                                'network_label': 'physnet1',
                                'interface_name': 'eth1'}
    test_required_attributes = {}
    test_search_attributes = {'host_name': 'host1.example.com',
                              'network_label': 'physnet1'}
    test_update_attributes = {}
    test_default_values = {}
    res_command = 'host-link-network-label'


class TestSecurityGroupMixin(object):
    resource_class = resource.SecurityGroup
    resource_root_type = resource.Tenant._aci_mo_name
    test_identity_attributes = {'tenant_name': 'tenant1', 'name': 'sg1'}
    test_required_attributes = {'tenant_name': 'tenant1', 'name': 'sg1'}
    test_search_attributes = {'display_name': 'sg-display'}
    test_update_attributes = {'display_name': 'sg-display2'}
    test_dn = 'uni/tn-tenant1/pol-sg1'
    res_command = 'security-group'


class TestSecurityGroupSubjectMixin(object):
    resource_class = resource.SecurityGroupSubject
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [
        resource.SecurityGroup(tenant_name='tenant1', name='sg1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'security_group_name': 'sg1',
                                'name': 'subject1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'security_group_name': 'sg1',
                                'name': 'subject1'}
    test_search_attributes = {'display_name': 'sgs-display'}
    test_update_attributes = {'display_name': 'sgs-display-2'}
    test_dn = 'uni/tn-tenant1/pol-sg1/subj-subject1'
    res_command = 'security-group-subject'


class TestSecurityGroupRuleMixin(object):
    resource_class = resource.SecurityGroupRule
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [
        resource.SecurityGroup(tenant_name='tenant1', name='sg1'),
        resource.SecurityGroupSubject(
            tenant_name='tenant1', security_group_name='sg1', name='subject1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'security_group_name': 'sg1',
                                'security_group_subject_name': 'subject1',
                                'name': 'rule1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'security_group_name': 'sg1',
                                'security_group_subject_name': 'subject1',
                                'name': 'rule1',
                                'direction': 'ingress',
                                'remote_ips': ['10.0.0.1/30',
                                               '192.168.0.0/24']}
    test_search_attributes = {'direction': 'ingress'}
    test_update_attributes = {'remote_ips': [], 'from_port': '80',
                              'to_port': '443'}
    test_dn = 'uni/tn-tenant1/pol-sg1/subj-subject1/rule-rule1'
    res_command = 'security-group-rule'


class TestConfigurationMixin(object):
    resource_class = resource.Configuration
    test_identity_attributes = {'key': 'apic_hosts',
                                'host': 'h1',
                                'group': 'default'}
    test_required_attributes = {'key': 'apic_hosts',
                                'host': 'h1',
                                'group': 'default'}
    test_search_attributes = {'value': 'v1'}
    test_update_attributes = {'value': 'v2'}
    res_command = 'configuration'


class TestDeviceClusterMixin(object):
    resource_class = aim_service_graph.DeviceCluster
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'cl1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'cl1',
                                'device_type': 'VIRTUAL',
                                'service_type': 'ADC',
                                'managed': False,
                                'physical_domain_name': 'physdom',
                                'encap': 'vlan-44',
                                'devices': [{'name': '1', 'path': 'a'},
                                            {'name': '2', 'path': 'b'}]}
    test_search_attributes = {'device_type': 'VIRTUAL'}
    test_update_attributes = {'devices': [],
                              'physical_domain_name': 'virt',
                              'encap': 'vlan-200'}
    test_default_values = {'device_type': 'PHYSICAL',
                           'service_type': 'OTHERS',
                           'context_aware': 'single-Context',
                           'managed': True,
                           'physical_domain_name': '',
                           'encap': '',
                           'devices': []}
    test_dn = 'uni/tn-tenant1/lDevVip-cl1'
    res_command = 'device-cluster'


class TestDeviceClusterInterfaceMixin(object):
    resource_class = aim_service_graph.DeviceClusterInterface
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1'),
                      aim_service_graph.DeviceCluster(tenant_name='tenant1',
                                                      name='cl1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'device_cluster_name': 'cl1',
                                'name': 'if1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'device_cluster_name': 'cl1',
                                'name': 'if1',
                                'encap': 'vlan-44',
                                'concrete_interfaces': ['a', 'b', 'c']}
    test_search_attributes = {'encap': 'vlan-44'}
    test_update_attributes = {'concrete_interfaces': ['d'],
                              'encap': 'vlan-200'}
    test_default_values = {'encap': '',
                           'concrete_interfaces': []}
    test_dn = 'uni/tn-tenant1/lDevVip-cl1/lIf-if1'
    res_command = 'device-cluster-interface'


class TestConcreteDeviceMixin(object):
    resource_class = aim_service_graph.ConcreteDevice
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1'),
                      aim_service_graph.DeviceCluster(tenant_name='tenant1',
                                                      name='cl1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'device_cluster_name': 'cl1',
                                'name': 'cdev1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'device_cluster_name': 'cl1',
                                'name': 'cdev1'}
    test_search_attributes = {'name': 'cdev1'}
    test_update_attributes = {'display_name': 'DEVICE'}
    test_dn = 'uni/tn-tenant1/lDevVip-cl1/cDev-cdev1'
    res_command = 'concrete-device'


class TestConcreteDeviceInterfaceMixin(object):
    resource_class = aim_service_graph.ConcreteDeviceInterface
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1'),
                      aim_service_graph.DeviceCluster(tenant_name='tenant1',
                                                      name='cl1'),
                      aim_service_graph.ConcreteDevice(
                          tenant_name='tenant1', device_cluster_name='cl1',
                          name='cdev1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'device_cluster_name': 'cl1',
                                'device_name': 'cdev1',
                                'name': 'if1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'device_cluster_name': 'cl1',
                                'device_name': 'cdev1',
                                'name': 'if1',
                                'path': 'abc'}
    test_search_attributes = {'device_name': 'cdev1'}
    test_update_attributes = {'path': 'pqr'}
    test_default_values = {'path': ''}
    test_dn = 'uni/tn-tenant1/lDevVip-cl1/cDev-cdev1/cIf-[if1]'
    res_command = 'concrete-device-interface'


class TestServiceGraphMixin(object):
    resource_class = aim_service_graph.ServiceGraph
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'gr1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'gr1',
                                'linear_chain_nodes': [
                                    {'name': '1'},
                                    {'name': '2',
                                     'device_cluster_name': 'a',
                                     'device_cluster_tenant_name': 'b'}]}
    test_search_attributes = {'name': 'gr1'}
    test_update_attributes = {'linear_chain_nodes': [],
                              'display_name': 'virt'}
    test_default_values = {'linear_chain_nodes': []}
    test_dn = 'uni/tn-tenant1/AbsGraph-gr1'
    res_command = 'service-graph'


class TestServiceGraphNodeMixin(object):
    resource_class = aim_service_graph.ServiceGraphNode
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1'),
                      aim_service_graph.ServiceGraph(tenant_name='tenant1',
                                                     name='gr1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'service_graph_name': 'gr1',
                                'name': 'node1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'service_graph_name': 'gr1',
                                'name': 'node1',
                                'function_type': 'GoThrough',
                                'managed': False,
                                'routing_mode': 'Redirect',
                                'connectors': ['a', 'b'],
                                'device_cluster_name': 'cl1',
                                'device_cluster_tenant_name': 'common'}
    test_search_attributes = {'function_type': 'GoThrough'}
    test_update_attributes = {'connectors': ['p', 'q'],
                              'routing_mode': 'unspecified'}
    test_default_values = {'function_type': 'GoTo',
                           'managed': True,
                           'routing_mode': 'unspecified',
                           'connectors': [],
                           'device_cluster_name': '',
                           'device_cluster_tenant_name': ''}
    test_dn = 'uni/tn-tenant1/AbsGraph-gr1/AbsNode-node1'
    res_command = 'service-graph-node'


class TestServiceGraphConnectionMixin(object):
    resource_class = aim_service_graph.ServiceGraphConnection
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1'),
                      aim_service_graph.ServiceGraph(tenant_name='tenant1',
                                                     name='gr1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'service_graph_name': 'gr1',
                                'name': 'conn1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'service_graph_name': 'gr1',
                                'name': 'conn1',
                                'adjacency_type': 'L3',
                                'connector_direction': 'consumer',
                                'connector_type': 'internal',
                                'direct_connect': True,
                                'unicast_route': True,
                                'connector_dns': ['bar', 'foo']}
    test_search_attributes = {'adjacency_type': 'L3'}
    test_update_attributes = {'connector_type': 'external',
                              'connector_dns': ['bar', 'bar1']}
    test_default_values = {'adjacency_type': 'L2',
                           'connector_direction': 'provider',
                           'connector_type': 'external',
                           'direct_connect': False,
                           'unicast_route': False,
                           'connector_dns': []}
    test_dn = 'uni/tn-tenant1/AbsGraph-gr1/AbsConnection-conn1'
    res_command = 'service-graph-connection'


class TestServiceRedirectPolicyMixin(object):
    resource_class = aim_service_graph.ServiceRedirectPolicy
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'name': 'srp1'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'name': 'srp1',
                                'destinations': [{'ip': '1'},
                                                 {'ip': '2',
                                                  'mac': 'aa:bb:bb:cc:dd:ee'}]}
    test_search_attributes = {'name': 'srp1'}
    test_update_attributes = {'destinations': [],
                              'display_name': 'REDIR'}
    test_default_values = {'destinations': []}
    test_dn = 'uni/tn-tenant1/svcCont/svcRedirectPol-srp1'
    res_command = 'service-redirect-policy'


class TestDeviceClusterContextMixin(object):
    resource_class = aim_service_graph.DeviceClusterContext
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'contract_name': 'c1',
                                'service_graph_name': 'g0',
                                'node_name': 'N0'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'contract_name': 'c1',
                                'service_graph_name': 'g0',
                                'node_name': 'N0',
                                'device_cluster_name': 'ldc1',
                                'device_cluster_tenant_name': 'common',
                                'bridge_domain_name': 'bd1',
                                'bridge_domain_tenant_name': 'bd_t1',
                                'service_redirect_policy_name': 'srp1',
                                'service_redirect_policy_tenant_name':
                                'srp_t1'}
    test_search_attributes = {'node_name': 'N0'}
    test_update_attributes = {'device_cluster_name': 'cluster1',
                              'bridge_domain_tenant_name': 'common',
                              'display_name': 'CTX'}
    test_default_values = {'device_cluster_name': '',
                           'device_cluster_tenant_name': '',
                           'service_redirect_policy_name': '',
                           'service_redirect_policy_tenant_name': '',
                           'bridge_domain_name': '',
                           'bridge_domain_tenant_name': ''}
    test_dn = 'uni/tn-tenant1/ldevCtx-c-c1-g-g0-n-N0'
    res_command = 'device-cluster-context'


class TestDeviceClusterInterfaceContextMixin(object):
    resource_class = aim_service_graph.DeviceClusterInterfaceContext
    resource_root_type = resource.Tenant._aci_mo_name
    prereq_objects = [resource.Tenant(name='tenant1'),
                      aim_service_graph.DeviceClusterContext(
                          tenant_name='tenant1',
                          contract_name='c1',
                          service_graph_name='g0',
                          node_name='N0')]
    test_identity_attributes = {'tenant_name': 'tenant1',
                                'contract_name': 'c1',
                                'service_graph_name': 'g0',
                                'node_name': 'N0',
                                'connector_name': 'cons'}
    test_required_attributes = {'tenant_name': 'tenant1',
                                'contract_name': 'c1',
                                'service_graph_name': 'g0',
                                'node_name': 'N0',
                                'connector_name': 'cons',
                                'device_cluster_interface_dn': 'a',
                                'service_redirect_policy_dn': 'b',
                                'bridge_domain_dn': 'c'}
    test_search_attributes = {'device_cluster_interface_dn': 'a'}
    test_update_attributes = {'bridge_domain_dn': 'bd',
                              'display_name': 'CONN'}
    test_default_values = {'device_cluster_interface_dn': '',
                           'service_redirect_policy_dn': '',
                           'bridge_domain_dn': ''}
    test_dn = 'uni/tn-tenant1/ldevCtx-c-c1-g-g0-n-N0/lIfCtx-c-cons'
    res_command = 'device-cluster-interface-context'


class TestOpflexDeviceMixin(object):
    resource_class = infra.OpflexDevice
    resource_root_type = resource.Topology._aci_mo_name
    test_identity_attributes = {'pod_id': '1',
                                'node_id': '301',
                                'bridge_interface': 'eth1/33',
                                'dev_id': '167776320'}
    test_required_attributes = {'pod_id': '1',
                                'node_id': '301',
                                'bridge_interface': 'eth1/33',
                                'dev_id': '167776320',
                                'host_name': 'f1-compute-1',
                                'ip': '10.0.16.64',
                                'domain_name': 'k8s',
                                'controller_name': 'cluster1',
                                'fabric_path_dn': ('topology/pod-1/'
                                                   'protpaths-201-202/'
                                                   'pathep-[bundle-201-'
                                                   '1-33-and-202-1-33]')}
    test_search_attributes = {'host_name': 'f1-compute-1'}
    test_update_attributes = {'host_name': 'f1-compute-2',
                              'domain_name': 'ostack',
                              'fabric_path_dn': ('topology/pod-1/paths-101/'
                                                 'pathep-[eth1/33]')}
    test_default_values = {'host_name': '',
                           'ip': '',
                           'fabric_path_dn': '',
                           'domain_name': '',
                           'controller_name': ''}
    test_dn = 'topology/pod-1/node-301/sys/br-[eth1/33]/odev-167776320'
    res_command = 'opflex-device'

    def test_implicit_monitored(self):
        odev = self.mgr.create(
            self.ctx, infra.OpflexDevice(pod_id='1', node_id='301',
                                         bridge_interface='eth1/33',
                                         dev_id='167776320'))
        self.assertTrue(odev.monitored)
        odev.host_name = 'test'
        self.mgr.create(self.ctx, odev, overwrite=True, fix_ownership=True)


class TestPodMixin(object):
    resource_class = resource.Pod
    resource_root_type = resource.Topology._aci_mo_name
    test_identity_attributes = {'name': '1'}
    test_required_attributes = {'name': '1'}
    test_search_attributes = {}
    test_update_attributes = {}
    test_default_values = {}
    res_command = 'pod'
    test_dn = 'topology/pod-1'


class TestTopologyMixin(object):
    resource_class = resource.Topology
    resource_root_type = resource.Topology._aci_mo_name
    test_identity_attributes = {}
    test_required_attributes = {}
    test_search_attributes = {}
    test_update_attributes = {}
    test_default_values = {}
    res_command = 'topology'
    test_dn = 'topology'


class TestVMMControllerMixin(object):
    resource_class = resource.VMMController
    resource_root_type = resource.VMMPolicy._aci_mo_name
    prereq_objects = [resource.VMMPolicy(type='OpenStack'),
                      resource.VMMDomain(type='OpenStack',
                                         name='openstack')]
    test_identity_attributes = {'domain_type': 'OpenStack',
                                'domain_name': 'openstack',
                                'name': 'cluster1'}
    test_required_attributes = {'domain_type': 'OpenStack',
                                'domain_name': 'openstack',
                                'name': 'cluster1',
                                'scope': 'kubernetes',
                                'root_cont_name': 'root-cluster1',
                                'host_or_ip': 'host-cluster1',
                                'mode': 'k8s'}
    test_search_attributes = {'name': 'cluster1'}
    test_update_attributes = {'display_name': 'OSTK',
                              'scope': 'unmanaged'}
    test_default_values = {'scope': 'openstack',
                           'root_cont_name': 'cluster1',
                           'host_or_ip': 'cluster1',
                           'mode': 'ovs'}
    res_command = 'vmm-controller'
    test_dn = 'uni/vmmp-OpenStack/dom-openstack/ctrlr-cluster1'


def _setup_injected_object(test_obj, inj_klass, inj_attr, inj_name):
    if inj_klass == resource.VmmInjectedNamespace:
        inj_name = 'ns-' + inj_name
    test_obj.test_dn = test_obj.test_dn.replace('{%s}' % inj_attr, inj_name)
    test_obj.prereq_objects = copy.copy(test_obj.prereq_objects)
    inj_obj = [p for p in test_obj.prereq_objects if isinstance(p, inj_klass)]
    if inj_obj:
        setattr(inj_obj[0], 'name', inj_name)
    test_obj.test_identity_attributes = copy.copy(
        test_obj.test_identity_attributes)
    test_obj.test_identity_attributes[inj_attr] = inj_name
    test_obj.test_required_attributes = copy.copy(
        test_obj.test_required_attributes)
    test_obj.test_required_attributes[inj_attr] = inj_name
    test_obj.test_search_attributes = copy.copy(
        test_obj.test_search_attributes)
    test_obj.test_search_attributes[inj_attr] = inj_name


class TestVmmInjectedNamespaceMixin(object):
    resource_class = resource.VmmInjectedNamespace
    resource_root_type = resource.VMMPolicy._aci_mo_name
    prereq_objects = []
    test_identity_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster'}
    test_required_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster'}
    test_search_attributes = {}
    test_update_attributes = {'display_name': 'KUBE'}
    test_default_values = {}
    test_dn = ('comp/prov-Kubernetes/ctrlr-[kubernetes]-kube-cluster/injcont/'
               'ns-[{name}]')
    res_command = 'vmm-injected-namespace'

    def _setUp(self):
        _setup_injected_object(self, resource.VmmInjectedNamespace,
                               'name', self.test_id)


class TestVmmInjectedDeploymentMixin(object):
    resource_class = resource.VmmInjectedDeployment
    resource_root_type = resource.VMMPolicy._aci_mo_name
    prereq_objects = [
        resource.VmmInjectedNamespace(domain_type='Kubernetes',
                                      domain_name='kubernetes',
                                      controller_name='kube-cluster',
                                      name='')]
    test_identity_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster',
                                'name': 'depl1'}
    test_required_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster',
                                'name': 'depl1',
                                'replicas': 1}
    test_search_attributes = {'name': 'depl1'}
    test_update_attributes = {'replicas': 2,
                              'display_name': 'DEPL'}
    test_default_values = {'replicas': 0}
    test_dn = ('comp/prov-Kubernetes/ctrlr-[kubernetes]-kube-cluster/injcont/'
               'ns-[{namespace_name}]/depl-[depl1]')
    res_command = 'vmm-injected-deployment'

    def _setUp(self):
        _setup_injected_object(self, resource.VmmInjectedNamespace,
                               'namespace_name', self.test_id)


class TestVmmInjectedReplicaSetMixin(object):
    resource_class = resource.VmmInjectedReplicaSet
    resource_root_type = resource.VMMPolicy._aci_mo_name
    prereq_objects = [
        resource.VmmInjectedNamespace(domain_type='Kubernetes',
                                      domain_name='kubernetes',
                                      controller_name='kube-cluster',
                                      name='')]
    test_identity_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster',
                                'name': 'repl1'}
    test_required_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster',
                                'deployment_name': 'depl1',
                                'name': 'repl1'}
    test_search_attributes = {'name': 'repl1'}
    test_update_attributes = {'display_name': 'REPL'}
    test_default_values = {}
    test_dn = ('comp/prov-Kubernetes/ctrlr-[kubernetes]-kube-cluster/injcont/'
               'ns-[{namespace_name}]/rs-[repl1]')
    res_command = 'vmm-injected-replica-set'

    def _setUp(self):
        _setup_injected_object(self, resource.VmmInjectedNamespace,
                               'namespace_name', self.test_id)


class TestVmmInjectedServiceMixin(object):
    resource_class = resource.VmmInjectedService
    resource_root_type = resource.VMMPolicy._aci_mo_name
    prereq_objects = [
        resource.VmmInjectedNamespace(domain_type='Kubernetes',
                                      domain_name='kubernetes',
                                      controller_name='kube-cluster',
                                      name='')]
    test_identity_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster',
                                'name': 'svc1'}
    test_required_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster',
                                'name': 'svc1',
                                'service_type': 'loadBalancer',
                                'load_balancer_ip': '5.6.7.8',
                                'service_ports': [{'port': '23',
                                                   'protocol': 'tcp',
                                                   'target_port': '45',
                                                   'node_port': '32342'}],
                                'endpoints': [{'ip': '1.2.3.4',
                                               'pod_name': 'foo'},
                                              {'ip': '2.1.3.4',
                                               'pod_name': 'bar'}]}
    test_search_attributes = {'name': 'svc1'}
    test_update_attributes = {'load_balancer_ip': '56.77.78.88',
                              'endpoints': []}
    test_default_values = {'service_type': 'clusterIp',
                           'cluster_ip': '0.0.0.0',
                           'load_balancer_ip': '0.0.0.0',
                           'service_ports': []}
    test_dn = ('comp/prov-Kubernetes/ctrlr-[kubernetes]-kube-cluster/injcont/'
               'ns-[{namespace_name}]/svc-[svc1]')
    res_command = 'vmm-injected-service'

    def _setUp(self):
        _setup_injected_object(self, resource.VmmInjectedNamespace,
                               'namespace_name', self.test_id)
        if 'k8s' in self.ctx.store.features:
            self.skip_overwrite = True
            np1 = 30000 + int(self.test_id.split('-')[0], 16) % 2767
            self.test_required_attributes[
                'service_ports'][0]['node_port'] = str(np1)
            self.test_required_attributes.pop('endpoints', None)


class TestVmmInjectedHostMixin(object):
    resource_class = resource.VmmInjectedHost
    resource_root_type = resource.VMMPolicy._aci_mo_name
    prereq_objects = []
    test_identity_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster'}
    test_required_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster',
                                'host_name': 'host1.local.lab',
                                'os': 'Ubuntu',
                                'kernel_version': '4.16.8'}
    test_search_attributes = {'os': 'Ubuntu'}
    test_update_attributes = {'host_name': 'host2.local.lab'}
    test_default_values = {}
    test_dn = ('comp/prov-Kubernetes/ctrlr-[kubernetes]-kube-cluster/injcont/'
               'host-[{name}]')
    res_command = 'vmm-injected-host'

    def _setUp(self):
        _setup_injected_object(self, resource.VmmInjectedHost,
                               'name', self.test_id)


class TestVmmInjectedContGroupMixin(object):
    resource_class = resource.VmmInjectedContGroup
    resource_root_type = resource.VMMPolicy._aci_mo_name
    prereq_objects = [
        resource.VmmInjectedNamespace(domain_type='Kubernetes',
                                      domain_name='kubernetes',
                                      controller_name='kube-cluster',
                                      name='')]
    test_identity_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster',
                                'name': 'pod1'}
    test_required_attributes = {'domain_type': 'Kubernetes',
                                'domain_name': 'kubernetes',
                                'controller_name': 'kube-cluster',
                                'name': 'pod1',
                                'host_name': 'host1',
                                'compute_node_name': 'host1',
                                'replica_set_name': 'rs1'}
    test_search_attributes = {'name': 'pod1'}
    test_update_attributes = {'display_name': 'POD'}
    test_default_values = {'host_name': ''}
    test_dn = ('comp/prov-Kubernetes/ctrlr-[kubernetes]-kube-cluster/injcont/'
               'ns-[{namespace_name}]/grp-[pod1]')
    res_command = 'vmm-injected-cont-group'

    def _setUp(self):
        _setup_injected_object(self, resource.VmmInjectedNamespace,
                               'namespace_name', self.test_id)


class TestActionLogMixin(object):
    resource_class = api_tree.ActionLog
    test_identity_attributes = {}
    test_required_attributes = {'root_rn': 'tn-common',
                                'action': 'create',
                                'object_type': 'BridgeDomain',
                                'object_dict': ('{"tenant_name": "common", '
                                                '"name": "ciao"}')
                                }
    test_search_attributes = {'root_rn': 'tn-common'}
    test_update_attributes = {'action': 'delete'}
    test_default_values = {}
    res_command = 'action-log'


class TestTenant(TestTenantMixin, TestAciResourceOpsBase, base.TestAimDBBase):

    def test_status(self):
        pass


class TestBridgeDomain(TestBridgeDomainMixin, TestAciResourceOpsBase,
                       base.TestAimDBBase):
    pass


class TestActionLog(TestActionLogMixin, TestResourceOpsBase,
                    base.TestAimDBBase):
    def setUp(self):
        super(TestActionLog, self).setUp()
        self.catchup_logs = mock.patch(
            'aim.db.hashtree_db_listener.HashTreeDbListener.'
            'catch_up_with_action_log')
        self.catchup_logs.start()
        self.addCleanup(self.catchup_logs.stop)

    @base.requires(['sql'])
    def test_increasing_id(self):
        for i in range(1, 11):
            # New UUID every time
            action = api_tree.ActionLog(
                root_rn='tenant', action='create', object_type='Tenant',
                object_dict='{"name": "tenant"}')
            obj = self.mgr.create(self.ctx, action)
            self.assertEqual(i, obj.id)
        for i in range(1, 11):
            # New UUID every time
            action = api_tree.ActionLog(
                root_rn='tenant1', action='create', object_type='Tenant',
                object_dict='{"name": "tenant"}')
            self.mgr.create(self.ctx, action)
        action = api_tree.ActionLog(
            root_rn='tenant', action='reset', object_type='Tenant',
            object_dict='{"name": "tenant"}')
        obj = self.mgr.create(self.ctx, action)
        self.assertEqual(21, self.mgr.count(self.ctx, api_tree.ActionLog))
        self.assertEqual(10, self.mgr.count(self.ctx, api_tree.ActionLog,
                                            in_={'root_rn': ['tenant1']}))
        self.assertEqual('reset', obj.action)
        ordered = self.mgr.find(
            self.ctx, api_tree.ActionLog,
            in_={'root_rn': ['tenant', 'tenant1']}, order_by=['root_rn', 'id'])
        prev = ordered[0]
        self.assertEqual(1, prev.id)
        for obj in ordered[1:11]:
            self.assertEqual('tenant', obj.root_rn)
            self.assertTrue(prev.id < obj.id)
            prev = obj
        prev = ordered[11]
        for obj in ordered[12:]:
            self.assertEqual('tenant1', obj.root_rn)
            self.assertTrue(prev.id < obj.id)
            prev = obj
        self.mgr.delete_all(self.ctx, api_tree.ActionLog, root_rn='tenant1')
        self.assertEqual(0, self.mgr.count(self.ctx, api_tree.ActionLog,
                                           in_={'root_rn': ['tenant1']}))
        self.mgr.delete_all(self.ctx, api_tree.ActionLog,
                            notin_={'root_rn': ['tenant1']})
        self.assertEqual(0, self.mgr.count(self.ctx, api_tree.ActionLog))
        # Non existent doesn't raise
        self.mgr.delete_all(self.ctx, api_tree.ActionLog, root_rn='tenant1')


class TestAgent(TestAgentMixin, TestResourceOpsBase, base.TestAimDBBase):

    def setUp(self):
        super(TestAgent, self).setUp()
        self.tree_mgr = tree_manager.HashTreeManager()
        self.tree_mgr.update_bulk(
            self.ctx,
            [structured_tree.StructuredHashTree(root_key=('fvTenant|t1',)),
             structured_tree.StructuredHashTree(root_key=('fvTenant|t2',))])

    def _clean_trees(self):
        tree_manager.HashTreeManager().delete_by_root_rn(self.ctx, 'tn-t1')
        tree_manager.HashTreeManager().delete_by_root_rn(self.ctx, 'tn-t2')

    def test_timestamp(self):
        if self.ctx.store.current_timestamp:
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
        agent = self.mgr.create(self.ctx, agent)
        self.assertFalse(agent.is_down(self.ctx))
        if self.ctx.store.current_timestamp:
            self.set_override('agent_down_time', 0, 'aim')
            self.assertTrue(agent.is_down(self.ctx))

    def test_status(self):
        pass


class TestSubnet(TestSubnetMixin, TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestVRF(TestVRFMixin, TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestApplicationProfile(TestApplicationProfileMixin,
                             TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestEndpointGroup(TestEndpointGroupMixin, TestAciResourceOpsBase,
                        base.TestAimDBBase):

    def test_update_other_attributes(self):
        self._create_prerequisite_objects()
        for res in [resource.VMMPolicy(type='OpenStack'),
                    resource.VMMDomain(type='OpenStack', name='openstack'),
                    resource.PhysicalDomain(name='phys')]:
            self.mgr.create(self.ctx, res)
        res = resource.EndpointGroup(**self.test_required_attributes)
        r0 = self.mgr.create(self.ctx, res)
        self.assertEqual(['k', 'p1', 'p2'],
                         getattr_canonical(r0, 'provided_contract_names'))
        self.assertEqual(['openstack'],
                         getattr_canonical(r0, 'openstack_vmm_domain_names'))
        self.assertEqual([{'type': 'OpenStack', 'name': 'openstack'}],
                         getattr_canonical(r0, 'vmm_domains'))

        r1 = self.mgr.update(self.ctx, res, bd_name='net1')
        self.assertEqual('net1', r1.bd_name)
        self.assertEqual(['k', 'p1', 'p2'],
                         getattr_canonical(r1, 'provided_contract_names'))
        self.assertEqual(['c1', 'c2', 'k'],
                         getattr_canonical(r1, 'consumed_contract_names'))

        r2 = self.mgr.update(self.ctx, res, provided_contract_names=[],
                             vmm_domains=[])
        self.assertEqual('net1', r2.bd_name)
        self.assertEqual([], getattr_canonical(r2, 'provided_contract_names'))
        self.assertEqual(['c1', 'c2', 'k'],
                         getattr_canonical(r2, 'consumed_contract_names'))
        self.assertEqual([],
                         getattr_canonical(r2, 'openstack_vmm_domain_names'))
        self.assertEqual([],
                         getattr_canonical(r2, 'vmm_domains'))


class TestFilter(TestFilterMixin, TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestFilterEntry(TestFilterEntryMixin, TestAciResourceOpsBase,
                      base.TestAimDBBase):
    pass


class TestContract(TestContractMixin, TestAciResourceOpsBase,
                   base.TestAimDBBase):
    pass


class TestContractSubject(TestContractSubjectMixin, TestAciResourceOpsBase,
                          base.TestAimDBBase):
    pass


class TestEndpoint(TestEndpointMixin, TestResourceOpsBase, base.TestAimDBBase):
    pass


class TestVMMDomain(TestVMMDomainMixin, TestAciResourceOpsBase,
                    base.TestAimDBBase):
    pass


class TestPhysicalDomain(TestPhysicalDomainMixin, TestResourceOpsBase,
                         base.TestAimDBBase):
    pass


class TestL3Outside(TestL3OutsideMixin, TestAciResourceOpsBase,
                    base.TestAimDBBase):
    pass


class TestExternalNetwork(TestExternalNetworkMixin, TestAciResourceOpsBase,
                          base.TestAimDBBase):
    pass


class TestExternalSubnet(TestExternalSubnetMixin, TestAciResourceOpsBase,
                         base.TestAimDBBase):
    pass


class TestHostLink(TestHostLinkMixin, TestAciResourceOpsBase,
                   base.TestAimDBBase):

    def test_dn_op(self):
        pass

    def test_status(self):
        pass


class TestHostDomainMapping(TestHostDomainMappingMixin, TestResourceOpsBase,
                            base.TestAimDBBase):
    pass


class TestHostLinkNetworkLabel(TestHostLinkNetworkLabelMixin,
                               TestResourceOpsBase, base.TestAimDBBase):
    pass


class TestSecurityGroup(TestSecurityGroupMixin, TestAciResourceOpsBase,
                        base.TestAimDBBase):
    pass


class TestSecurityGroupSubject(TestSecurityGroupSubjectMixin,
                               TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestSecurityGroupRule(TestSecurityGroupRuleMixin,
                            TestAciResourceOpsBase, base.TestAimDBBase):

    @base.requires(['k8s'])
    def test_k8s_repr(self):
        sgr = resource.SecurityGroupRule(
            name='0_0', tenant_name='kubernetes',
            security_group_subject_name='NetworkPolicy',
            security_group_name='default_test-network-policy')
        db_obj = self.ctx.store.resource_to_db_type(
            resource.SecurityGroupRule)()
        self.ctx.store.from_attr(db_obj, resource.SecurityGroupRule,
                                 sgr.__dict__)
        self.assertEqual(
            's5u2ian7mxyipkk3rx632jc3zptp3ivwut4xxutricexuqn5fbia',
            db_obj['metadata']['labels']['tenant_name'])
        self.assertEqual(
            'igvrfnunwbqt35yheohgplxpzfilv7oyageq3qysiyiidx2rqknq',
            db_obj['metadata']['labels']['security_group_subject_name'])
        self.assertEqual(
            'l2yj2yf7qdftxom2xzclfhmfnp7fh75xyxryq2ggbvh77v7mjcla',
            db_obj['metadata']['labels']['security_group_name'])
        self.assertEqual(
            '3lmgcuqwadvc425mfmk7dt5keazplrjrt7ygaorbjhna6ttv4ndq',
            db_obj['metadata']['labels']['name'])
        self.assertEqual(
            'uwb4yv2u6k6lvjrhoi36genjxnhgkevjg24rvhuns7gzmeibpjyq',
            db_obj['metadata']['name'])


class TestConfiguration(TestConfigurationMixin, TestResourceOpsBase,
                        base.TestAimDBBase):
    pass


class TestDeviceCluster(TestDeviceClusterMixin,
                        TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestDeviceClusterInterface(TestDeviceClusterInterfaceMixin,
                                 TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestConcreteDevice(TestConcreteDeviceMixin,
                         TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestConcreteDeviceInterface(TestConcreteDeviceInterfaceMixin,
                                  TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestServiceGraphNode(TestServiceGraphNodeMixin,
                           TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestServiceGraphConnection(TestServiceGraphConnectionMixin,
                                 TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestServiceGraph(TestServiceGraphMixin,
                       TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestServiceRedirectPolicy(TestServiceRedirectPolicyMixin,
                                TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestDeviceClusterContext(TestDeviceClusterContextMixin,
                               TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestDeviceClusterInterfaceContext(TestDeviceClusterInterfaceContextMixin,
                                        TestAciResourceOpsBase,
                                        base.TestAimDBBase):
    pass


class TestOpflexDevice(TestOpflexDeviceMixin, TestAciResourceOpsBase,
                       base.TestAimDBBase):
    pass


class TestPod(TestPodMixin, TestAciResourceOpsBase, base.TestAimDBBase):
    pass


class TestTopology(TestTopologyMixin, TestResourceOpsBase,
                   base.TestAimDBBase):
    pass


class TestVMMController(TestVMMControllerMixin, TestAciResourceOpsBase,
                        base.TestAimDBBase):
    pass


class TestVmmInjectedNamespace(TestVmmInjectedNamespaceMixin,
                               TestAciResourceOpsBase, base.TestAimDBBase):

    def setUp(self):
        super(TestVmmInjectedNamespace, self).setUp()
        self._setUp()


class TestVmmInjectedDeployment(TestVmmInjectedDeploymentMixin,
                                TestAciResourceOpsBase, base.TestAimDBBase):

    def setUp(self):
        super(TestVmmInjectedDeployment, self).setUp()
        self._setUp()


class TestVmmInjectedReplicaSet(TestVmmInjectedReplicaSetMixin,
                                TestAciResourceOpsBase, base.TestAimDBBase):

    def setUp(self):
        super(TestVmmInjectedReplicaSet, self).setUp()
        self._setUp()

    @base.requires(['k8s'])
    def test_owner_reference(self):
        # Creating a Deployment creates an implicit ReplicaSet.
        # Verify that the ReplicaSet points to the Deployment.
        self._create_prerequisite_objects()
        ns = [o for o in self.prereq_objects
              if isinstance(o, resource.VmmInjectedNamespace)][0]
        depl = resource.VmmInjectedDeployment(
            domain_type=ns.domain_type,
            domain_name=ns.domain_name,
            controller_name=ns.controller_name,
            namespace_name=ns.name,
            name='depl1')
        self.mgr.create(self.ctx, depl)
        rss = self.mgr.find(self.ctx, resource.VmmInjectedReplicaSet,
                            domain_type=ns.domain_type,
                            domain_name=ns.domain_name,
                            controller_name=ns.controller_name,
                            namespace_name=ns.name)
        self.assertGreater(len(rss), 0)
        for rs in rss:
            self.assertEqual(depl.name, rs.deployment_name)

        # test older k8s version - simulate no ownerReferences
        rs_db_obj = self.ctx.store.make_db_obj(rs)
        curr = self.ctx.store.klient.read(type(rs_db_obj),
                                          rs_db_obj['metadata']['name'],
                                          rs_db_obj['metadata']['namespace'])
        curr['metadata'].pop('ownerReferences', None)
        self.ctx.store.klient.replace(type(rs_db_obj),
                                      rs_db_obj['metadata']['name'],
                                      rs_db_obj['metadata']['namespace'],
                                      curr)
        curr = self.ctx.store.klient.read(type(rs_db_obj),
                                          rs_db_obj['metadata']['name'],
                                          rs_db_obj['metadata']['namespace'])
        self.assertFalse(curr['metadata'].get('ownerReferences'))

        rs = self.mgr.get(self.ctx, rs)
        self.assertEqual(depl.name, rs.deployment_name)


class TestVmmInjectedService(TestVmmInjectedServiceMixin,
                             TestAciResourceOpsBase, base.TestAimDBBase):

    def setUp(self):
        super(TestVmmInjectedService, self).setUp()
        self._setUp()

    @base.requires(['k8s'])
    def test_endpoints(self):
        # Create an Endpoints object for a Service and verify that it
        # gets reported properly in VmmInjectedService
        self._create_prerequisite_objects()
        svc = resource.VmmInjectedService(**self.test_required_attributes)
        svc = self.mgr.create(self.ctx, svc)

        exp_ep = [{'ip': '10.1.2.3', 'pod_name': 'foo'},
                  {'ip': '10.1.2.4', 'pod_name': 'bar'}]

        store = self.ctx.store

        # create Endpoints
        svc.endpoints = exp_ep
        svc_db_obj = store.make_db_obj(svc)
        ep_db_obj = svc_db_obj.endpoints
        ep_db_obj['subsets'][0]['ports'] = [{'port': 80}]
        store.klient.create(type(ep_db_obj),
                            ep_db_obj['metadata']['namespace'],
                            ep_db_obj)

        svc = self.mgr.get(self.ctx, svc)
        self.assertEqual(exp_ep, svc.endpoints)

        # update Endpoints
        exp_ep.append({'ip': '10.1.2.5', 'pod_name': 'baz'})
        svc.endpoints = exp_ep
        svc_db_obj = store.make_db_obj(svc)
        ep_db_obj = svc_db_obj.endpoints
        ep_db_obj['subsets'][0]['ports'] = [{'port': 80}]
        store.klient.replace(type(ep_db_obj),
                             ep_db_obj['metadata']['name'],
                             ep_db_obj['metadata']['namespace'],
                             ep_db_obj)

        svc = self.mgr.get(self.ctx, svc)
        self.assertEqual(exp_ep, svc.endpoints)


class TestVmmInjectedHost(TestVmmInjectedHostMixin,
                          TestAciResourceOpsBase, base.TestAimDBBase):

    def setUp(self):
        super(TestVmmInjectedHost, self).setUp()
        self._setUp()


class TestVmmInjectedContGroup(TestVmmInjectedContGroupMixin,
                               TestAciResourceOpsBase, base.TestAimDBBase):

    def setUp(self):
        super(TestVmmInjectedContGroup, self).setUp()
        self._setUp()

    @base.requires(['k8s'])
    def test_owner_reference(self):
        # Inject an ownerReference to a Pod object and verify
        # replica_set_name is reported correctly
        self._create_prerequisite_objects()
        ns = [o for o in self.prereq_objects
              if isinstance(o, resource.VmmInjectedNamespace)][0]
        rs = resource.VmmInjectedReplicaSet(
            domain_type=ns.domain_type,
            domain_name=ns.domain_name,
            controller_name=ns.controller_name,
            namespace_name=ns.name,
            name='rs1')
        rs = self.mgr.create(self.ctx, rs)
        store = self.ctx.store
        rs_db_obj = store.make_db_obj(rs)
        rs_db_obj = store.klient.read(type(rs_db_obj),
                                      rs_db_obj['metadata']['name'],
                                      rs_db_obj['metadata']['namespace'])

        grp = self.mgr.create(
            self.ctx,
            resource.VmmInjectedContGroup(**self.test_required_attributes))
        grp_db_obj = store.make_db_obj(grp)
        grp_db_type = type(grp_db_obj)
        grp_db_obj = store.klient.read(grp_db_type,
                                       grp_db_obj['metadata']['name'],
                                       grp_db_obj['metadata']['namespace'])

        own_ref = {'kind': rs_db_obj['kind'],
                   'apiVersion': rs_db_obj['apiVersion'],
                   'name': rs_db_obj['metadata']['name'],
                   'uid': rs_db_obj['metadata']['uid']}
        grp_db_obj['metadata']['ownerReferences'] = [own_ref]
        self.ctx.store.klient.replace(grp_db_type,
                                      grp_db_obj['metadata']['name'],
                                      grp_db_obj['metadata']['namespace'],
                                      grp_db_obj)

        grp = self.mgr.get(self.ctx, grp)
        self.assertEqual(rs.name, grp.replica_set_name)
