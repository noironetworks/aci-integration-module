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

from aim.agent.aid.universes.aci import converter
from aim.api import resource
from aim.tests import base


class TestAciToAimConverterBase(object):
    resource_type = None
    reverse_map_output = []
    sample_input = []
    sample_output = []
    partial_change_input = None
    partial_change_output = None

    def setUp(self):
        super(TestAciToAimConverterBase, self).setUp()
        self.converter = converter.AciToAimModelConverter()

    def _test_convert(self, example1, expected1, example2, expected2):
        result = self.converter.convert(example1)
        self.assertEqual(len(expected1), len(result))
        for item in expected1:
            self.assertTrue(item in result,
                            'Expected %s not in %s' % (item, result))

        result = self.converter.convert(example1 + example2)
        self.assertEqual(len(expected1) + len(expected2), len(result))
        for item in expected1:
            self.assertTrue(item in result)
        for item in expected2:
            self.assertTrue(item in result,
                            'Expected %s not in %s' % (item, result))

    def _test_non_existing_resource(self, example, expected):
        result = self.converter.convert(example + [{'fvCtxNonEx': {}}])
        # Extra resource is ignored
        self.assertEqual(len(expected), len(result))
        for item in expected:
            self.assertTrue(item in result,
                            'Expected %s not in %s' % (item, result))

    def _test_partial_change(self, partial, expected):
        if (self.partial_change_input is None or
                self.partial_change_output is None):
            return
        result = self.converter.convert(partial)
        for item in expected:
            self.assertTrue(item in result,
                            'Expected %s not in %s' % (item, result))

    def _test_deleted_object(self, example, expected):
        for item in example:
            item.values()[0]['status'] = 'deleted'
        for item in expected:
            item._status = 'deleted'
        result = self.converter.convert(example)
        self.assertEqual(len(expected), len(result))
        for item in expected:
            self.assertTrue(item in result,
                            'Expected %s not in %s' % (item, result))

    def _test_reverse_map(self, resource_type, expected):
        reverse = converter.reverse_resource_map[resource_type]
        self.assertEqual(len(expected), len(reverse))
        for idx in xrange(len(expected)):
            self.assertTrue(expected[idx] in reverse,
                            'Expected %s not in %s' % (expected[idx], reverse))

    def test_reverse_map(self):
        self._test_reverse_map(self.resource_type, self.reverse_map_output)

    def test_convert(self):
        self.assertEqual(2, len(self.sample_input))
        self.assertEqual(2, len(self.sample_output))

        self._test_convert([self.sample_input[0]], [self.sample_output[0]],
                           [self.sample_input[1]], [self.sample_output[1]])

    def test_non_existing_resource(self):
        self._test_non_existing_resource([self.sample_input[0]],
                                         [self.sample_output[0]])

    def test_partial_change(self):
        self._test_partial_change([self.partial_change_input],
                                  [self.partial_change_output])

    def test_deleted_object(self):
        self._test_deleted_object([self.sample_input[0]],
                                  [self.sample_output[0]])


class TestAciToAimConverterBD(TestAciToAimConverterBase, base.TestAimDBBase):
    resource_type = resource.BridgeDomain
    reverse_map_output = [{
        'resource': 'fvBD',
        'exceptions': {
            'enable_arp_flood': {
                'other': 'arpFlood',
                'converter': converter.boolean
            },
            'enable_routing': {
                'other': 'unicastRoute',
                'converter': converter.boolean
            },
            'limit_ip_learn_to_subnets': {
                'other': 'limitIpLearnToSubnets',
                'converter': converter.boolean
            },
            'l2_unknown_unicast_mode': {
                'other': 'unkMacUcastAct',
            }
        },
        'identity_converter': None,
        'converter': None,
        'to_resource': converter.fv_bd_to_resource}, {
        'resource': 'fvRsCtx',
        'exceptions': {
            'vrf_name': {
                'other': 'tnFvCtxName'
            },
        },
        'to_resource': converter.fv_rs_ctx_to_resource,
    }]
    sample_input = [base.TestAimDBBase._get_example_aci_bd(),
                    base.TestAimDBBase._get_example_aci_bd(
                        dn='uni/tn-test-tenant/BD-test-1')]
    sample_output = [
        resource.BridgeDomain(tenant_name='test-tenant',
                              name='test',
                              enable_arp_flood=False,
                              enable_routing=True,
                              limit_ip_learn_to_subnets=False,
                              l2_unknown_unicast_mode='proxy',
                              ep_move_detect_mode=''),
        resource.BridgeDomain(tenant_name='test-tenant',
                              name='test-1',
                              enable_arp_flood=False,
                              enable_routing=True,
                              limit_ip_learn_to_subnets=False,
                              l2_unknown_unicast_mode='proxy',
                              ep_move_detect_mode='')]
    partial_change_input = {
        'fvBD': {'attributes': {
            'dn': 'uni/tn-test-tenant/BD-test',
            'status': 'modified',
            'unkMacUcastAct': 'flood',
            'arpFlood': 'yes', 'seg': '14909412',
            'modTs': '2016-03-24T14:55:12.867+00:00',
            'rn': '', 'childAction': ''}}}
    partial_change_output = resource.BridgeDomain(
        tenant_name='test-tenant',
        name='test',
        enable_arp_flood=True,
        l2_unknown_unicast_mode='flood')


class TestAciToAimConverterVRF(TestAciToAimConverterBase, base.TestAimDBBase):
    resource_type = resource.VRF
    reverse_map_output = [{
        'resource': 'fvCtx',
        'exceptions': {
            'policy_enforcement_pref': {
                'other': 'pcEnfPref'
            },
        }}]
    sample_input = [base.TestAimDBBase._get_example_aci_vrf(),
                    base.TestAimDBBase._get_example_aci_vrf(
                        dn='uni/tn-test-tenant/ctx-test-1')]
    sample_output = [
        resource.VRF(tenant_name='test-tenant',
                     name='test',
                     policy_enforcement_pref=resource.VRF.POLICY_ENFORCED),
        resource.VRF(tenant_name='test-tenant',
                     name='test-1',
                     policy_enforcement_pref=resource.VRF.POLICY_ENFORCED)]
    partial_change_input = {
        'fvCtx': {'attributes': {
            'dn': 'uni/tn-test-tenant/ctx-test',
            'status': 'modified',
            'pcEnfPref': 'unenforced',
            'modTs': '2016-03-24T14:55:12.867+00:00',
            'rn': '', 'childAction': ''}}}
    partial_change_output = resource.VRF(
        tenant_name='test-tenant',
        name='test',
        policy_enforcement_pref=resource.VRF.POLICY_UNENFORCED)


class TestAciToAimConverterSubnet(TestAciToAimConverterBase,
                                  base.TestAimDBBase):
    resource_type = resource.Subnet
    reverse_map_output = [{'exceptions': {},
                           'resource': 'fvSubnet'}]
    sample_input = [base.TestAimDBBase._get_example_aci_subnet(),
                    base.TestAimDBBase._get_example_aci_subnet(
                        dn='uni/tn-t1/BD-test/subnet-[10.10.20.0/28]')]
    sample_output = [
        resource.Subnet(tenant_name='t1',
                        bd_name='test',
                        gw_ip_mask='10.10.10.0/28',
                        scope=resource.Subnet.SCOPE_PRIVATE),
        resource.Subnet(tenant_name='t1',
                        bd_name='test',
                        gw_ip_mask='10.10.20.0/28',
                        scope=resource.Subnet.SCOPE_PRIVATE)]
    partial_change_input = {
        'fvSubnet': {
            'attributes': {
                'dn': 'uni/tn-t1/BD-test/subnet-[10.10.10.0/28]',
                'scope': 'public',
                'modTs': '2016-03-24T14:55:12.867+00:00',
                'rn': '', 'childAction': ''}}}
    partial_change_output = resource.Subnet(
        tenant_name='t1',
        bd_name='test',
        gw_ip_mask='10.10.10.0/28',
        scope=resource.Subnet.SCOPE_PUBLIC)


class TestAciToAimConverterTenant(TestAciToAimConverterBase,
                                  base.TestAimDBBase):
    resource_type = resource.Tenant
    reverse_map_output = [{'exceptions': {},
                           'resource': 'fvTenant'}]
    sample_input = [base.TestAimDBBase._get_example_aci_tenant(),
                    base.TestAimDBBase._get_example_aci_tenant(
                        dn='uni/tn-test-tenant1')]
    sample_output = [
        resource.Tenant(name='test-tenant'),
        resource.Tenant(name='test-tenant1')]


class TestAciToAimConverterAppProfile(TestAciToAimConverterBase,
                                      base.TestAimDBBase):
    resource_type = resource.ApplicationProfile
    reverse_map_output = [{'exceptions': {},
                           'resource': 'fvAp'}]
    sample_input = [base.TestAimDBBase._get_example_aci_app_profile(),
                    base.TestAimDBBase._get_example_aci_app_profile(
                        dn='uni/tn-test-tenant/ap-test-1')]
    sample_output = [
        resource.ApplicationProfile(tenant_name='test-tenant',
                                    name='test'),
        resource.ApplicationProfile(tenant_name='test-tenant',
                                    name='test-1')]


class TestAciToAimConverterEPG(TestAciToAimConverterBase, base.TestAimDBBase):
    resource_type = resource.EndpointGroup
    reverse_map_output = [{
        'resource': 'fvAEPg',
        'exceptions': {},
        'to_resource': converter.fv_aepg_to_resource}, {
        'resource': 'fvRsBd',
        'exceptions': {
            'bd_name': {
                'other': 'tnFvBDName'
            },
        },
        'to_resource': converter.fv_rs_bd_to_resource,
    }]
    sample_input = [base.TestAimDBBase._get_example_aci_epg(),
                    base.TestAimDBBase._get_example_aci_epg(
                        dn='uni/tn-t1/ap-a1/epg-test-1')]
    sample_output = [
        resource.EndpointGroup(tenant_name='t1',
                               app_profile_name='a1',
                               name='test'),
        resource.EndpointGroup(tenant_name='t1',
                               app_profile_name='a1',
                               name='test-1')]


class TestAimToAciConverterBase(object):
    sample_input = []
    sample_output = []
    missing_ref_input = None
    missing_ref_output = None

    def setUp(self):
        super(TestAimToAciConverterBase, self).setUp()
        self.converter = converter.AimToAciModelConverter()

    def _test_convert(self, example1, expected1, example2, expected2):
        result = self.converter.convert([example1])

        self.assertEqual(len(expected1), len(result))
        for item in expected1:
            self.assertTrue(item in result,
                            'Expected %s not in result %s' % (item, result))
        # Convert another BD
        result = self.converter.convert([example1, example2])
        self.assertEqual(len(expected1) + len(expected2), len(result))
        for item in expected1:
            self.assertTrue(item in result,
                            'Expected %s not in result %s' % (item, result))
        for item in expected2:
            self.assertTrue(item in result,
                            'Expected %s not in result %s' % (item, result))

    def _test_consistent_conversion(self, example_resource):
        to_aim_converter = converter.AciToAimModelConverter()
        # AIM to ACI
        result = self.converter.convert([example_resource])
        # Back to AIM
        result = to_aim_converter.convert(result)
        self.assertEqual([example_resource], result)

    def _test_non_existing_resource(self, example_resource, expected):
        result = self.converter.convert([example_resource, object()])
        # Extra resource is ignored
        self.assertEqual(len(expected), len(result))
        for item in expected:
            self.assertTrue(item in result,
                            'Expected %s not in result %s' % (item, result))

    def _test_missing_reference(self, example, expected):
        if example is None or expected is None:
            return
        result = self.converter.convert([example])
        self.assertEqual(len(expected), len(result))
        self.assertEqual(expected, result)

    def test_bd_consistent_conversion(self):
        self._test_consistent_conversion(self.sample_input[0])

    def test_non_existing_resource(self):
        self._test_non_existing_resource(self.sample_input[0],
                                         self.sample_output[0])

    def test_missing_reference(self):
        self._test_missing_reference(self.missing_ref_input,
                                     self.missing_ref_output)

    def test_convert(self):
        self._test_convert(self.sample_input[0], self.sample_output[0],
                           self.sample_input[1], self.sample_output[1])


class TestAimToAciConverterBD(TestAimToAciConverterBase, base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_bd(),
                    base.TestAimDBBase._get_example_aim_bd(
                        name='test-1', vrf_name='common')]
    sample_output = [
        [{
            "fvBD": {
                "attributes": {
                    "arpFlood": "no",
                    "dn": "uni/tn-test-tenant/BD-test",
                    "epMoveDetectMode": "",
                    "limitIpLearnToSubnets": "no",
                    "unicastRoute": "yes",
                    "unkMacUcastAct": "proxy"}}}, {
            "fvRsCtx": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/BD-test/rsctx",
                    'tnFvCtxName': 'default'}}}],
        [{
            "fvBD": {
                "attributes": {
                    "arpFlood": "no",
                    "dn": "uni/tn-test-tenant/BD-test-1",
                    "epMoveDetectMode": "",
                    "limitIpLearnToSubnets": "no",
                    "unicastRoute": "yes",
                    "unkMacUcastAct": "proxy"}}}, {
            "fvRsCtx": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/BD-test-1/rsctx",
                    'tnFvCtxName': 'common'}}}]]
    missing_ref_input = base.TestAimDBBase._get_example_aim_bd(vrf_name=None)
    missing_ref_output = [{
        "fvBD": {
            "attributes": {
                "arpFlood": "no",
                "dn": "uni/tn-test-tenant/BD-test",
                "epMoveDetectMode": "",
                "limitIpLearnToSubnets": "no",
                "unicastRoute": "yes",
                "unkMacUcastAct": "proxy"}}}]


class TestAimToAciConverterVRF(TestAimToAciConverterBase, base.TestAimDBBase):
    sample_input = [
        base.TestAimDBBase._get_example_aim_vrf(),
        base.TestAimDBBase._get_example_aim_vrf(
            name='test-1',
            policy_enforcement_pref=resource.VRF.POLICY_UNENFORCED)]
    sample_output = [
        [{
            "fvCtx": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ctx-test",
                    "pcEnfPref": "enforced"}}}],
        [{
            "fvCtx": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ctx-test-1",
                    "pcEnfPref": "unenforced"}}}]]


class TestAimToAciConverterSubnet(TestAimToAciConverterBase,
                                  base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_subnet(),
                    base.TestAimDBBase._get_example_aim_subnet(
                        gw_ip_mask='10.10.20.0/28',
                        scope=resource.Subnet.SCOPE_PUBLIC)]
    sample_output = [
        [{
            "fvSubnet": {
                "attributes": {
                    "dn": "uni/tn-t1/BD-test/subnet-[10.10.10.0/28]",
                    "scope": "private"}}}],
        [{
            "fvSubnet": {
                "attributes": {
                    "dn": "uni/tn-t1/BD-test/subnet-[10.10.20.0/28]",
                    "scope": "public"}}}]]


class TestAimToAciConverterAppProfile(TestAimToAciConverterBase,
                                      base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_app_profile(),
                    base.TestAimDBBase._get_example_aim_app_profile(
                        name='test1')]
    sample_output = [
        [{
            "fvAp": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ap-test"}}}],
        [{
            "fvAp": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ap-test1"}}}]]


class TestAimToAciConverterTenant(TestAimToAciConverterBase,
                                  base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_tenant(),
                    base.TestAimDBBase._get_example_aim_tenant(name='test1')]
    sample_output = [
        [{
            "fvTenant": {
                "attributes": {"dn": "uni/tn-test-tenant"}}}],
        [{
            "fvTenant": {
                "attributes": {"dn": "uni/tn-test1"}}}]]


class TestAimToAciConverterEPG(TestAimToAciConverterBase, base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_epg(),
                    base.TestAimDBBase._get_example_aim_epg(
                        name='test-1', bd_name='net2')]
    sample_output = [
        [{
            "fvAEPg": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test", }}}, {
            "fvRsBd": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test/rsbd",
                    "tnFvBDName": "net1"}}}],
        [{
            "fvAEPg": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-1", }}}, {
            "fvRsBd": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-1/rsbd",
                    "tnFvBDName": "net2"}}}]]
    missing_ref_input = base.TestAimDBBase._get_example_aim_epg(bd_name=None)
    missing_ref_output = [{
        "fvAEPg": {"attributes": {"dn": "uni/tn-t1/ap-a1/epg-test", }}}]
