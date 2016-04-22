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

    def _test_convert(self, example1, expected1, example2, expected2):
        result = self.converter.convert(example1)
        self.assertEqual(len(expected1), len(result))
        for item in expected1:
            self.assertTrue(item in result)

        result = self.converter.convert(example1 + example2)
        self.assertEqual(len(expected1) + len(expected2), len(result))
        for item in expected1:
            self.assertTrue(item in result)
        for item in expected2:
            self.assertTrue(item in result)

    def _test_non_existing_resource(self, example, expected):
        result = self.converter.convert(example + [{'fvCtxNonEx': {}}])
        # Extra resource is ignored
        self.assertEqual(len(expected), len(result))
        for item in expected:
            self.assertTrue(item in result)

    def _test_partial_change(self, partial, expected):
        result = self.converter.convert(partial)
        for item in expected:
            self.assertTrue(item in result)

    def _test_deleted_object(self, example, expected):
        for item in example:
            item.values()[0]['status'] = 'deleted'
        for item in expected:
            item._status = 'deleted'
        result = self.converter.convert(example)
        self.assertEqual(len(expected), len(result))
        for item in expected:
            self.assertTrue(item in result)

    def test_bd_reverse_map(self):
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

    # Test BD conversion strategy

    def test_bd_convert(self):
        example1 = self._get_example_aci_bd()
        expected1 = resource.BridgeDomain(tenant_name='test-tenant',
                                          name='test',
                                          enable_arp_flood=False,
                                          enable_routing=True,
                                          limit_ip_learn_to_subnets=False,
                                          l2_unknown_unicast_mode='proxy',
                                          ep_move_detect_mode='')
        example2 = self._get_example_aci_bd(
            dn='uni/tn-test-tenant/BD-test-1')
        expected2 = resource.BridgeDomain(tenant_name='test-tenant',
                                          name='test-1',
                                          enable_arp_flood=False,
                                          enable_routing=True,
                                          limit_ip_learn_to_subnets=False,
                                          l2_unknown_unicast_mode='proxy',
                                          ep_move_detect_mode='')
        self._test_convert([example1], [expected1], [example2], [expected2])

    def test_bd_non_existing_resource(self):
        example = self._get_example_aci_bd()
        expected = resource.BridgeDomain(tenant_name='test-tenant',
                                         name='test',
                                         enable_arp_flood=False,
                                         enable_routing=True,
                                         limit_ip_learn_to_subnets=False,
                                         l2_unknown_unicast_mode='proxy',
                                         ep_move_detect_mode='')
        self._test_non_existing_resource([example], [expected])

    def test_bd_partial_change(self):
        partial_bd = {
            'fvBD': {'attributes': {
                'dn': 'uni/tn-test-tenant/BD-test',
                'status': 'modified',
                'unkMacUcastAct': 'flood',
                'arpFlood': 'yes', 'seg': '14909412',
                'modTs': '2016-03-24T14:55:12.867+00:00',
                'rn': '', 'childAction': ''}}}
        expected = resource.BridgeDomain(tenant_name='test-tenant',
                                         name='test',
                                         enable_arp_flood=True,
                                         l2_unknown_unicast_mode='flood')
        self._test_partial_change([partial_bd], [expected])

    def test_bd_deleted_object(self):
        example = self._get_example_aci_bd()
        expected = resource.BridgeDomain(tenant_name='test-tenant',
                                         name='test',
                                         enable_arp_flood=False,
                                         enable_routing=True,
                                         limit_ip_learn_to_subnets=False,
                                         l2_unknown_unicast_mode='proxy',
                                         ep_move_detect_mode='')
        self._test_deleted_object([example], [expected])


class TestAimToAciConverter(base.TestAimDBBase):

    def setUp(self):
        super(TestAimToAciConverter, self).setUp()
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
    # Test BD conversion strategy

    def test_bd_consistent_conversion(self):
        self._test_consistent_conversion(self._get_example_aim_bd())

    def test_bd_non_existing_resource(self):
        self._test_non_existing_resource(
            self._get_example_aim_bd(),
            [
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
                            'tnFvCtxName': 'default'}}}])

    def test_bd_missing_reference(self):
        example_bd = self._get_example_aim_bd()
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

    def test_bd_convert(self):
        expected1 = [
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
        expected2 = [
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
        self._test_convert(self._get_example_aim_bd(), expected1,
                           self._get_example_aim_bd(name='test-1',
                                                    vrf_name='common'),
                           expected2)

    # Test VRF conversion strategy

    # def test_vrf_consistent_conversion(self):
    #     self._test_consistent_conversion(self._get_example_aim_vrf())

    # def test_vrf_non_existing_resource(self):
    #     self._test_non_existing_resource(
    #         self._get_example_aim_vrf(),
    #         [{
    #             "fvCtx": {
    #                 "attributes": {
    #                     "dn": "uni/tn-test-tenant/ctx-test",
    #                     "pcEnfPref": "enforced"}}}])

    # def test_vrf_convert(self):
    #     expected1 = [
    #         {
    #             "fvCtx": {
    #                 "attributes": {
    #                     "dn": "uni/tn-test-tenant/ctx-test",
    #                     "pcEnfPref": "enforced"}}}
    #     ]
    #     expected2 = [
    #         {
    #             "fvCtx": {
    #                 "attributes": {
    #                     "dn": "uni/tn-test-tenant/ctx-test-1",
    #                     "pcEnfPref": "unenforced"}}}
    #     ]
    #     self._test_convert(self._get_example_aim_vrf(), expected1,
    #                        self._get_example_aim_vrf(
    #                            name='test-1', policy_enforcement_pref=2),
    #                        expected2)
