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


class TestAciToAimConverter(base.TestAimDBBase):

    def setUp(self):
        super(TestAciToAimConverter, self).setUp()
        self.converter = converter.AciToAimModelConverter()

    def test_convert_bd(self):
        example_bd = self._get_example_bd()
        result = self.converter.convert([example_bd])
        # Expected object
        expected = resource.BridgeDomain(tenant_name='test-tenant',
                                         name='test',
                                         enable_arp_flood=False,
                                         enable_routing=True,
                                         limit_ip_learn_to_subnets=False,
                                         l2_unknown_unicast_mode='proxy',
                                         ep_move_detect_mode='')
        self.assertEqual(1, len(result))
        self.assertEqual(expected, result[0])
        # Convert another BD
        example_bd_2 = self._get_example_bd(dn='uni/tn-test-tenant/BD-test-1')
        expected_2 = resource.BridgeDomain(tenant_name='test-tenant',
                                           name='test-1',
                                           enable_arp_flood=False,
                                           enable_routing=True,
                                           limit_ip_learn_to_subnets=False,
                                           l2_unknown_unicast_mode='proxy',
                                           ep_move_detect_mode='')
        result = self.converter.convert([example_bd, example_bd_2])
        self.assertTrue(expected in result)
        self.assertTrue(expected_2 in result)

    def test_non_existing_resource(self):
        example_bd = self._get_example_bd()
        result = self.converter.convert([example_bd, {'fvCtxNonEx': {}}])
        expected = resource.BridgeDomain(tenant_name='test-tenant',
                                         name='test',
                                         enable_arp_flood=False,
                                         enable_routing=True,
                                         limit_ip_learn_to_subnets=False,
                                         l2_unknown_unicast_mode='proxy',
                                         ep_move_detect_mode='')
        # Extra resource is ignored
        self.assertEqual(1, len(result))
        self.assertEqual(expected, result[0])

    def test_non_uni_dn(self):
        example_bd = self._get_example_bd(dn='tn-test-tenant/BD-test')
        result = self.converter.convert([example_bd])
        expected = resource.BridgeDomain(tenant_name='test-tenant',
                                         name='test',
                                         enable_arp_flood=False,
                                         enable_routing=True,
                                         limit_ip_learn_to_subnets=False,
                                         l2_unknown_unicast_mode='proxy',
                                         ep_move_detect_mode='')
        # Extra resource is ignored
        self.assertEqual(1, len(result))
        self.assertEqual(expected, result[0])

    def test_reverse_map(self):
        # test based on the BD resource
        bd_reverse = converter.reverse_resource_map[resource.BridgeDomain]
        expected = [{
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
        self.assertTrue(expected[0] in bd_reverse,
                        'Expceted %s not in %s' % (expected[0], bd_reverse))
        self.assertTrue(expected[1] in bd_reverse,
                        'Expceted %s not in %s' % (expected[0], bd_reverse))
        self.assertEqual(2, len(bd_reverse))

    def test_partial_change(self):
        partial_bd = [{
            'fvBD': {'attributes': {
                'dn': 'uni/tn-test-tenant/BD-test',
                'status': 'modified',
                'unkMacUcastAct': 'flood',
                'arpFlood': 'yes', 'seg': '14909412',
                'modTs': '2016-03-24T14:55:12.867+00:00',
                'rn': '', 'childAction': ''}}}]
        expected = resource.BridgeDomain(tenant_name='test-tenant',
                                         name='test',
                                         enable_arp_flood=True,
                                         l2_unknown_unicast_mode='flood')
        result = self.converter.convert(partial_bd)
        # Verify that dictionary doesn't have more values than it should
        self.assertEqual({'tenant_name': 'test-tenant',
                          'name': 'test', 'enable_arp_flood': True,
                          'l2_unknown_unicast_mode': 'flood'},
                         expected.__dict__)
        self.assertEqual(expected, result[0])

    def test_deleted_object(self):
        deleted_bd = [{
            'fvBD': {'attributes': {
                'dn': 'uni/tn-test-tenant/BD-test',
                'status': 'deleted'}}}]
        expected = resource.BridgeDomain(tenant_name='test-tenant',
                                         name='test',
                                         _status='deleted')
        result = self.converter.convert(deleted_bd)
        self.assertEqual({'tenant_name': 'test-tenant',
                          'name': 'test', '_status': 'deleted'},
                         expected.__dict__)
        self.assertEqual(expected, result[0])


class TestAimToAciConverter(base.TestAimDBBase):

    def setUp(self):
        super(TestAimToAciConverter, self).setUp()
        self.converter = converter.AimToAciModelConverter()

    def test_convert_bd(self):
        example_bd = self._get_example_bridge_domain()
        result = self.converter.convert([example_bd])
        # Expected object
        expected = [
            {
                "fvBD": {
                    "attributes": {
                        "arpFlood": "no",
                        "dn": "uni/tn-test-tenant/BD-test",
                        "epMoveDetectMode": "",
                        "limitIpLearnToSubnets": "no",
                        "unicastRoute": "yes",
                        "unkMacUcastAct": "proxy"}}},
            {
                "fvRsCtx": {
                    "attributes": {
                        "dn": "uni/tn-test-tenant/BD-test/rsctx",
                        'tnFvCtxName': 'default'}}}
        ]

        self.assertEqual(2, len(result))
        self.assertTrue(expected[0] in result,
                        'Expected %s not in result %s' % (expected[0], result))
        self.assertTrue(expected[1] in result,
                        'Expected %s not in result %s' % (expected[1], result))
        # Convert another BD
        example_bd_2 = self._get_example_bridge_domain(name='test-1',
                                                       vrf_name='common')
        expected_2 = [
            {
                "fvBD": {
                    "attributes": {
                        "arpFlood": "no",
                        "dn": "uni/tn-test-tenant/BD-test-1",
                        "epMoveDetectMode": "",
                        "limitIpLearnToSubnets": "no",
                        "unicastRoute": "yes",
                        "unkMacUcastAct": "proxy"}}},
            {
                "fvRsCtx": {
                    "attributes": {
                        "dn": "uni/tn-test-tenant/BD-test-1/rsctx",
                        'tnFvCtxName': 'common'}}}
        ]
        result = self.converter.convert([example_bd, example_bd_2])
        self.assertEqual(4, len(result))
        self.assertTrue(expected[0] in result,
                        'Expected %s not in result %s' % (expected[0], result))
        self.assertTrue(expected[1] in result,
                        'Expected %s not in result %s' % (expected[1], result))
        self.assertTrue(expected_2[0] in result,
                        'Expected %s not in result %s' % (expected[0], result))
        self.assertTrue(expected_2[1] in result,
                        'Expected %s not in result %s' % (expected[1], result))

    def test_consistent_conversion(self):
        to_aim_converter = converter.AciToAimModelConverter()
        example_bd = self._get_example_bridge_domain()
        # AIM to ACI
        result = self.converter.convert([example_bd])
        # Back to AIM
        result = to_aim_converter.convert(result)
        self.assertEqual(example_bd, result[0])

    def test_non_existing_resource(self):
        example_bd = self._get_example_bridge_domain()
        result = self.converter.convert([example_bd, object()])
        expected = [
            {
                "fvBD": {
                    "attributes": {
                        "arpFlood": "no",
                        "dn": "uni/tn-test-tenant/BD-test",
                        "epMoveDetectMode": "",
                        "limitIpLearnToSubnets": "no",
                        "unicastRoute": "yes",
                        "unkMacUcastAct": "proxy"}}},
            {
                "fvRsCtx": {
                    "attributes": {
                        "dn": "uni/tn-test-tenant/BD-test/rsctx",
                        'tnFvCtxName': 'default'}}}
        ]
        # Extra resource is ignored
        self.assertEqual(2, len(result))
        self.assertTrue(expected[0] in result,
                        'Expected %s not in result %s' % (expected[0], result))
        self.assertTrue(expected[1] in result,
                        'Expected %s not in result %s' % (expected[1], result))

    def test_missing_reference(self):
        example_bd = self._get_example_bridge_domain()
        example_bd.vrf_name = None
        result = self.converter.convert([example_bd])
        self.assertEqual(1, len(result))
        expected = [
            {
                "fvBD": {
                    "attributes": {
                        "arpFlood": "no",
                        "dn": "uni/tn-test-tenant/BD-test",
                        "epMoveDetectMode": "",
                        "limitIpLearnToSubnets": "no",
                        "unicastRoute": "yes",
                        "unkMacUcastAct": "proxy"}}}
        ]
        self.assertEqual(expected, result)
