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

import pprint

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes.aci.converters import (
    service_graph as conv_service_graph)
from aim.agent.aid.universes.aci.converters import utils as conv_utils
from aim.api import infra as aim_infra
from aim.api import resource
from aim.api import service_graph as aim_service_graph
from aim.api import status as aim_status
from aim import config as aim_cfg
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

    def _dump(self, res):
        return ([r.__dict__ for r in res] if isinstance(res, list)
                else res.__dict__)

    def _test_convert(self, example1, expected1, example2, expected2):
        result = self.converter.convert(example1)
        self.assertEqual(len(expected1), len(result))
        for item in expected1:
            self.assertTrue(
                item in result,
                'Expected\n%s\nnot in\n%s' % (self._dump(item),
                                              self._dump(result)))

        result = self.converter.convert(example1 + example2)
        self.assertEqual(len(expected1) + len(expected2), len(result))
        for item in expected1:
            self.assertTrue(item in result,
                            'Expected\n%s\nnot in\n%s' % (self._dump(item),
                                                          self._dump(result)))
        for item in expected2:
            self.assertTrue(
                item in result,
                'Expected\n%s\nnot in\n%s' % (self._dump(item),
                                              self._dump(result)))

    def _test_non_existing_resource(self, example, expected):
        result = self.converter.convert(example + [{'fvCtxNonEx': {}}])
        # Extra resource is ignored
        self.assertEqual(len(expected), len(result))
        for item in expected:
            self.assertTrue(
                item in result,
                'Expected\n%s\nnot in\n%s' % (self._dump(item),
                                              self._dump(result)))

    def _test_partial_change(self, partial, expected):
        if (self.partial_change_input is None or
                self.partial_change_output is None):
            return
        result = self.converter.convert(partial)
        for item in expected:
            self.assertTrue(
                item in result,
                'Expected\n%s\nnot in\n%s' % (self._dump(item),
                                              self._dump(result)))

    def _test_deleted_object(self, example, expected):
        for item in example:
            list(item.values())[0]['status'] = 'deleted'
        for item in expected:
            item._status = 'deleted'
        result = self.converter.convert(example)
        self.assertEqual(len(expected), len(result),
                         '\nexpected: %s\ncurrent: %s' % (expected, result))
        for item in expected:
            self.assertTrue(
                item in result,
                'Expected\n%s\nnot in\n%s' % (self._dump(item),
                                              self._dump(result)))

    def _test_reverse_map(self, resource_type, expected):
        reverse = converter.reverse_resource_map[resource_type]
        self.assertEqual(len(expected), len(reverse),
                         '\nExpected:\n%s\nFound:\n%s' %
                            (pprint.pformat(expected),
                             pprint.pformat(reverse)))
        for idx in range(len(expected)):
            self.assertTrue(expected[idx] in reverse,
                            '\nExpected:\n%s\nnot in\n%s' %
                            (pprint.pformat(expected[idx]),
                             pprint.pformat(reverse)))

    def _to_list(self, obj):
        return obj if isinstance(obj, list) else [obj]

    def test_reverse_map(self):
        self._test_reverse_map(self.resource_type, self.reverse_map_output)

    def test_convert(self):
        self.assertEqual(2, len(self.sample_input))
        self.assertEqual(2, len(self.sample_output))

        self._test_convert(self._to_list(self.sample_input[0]),
                           [self.sample_output[0]],
                           self._to_list(self.sample_input[1]),
                           [self.sample_output[1]])

    def test_non_existing_resource(self):
        self._test_non_existing_resource(self._to_list(self.sample_input[0]),
                                         [self.sample_output[0]])

    def test_partial_change(self):
        self._test_partial_change([self.partial_change_input],
                                  [self.partial_change_output])

    def test_deleted_object(self):
        self._test_deleted_object(self._to_list(self.sample_input[0]),
                                  [self.sample_output[0]])


def _aci_obj(mo_type, **attr):
    return {mo_type: {'attributes': attr}}


class TestAciToAimConverterBD(TestAciToAimConverterBase, base.TestAimDBBase):
    resource_type = resource.BridgeDomain
    reverse_map_output = [
        {'resource': 'fvBD',
         'exceptions': {'enable_arp_flood': {'other': 'arpFlood',
                                             'converter': converter.boolean},
                        'enable_routing': {'other': 'unicastRoute',
                                           'converter': converter.boolean},
                        'limit_ip_learn_to_subnets': {
                        'other': 'limitIpLearnToSubnets',
                        'converter': converter.boolean},
                        'l2_unknown_unicast_mode': {
                        'other': 'unkMacUcastAct', },
                        'ip_learning': {'other': 'ipLearning',
                                        'converter': converter.boolean}, },
         'identity_converter': None,
         'converter': None,
         'skip': ['vrfName', 'l3outNames']},
        {'resource': 'fvRsCtx',
         'exceptions': {'vrf_name': {'other': 'tnFvCtxName'}},
         'to_resource': converter.default_to_resource_strict},
        {'resource': 'fvRsBDToOut',
         'exceptions': {},
         'converter': converter.fvRsBDToOut_converter, }]
    sample_input = [base.TestAimDBBase._get_example_aci_bd(),
                    [base.TestAimDBBase._get_example_aci_bd(
                        dn='uni/tn-test-tenant/BD-test-1',
                        nameAlias='alias',
                        ipLearning='no'),
                     _aci_obj('fvRsCtx',
                              dn='uni/tn-test-tenant/BD-test-1/rsctx',
                              tnFvCtxName='shared'),
                     _aci_obj('fvRsBDToOut',
                              dn='uni/tn-test-tenant/BD-test-1/rsBDToOut-o1',
                              tnL3extOutName='o1')]]
    sample_output = [
        resource.BridgeDomain(tenant_name='test-tenant',
                              name='test',
                              enable_arp_flood=False,
                              enable_routing=True,
                              limit_ip_learn_to_subnets=False,
                              ip_learning=True,
                              l2_unknown_unicast_mode='proxy',
                              ep_move_detect_mode=''),
        resource.BridgeDomain(tenant_name='test-tenant',
                              name='test-1',
                              enable_arp_flood=False,
                              enable_routing=True,
                              limit_ip_learn_to_subnets=False,
                              ip_learning=False,
                              l2_unknown_unicast_mode='proxy',
                              ep_move_detect_mode='',
                              vrf_name='shared',
                              l3out_names=['o1'],
                              display_name='alias')]
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
                        dn='uni/tn-test-tenant/ctx-test-1',
                        nameAlias='alias')]
    sample_output = [
        resource.VRF(tenant_name='test-tenant',
                     name='test',
                     policy_enforcement_pref=resource.VRF.POLICY_ENFORCED),
        resource.VRF(tenant_name='test-tenant',
                     name='test-1',
                     policy_enforcement_pref=resource.VRF.POLICY_ENFORCED,
                     display_name='alias')]
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
                        dn='uni/tn-t1/BD-test/subnet-[10.10.20.0/28]',
                        nameAlias='alias')]
    sample_output = [
        resource.Subnet(tenant_name='t1',
                        bd_name='test',
                        gw_ip_mask='10.10.10.0/28',
                        scope=resource.Subnet.SCOPE_PRIVATE),
        resource.Subnet(tenant_name='t1',
                        bd_name='test',
                        gw_ip_mask='10.10.20.0/28',
                        scope=resource.Subnet.SCOPE_PRIVATE,
                        display_name='alias')]
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
    sample_input = [base.TestAimDBBase._get_example_aci_tenant(nameAlias='tt'),
                    base.TestAimDBBase._get_example_aci_tenant(
                        dn='uni/tn-test-tenant1', descr='my description')]
    sample_output = [
        resource.Tenant(name='test-tenant', display_name='tt'),
        resource.Tenant(name='test-tenant1', descr='my description')]


class TestAciToAimConverterAppProfile(TestAciToAimConverterBase,
                                      base.TestAimDBBase):
    resource_type = resource.ApplicationProfile
    reverse_map_output = [{'exceptions': {},
                           'resource': 'fvAp'}]
    sample_input = [base.TestAimDBBase._get_example_aci_app_profile(),
                    base.TestAimDBBase._get_example_aci_app_profile(
                        dn='uni/tn-test-tenant/ap-test-1',
                        nameAlias='alias')]
    sample_output = [
        resource.ApplicationProfile(tenant_name='test-tenant',
                                    name='test'),
        resource.ApplicationProfile(tenant_name='test-tenant',
                                    name='test-1',
                                    display_name='alias')]


class TestAciToAimConverterEPG(TestAciToAimConverterBase, base.TestAimDBBase):
    resource_type = resource.EndpointGroup
    reverse_map_output = [
        {'resource': 'fvAEPg',
         'exceptions': {'policy_enforcement_pref': {'other': 'pcEnfPref'}, },
         'skip': ['bdName', 'providedContractNames',
                  'consumedContractNames',
                  'openstackVmmDomainNames',
                  'physicalDomainNames',
                  'physicalDomains',
                  'vmmDomains',
                  'staticPaths',
                  'epgContractMasters']},
        {'resource': 'fvRsBd',
         'exceptions': {'bd_name': {'other': 'tnFvBDName'}, },
         'to_resource': converter.default_to_resource_strict, },
        {'resource': 'fvRsProv',
         'exceptions': {},
         'converter': converter.fvRsProv_converter, },
        {'resource': 'fvRsCons',
         'exceptions': {},
         'converter': converter.fvRsCons_converter, },
        {'resource': 'fvRsDomAtt',
         'exceptions': {},
         'converter': converter.fv_rs_dom_att_converter, },
        {'resource': 'fvRsPathAtt',
         'exceptions': {},
         'converter': converter.fv_rs_path_att_converter, },
        {'resource': 'fvRsSecInherited',
         'exceptions': {},
         'converter': converter.fv_rs_master_epg_converter, }
    ]
    sample_input = [[base.TestAimDBBase._get_example_aci_epg(nameAlias='alia'),
                     {'fvRsBd':
                      {'attributes':
                       {'dn': 'uni/tn-t1/ap-a1/epg-test/rsbd',
                        'tnFvBDName': 'bd1', }}},
                     {'fvRsProv':
                      {'attributes':
                       {'dn': 'uni/tn-t1/ap-a1/epg-test/rsprov-p1',
                        'tnVzBrCPName': 'p1', }}},
                     {'fvRsProv':
                      {'attributes':
                       {'dn': 'uni/tn-t1/ap-a1/epg-test/rsprov-k',
                        'tnVzBrCPName': 'k', }}},
                     {'fvRsCons':
                      {'attributes':
                       {'dn': 'uni/tn-t1/ap-a1/epg-test/rscons-c1',
                        'tnVzBrCPName': 'c1', }}},
                     {'fvRsCons':
                      {'attributes':
                       {'dn': 'uni/tn-t1/ap-a1/epg-test/rscons-k',
                        'tnVzBrCPName': 'k', }}},
                     {'fvRsDomAtt':
                      {'attributes':
                       {'dn': 'uni/tn-t1/ap-a1/epg-test/'
                              'rsdomAtt-[uni/phys-phys]', }}},
                     {'fvRsDomAtt':
                      {'attributes':
                       {'dn': 'uni/tn-t1/ap-a1/epg-test/'
                              'rsdomAtt-[uni/vmmp-OpenStack/dom-op]', }}},
                     {'fvRsDomAtt':
                      {'attributes':
                       {'dn': 'uni/tn-t1/ap-a1/epg-test/'
                              'rsdomAtt-[uni/vmmp-OpenStack/dom-op2]', }}},
                     _aci_obj('fvRsPathAtt',
                              dn='uni/tn-t1/ap-a1/epg-test/rspathAtt-'
                                 '[topology/pod-1/paths-202/pathep-[eth1/7]]',
                              tDn='topology/pod-1/paths-202/pathep-[eth1/7]',
                              encap='vlan-33'),
                     _aci_obj('fvRsPathAtt',
                              dn='uni/tn-t1/ap-a1/epg-test/rspathAtt-'
                                 '[topology/pod-1/paths-102/pathep-[eth1/2]]',
                              tDn='topology/pod-1/paths-102/pathep-[eth1/2]',
                              encap='vlan-39', mode='untagged'),
                     _aci_obj('fvRsSecInherited',
                              dn='uni/tn-t1/ap-a1/epg-test/rssecInherited-'
                                 '[uni/tn-t1/ap-masterap1/epg-masterepg1]',
                              tDn='uni/tn-t1/ap-masterap1/epg-masterepg1'),
                     ],
                    base.TestAimDBBase._get_example_aci_epg(
                        dn='uni/tn-t1/ap-a1/epg-test-1',
                        pcEnfPref='enforced')]
    sample_output = [
        resource.EndpointGroup(tenant_name='t1',
                               app_profile_name='a1',
                               name='test', bd_name='bd1',
                               policy_enforcement_pref=(
                                   resource.EndpointGroup.POLICY_UNENFORCED),
                               provided_contract_names=['p1', 'k'],
                               consumed_contract_names=['c1', 'k'],
                               openstack_vmm_domain_names=['op', 'op2'],
                               physical_domain_names=['phys'],
                               vmm_domains=[{'type': 'OpenStack',
                                             'name': 'op'},
                                            {'type': 'OpenStack',
                                             'name': 'op2'}],
                               physical_domains=[{'name': 'phys'}],
                               static_paths=[{'path': 'topology/pod-1/paths'
                                                      '-202/pathep-[eth1/7]',
                                              'encap': 'vlan-33',
                                              'mode': 'regular'},
                                             {'path': 'topology/pod-1/paths'
                                                      '-102/pathep-[eth1/2]',
                                              'encap': 'vlan-39',
                                              'mode': 'untagged'}],
                               epg_contract_masters=[
                                   {'app_profile_name': 'masterap1',
                                    'name': 'masterepg1'}],
                               display_name='alia'),
        resource.EndpointGroup(tenant_name='t1',
                               app_profile_name='a1',
                               name='test-1',
                               policy_enforcement_pref=(
                                   resource.EndpointGroup.POLICY_ENFORCED))]


def get_example_aci_filter(**kwargs):
    attr = {'name': 'f1',
            'dn': 'uni/tn-test-tenant/flt-f1'}
    attr.update(**kwargs)
    return _aci_obj('vzFilter', **attr)


class TestAciToAimConverterFilter(TestAciToAimConverterBase,
                                  base.TestAimDBBase):
    resource_type = resource.Filter
    reverse_map_output = [{'exceptions': {},
                           'resource': 'vzFilter'}]
    sample_input = [get_example_aci_filter(),
                    get_example_aci_filter(dn='uni/tn-test-tenant/flt-f2',
                                           nameAlias='alias')]
    sample_output = [
        resource.Filter(tenant_name='test-tenant', name='f1'),
        resource.Filter(tenant_name='test-tenant', name='f2',
                        display_name='alias')]


def get_example_aci_filter_entry(**kwargs):
    attr = {'name': 'e1',
            'dn': 'uni/tn-test-tenant/flt-f1/e-e1',
            'arpOpc': 'req',
            'etherT': 'arp',
            'icmpv4T': 'unspecified', 'icmpv6T': 'unspecified',
            'sFromPort': '200', 'sToPort': 'https',
            'dFromPort': '2000', 'dToPort': '4000',
            'tcpRules': 'est',
            'stateful': 'yes',
            'applyToFrag': 'no'}
    attr.update(**kwargs)
    return _aci_obj('vzEntry', **attr)


class TestAciToAimConverterFilterEntry(TestAciToAimConverterBase,
                                       base.TestAimDBBase):
    resource_type = resource.FilterEntry
    reverse_map_output = [{
        'resource': 'vzEntry',
        'exceptions': {
            'arp_opcode': {'other': 'arpOpc',
                           'converter': converter.arp_opcode},
            'ether_type': {'other': 'etherT',
                           'converter': converter.ether_type},
            'ip_protocol': {'other': 'prot',
                            'converter': converter.ip_protocol},
            'icmpv4_type': {'other': 'icmpv4T',
                            'converter': converter.icmpv4_type},
            'icmpv6_type': {'other': 'icmpv6T',
                            'converter': converter.icmpv6_type},
            'source_from_port': {'other': 'sFromPort',
                                 'converter': converter.port},
            'source_to_port': {'other': 'sToPort',
                               'converter': converter.port},
            'dest_from_port': {'other': 'dFromPort',
                               'converter': converter.port},
            'dest_to_port': {'other': 'dToPort',
                             'converter': converter.port},
            'tcp_flags': {'other': 'tcpRules',
                          'converter': converter.tcp_flags},
            'stateful': {'other': 'stateful',
                         'converter': converter.boolean},
            'fragment_only': {'other': 'applyToFrag',
                              'converter': converter.boolean}
        },
    }]
    sample_input = [get_example_aci_filter_entry(),
                    get_example_aci_filter_entry(
                        dn='uni/tn-test-tenant/flt-f1/e-e2',
                        etherT='unspecified',
                        dFromPort='unspecified', dToPort='unspecified',
                        stateful='no',
                        applyToFrag='yes', nameAlias='alias')]
    sample_output = [
        resource.FilterEntry(tenant_name='test-tenant', filter_name='f1',
                             name='e1', arp_opcode='req', ether_type='arp',
                             source_from_port='200', source_to_port='https',
                             dest_from_port='2000', dest_to_port='4000',
                             tcp_flags='est', stateful=True),
        resource.FilterEntry(tenant_name='test-tenant', filter_name='f1',
                             name='e2', arp_opcode='req',
                             source_from_port='200', source_to_port='https',
                             tcp_flags='est', fragment_only=True,
                             display_name='alias')]
    partial_change_input = _aci_obj('vzEntry',
                                    dn='uni/tn-test-tenant/flt-f1/e-e1',
                                    status='modified',
                                    prot='icmp',
                                    tcpRules='rst',
                                    stateful='yes',
                                    modTs='2016-03-24T14:55:12.867+00:00',
                                    rn='', childAction='')
    partial_change_output = resource.FilterEntry(
        tenant_name='test-tenant', filter_name='f1', name='e1',
        ip_protocol='icmp', tcp_flags='rst', stateful=True)


def get_example_aci_contract(**kwargs):
    attr = {'name': 'c1',
            'dn': 'uni/tn-test-tenant/brc-c1',
            'scope': 'context'}
    attr.update(**kwargs)
    return _aci_obj('vzBrCP', **attr)


class TestAciToAimConverterContract(TestAciToAimConverterBase,
                                    base.TestAimDBBase):
    resource_type = resource.Contract
    reverse_map_output = [{'exceptions': {},
                           'resource': 'vzBrCP'}]
    sample_input = [get_example_aci_contract(),
                    get_example_aci_contract(dn='uni/tn-test-tenant/brc-c2',
                                             scope='tenant',
                                             nameAlias='alias')]
    sample_output = [
        resource.Contract(tenant_name='test-tenant', name='c1'),
        resource.Contract(tenant_name='test-tenant', name='c2',
                          scope='tenant', display_name='alias')]


def get_example_aci_subject(**kwargs):
    attr = {'name': 's1',
            'dn': 'uni/tn-t1/brc-c/subj-s'}
    attr.update(**kwargs)
    return _aci_obj('vzSubj', **attr)


class TestAciToAimConverterContractSubject(TestAciToAimConverterBase,
                                           base.TestAimDBBase):
    resource_type = resource.ContractSubject
    reverse_map_output = [
        {'resource': 'vzSubj',
         'exceptions': {},
         'skip': ['inFilters', 'outFilters', 'biFilters',
                  'serviceGraphName', 'inServiceGraphName',
                  'outServiceGraphName']},
        {'resource': 'vzRsSubjFiltAtt',
         'exceptions': {},
         'converter': converter.vzRsSubjFiltAtt_converter},
        {'resource': 'vzRsSubjGraphAtt',
         'exceptions': {'service_graph_name': {'other': 'tnVnsAbsGraphName',
                                               'skip_if_empty': True}},
         'to_resource': converter.default_to_resource_strict},
        {'resource': 'vzRsFiltAtt',
         'exceptions': {},
         'converter': converter.vzInTerm_vzRsFiltAtt_converter},
        {'resource': 'vzRsFiltAtt',
         'exceptions': {},
         'converter': converter.vzOutTerm_vzRsFiltAtt_converter},
        {'resource': 'vzInTerm',
         'exceptions': {},
         'skip': ['displayName'],
         'to_resource': converter.to_resource_filter_container},
        {'resource': 'vzOutTerm',
         'exceptions': {},
         'skip': ['displayName'],
         'to_resource': converter.to_resource_filter_container},
        {'resource': 'vzRsInTermGraphAtt',
         'exceptions': {'in_service_graph_name':
                        {'other': 'tnVnsAbsGraphName',
                         'skip_if_empty': True}},
         'to_resource': converter.default_to_resource_strict},
        {'resource': 'vzRsOutTermGraphAtt',
         'exceptions': {'out_service_graph_name':
                        {'other': 'tnVnsAbsGraphName',
                         'skip_if_empty': True}},
         'to_resource': converter.default_to_resource_strict}]
    sample_input = [[get_example_aci_subject(nameAlias='alias'),
                     _aci_obj('vzRsSubjFiltAtt',
                              dn='uni/tn-t1/brc-c/subj-s/rssubjFiltAtt-f1',
                              tnVzFilterName='f1'),
                     _aci_obj('vzRsSubjFiltAtt',
                              dn='uni/tn-t1/brc-c/subj-s/rssubjFiltAtt-f2',
                              tnVzFilterName='f2'),
                     _aci_obj('vzRsSubjGraphAtt',
                              dn='uni/tn-t1/brc-c/subj-s/rsSubjGraphAtt',
                              tnVnsAbsGraphName='g1'),
                     _aci_obj('vzInTerm',
                              dn='uni/tn-t1/brc-c/subj-s/intmnl'),
                     _aci_obj('vzOutTerm',
                              dn='uni/tn-t1/brc-c/subj-s/outtmnl'),
                     _aci_obj('vzRsFiltAtt',
                              dn='uni/tn-t1/brc-c/subj-s/intmnl/rsfiltAtt-i1',
                              tnVzFilterName='i1'),
                     _aci_obj('vzRsFiltAtt',
                              dn='uni/tn-t1/brc-c/subj-s/intmnl/rsfiltAtt-i2',
                              tnVzFilterName='i2'),
                     _aci_obj('vzRsFiltAtt',
                              dn='uni/tn-t1/brc-c/subj-s/outtmnl/rsfiltAtt-o1',
                              tnVzFilterName='o1'),
                     _aci_obj('vzRsFiltAtt',
                              dn='uni/tn-t1/brc-c/subj-s/outtmnl/rsfiltAtt-o2',
                              tnVzFilterName='o2'),
                     _aci_obj('vzRsInTermGraphAtt',
                              dn='uni/tn-t1/brc-c/subj-s/intmnl/'
                                 'rsInTermGraphAtt',
                              tnVnsAbsGraphName='g2'),
                     _aci_obj('vzRsOutTermGraphAtt',
                              dn='uni/tn-t1/brc-c/subj-s/outtmnl/'
                                 'rsOutTermGraphAtt',
                              tnVnsAbsGraphName='g3'), ],
                    [{'vzSubj': {
                        'attributes': {
                            'dn': 'uni/tn-common/brc-prs1/subj-prs1',
                            'revFltPorts': 'yes', 'nameAlias': 'prs1',
                            'name': 'prs1', 'prio': 'unspecified',
                            'targetDscp': 'unspecified', 'descr': '',
                            'consMatchT': 'AtleastOne',
                            'provMatchT': 'AtleastOne'}}},
                     {'vzRsFiltAtt': {
                         'attributes': {
                             'dn': 'uni/tn-common/brc-prs1/subj-prs1/intmnl'
                                   '/rsfiltAtt-reverse-pr1', 'directives': '',
                             'tnVzFilterName': 'reverse-pr1'}}},
                     {'vzRsFiltAtt': {
                         'attributes': {
                             'dn': 'uni/tn-common/brc-prs1/subj-prs1/intmnl'
                                   '/rsfiltAtt-pr1',
                             'directives': '', 'tnVzFilterName': 'pr1'}}},
                     {'vzRsFiltAtt': {
                         'attributes': {
                             'dn': 'uni/tn-common/brc-prs1/subj-prs1/outtmnl'
                                   '/rsfiltAtt-pr1', 'directives': '',
                             'tnVzFilterName': 'pr1'}}},
                     {'vzRsFiltAtt': {
                         'attributes': {
                             'dn': 'uni/tn-common/brc-prs1/subj-prs1/outtmnl'
                                   '/rsfiltAtt-reverse-pr1', 'directives': '',
                             'tnVzFilterName': 'reverse-pr1'}}},
                     {'vzInTerm': {
                         'attributes': {
                             'dn': 'uni/tn-common/brc-prs1/subj-prs1/intmnl',
                             'nameAlias': '', 'name': '', 'descr': '',
                             'targetDscp': 'unspecified',
                             'prio': 'unspecified'}}},
                     {'vzOutTerm': {
                         'attributes': {
                             'dn': 'uni/tn-common/brc-prs1/subj-prs1/outtmnl',
                             'nameAlias': '', 'name': '', 'descr': '',
                             'targetDscp': 'unspecified',
                             'prio': 'unspecified'}}}]]
    sample_output = [
        resource.ContractSubject(tenant_name='t1', contract_name='c', name='s',
                                 in_filters=['i1', 'i2'],
                                 out_filters=['o1', 'o2'],
                                 bi_filters=['f1', 'f2'],
                                 service_graph_name='g1',
                                 in_service_graph_name='g2',
                                 out_service_graph_name='g3',
                                 display_name='alias'),
        resource.ContractSubject(tenant_name='common', contract_name='prs1',
                                 name='prs1', display_name='prs1',
                                 in_filters=['pr1', 'reverse-pr1'],
                                 out_filters=['pr1', 'reverse-pr1'])]


class TestAciToAimConverterFault(TestAciToAimConverterBase,
                                 base.TestAimDBBase):
    resource_type = aim_status.AciFault
    reverse_map_output = [{
        'resource': 'faultInst',
        'exceptions': {'fault_code': {'other': 'code'},
                       'description': {'other': 'descr'}},
        'to_resource': converter.fault_inst_to_resource,
        'identity_converter': converter.fault_identity_converter}]
    sample_input = [base.TestAimDBBase._get_example_aci_fault(),
                    base.TestAimDBBase._get_example_aci_fault(
                        dn='uni/tn-t1/ap-a1/epg-test-1/fault-500',
                        code='500', nameAlias='alias')]
    sample_output = [
        aim_status.AciFault(
            fault_code='951',
            external_identifier='uni/tn-t1/ap-a1/epg-test/fault-951',
            description='cannot resolve',
            severity='warning',
            cause='resolution-failed'),
        aim_status.AciFault(
            fault_code='500',
            external_identifier='uni/tn-t1/ap-a1/epg-test-1/fault-500',
            description='cannot resolve',
            severity='warning',
            cause='resolution-failed', display_name='alias')]


def get_example_aci_l3outside(**kwargs):
    attr = {'name': 'inet1',
            'dn': 'uni/tn-t1/out-inet1'}
    attr.update(**kwargs)
    return _aci_obj('l3extOut', **attr)


class TestAciToAimConverterL3Outside(TestAciToAimConverterBase,
                                     base.TestAimDBBase):
    resource_type = resource.L3Outside
    reverse_map_output = [
        {'resource': 'l3extOut',
         'exceptions': {},
         'skip': ['vrfName', 'l3DomainDn', 'bgpEnable']},
        {'resource': 'l3extRsEctx',
         'exceptions': {'vrf_name': {'other': 'tnFvCtxName'}, },
         'to_resource': converter.default_to_resource_strict},
        {'resource': 'l3extRsL3DomAtt',
         'exceptions': {'l3_domain_dn': {'other': 'tDn'}, },
         'to_resource': converter.default_to_resource_strict},
        {'converter': converter.bgp_extp_converter,
         'exceptions': {},
         'resource': 'bgpExtP'}
    ]
    sample_input = [[get_example_aci_l3outside(nameAlias='alias'),
                     _aci_obj('l3extRsEctx',
                              dn='uni/tn-t1/out-inet1/rsectx',
                              tnFvCtxName='shared'),
                     _aci_obj('l3extRsL3DomAtt',
                              dn='uni/tn-t1/out-inet1/rsl3DomAtt',
                              tDn='uni/l3dom-l3ext')],
                    get_example_aci_l3outside(dn='uni/tn-t1/out-inet2')]
    sample_output = [
        resource.L3Outside(tenant_name='t1', name='inet1',
                           vrf_name='shared', l3_domain_dn='uni/l3dom-l3ext',
                           display_name='alias'),
        resource.L3Outside(tenant_name='t1', name='inet2')]


def get_example_aci_l3out_node_profile(**kwargs):
    attr = {'name': 'inet1',
            'dn': 'uni/tn-t1/out-o1/lnodep-np1'}
    attr.update(**kwargs)
    return _aci_obj('l3extLNodeP', **attr)


class TestAciToAimConverterL3OutNodeProfile(TestAciToAimConverterBase,
                                            base.TestAimDBBase):
    resource_type = resource.L3OutNodeProfile
    reverse_map_output = [
        {'exceptions': {},
         'resource': 'l3extLNodeP'}]
    sample_input = [get_example_aci_l3out_node_profile(nameAlias='alias'),
                    get_example_aci_l3out_node_profile(
                        dn='uni/tn-t1/out-o2/lnodep-np2')]
    sample_output = [
        resource.L3OutNodeProfile(tenant_name='t1', l3out_name='o1',
                                  name='np1', display_name='alias'),
        resource.L3OutNodeProfile(tenant_name='t1', l3out_name='o2',
                                  name='np2')]


def get_example_l3out_aci_node(**kwargs):
    attr = {'rtrId': '9.9.9.9',
            'rtrIdLoopBack': 'yes',
            'dn': 'uni/tn-t1/out-o1/lnodep-np1/rsnodeL3OutAtt-'
                  '[topology/pod-1/node-101]'}
    attr.update(**kwargs)
    return _aci_obj('l3extRsNodeL3OutAtt', **attr)


class TestAciToAimConverterL3OutNode(TestAciToAimConverterBase,
                                     base.TestAimDBBase):
    resource_type = resource.L3OutNode
    reverse_map_output = [
        {'resource': 'l3extRsNodeL3OutAtt',
         'exceptions': {'router_id': {'other': 'rtrId'},
                        'router_id_loopback': {'other': 'rtrIdLoopBack',
                                               'converter': converter.boolean}
                        }}]
    sample_input = [get_example_l3out_aci_node(),
                    get_example_l3out_aci_node(
                        rtrId='8.8.8.8',
                        rtrIdLoopBack='no',
                        dn='uni/tn-t1/out-o1/lnodep-np1/rsnodeL3OutAtt-'
                           '[topology/pod-1/node-201]')]
    sample_output = [
        resource.L3OutNode(tenant_name='t1', l3out_name='o1',
                           node_profile_name='np1',
                           node_path='topology/pod-1/node-101',
                           router_id='9.9.9.9',
                           router_id_loopback=True),
        resource.L3OutNode(tenant_name='t1', l3out_name='o1',
                           node_profile_name='np1',
                           node_path='topology/pod-1/node-201',
                           router_id='8.8.8.8',
                           router_id_loopback=False)]


def get_example_aci_l3out_static_route(**kwargs):
    attr = {'pref': '1',
            'dn': 'uni/tn-t1/out-o1/lnodep-np1/rsnodeL3OutAtt-'
                  '[topology/pod-1/node-101]/rt-[1.1.1.0/24]'}
    attr.update(**kwargs)
    return _aci_obj('ipRouteP', **attr)


class TestAciToAimConverterL3OutStaticRoute(TestAciToAimConverterBase,
                                            base.TestAimDBBase):
    resource_type = resource.L3OutStaticRoute
    reverse_map_output = [
        {'resource': 'ipRouteP',
         'exceptions': {'preference': {'other': 'pref'}},
         'skip': ['nextHopList']},
        {'exceptions': {},
         'resource': 'ipNexthopP',
         'converter': converter.l3ext_next_hop_converter}]
    sample_input = [get_example_aci_l3out_static_route(nameAlias='alias'),
                    [get_example_aci_l3out_static_route(
                        pref='2',
                        dn='uni/tn-t1/out-o1/lnodep-np1/rsnodeL3OutAtt-'
                           '[topology/pod-1/node-101]/rt-[2.2.2.0/24]'),
                     _aci_obj('ipNexthopP',
                              dn='uni/tn-t1/out-o1/lnodep-np1/rsnodeL3OutAtt-'
                                 '[topology/pod-1/node-101]/rt-[2.2.2.0/24]/'
                                 'nh-[2.2.2.251]',
                              nhAddr='2.2.2.251',
                              type='prefix',
                              pref='1'),
                     _aci_obj('ipNexthopP',
                              dn='uni/tn-t1/out-o1/lnodep-np1/rsnodeL3OutAtt-'
                                 '[topology/pod-1/node-101]/rt-[2.2.2.0/24]/'
                                 'nh-[2.2.2.252]',
                              nhAddr='2.2.2.252',
                              type='prefix',
                              pref='2')]]
    sample_output = [
        resource.L3OutStaticRoute(tenant_name='t1', l3out_name='o1',
                                  node_profile_name='np1',
                                  node_path='topology/pod-1/node-101',
                                  cidr='1.1.1.0/24',
                                  display_name='alias'),
        resource.L3OutStaticRoute(tenant_name='t1', l3out_name='o1',
                                  node_profile_name='np1',
                                  node_path='topology/pod-1/node-101',
                                  cidr='2.2.2.0/24',
                                  preference='2',
                                  next_hop_list=[{'addr': '2.2.2.251',
                                                  'preference': '1'},
                                                 {'addr': '2.2.2.252',
                                                  'preference': '2'}])]


def get_example_aci_l3out_interface_profile(**kwargs):
    attr = {'name': 'inet1',
            'dn': 'uni/tn-t1/out-l1/lnodep-np1/lifp-ip1'}
    attr.update(**kwargs)
    return _aci_obj('l3extLIfP', **attr)


class TestAciToAimConverterInterfaceProfile(TestAciToAimConverterBase,
                                            base.TestAimDBBase):
    resource_type = resource.L3OutInterfaceProfile
    reverse_map_output = [
        {'exceptions': {},
         'resource': 'l3extLIfP'}]
    sample_input = [get_example_aci_l3out_interface_profile(nameAlias='name'),
                    get_example_aci_l3out_interface_profile(
                        dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip2')]
    sample_output = [
        resource.L3OutInterfaceProfile(tenant_name='t1', l3out_name='l1',
                                       node_profile_name='np1', name='ip1',
                                       display_name='name'),
        resource.L3OutInterfaceProfile(tenant_name='t1', l3out_name='l1',
                                       node_profile_name='np1', name='ip2')]


def get_example_aci_l3out_interface(**kwargs):
    attr = {'addr': '1.1.1.0/24',
            'encap': 'vlan-1001',
            'ifInstT': 'ext-svi',
            'dn': 'uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/rspathL3OutAtt-'
                  '[topology/pod-1/paths-101/pathep-[eth1/1]]'}
    attr.update(**kwargs)
    return _aci_obj('l3extRsPathL3OutAtt', **attr)


class TestAciToAimConverterL3OutInterface(TestAciToAimConverterBase,
                                          base.TestAimDBBase):
    resource_type = resource.L3OutInterface
    reverse_map_output = [
        {'exceptions': {'type': {'other': 'ifInstT'},
                        'primary_addr_a': {'other': 'addr'}},
         'resource': 'l3extRsPathL3OutAtt',
         'skip': ['primaryAddrB', 'secondaryAddrAList',
                  'secondaryAddrBList', 'host']},
        {'exceptions': {},
         'skip': ['host'],
         'resource': 'l3extIp',
         'converter': converter.l3ext_ip_converter},
        {'exceptions': {},
         'skip': ['host'],
         'resource': 'l3extIp__Member',
         'converter': converter.l3ext_ip_converter},
        {'exceptions': {},
         'skip': ['host'],
         'resource': 'l3extMember',
         'converter': converter.l3ext_member_converter}]
    sample_input = [[get_example_aci_l3out_interface(nameAlias='alias'),
                     _aci_obj('l3extIp',
                              dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                                 'rspathL3OutAtt-[topology/pod-1/paths-101/'
                                 'pathep-[eth1/1]]/addr-[1.1.1.2/24]',
                              addr='1.1.1.2/24'),
                     _aci_obj('l3extIp',
                              dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                                 'rspathL3OutAtt-[topology/pod-1/paths-101/'
                                 'pathep-[eth1/1]]/addr-[1.1.1.3/24]',
                              addr='1.1.1.3/24')],
                    [get_example_aci_l3out_interface(
                        addr='0.0.0.0',
                        encap='vlan-1002',
                        mode='native',
                        dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                           'rspathL3OutAtt-[topology/pod-1/paths-101/'
                           'pathep-[eth1/2]]'),
                     _aci_obj('l3extMember',
                              dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                                 'rspathL3OutAtt-[topology/pod-1/paths-101/'
                                 'pathep-[eth1/2]]/mem-A',
                              side='A',
                              addr='1.1.1.101/24'),
                     _aci_obj('l3extIp',
                              dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                                 'rspathL3OutAtt-[topology/pod-1/paths-101/'
                                 'pathep-[eth1/2]]/mem-A/addr-[1.1.1.11/24]',
                              addr='1.1.1.11/24'),
                     _aci_obj('l3extIp',
                              dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                                 'rspathL3OutAtt-[topology/pod-1/paths-101/'
                                 'pathep-[eth1/2]]/mem-A/addr-[1.1.1.12/24]',
                              addr='1.1.1.12/24'),
                     _aci_obj('l3extMember',
                              dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                                 'rspathL3OutAtt-[topology/pod-1/paths-101/'
                                 'pathep-[eth1/2]]/mem-B',
                              side='B',
                              addr='1.1.1.102/24'),
                     _aci_obj('l3extIp__Member',
                              dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                                 'rspathL3OutAtt-[topology/pod-1/paths-101/'
                                 'pathep-[eth1/2]]/mem-B/addr-[1.1.1.13/24]',
                              addr='1.1.1.13/24'),
                     _aci_obj('l3extIp__Member',
                              dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                                 'rspathL3OutAtt-[topology/pod-1/paths-101/'
                                 'pathep-[eth1/2]]/mem-B/addr-[1.1.1.14/24]',
                              addr='1.1.1.14/24')]]
    sample_output = [
        resource.L3OutInterface(
            tenant_name='t1', l3out_name='l1',
            node_profile_name='np1', interface_profile_name='ip1',
            interface_path='topology/pod-1/paths-101/pathep-[eth1/1]',
            primary_addr_a='1.1.1.0/24',
            secondary_addr_a_list=[{'addr': '1.1.1.2/24'},
                                   {'addr': '1.1.1.3/24'}],
            encap='vlan-1001',
            mode='regular',
            type='ext-svi',
            display_name='alias'),
        resource.L3OutInterface(
            tenant_name='t1', l3out_name='l1',
            node_profile_name='np1', interface_profile_name='ip1',
            interface_path='topology/pod-1/paths-101/pathep-[eth1/2]',
            primary_addr_a='1.1.1.101/24',
            secondary_addr_a_list=[{'addr': '1.1.1.11/24'},
                                   {'addr': '1.1.1.12/24'}],
            primary_addr_b='1.1.1.102/24',
            secondary_addr_b_list=[{'addr': '1.1.1.13/24'},
                                   {'addr': '1.1.1.14/24'}],
            encap='vlan-1002',
            mode='native',
            type='ext-svi')]


def get_example_aci_external_network(**kwargs):
    attr = {'name': 'inet1',
            'dn': 'uni/tn-t1/out-o1/instP-inet1'}
    attr.update(**kwargs)
    return _aci_obj('l3extInstP', **attr)


class TestAciToAimConverterExternalNetwork(TestAciToAimConverterBase,
                                           base.TestAimDBBase):
    resource_type = resource.ExternalNetwork
    reverse_map_output = [
        {'exceptions': {},
         'resource': 'l3extInstP',
         'skip': ['natEpgDn', 'providedContractNames',
                  'consumedContractNames']},
        {'resource': 'l3extRsInstPToNatMappingEPg',
         'exceptions': {'nat_epg_dn': {'other': 'tDn'}, },
         'to_resource': converter.default_to_resource_strict},
        {'resource': 'fvRsProv',
         'exceptions': {},
         'converter': converter.fvRsProv_Ext_converter,
         'convert_pre_existing': True,
         'convert_monitored': False},
        {'resource': 'fvRsCons',
         'exceptions': {},
         'converter': converter.fvRsCons_Ext_converter,
         'convert_pre_existing': True,
         'convert_monitored': False}
    ]
    sample_input = [[get_example_aci_external_network(nameAlias='alias'),
                     _aci_obj('l3extRsInstPToNatMappingEPg',
                              dn=('uni/tn-t1/out-o1/instP-inet1/'
                                  'rsInstPToNatMappingEPg'),
                              tDn='uni/tn-t1/ap-a1/epg-g1'),
                     _aci_obj('fvRsProv',
                              dn='uni/tn-t1/out-o1/instP-inet1/rsprov-p1',
                              tnVzBrCPName='p1'),
                     _aci_obj('fvRsProv',
                              dn='uni/tn-t1/out-o1/instP-inet1/rsprov-k',
                              tnVzBrCPName='k'),
                     _aci_obj('fvRsCons',
                              dn='uni/tn-t1/out-o1/instP-inet1/rscons-c1',
                              tnVzBrCPName='c1'),
                     _aci_obj('fvRsCons',
                              dn='uni/tn-t1/out-o1/instP-inet1/rscons-k',
                              tnVzBrCPName='k')],
                    get_example_aci_external_network(
                        dn='uni/tn-t1/out-o2/instP-inet2')]
    sample_output = [
        resource.ExternalNetwork(tenant_name='t1', l3out_name='o1',
                                 name='inet1',
                                 nat_epg_dn='uni/tn-t1/ap-a1/epg-g1',
                                 provided_contract_names=['p1', 'k'],
                                 consumed_contract_names=['c1', 'k'],
                                 display_name='alias'),
        resource.ExternalNetwork(tenant_name='t1', l3out_name='o2',
                                 name='inet2')]


def get_example_aci_external_subnet(**kwargs):
    attr = {'name': '20.0.0.0/8',
            'dn': 'uni/tn-t1/out-o1/instP-inet1/extsubnet-[20.0.0.0/8]'}
    attr.update(**kwargs)
    return _aci_obj('l3extSubnet', **attr)


class TestAciToAimConverterExternalSubnet(TestAciToAimConverterBase,
                                          base.TestAimDBBase):
    resource_type = resource.ExternalSubnet
    reverse_map_output = [{'exceptions': {},
                           'resource': 'l3extSubnet'}]
    sample_input = [get_example_aci_external_subnet(),
                    get_example_aci_external_subnet(
                        dn=('uni/tn-t1/out-o2/instP-inet2/'
                            'extsubnet-[30.0.0.0/16]'),
                        nameAlias='alias')]
    sample_output = [
        resource.ExternalSubnet(tenant_name='t1', l3out_name='o1',
                                external_network_name='inet1',
                                cidr='20.0.0.0/8'),
        resource.ExternalSubnet(tenant_name='t1', l3out_name='o2',
                                external_network_name='inet2',
                                cidr='30.0.0.0/16', display_name='alias')]


def get_example_aci_security_group_rule(**kwargs):
    attr = {'name': 'rule1',
            'dn': 'uni/tn-t1/pol-sg1/subj-sgs1/rule-rule1'}
    attr.update(**kwargs)
    return _aci_obj('hostprotRule', **attr)


class TestAciToAimConverterSecurityGroupRule(TestAciToAimConverterBase,
                                             base.TestAimDBBase):
    resource_type = resource.SecurityGroupRule
    reverse_map_output = [
        {'exceptions': {
            'ip_protocol': {'other': 'protocol',
                            'converter': converter.ip_protocol},
            'from_port': {'other': 'fromPort',
                          'converter': converter.port},
            'to_port': {'other': 'toPort',
                        'converter': converter.port},
            'icmp_type': {'other': 'icmpType',
                          'converter': converter.icmpv4_type},
            'icmp_code': {'other': 'icmpCode',
                          'converter': converter.icmpv4_code},
            'ethertype': {'other': 'ethertype',
                          'converter': converter.ethertype}},
         'skip': ['remoteIps', 'remoteGroupId'],
         'resource': 'hostprotRule'},
        {'exceptions': {},
         'converter': converter.hostprotRemoteIp_converter,
         'resource': 'hostprotRemoteIp'}]
    sample_input = [get_example_aci_security_group_rule(),
                    get_example_aci_security_group_rule(
                        dn='uni/tn-t1/pol-sg1/subj-sgs2/rule-rule1',
                        connTrack='normal', icmpType='0xffff',
                        protocol='eigrp', ethertype='ipv4', icmpCode='0')]

    sample_output = [
        resource.SecurityGroupRule(
            tenant_name='t1', security_group_name='sg1',
            security_group_subject_name='sgs1', name='rule1',
            conn_track='reflexive', icmp_code='unspecified',
            icmp_type='unspecified', ethertype='undefined'),
        resource.SecurityGroupRule(
            tenant_name='t1', security_group_name='sg1',
            security_group_subject_name='sgs2', name='rule1',
            conn_track='normal', icmp_type='0xffff', icmp_code='0',
            ip_protocol='eigrp', ethertype='ipv4',
            remote_group_id='')
    ]


class TestAciToAimConverterDeviceCluster(TestAciToAimConverterBase,
                                         base.TestAimDBBase):
    resource_type = aim_service_graph.DeviceCluster
    reverse_map_output = [
        {'resource': 'vnsRsALDevToDomP',
         'exceptions': {
             'vmm_domain_name': {
                 'converter': conv_service_graph.vnsRsALDevToDomP_converter,
                 'other': 'tDn', 'skip_if_empty': True}},
         'to_resource': conv_utils.default_to_resource_strict},
        {'resource': 'vnsLDevVip',
         'exceptions': {'managed': {'converter': converter.boolean,
                                    'other': 'managed'},
                        'device_type': {'other': 'devtype'},
                        'service_type': {'other': 'svcType'}},
         'skip': ['physicalDomainName', 'encap', 'devices', 'vmmDomainName',
                  'vmmDomainType'],
         'converter': conv_service_graph.device_cluster_converter},
        {'resource': 'vnsRsALDevToPhysDomP',
         'exceptions':
         {'physical_domain_name':
          {'other': 'tDn',
           'converter': conv_service_graph.vnsRsALDevToPhysDomP_converter}},
         'to_resource': conv_utils.default_to_resource_strict}]
    sample_input = [[_aci_obj('vnsLDevVip',
                              dn='uni/tn-t1/lDevVip-cl1',
                              nameAlias='alias'),
                     _aci_obj('vnsRsALDevToPhysDomP',
                              dn='uni/tn-t1/lDevVip-cl1/rsALDevToPhysDomP',
                              tDn='uni/phys-PHYS')],
                    [_aci_obj('vnsLDevVip',
                              dn='uni/tn-t1/lDevVip-cl2',
                              managed='no',
                              devtype='VIRTUAL', svcType='ADC',
                              contextAware='multi-Context'),
                     _aci_obj('vnsRsALDevToDomP',
                              dn='uni/tn-t1/lDevVip-cl2/rsALDevToDomP',
                              tDn='uni/vmmp-OpenStack/dom-test')]]
    sample_output = [
        aim_service_graph.DeviceCluster(
            tenant_name='t1', name='cl1', physical_domain_name='PHYS',
            display_name='alias'),
        aim_service_graph.DeviceCluster(
            tenant_name='t1', name='cl2', managed=False,
            service_type='ADC', device_type='VIRTUAL',
            context_aware='multi-Context', physical_domain_name='',
            vmm_domain_type='OpenStack', vmm_domain_name='test')]


class TestAciToAimConverterDeviceClusterInterface(TestAciToAimConverterBase,
                                                  base.TestAimDBBase):
    resource_type = aim_service_graph.DeviceClusterInterface
    reverse_map_output = [
        {'resource': 'vnsLIf',
         'exceptions': {},
         'skip': ['concreteInterfaces']},
        {'resource': 'vnsRsCIfAttN',
         'exceptions': {},
         'converter': conv_service_graph.vnsRsCIfAttN_converter}]
    sample_input = [[_aci_obj('vnsLIf',
                              dn='uni/tn-t1/lDevVip-cl1/lIf-if1',
                              encap='vlan-55',
                              nameAlias='alias'),
                     _aci_obj('vnsRsCIfAttN',
                              dn=('uni/tn-t1/lDevVip-cl1/lIf-if1/'
                                  'rscIfAttN-[abc]'),
                              tDn='abc'),
                     _aci_obj('vnsRsCIfAttN',
                              dn=('uni/tn-t1/lDevVip-cl1/lIf-if1/'
                                  'rscIfAttN-[xyz]'),
                              tDn='xyz')],
                    [_aci_obj('vnsLIf',
                              dn='uni/tn-t1/lDevVip-cl1/lIf-if2',
                              encap='')]]
    sample_output = [
        aim_service_graph.DeviceClusterInterface(
            tenant_name='t1', device_cluster_name='cl1', name='if1',
            encap='vlan-55', concrete_interfaces=['abc', 'xyz'],
            display_name='alias'),
        aim_service_graph.DeviceClusterInterface(
            tenant_name='t1', device_cluster_name='cl1', name='if2',
            encap='', concrete_interfaces=[])]


class TestAciToAimConverterConcreteDevice(TestAciToAimConverterBase,
                                          base.TestAimDBBase):
    resource_type = aim_service_graph.ConcreteDevice
    reverse_map_output = [
        {'resource': 'vnsCDev',
         'exceptions': {}}]
    sample_input = [_aci_obj('vnsCDev',
                             dn='uni/tn-t1/lDevVip-cl1/cDev-n1',
                             nameAlias='alias'),
                    _aci_obj('vnsCDev',
                             dn='uni/tn-t1/lDevVip-cl1/cDev-n2')]
    sample_output = [
        aim_service_graph.ConcreteDevice(
            tenant_name='t1', device_cluster_name='cl1', name='n1',
            display_name='alias'),
        aim_service_graph.ConcreteDevice(
            tenant_name='t1', device_cluster_name='cl1', name='n2')]


class TestAciToAimConverterConcreteDeviceInterface(
    TestAciToAimConverterBase, base.TestAimDBBase):
    resource_type = aim_service_graph.ConcreteDeviceInterface
    reverse_map_output = [
        {'resource': 'vnsCIf',
         'skip': ['path', 'host'],
         'exceptions': {}},
        {'resource': 'vnsRsCIfPathAtt',
         'skip': ['host'],
         'exceptions': {'path': {'other': 'tDn'}},
         'to_resource': converter.default_to_resource_strict}]
    sample_input = [[_aci_obj('vnsCIf',
                              dn='uni/tn-t1/lDevVip-cl1/cDev-n1/cIf-[if1]',
                              nameAlias='alias'),
                     _aci_obj('vnsRsCIfPathAtt',
                              dn=('uni/tn-t1/lDevVip-cl1/cDev-n1/cIf-[if1]/'
                                  'rsCIfPathAtt'),
                              tDn='xyz')],
                    [_aci_obj('vnsCIf',
                              dn='uni/tn-t1/lDevVip-cl1/cDev-n1/cIf-[if2]')]]
    sample_output = [
        aim_service_graph.ConcreteDeviceInterface(
            tenant_name='t1', device_cluster_name='cl1', device_name='n1',
            name='if1', display_name='alias', path='xyz'),
        aim_service_graph.ConcreteDeviceInterface(
            tenant_name='t1', device_cluster_name='cl1', device_name='n1',
            name='if2', path='')]


class TestAciToAimConverterServiceGraph(TestAciToAimConverterBase,
                                        base.TestAimDBBase):
    resource_type = aim_service_graph.ServiceGraph
    reverse_map_output = [
        {'resource': 'vnsAbsGraph',
         'skip': ['linearChainNodes'],
         'exceptions': {},
         'converter': conv_service_graph.service_graph_converter}]
    sample_input = [_aci_obj('vnsAbsGraph',
                             dn='uni/tn-t1/AbsGraph-gr1',
                             nameAlias='alias'),
                    _aci_obj('vnsAbsGraph',
                             dn='uni/tn-t1/AbsGraph-gr2')]
    sample_output = [
        aim_service_graph.ServiceGraph(
            tenant_name='t1', name='gr1', display_name='alias'),
        aim_service_graph.ServiceGraph(tenant_name='t1', name='gr2')]


class TestAciToAimConverterServiceGraphNode(TestAciToAimConverterBase,
                                            base.TestAimDBBase):
    resource_type = aim_service_graph.ServiceGraphNode
    reverse_map_output = [
        {'resource': 'vnsAbsNode',
         'skip': ['connectors', 'deviceClusterName',
                  'deviceClusterTenantName'],
         'exceptions': {'function_type': {'other': 'funcType'},
                        'managed': {'other': 'managed',
                                    'converter': conv_utils.boolean}, }},
        {'resource': 'vnsRsNodeToLDev',
         'exceptions': {'device_cluster_name':
                        {'other': 'tDn',
                         'converter':
                         conv_service_graph.vnsLDevVip_dn_decomposer}, },
         'to_resource': conv_utils.default_to_resource_strict, },
        {'resource': 'vnsAbsFuncConn',
         'converter': conv_service_graph.vnsAbsFuncConn_converter,
         'exceptions': {}}]
    sample_input = [[_aci_obj('vnsAbsNode',
                              dn='uni/tn-t1/AbsGraph-gr1/AbsNode-N1',
                              nameAlias='alias', managed='no',
                              funcType='GoThrough', routingMode='Redirect',
                              sequenceNumber='1'),
                     _aci_obj('vnsAbsFuncConn',
                              dn=('uni/tn-t1/AbsGraph-gr1/AbsNode-N1/'
                                  'AbsFConn-c'),
                              name='c'),
                     _aci_obj('vnsRsNodeToLDev',
                              dn=('uni/tn-t1/AbsGraph-gr1/AbsNode-N1/'
                                  'rsNodeToLDev'),
                              tDn='uni/tn-common/lDevVip-cl1')],
                    _aci_obj('vnsAbsNode',
                             dn='uni/tn-t1/AbsGraph-gr2/AbsNode-N2',
                             sequenceNumber='3')]
    sample_output = [
        aim_service_graph.ServiceGraphNode(
            tenant_name='t1', service_graph_name='gr1', name='N1',
            display_name='alias', managed=False, function_type='GoThrough',
            routing_mode='Redirect', connectors=['c'],
            device_cluster_tenant_name='common',
            device_cluster_name='cl1', sequence_number='1'),
        aim_service_graph.ServiceGraphNode(
            tenant_name='t1', service_graph_name='gr2', name='N2',
            sequence_number='3')]


class TestAciToAimConverterServiceGraphConnection(TestAciToAimConverterBase,
                                                  base.TestAimDBBase):
    resource_type = aim_service_graph.ServiceGraphConnection
    reverse_map_output = [
        {'resource': 'vnsAbsConnection',
         'exceptions':
         {'adjacency_type': {'other': 'adjType'},
          'connector_direction': {'other': 'connDir'},
          'connector_type': {'other': 'connType'},
          'direct_connect': {'other': 'directConnect',
                             'converter': conv_utils.boolean},
          'unicast_route': {'other': 'unicastRoute',
                            'converter': conv_utils.boolean}},
         'skip': ['connectorDns'], },
        {'resource': 'vnsRsAbsConnectionConns',
         'converter': conv_service_graph.vnsRsAbsConnectionConns_converter,
         'exceptions': {}}]
    sample_input = [[_aci_obj('vnsAbsConnection',
                              dn='uni/tn-t1/AbsGraph-gr1/AbsConnection-c1',
                              nameAlias='alias', adjType='L3',
                              connDir='consumer', connType='internal',
                              directConnect='yes', unicastRoute='yes'),
                     _aci_obj('vnsRsAbsConnectionConns',
                              dn=('uni/tn-t1/AbsGraph-gr1/AbsConnection-c1/'
                                  'rsabsConnectionConns-[foo-bar]'),
                              tDn='foo-bar'),
                     _aci_obj('vnsRsAbsConnectionConns',
                              dn=('uni/tn-t1/AbsGraph-gr1/AbsConnection-c1/'
                                  'rsabsConnectionConns-[bar-bar]'),
                              tDn='bar-bar')],
                    _aci_obj('vnsAbsConnection',
                             dn='uni/tn-t1/AbsGraph-gr1/AbsConnection-c2')]
    sample_output = [
        aim_service_graph.ServiceGraphConnection(
            tenant_name='t1', service_graph_name='gr1', name='c1',
            display_name='alias', adjacency_type='L3',
            connector_direction='consumer', connector_type='internal',
            direct_connect=True, unicast_route=True,
            connector_dns=['foo-bar', 'bar-bar']),
        aim_service_graph.ServiceGraphConnection(
            tenant_name='t1', service_graph_name='gr1', name='c2')]


class TestAciToAimConverterServiceRedirectPolicy(TestAciToAimConverterBase,
                                                 base.TestAimDBBase):
    resource_type = aim_service_graph.ServiceRedirectPolicy
    reverse_map_output = [
        {'resource': 'vnsSvcRedirectPol',
         'exceptions': {},
         'skip': ['destinations', 'monitoringPolicyTenantName',
                  'monitoringPolicyName']},
        {'resource': 'vnsRedirectDest',
         'converter': conv_service_graph.vnsRedirectDest_converter,
         'exceptions': {}},
        {'resource': 'vnsRsIPSLAMonitoringPol',
         'exceptions': {},
         'converter': conv_service_graph.vnsRsIPSLAMonitoringPol_converter,
         'to_resource': conv_utils.default_to_resource_strict},
        {'resource': 'vnsRsRedirectHealthGroup',
         'exceptions': {},
         'converter': conv_service_graph.vnsRsRedirectHealthGroup_converter},

    ]
    sample_input = [[_aci_obj('vnsSvcRedirectPol',
                              dn='uni/tn-t1/svcCont/svcRedirectPol-r1',
                              nameAlias='alias'),
                     _aci_obj('vnsRedirectDest',
                              dn=('uni/tn-t1/svcCont/svcRedirectPol-r1/'
                                  'RedirectDest_ip-[10.6.1.1]'),
                              ip='10.6.1.1',
                              mac='90:E2:Ba:b1:36:6c'),
                     _aci_obj('vnsRsRedirectHealthGroup',
                              dn='uni/tn-t1/svcCont/svcRedirectPol-r1/'
                                 'RedirectDest_ip-[10.6.1.1]/rsRedirect'
                                 'HealthGroup',
                              tDn=''),
                     _aci_obj('vnsRedirectDest',
                              dn=('uni/tn-t1/svcCont/svcRedirectPol-r1/'
                                  'RedirectDest_ip-[10.6.1.2]'),
                              ip='10.6.1.2'),
                     _aci_obj('vnsRsRedirectHealthGroup',
                              dn='uni/tn-t1/svcCont/svcRedirectPol-r1/'
                                 'RedirectDest_ip-[10.6.1.2]/rsRedirect'
                                 'HealthGroup',
                              tDn='my/dn2'),
                     _aci_obj('vnsRsIPSLAMonitoringPol',
                              dn='uni/tn-t1/svcCont/svcRedirectPol-r1/'
                                 'rsIPSLAMonitoringPol',
                              tDn='uni/tn-common/ipslaMonitoringPol-'
                                  'mon_policy'),
                    _aci_obj('vnsRedirectDest',
                             dn=('uni/tn-t1/svcCont/svcRedirectPol-r1/'
                                 'RedirectDest_ip-[10.6.1.3]'),
                             ip='10.6.1.3',
                             mac='90:E2:Ba:b1:36:6d', destName='dest-name')
                     ],
                    _aci_obj('vnsSvcRedirectPol',
                             dn='uni/tn-t1/svcCont/svcRedirectPol-r2')]
    sample_output = [
        aim_service_graph.ServiceRedirectPolicy(
            tenant_name='t1', name='r1',
            display_name='alias', monitoring_policy_tenant_name='common',
            monitoring_policy_name='mon_policy',
            destinations=[{'ip': '10.6.1.1', 'mac': '90:E2:BA:B1:36:6C',
                           'redirect_health_group_dn': ''},
                          {'ip': '10.6.1.2',
                           'redirect_health_group_dn': 'my/dn2'},
                          {'ip': '10.6.1.3', 'mac': '90:E2:BA:B1:36:6D',
                           'name': 'dest-name'}]),
        aim_service_graph.ServiceRedirectPolicy(tenant_name='t1', name='r2')
    ]


class TestAciToAimConverterServiceRedirectMonitoringPolicy(
        TestAciToAimConverterBase, base.TestAimDBBase):
    resource_type = aim_service_graph.ServiceRedirectMonitoringPolicy
    reverse_map_output = [
        {'resource': 'fvIPSLAMonitoringPol',
         'exceptions': {
             'tcp_port': {'other': 'slaPort'},
             'type': {'other': 'slaType'},
             'frequency': {'other': 'slaFrequency'}}
         }
    ]
    sample_input = [[_aci_obj('fvIPSLAMonitoringPol',
                              dn='uni/tn-t1/ipslaMonitoringPol-sla1',
                              nameAlias='alias')],
                    _aci_obj('fvIPSLAMonitoringPol',
                             dn='uni/tn-t1/ipslaMonitoringPol-sla2',
                             slaPort='8080', slaType='tcp',
                             slaFrequency='50')]
    sample_output = [
        aim_service_graph.ServiceRedirectMonitoringPolicy(
            tenant_name='t1', name='sla1', display_name='alias'),
        aim_service_graph.ServiceRedirectMonitoringPolicy(
            tenant_name='t1', name='sla2', tcp_port='8080',
            type='tcp', frequency='50')
    ]


class TestAciToAimConverterServiceRedirectHealthGroup(
        TestAciToAimConverterBase, base.TestAimDBBase):
    resource_type = aim_service_graph.ServiceRedirectHealthGroup
    reverse_map_output = [
        {'resource': 'vnsRedirectHealthGroup',
         'exceptions': {}}]
    sample_input = [[_aci_obj('vnsRedirectHealthGroup',
                              dn='uni/tn-t1/svcCont/redirectHealthGroup-h1',
                              nameAlias='alias')],
                    _aci_obj('vnsRedirectHealthGroup',
                             dn='uni/tn-t1/svcCont/redirectHealthGroup-h2')]
    sample_output = [
        aim_service_graph.ServiceRedirectHealthGroup(
            tenant_name='t1', name='h1', display_name='alias'),
        aim_service_graph.ServiceRedirectHealthGroup(
            tenant_name='t1', name='h2')
    ]


class TestAciToAimConverterDeviceClusterInterfaceContext(
        TestAciToAimConverterBase, base.TestAimDBBase):
    resource_type = aim_service_graph.DeviceClusterInterfaceContext
    reverse_map_output = [
        {'resource': 'vnsLIfCtx',
         'exceptions': {},
         'skip': ['deviceClusterInterfaceDn',
                  'serviceRedirectPolicyDn',
                  'bridgeDomainDn'], },
        {'resource': 'vnsRsLIfCtxToSvcRedirectPol',
         'exceptions': {'service_redirect_policy_dn': {'other': 'tDn'}},
         'to_resource': conv_utils.default_to_resource_strict, },
        {'resource': 'vnsRsLIfCtxToBD',
         'exceptions': {'bridge_domain_dn': {'other': 'tDn'}},
         'to_resource': conv_utils.default_to_resource_strict, },
        {'resource': 'vnsRsLIfCtxToLIf',
         'exceptions': {'device_cluster_interface_dn': {'other': 'tDn'}},
         'to_resource': conv_utils.default_to_resource_strict, }
    ]
    sample_input = [[_aci_obj('vnsLIfCtx',
                              dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/'
                                  'lIfCtx-c-prov'),
                              nameAlias=''),
                     _aci_obj('vnsRsLIfCtxToSvcRedirectPol',
                              dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/'
                                  'lIfCtx-c-prov/rsLIfCtxToSvcRedirectPol'),
                              tDn='srp'),
                     _aci_obj('vnsRsLIfCtxToBD',
                              dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/'
                                  'lIfCtx-c-prov/rsLIfCtxToBD'),
                              tDn='bd'),
                     _aci_obj('vnsRsLIfCtxToLIf',
                              dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/'
                                  'lIfCtx-c-prov/rsLIfCtxToLIf'),
                              tDn='dci')],
                    _aci_obj('vnsLIfCtx',
                             dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/'
                                 'lIfCtx-c-cons'),
                             nameAlias='CONS')]
    sample_output = [
        aim_service_graph.DeviceClusterInterfaceContext(
            tenant_name='t1', contract_name='c1',
            service_graph_name='g0', node_name='N0',
            connector_name='prov', device_cluster_interface_dn='dci',
            service_redirect_policy_dn='srp', bridge_domain_dn='bd'),
        aim_service_graph.DeviceClusterInterfaceContext(
            tenant_name='t1', contract_name='c1',
            service_graph_name='g0', node_name='N0',
            connector_name='cons', display_name='CONS')
    ]


class TestAciToAimConverterDeviceClusterContext(TestAciToAimConverterBase,
                                                base.TestAimDBBase):
    resource_type = aim_service_graph.DeviceClusterContext
    reverse_map_output = [
        {'resource': 'vnsLDevCtx',
         'exceptions': {},
         'skip': ['deviceClusterName', 'deviceClusterTenantName',
                  'serviceRedirectPolicyName',
                  'serviceRedirectPolicyTenantName',
                  'bridgeDomainName', 'bridgeDomainTenantName'],
         'converter': conv_service_graph.device_cluster_context_converter, },
        {'resource': 'vnsRsLDevCtxToLDev',
         'exceptions':
         {'device_cluster_name':
          {'other': 'tDn',
           'converter': conv_service_graph.vnsLDevVip_dn_decomposer}, },
         'to_resource': conv_utils.default_to_resource_strict,
         'converter': conv_service_graph.device_cluster_context_converter, }
    ]
    sample_input = [[_aci_obj('vnsLDevCtx',
                              dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/')),
                     _aci_obj('vnsRsLDevCtxToLDev',
                              dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/'
                                  'rsLDevCtxToLDev'),
                              tDn='uni/tn-common/lDevVip-ldc1')],
                    _aci_obj('vnsLDevCtx',
                             dn='uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1',
                             nameAlias='alias')]
    sample_output = [
        aim_service_graph.DeviceClusterContext(
            tenant_name='t1', contract_name='c1',
            service_graph_name='g0', node_name='N0',
            device_cluster_name='ldc1',
            device_cluster_tenant_name='common'),
        aim_service_graph.DeviceClusterContext(
            tenant_name='t1', contract_name='c1',
            service_graph_name='g1', node_name='N1', display_name='alias')
    ]


class TestAciToAimConverterOpflexDevice(TestAciToAimConverterBase,
                                        base.TestAimDBBase):
    resource_type = aim_infra.OpflexDevice
    reverse_map_output = [
        {'resource': 'opflexODev',
         'exceptions': {'domain_name': {'other': 'domName'},
                        'controller_name': {'other': 'ctrlrName'}}}]
    sample_input = [_aci_obj('opflexODev',
                             dn=('topology/pod-1/node-301/sys/br-[eth1/33]/'
                                 'odev-167776320')),
                    _aci_obj('opflexODev',
                             dn=('topology/pod-1/node-201/sys/br-[eth1/34]/'
                                 'odev-167776321'),
                             hostName='f1-compute-1',
                             ip='10.0.16.64',
                             domName='k8s',
                             ctrlrName='cluster1',
                             fabricPathDn=('topology/pod-1/protpaths-201-202'
                                           '/pathep-[bundle-201-1-33-and-'
                                           '202-1-33]'))]

    sample_output = [
        aim_infra.OpflexDevice(
            pod_id='1', node_id='301', bridge_interface='eth1/33',
            dev_id='167776320'),
        aim_infra.OpflexDevice(
            pod_id='1', node_id='201', bridge_interface='eth1/34',
            dev_id='167776321', host_name='f1-compute-1', ip='10.0.16.64',
            domain_name='k8s', controller_name='cluster1',
            fabric_path_dn=('topology/pod-1/protpaths-201-202/'
                            'pathep-[bundle-201-1-33-and-202-1-33]'))
    ]


class TestAciToAimConverterVMMDomain(TestAciToAimConverterBase,
                                     base.TestAimDBBase):
    resource_type = resource.VMMDomain
    reverse_map_output = [
        {'resource': 'vmmDomP',
         'skip': ['vlanPoolName', 'vlanPoolType', 'mcastAddrPoolName'],
         'exceptions': {'mcast_address': {'other': 'mcastAddr'},
                        'enforcement_pref': {'other': 'enfPref'}}},
        {'resource': 'infraRsVlanNs',
         'exceptions': {'vlan_pool_name':
                        {'other': 'tDn',
                         'converter': converter.infraRsVlanNs_vmm_converter,
                         'skip_if_empty': True}},
         'identity_converter': converter.infraRsVlan_vmm_id_converter,
         'to_resource': converter.default_to_resource_strict},
        {'resource': 'vmmRsDomMcastAddrNs',
         'exceptions': {'mcast_addr_pool_name':
                        {'other': 'tDn',
                         'converter': converter.vmmRsDomMcastAddrNs_converter,
                         'skip_if_empty': True}},
         'to_resource': converter.default_to_resource_strict}]
    sample_input = [[_aci_obj('vmmDomP',
                              dn='uni/vmmp-Kubernetes/dom-k8s',
                              enfPref='sw',
                              mode='k8s',
                              encapMode='vxlan',
                              prefEncapMode='vlan',
                              nameAlias='VMM_DOM'),
                     _aci_obj('infraRsVlanNs',
                              dn='uni/vmmp-Kubernetes/dom-k8s/rsvlanNs',
                              tDn='uni/infra/vlanns-[vpool1]-static')],
                    [_aci_obj('vmmDomP',
                              dn='uni/vmmp-OpenStack/dom-ostk',
                              nameAlias='',
                              mcastAddr='225.1.2.3',
                              encapMode='vxlan',
                              enfPref='hw'),
                     _aci_obj('vmmRsDomMcastAddrNs',
                              dn=('uni/vmmp-OpenStack/dom-ostk/'
                                  'rsdomMcastAddrNs'),
                              tDn='uni/infra/maddrns-mpool3')],
                    ]
    sample_output = [
        resource.VMMDomain(
            type='Kubernetes', name='k8s', display_name='VMM_DOM',
            enforcement_pref='sw', mode='k8s',
            mcast_address='0.0.0.0', encap_mode='vxlan',
            pref_encap_mode='vlan', vlan_pool_name='vpool1',
            vlan_pool_type='static'),
        resource.VMMDomain(
            type='OpenStack', name='ostk', mcast_addr_pool_name='mpool3',
            mcast_address='225.1.2.3', enforcement_pref='hw',
            mode='ovs', encap_mode='vxlan', pref_encap_mode='unspecified'),
    ]


class TestAciToAimConverterVMMController(TestAciToAimConverterBase,
                                         base.TestAimDBBase):
    resource_type = resource.VMMController
    reverse_map_output = [
        {'resource': 'vmmCtrlrP',
         'exceptions': {}}]
    sample_input = [_aci_obj('vmmCtrlrP',
                             dn='uni/vmmp-Kubernetes/dom-k8s/ctrlr-cluster1',
                             nameAlias='CLSTR',
                             scope='kubernetes',
                             mode='ovs',
                             rootContName='center1',
                             hostOrIp='my.cluster.host'),
                    [_aci_obj('vmmCtrlrP',
                              dn=('uni/vmmp-Kubernetes/dom-k8s/ctrlr-cls2'),
                              nameAlias='',
                              scope='iaas')]]
    sample_output = [
        resource.VMMController(
            domain_type='Kubernetes', domain_name='k8s',
            name='cluster1', display_name='CLSTR',
            scope='kubernetes', root_cont_name='center1',
            host_or_ip='my.cluster.host', mode='ovs'),
        resource.VMMController(
            domain_type='Kubernetes', domain_name='k8s', name='cls2',
            scope='iaas'),
    ]


class TestAciToAimConverterVmmInjNamespace(TestAciToAimConverterBase,
                                           base.TestAimDBBase):
    resource_type = resource.VmmInjectedNamespace
    reverse_map_output = [
        {'resource': 'vmmInjectedNs',
         'exceptions': {}}]
    sample_input = [_aci_obj('vmmInjectedNs',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/ns-[ns1]')),
                    _aci_obj('vmmInjectedNs',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/ns-[ns2]'),
                             nameAlias='N')]

    sample_output = [
        resource.VmmInjectedNamespace(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', name='ns1'),
        resource.VmmInjectedNamespace(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', name='ns2', display_name='N')
    ]


class TestAciToAimConverterVmmInjDeployment(TestAciToAimConverterBase,
                                            base.TestAimDBBase):
    resource_type = resource.VmmInjectedDeployment
    reverse_map_output = [
        {'resource': 'vmmInjectedDepl',
         'exceptions': {'replicas': {'converter': conv_utils.integer_str,
                                     'other': 'replicas'}}}]
    sample_input = [_aci_obj('vmmInjectedDepl',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/ns-[ns1]/depl-[depl1]'),
                             replicas='5'),
                    _aci_obj('vmmInjectedDepl',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/ns-[ns2]/depl-[depl2]'),
                             nameAlias='D')]

    sample_output = [
        resource.VmmInjectedDeployment(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', namespace_name='ns1', name='depl1',
            replicas=5),
        resource.VmmInjectedDeployment(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', namespace_name='ns2', name='depl2',
            display_name='D')
    ]


class TestAciToAimConverterVmmInjReplicaSet(TestAciToAimConverterBase,
                                            base.TestAimDBBase):
    resource_type = resource.VmmInjectedReplicaSet
    reverse_map_output = [
        {'resource': 'vmmInjectedReplSet',
         'exceptions': {}}]
    sample_input = [_aci_obj('vmmInjectedReplSet',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/ns-[ns1]/rs-[set1]'),
                             deploymentName='depl1'),
                    _aci_obj('vmmInjectedReplSet',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/ns-[ns2]/rs-[set2]'),
                             nameAlias='RS')]

    sample_output = [
        resource.VmmInjectedReplicaSet(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', namespace_name='ns1',
            deployment_name='depl1', name='set1'),
        resource.VmmInjectedReplicaSet(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', namespace_name='ns2',
            name='set2', display_name='RS')
    ]


class TestAciToAimConverterVmmInjService(TestAciToAimConverterBase,
                                         base.TestAimDBBase):
    resource_type = resource.VmmInjectedService
    reverse_map_output = [
        {'resource': 'vmmInjectedSvc',
         'skip': ['servicePorts', 'endpoints'],
         'exceptions': {'service_type': {'other': 'type'},
                        'load_balancer_ip': {'other': 'lbIp'}}},
        {'resource': 'vmmInjectedSvcPort',
         'converter': converter.vmmInjectedSvcPort_converter,
         'exceptions': {}},
        {'resource': 'vmmInjectedSvcEp',
         'converter': converter.vmmInjectedSvcEp_converter,
         'exceptions': {}}]
    sample_input = [[_aci_obj('vmmInjectedSvc',
                              dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                  'injcont/ns-[ns1]/svc-[svc1]'),
                              clusterIp='1.2.3.4',
                              type='loadBalancer',
                              lbIp='5.6.7.8'),
                     _aci_obj('vmmInjectedSvcPort',
                              dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                  'injcont/ns-[ns1]/svc-[svc1]/'
                                  'p-https-prot-tcp-t-INT_HTTP'),
                              port='https',
                              protocol='tcp',
                              targetPort='INT_HTTP',),
                     _aci_obj('vmmInjectedSvcPort',
                              dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                  'injcont/ns-[ns1]/svc-[svc1]/'
                                  'p-56-prot-udp-t-2056'),
                              port='56',
                              protocol='udp',
                              targetPort='2056',
                              nodePort='http'),
                     _aci_obj('vmmInjectedSvcEp',
                              dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                  'injcont/ns-[ns1]/svc-[svc1]/ep-foo'),
                              contGrpName='foo'),
                     _aci_obj('vmmInjectedSvcEp',
                              dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                  'injcont/ns-[ns1]/svc-[svc1]/ep-bar'),
                              contGrpName='bar')],
                    _aci_obj('vmmInjectedSvc',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/ns-[ns2]/svc-[svc2]'),
                             nameAlias='SVC')]

    sample_output = [
        resource.VmmInjectedService(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', namespace_name='ns1', name='svc1',
            cluster_ip='1.2.3.4', service_type='loadBalancer',
            load_balancer_ip='5.6.7.8',
            service_ports=[{'port': 'https', 'protocol': 'tcp',
                            'target_port': 'INT_HTTP'},
                           {'port': '56', 'protocol': 'udp',
                            'target_port': '2056', 'node_port': 'http'}],
            endpoints=[{'pod_name': 'foo'},
                       {'pod_name': 'bar'}]),
        resource.VmmInjectedService(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', namespace_name='ns2', name='svc2',
            display_name='SVC', cluster_ip='0.0.0.0',
            service_type='clusterIp', load_balancer_ip='0.0.0.0',
            service_ports=[])
    ]


class TestAciToAimConverterVmmInjHost(TestAciToAimConverterBase,
                                      base.TestAimDBBase):
    resource_type = resource.VmmInjectedHost
    reverse_map_output = [
        {'resource': 'vmmInjectedHost',
         'exceptions': {'kernel_version': {'other': 'kernelVer'}}}]
    sample_input = [_aci_obj('vmmInjectedHost',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/host-[host1]'),
                             os='Ubuntu',
                             kernelVer='4.0',
                             hostName='my.local.host'),
                    _aci_obj('vmmInjectedHost',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/host-[host2]'),
                             nameAlias='HOST')]

    sample_output = [
        resource.VmmInjectedHost(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', name='host1',
            os='Ubuntu', kernel_version='4.0', host_name='my.local.host'),
        resource.VmmInjectedHost(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', name='host2',
            display_name='HOST')
    ]


class TestAciToAimConverterVmmInjContGroup(TestAciToAimConverterBase,
                                           base.TestAimDBBase):
    resource_type = resource.VmmInjectedContGroup
    reverse_map_output = [
        {'resource': 'vmmInjectedContGrp',
         'exceptions': {}}]
    sample_input = [_aci_obj('vmmInjectedContGrp',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/ns-[ns1]/grp-[pod1]'),
                             hostName='my.local.host',
                             computeNodeName='host1',
                             replicaSetName='rs1'),
                    _aci_obj('vmmInjectedContGrp',
                             dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                                 'injcont/ns-[ns2]/grp-[pod2]'),
                             nameAlias='POD')]

    sample_output = [
        resource.VmmInjectedContGroup(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', compute_node_name='host1',
            name='pod1', namespace_name='ns1', host_name='my.local.host',
            replica_set_name='rs1'),
        resource.VmmInjectedContGroup(
            domain_type='Kubernetes', domain_name='k8s',
            controller_name='cluster1', namespace_name='ns2',
            name='pod2', display_name='POD', replica_set_name='')
    ]


class TestAimToAciConverterBase(object):
    sample_input = []
    sample_output = []
    missing_ref_input = None
    missing_ref_output = None

    def setUp(self):
        super(TestAimToAciConverterBase, self).setUp()
        self.converter = converter.AimToAciModelConverter()

    def _dump(self, res):
        return ([r.__dict__ for r in res] if isinstance(res, list)
                else res.__dict__)

    def _test_convert(self, example, expected):

        to_convert = []
        self.assertEqual(len(example), len(expected))

        for new in example:
            to_convert.append(new)
            expected_step = expected[:len(to_convert)]
            result = self.converter.convert(to_convert)

            self.assertEqual(sum(len(x) for x in expected_step), len(result),
                             '\nExpected:\n%s\nResult:\n%s' % (
                             pprint.pformat(expected_step),
                             pprint.pformat(result)))
            for items in expected_step:
                for item in items:
                    self.assertTrue(item in result,
                                    '\nExpected:\n%s\nin Result:\n%s' % (
                                        pprint.pformat(item),
                                        pprint.pformat(result)))

    def _test_consistent_conversion(self, example_resource):
        to_aim_converter = converter.AciToAimModelConverter()
        # AIM to ACI
        result = self.converter.convert([example_resource])
        # Back to AIM
        result = to_aim_converter.convert(result)
        self.assertEqual(
            [example_resource], result,
            'Expected\n%s\nnot in\n%s' % (self._dump(example_resource),
                                          self._dump(result)))

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
        self._test_convert(self.sample_input, self.sample_output)


class TestAimToAciConverterBD(TestAimToAciConverterBase, base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_bd(l3out_names=[
                                                           'l1', 'l2']),
                    base.TestAimDBBase._get_example_aim_bd(name='test-1',
                                                           vrf_name='common',
                                                           display_name='ali',
                                                           ip_learning=False)]
    sample_output = [
        [_aci_obj('fvBD', dn="uni/tn-test-tenant/BD-test",
                  arpFlood='no', epMoveDetectMode="",
                  limitIpLearnToSubnets="no", unicastRoute="yes",
                  ipLearning="yes", unkMacUcastAct="proxy", nameAlias=""),
         _aci_obj('fvRsCtx', dn="uni/tn-test-tenant/BD-test/rsctx",
                  tnFvCtxName='default'),
         _aci_obj('fvRsBDToOut',
                  dn='uni/tn-test-tenant/BD-test/rsBDToOut-l1',
                  tnL3extOutName='l1'),
         _aci_obj('fvRsBDToOut',
                  dn='uni/tn-test-tenant/BD-test/rsBDToOut-l2',
                  tnL3extOutName='l2')],
        [{
            "fvBD": {
                "attributes": {
                    "arpFlood": "no",
                    "dn": "uni/tn-test-tenant/BD-test-1",
                    "epMoveDetectMode": "",
                    "limitIpLearnToSubnets": "no",
                    "ipLearning": "no",
                    "unicastRoute": "yes",
                    "nameAlias": "ali",
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
                "ipLearning": "yes",
                "unicastRoute": "yes",
                "unkMacUcastAct": "proxy",
                "nameAlias": ""}}}]


class TestAimToAciConverterVRF(TestAimToAciConverterBase, base.TestAimDBBase):
    sample_input = [
        base.TestAimDBBase._get_example_aim_vrf(),
        base.TestAimDBBase._get_example_aim_vrf(
            name='test-1', display_name='alias',
            policy_enforcement_pref=resource.VRF.POLICY_UNENFORCED)]
    sample_output = [
        [{
            "fvCtx": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ctx-test",
                    "pcEnfPref": "enforced",
                    "nameAlias": ""}}}],
        [{
            "fvCtx": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ctx-test-1",
                    "pcEnfPref": "unenforced",
                    "nameAlias": "alias"}}}]]


class TestAimToAciConverterSubnet(TestAimToAciConverterBase,
                                  base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_subnet(),
                    base.TestAimDBBase._get_example_aim_subnet(
                        gw_ip_mask='10.10.20.0/28',
                        scope=resource.Subnet.SCOPE_PRIVATE,
                        display_name='alias')]
    sample_output = [
        [{
            "fvSubnet": {
                "attributes": {
                    "dn": "uni/tn-t1/BD-test/subnet-[10.10.10.0/28]",
                    "scope": "public", "nameAlias": ""}}}],
        [{
            "fvSubnet": {
                "attributes": {
                    "dn": "uni/tn-t1/BD-test/subnet-[10.10.20.0/28]",
                    "scope": "private",
                    "nameAlias": "alias"}}}]]


class TestAimToAciConverterAppProfile(TestAimToAciConverterBase,
                                      base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_app_profile(),
                    base.TestAimDBBase._get_example_aim_app_profile(
                        name='test1', display_name='alias')]
    sample_output = [
        [{
            "fvAp": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ap-test", "nameAlias": ""}}}],
        [{
            "fvAp": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ap-test1",
                    "nameAlias": "alias"}}}]]


class TestAimToAciConverterTenant(TestAimToAciConverterBase,
                                  base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_tenant(),
                    base.TestAimDBBase._get_example_aim_tenant(
                        name='test1', display_name='alias', descr='2')]
    sample_output = [
        [{
            "fvTenant": {
                "attributes": {"dn": "uni/tn-test-tenant", "nameAlias": "",
                               "descr": ""}}}],
        [{
            "fvTenant": {
                "attributes": {"dn": "uni/tn-test1", "nameAlias": "alias",
                               "descr": "2"}}}]]


class TestAimToAciConverterEPG(TestAimToAciConverterBase, base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_epg(),
                    base.TestAimDBBase._get_example_aim_epg(
                        name='test-1', bd_name='net2',
                        policy_enforcement_pref=(
                            resource.EndpointGroup.POLICY_ENFORCED),
                        provided_contract_names=['k', 'p1'],
                        consumed_contract_names=['c1', 'k'],
                        openstack_vmm_domain_names=['op', 'op2'],
                        physical_domain_names=['phys'],
                        epg_contract_masters=[{'app_profile_name': 'masterap1',
                                               'name': 'masterepg1'},
                                              {'app_profile_name': 'masterap2',
                                               'name': 'masterepg2'}],
                        static_paths=[{'path': 'topology/pod-1/paths-202/'
                                               'pathep-[eth1/7]',
                                       'encap': 'vlan-33', 'mode': 'untagged'},
                                      {'path': 'topology/pod-1/'
                                       'protpaths-501-502/pathep-'
                                       '[sauto-po-501-1-48-and-502-1-48]',
                                       'encap': 'vlan-39'}],
                        display_name='alias'),
                    base.TestAimDBBase._get_example_aim_epg(
                        name='test-2',
                        openstack_vmm_domain_names=['op'],
                        physical_domain_names=['phys'],
                        vmm_domains=[{'type': 'VMware', 'name': 'vmw'},
                                     {'type': 'OpenStack', 'name': 'op'}],
                        physical_domains=[{'name': 'phys1'}])
                    ]
    sample_output = [
        [{
            "fvAEPg": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test",
                    "pcEnfPref": "unenforced", "nameAlias": ""}}}, {
            "fvRsBd": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test/rsbd",
                    "tnFvBDName": "net1"}}}],
        [{
            "fvAEPg": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-1",
                    "pcEnfPref": "enforced", "nameAlias": "alias"}}}, {
            "fvRsBd": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-1/rsbd",
                    "tnFvBDName": "net2"}}}, {
            "fvRsProv": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-1/rsprov-k",
                    "tnVzBrCPName": "k"}}}, {
            "fvRsProv": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-1/rsprov-p1",
                    "tnVzBrCPName": "p1"}}}, {
            "fvRsCons": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-1/rscons-c1",
                    "tnVzBrCPName": "c1"}}}, {
            "fvRsCons": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-1/rscons-k",
                    "tnVzBrCPName": "k"}}}, {
            'fvRsDomAtt': {
                'attributes': {
                    'dn': 'uni/tn-t1/ap-a1/epg-test-1/'
                          'rsdomAtt-[uni/phys-phys]',
                    'tDn': 'uni/phys-phys'}}}, {
            'fvRsDomAtt': {
                'attributes': {
                    'dn': 'uni/tn-t1/ap-a1/epg-test-1/'
                          'rsdomAtt-[uni/vmmp-OpenStack/dom-op]',
                    'tDn': 'uni/vmmp-OpenStack/dom-op',
                    'classPref': 'useg', 'instrImedcy': 'lazy'}}}, {
            'fvRsDomAtt': {
                'attributes': {
                    'dn': 'uni/tn-t1/ap-a1/epg-test-1/'
                          'rsdomAtt-[uni/vmmp-OpenStack/dom-op2]',
                    'tDn': 'uni/vmmp-OpenStack/dom-op2',
                    'classPref': 'useg', 'instrImedcy': 'lazy'}}},
            _aci_obj('fvRsPathAtt',
                     dn='uni/tn-t1/ap-a1/epg-test-1/rspathAtt-'
                        '[topology/pod-1/paths-202/pathep-[eth1/7]]',
                     tDn='topology/pod-1/paths-202/pathep-[eth1/7]',
                     encap='vlan-33', mode='untagged'),
            _aci_obj('fvRsPathAtt',
                     dn='uni/tn-t1/ap-a1/epg-test-1/rspathAtt-'
                        '[topology/pod-1/protpaths-501-502/'
                        'pathep-[sauto-po-501-1-48-and-502-1-48]]',
                     tDn='topology/pod-1/protpaths-501-502/'
                         'pathep-[sauto-po-501-1-48-and-502-1-48]',
                     encap='vlan-39', mode='regular'),
            _aci_obj('fvRsSecInherited',
                     dn='uni/tn-t1/ap-a1/epg-test-1/rssecInherited-'
                        '[uni/tn-t1/ap-masterap1/epg-masterepg1]',
                     tDn='uni/tn-t1/ap-masterap1/epg-masterepg1'),
            _aci_obj('fvRsSecInherited',
                     dn='uni/tn-t1/ap-a1/epg-test-1/rssecInherited-'
                        '[uni/tn-t1/ap-masterap2/epg-masterepg2]',
                     tDn='uni/tn-t1/ap-masterap2/epg-masterepg2')],
        [{
            "fvAEPg": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-2",
                    "pcEnfPref": "unenforced", "nameAlias": ""}}}, {
            "fvRsBd": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test-2/rsbd",
                    "tnFvBDName": "net1"}}}, {
            'fvRsDomAtt': {
                'attributes': {
                    'dn': 'uni/tn-t1/ap-a1/epg-test-2/'
                          'rsdomAtt-[uni/phys-phys]',
                    'tDn': 'uni/phys-phys'}}}, {
            'fvRsDomAtt': {
                'attributes': {
                    'dn': 'uni/tn-t1/ap-a1/epg-test-2/'
                          'rsdomAtt-[uni/phys-phys1]',
                    'tDn': 'uni/phys-phys1'}}}, {
            'fvRsDomAtt': {
                'attributes': {
                    'dn': 'uni/tn-t1/ap-a1/epg-test-2/'
                          'rsdomAtt-[uni/vmmp-OpenStack/dom-op]',
                    'tDn': 'uni/vmmp-OpenStack/dom-op',
                    'classPref': 'useg', 'instrImedcy': 'lazy'}}}, {
            'fvRsDomAtt': {
                'attributes': {
                    'dn': 'uni/tn-t1/ap-a1/epg-test-2/'
                          'rsdomAtt-[uni/vmmp-VMware/dom-vmw]',
                    'tDn': 'uni/vmmp-VMware/dom-vmw',
                    'classPref': 'useg', 'instrImedcy': 'immediate'}}}]

    ]
    missing_ref_input = base.TestAimDBBase._get_example_aim_epg(bd_name=None)
    missing_ref_output = [{
        "fvAEPg": {"attributes": {"dn": "uni/tn-t1/ap-a1/epg-test",
                                  "pcEnfPref": "unenforced",
                                  "nameAlias": ""}}}]


class TestAimToAciConverterEPGNoUseg(TestAimToAciConverterEPG):
    def setUp(self):
        super(TestAimToAciConverterEPGNoUseg, self).setUp()
        for tll in self.sample_output:
            for tla in tll:
                if 'fvRsDomAtt' in tla:
                    if 'classPref' in tla['fvRsDomAtt']['attributes']:
                        del(tla['fvRsDomAtt']['attributes']['classPref'])
        aim_cfg.CONF.set_override('disable_micro_segmentation', True, 'aim')


class TestAimToAciConverterFault(TestAimToAciConverterBase,
                                 base.TestAimDBBase):
    sample_output = [[base.TestAimDBBase._get_example_aci_fault()],
                     [base.TestAimDBBase._get_example_aci_fault(
                         dn='uni/tn-t1/ap-a1/epg-test-1/fault-500',
                         code='500')]]
    sample_input = [
        aim_status.AciFault(
            fault_code='951',
            external_identifier='uni/tn-t1/ap-a1/epg-test/fault-951',
            description='cannot resolve',
            severity='warning',
            cause='resolution-failed'),
        aim_status.AciFault(
            fault_code='500',
            external_identifier='uni/tn-t1/ap-a1/epg-test-1/fault-500',
            description='cannot resolve',
            severity='warning',
            cause='resolution-failed')]


def get_example_aim_filter(**kwargs):
    example = resource.Filter(tenant_name='test-tenant', name='f1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterFilter(TestAimToAciConverterBase,
                                  base.TestAimDBBase):
    sample_input = [get_example_aim_filter(),
                    get_example_aim_filter(name='f2', display_name='alias')]
    sample_output = [
        [_aci_obj('vzFilter', dn='uni/tn-test-tenant/flt-f1', nameAlias="")],
        [_aci_obj('vzFilter', dn='uni/tn-test-tenant/flt-f2',
                  nameAlias='alias')]
    ]


def get_example_aim_filter_entry(**kwargs):
    example = resource.FilterEntry(
        tenant_name='test-tenant', filter_name='f1', name='e1',
        arp_opcode='req', ether_type='arp',
        source_from_port='200', source_to_port='https',
        dest_from_port='2000', dest_to_port='4000',
        tcp_flags='est', stateful=True)
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterFilterEntry(TestAimToAciConverterBase,
                                       base.TestAimDBBase):
    sample_input = [
        get_example_aim_filter_entry(
            source_from_port='80', source_to_port=444,
            dest_from_port='110', dest_to_port='rstp',
            tcp_flags='unspecified', arp_opcode=1,
            ether_type='0x8847', ip_protocol=115,
            icmpv4_type=0, icmpv6_type='135', display_name='alias'),
        get_example_aim_filter_entry(
            name='e2', tcp_flags='ack', fragment_only=True)]
    sample_output = [
        [_aci_obj('vzEntry', dn='uni/tn-test-tenant/flt-f1/e-e1',
                  arpOpc='req', etherT='mpls_ucast', prot='l2tp',
                  icmpv4T='echo-rep', icmpv6T='nbr-solicit',
                  sFromPort='http', sToPort='444',
                  dFromPort='pop3', dToPort='rstp',
                  tcpRules='', stateful='yes', applyToFrag='no',
                  nameAlias='alias')],
        [_aci_obj('vzEntry', dn='uni/tn-test-tenant/flt-f1/e-e2',
                  arpOpc='req', etherT='arp', prot='unspecified',
                  icmpv4T='unspecified', icmpv6T='unspecified',
                  sFromPort='200', sToPort='https',
                  dFromPort='2000', dToPort='4000',
                  tcpRules='ack', stateful='yes', applyToFrag='yes',
                  nameAlias="")]
    ]

    def test_bd_consistent_conversion(self):
        # Consistent conversion is not guaranteed since we dont't know whether
        # the user specified a literal or a code to begin with
        self._test_consistent_conversion(self.sample_input[1])


def get_example_aim_contract(**kwargs):
    example = resource.Contract(tenant_name='test-tenant', name='c1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterContract(TestAimToAciConverterBase,
                                    base.TestAimDBBase):
    sample_input = [get_example_aim_contract(),
                    get_example_aim_contract(
                        name='c2', scope=resource.Contract.SCOPE_TENANT,
                        display_name='alias')]
    sample_output = [
        [_aci_obj('vzBrCP', dn='uni/tn-test-tenant/brc-c1', scope='context',
                  nameAlias="")],
        [_aci_obj('vzBrCP', dn='uni/tn-test-tenant/brc-c2', scope='tenant',
                  nameAlias='alias')]
    ]


def get_example_aim_contract_subject(**kwargs):
    example = resource.ContractSubject(tenant_name='test-tenant',
                                       contract_name='c1', name='s1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterContractSubject(TestAimToAciConverterBase,
                                           base.TestAimDBBase):
    sample_input = [
        get_example_aim_contract_subject(in_filters=['i1', 'i2'],
                                         out_filters=['o1', 'o2'],
                                         bi_filters=['f1', 'f2'],
                                         service_graph_name='g1',
                                         in_service_graph_name='g2',
                                         display_name='alias'),
        get_example_aim_contract_subject(name='s2',
                                         out_service_graph_name='g3')]
    sample_output = [
        [_aci_obj('vzSubj', dn='uni/tn-test-tenant/brc-c1/subj-s1',
                  nameAlias='alias'),
         _aci_obj('vzRsSubjFiltAtt',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/rssubjFiltAtt-f1',
                  tnVzFilterName='f1'),
         _aci_obj('vzRsSubjFiltAtt',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/rssubjFiltAtt-f2',
                  tnVzFilterName='f2'),
         _aci_obj('vzRsSubjGraphAtt',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/rsSubjGraphAtt',
                  tnVnsAbsGraphName='g1'),
         _aci_obj('vzRsFiltAtt__In',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/intmnl/rsfiltAtt-i1',
                  tnVzFilterName='i1'),
         _aci_obj('vzRsFiltAtt__In',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/intmnl/rsfiltAtt-i2',
                  tnVzFilterName='i2'),
         _aci_obj('vzRsFiltAtt__Out',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/outtmnl/rsfiltAtt-o1',
                  tnVzFilterName='o1'),
         _aci_obj('vzRsFiltAtt__Out',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/outtmnl/rsfiltAtt-o2',
                  tnVzFilterName='o2'),
         _aci_obj('vzInTerm',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/intmnl'),
         _aci_obj('vzOutTerm',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/outtmnl'),
         _aci_obj('vzRsInTermGraphAtt',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/intmnl/'
                     'rsInTermGraphAtt',
                  tnVnsAbsGraphName='g2')],
        [_aci_obj('vzSubj', dn='uni/tn-test-tenant/brc-c1/subj-s2',
                  nameAlias=""),
         _aci_obj('vzOutTerm',
                  dn='uni/tn-test-tenant/brc-c1/subj-s2/outtmnl'),
         _aci_obj('vzRsOutTermGraphAtt',
                  dn='uni/tn-test-tenant/brc-c1/subj-s2/outtmnl/'
                     'rsOutTermGraphAtt',
                  tnVnsAbsGraphName='g3')]]


def get_example_aim_l3outside(**kwargs):
    example = resource.L3Outside(tenant_name='t1',
                                 name='inet1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterL3Outside(TestAimToAciConverterBase,
                                     base.TestAimDBBase):
    resource_type = resource.L3Outside
    reverse_map_output = [
        {'resource': 'l3extOut',
         'exceptions': {},
         'skip': ['vrf_name', 'l3_domain_dn', 'bgpEnable']},
        {'converter': converter.bgp_extp_converter,
         'exceptions': {},
         'resource': 'bgpExtP'}
    ]
    sample_input = [get_example_aim_l3outside(name='inet2', vrf_name='l3p',
                                              l3_domain_dn='uni/foo'),
                    get_example_aim_l3outside(name='inet2', vrf_name='shared',
                                              l3_domain_dn='uni/foo',
                                              pre_existing=True),
                    get_example_aim_l3outside(vrf_name='shared',
                                              l3_domain_dn='uni/foo2',
                                              tenant_name='common',
                                              name='l3o2',
                                              dn='uni/tn-common/out-l3o2',
                                              monitored=True,
                                              display_name='alias'),
                    get_example_aim_l3outside(name='inet3')]
    sample_output = [
        [_aci_obj('l3extOut', dn='uni/tn-t1/out-inet2', nameAlias=""),
         _aci_obj('l3extRsEctx', dn='uni/tn-t1/out-inet2/rsectx',
                  tnFvCtxName='l3p'),
         _aci_obj('l3extRsL3DomAtt',
                  dn='uni/tn-t1/out-inet2/rsl3DomAtt',
                  tDn='uni/foo')],
        [],
        [_aci_obj('l3extOut', dn='uni/tn-common/out-l3o2', nameAlias='alias'),
         _aci_obj('l3extRsEctx', dn='uni/tn-common/out-l3o2/rsectx',
                  tnFvCtxName='shared'),
         _aci_obj('l3extRsL3DomAtt',
                  dn='uni/tn-common/out-l3o2/rsl3DomAtt',
                  tDn='uni/foo2')],
        [_aci_obj('l3extOut', dn='uni/tn-t1/out-inet3', nameAlias=''),
         _aci_obj('l3extRsEctx', dn='uni/tn-t1/out-inet3/rsectx',
                  tnFvCtxName=''),
         _aci_obj('l3extRsL3DomAtt',
                  dn='uni/tn-t1/out-inet3'
                     '/rsl3DomAtt',
                  tDn='')]]
    missing_ref_input = get_example_aim_l3outside(vrf_name=None,
                                                  l3_domain_dn=None)
    missing_ref_output = [_aci_obj('l3extOut', dn='uni/tn-t1/out-inet1',
                                   nameAlias='')]


def get_example_aim_l3out_node_profile(**kwargs):
    example = resource.L3OutNodeProfile(tenant_name='t1', l3out_name='l1',
                                        name='np1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterL3OutNodeProfile(TestAimToAciConverterBase,
                                            base.TestAimDBBase):
    sample_input = [
        get_example_aim_l3out_node_profile(
            name='np2',
            display_name='alias'),
        get_example_aim_l3out_node_profile(
            pre_existing=True),
        get_example_aim_l3out_node_profile(
            monitored=True)]
    sample_output = [
        [_aci_obj('l3extLNodeP', dn='uni/tn-t1/out-l1/lnodep-np2',
                  nameAlias='alias')],
        [],
        [_aci_obj('l3extLNodeP', dn='uni/tn-t1/out-l1/lnodep-np1',
                  nameAlias='')]]
    missing_ref_input = get_example_aim_l3out_node_profile()
    missing_ref_output = [_aci_obj('l3extLNodeP',
                                   dn='uni/tn-t1/out-l1/lnodep-np1',
                                   nameAlias='')]


def get_example_aim_l3out_node(**kwargs):
    example = resource.L3OutNode(tenant_name='t1', l3out_name='l1',
                                 node_profile_name='np1',
                                 node_path='topology/pod-1/node-101',
                                 router_id='9.9.9.9',
                                 router_id_loopback=True)
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterL3OutNode(TestAimToAciConverterBase,
                                     base.TestAimDBBase):
    sample_input = [
        get_example_aim_l3out_node(
            node_path='topology/pod-1/node-201',
            router_id='8.8.8.8',
            router_id_loopback=False),
        get_example_aim_l3out_node(
            pre_existing=True),
        get_example_aim_l3out_node(
            monitored=True)]
    sample_output = [
        [_aci_obj('l3extRsNodeL3OutAtt',
                  dn='uni/tn-t1/out-l1/lnodep-np1/rsnodeL3OutAtt-'
                     '[topology/pod-1/node-201]',
                  rtrId='8.8.8.8',
                  rtrIdLoopBack='no')],
        [],
        [_aci_obj('l3extRsNodeL3OutAtt',
                  dn='uni/tn-t1/out-l1/lnodep-np1/rsnodeL3OutAtt-'
                     '[topology/pod-1/node-101]',
                  rtrId='9.9.9.9',
                  rtrIdLoopBack='yes')]]
    missing_ref_input = get_example_aim_l3out_node()
    missing_ref_output = [_aci_obj('l3extRsNodeL3OutAtt',
                                   dn='uni/tn-t1/out-l1/lnodep-np1/'
                                      'rsnodeL3OutAtt-'
                                      '[topology/pod-1/node-101]',
                                   rtrId='9.9.9.9',
                                   rtrIdLoopBack='yes')]


def get_example_aim_l3out_static_route(**kwargs):
    example = resource.L3OutStaticRoute(tenant_name='t1', l3out_name='l1',
                                        node_profile_name='np1',
                                        node_path='topology/pod-1/node-101',
                                        cidr='1.1.1.0/24')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterL3OutStaticRoute(TestAimToAciConverterBase,
                                            base.TestAimDBBase):
    sample_input = [
        get_example_aim_l3out_static_route(
            cidr='2.2.2.0/24',
            preference='2',
            display_name='alias',
            next_hop_list=[{'addr': '2.2.2.251',
                            'preference': '1'},
                           {'addr': '2.2.2.252',
                            'preference': '2'}]),
        get_example_aim_l3out_static_route(
            pre_existing=True),
        get_example_aim_l3out_static_route(
            monitored=True)]
    sample_output = [
        [_aci_obj('ipRouteP',
                  dn='uni/tn-t1/out-l1/lnodep-np1/rsnodeL3OutAtt-'
                     '[topology/pod-1/node-101]/rt-[2.2.2.0/24]',
                  pref='2',
                  nameAlias='alias'),
         _aci_obj('ipNexthopP',
                  dn='uni/tn-t1/out-l1/lnodep-np1/rsnodeL3OutAtt-'
                     '[topology/pod-1/node-101]/rt-[2.2.2.0/24]/'
                     'nh-[2.2.2.251]',
                  nhAddr='2.2.2.251',
                  type='prefix',
                  pref='1'),
         _aci_obj('ipNexthopP',
                  dn='uni/tn-t1/out-l1/lnodep-np1/rsnodeL3OutAtt-'
                     '[topology/pod-1/node-101]/rt-[2.2.2.0/24]/'
                     'nh-[2.2.2.252]',
                  nhAddr='2.2.2.252',
                  type='prefix',
                  pref='2')],
        [],
        [_aci_obj('ipRouteP',
                  dn='uni/tn-t1/out-l1/lnodep-np1/rsnodeL3OutAtt-'
                     '[topology/pod-1/node-101]/rt-[1.1.1.0/24]',
                  pref='1',
                  nameAlias='')]]
    missing_ref_input = get_example_aim_l3out_static_route()
    missing_ref_output = [_aci_obj('ipRouteP',
                                   dn='uni/tn-t1/out-l1/lnodep-np1/'
                                      'rsnodeL3OutAtt-'
                                      '[topology/pod-1/node-101]/'
                                      'rt-[1.1.1.0/24]',
                                   pref='1',
                                   nameAlias='')]


def get_example_aim_l3out_interface_profile(**kwargs):
    example = resource.L3OutInterfaceProfile(tenant_name='t1', l3out_name='l1',
                                             node_profile_name='np1',
                                             name='ip1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterL3OutInterfaceProfile(TestAimToAciConverterBase,
                                                 base.TestAimDBBase):
    sample_input = [
        get_example_aim_l3out_interface_profile(
            name='ip2',
            display_name='alias'),
        get_example_aim_l3out_interface_profile(
            pre_existing=True),
        get_example_aim_l3out_interface_profile(
            monitored=True)]
    sample_output = [
        [_aci_obj('l3extLIfP', dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip2',
                  nameAlias='alias')],
        [],
        [_aci_obj('l3extLIfP', dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1',
                  nameAlias='')]]
    missing_ref_input = get_example_aim_l3out_interface_profile()
    missing_ref_output = [_aci_obj('l3extLIfP',
                                   dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1',
                                   nameAlias='')]


def get_example_aim_l3out_interface(**kwargs):
    example = resource.L3OutInterface(
        tenant_name='t1', l3out_name='l1',
        node_profile_name='np1', interface_profile_name='ip1',
        interface_path='topology/pod-1/paths-101/pathep-[eth1/1]',
        primary_addr_a='1.1.1.1/24',
        encap='vlan-1001',
        type='ext-svi')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterL3OutInterface(TestAimToAciConverterBase,
                                          base.TestAimDBBase):
    sample_input = [
        get_example_aim_l3out_interface(
            interface_path='topology/pod-1/paths-101/pathep-[eth1/2]',
            secondary_addr_a_list=[{'addr': '1.1.1.2/24'},
                                   {'addr': '1.1.1.3/24'}]),
        get_example_aim_l3out_interface(
            pre_existing=True),
        get_example_aim_l3out_interface(
            primary_addr_a='1.1.1.101/24',
            encap='vlan-1002',
            mode='native',
            secondary_addr_a_list=[{'addr': '1.1.1.11/24'},
                                   {'addr': '1.1.1.12/24'}],
            primary_addr_b='1.1.1.102/24',
            secondary_addr_b_list=[{'addr': '1.1.1.13/24'},
                                   {'addr': '1.1.1.14/24'}],
            monitored=True)]
    sample_output = [
        [_aci_obj('l3extRsPathL3OutAtt',
                  addr='1.1.1.1/24',
                  encap='vlan-1001',
                  mode='regular',
                  ifInstT='ext-svi',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/rspathL3OutAtt-'
                     '[topology/pod-1/paths-101/pathep-[eth1/2]]'),
         _aci_obj('l3extIp',
                  addr='1.1.1.2/24',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/2]]/addr-[1.1.1.2/24]'),
         _aci_obj('l3extIp',
                  addr='1.1.1.3/24',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/2]]/addr-[1.1.1.3/24]')],
        [],
        [_aci_obj('l3extRsPathL3OutAtt',
                  addr='1.1.1.101/24',
                  encap='vlan-1002',
                  mode='native',
                  ifInstT='ext-svi',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/rspathL3OutAtt-'
                     '[topology/pod-1/paths-101/pathep-[eth1/1]]'),
         _aci_obj('l3extMember',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/mem-A',
                  side='A',
                  addr='1.1.1.101/24'),
         _aci_obj('l3extIp__Member',
                  addr='1.1.1.11/24',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/mem-A/addr-[1.1.1.11/24]'),
         _aci_obj('l3extIp__Member',
                  addr='1.1.1.12/24',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/mem-A/addr-[1.1.1.12/24]'),
         _aci_obj('l3extMember',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/mem-B',
                  side='B',
                  addr='1.1.1.102/24'),
         _aci_obj('l3extIp__Member',
                  addr='1.1.1.13/24',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/mem-B/addr-[1.1.1.13/24]'),
         _aci_obj('l3extIp__Member',
                  addr='1.1.1.14/24',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/mem-B/addr-[1.1.1.14/24]')]]
    missing_ref_input = get_example_aim_l3out_interface()
    missing_ref_output = [_aci_obj('l3extRsPathL3OutAtt',
                                   addr='1.1.1.1/24',
                                   encap='vlan-1001',
                                   mode='regular',
                                   ifInstT='ext-svi',
                                   dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                                      'rspathL3OutAtt-[topology/pod-1'
                                      '/paths-101/pathep-[eth1/1]]')]


def get_example_aim_external_network(**kwargs):
    example = resource.ExternalNetwork(tenant_name='t1', l3out_name='l1',
                                       name='inet1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterExternalNetwork(TestAimToAciConverterBase,
                                           base.TestAimDBBase):
    sample_input = [
        get_example_aim_external_network(
            name='inet2',
            nat_epg_dn='uni/foo',
            provided_contract_names=['k', 'p1'],
            consumed_contract_names=['c1', 'k'],
            display_name='alias'),
        get_example_aim_external_network(
            nat_epg_dn='uni/foo',
            provided_contract_names=['k', 'p1'],
            consumed_contract_names=['c1', 'k'],
            pre_existing=True),
        get_example_aim_external_network(
            nat_epg_dn='uni/foo',
            provided_contract_names=['k', 'p1'],
            consumed_contract_names=['c1', 'k'],
            monitored=True)]
    sample_output = [
        [_aci_obj('l3extInstP', dn='uni/tn-t1/out-l1/instP-inet2',
                  nameAlias='alias'),
         _aci_obj('l3extRsInstPToNatMappingEPg',
                  dn=('uni/tn-t1/out-l1/instP-inet2/'
                      'rsInstPToNatMappingEPg'),
                  tDn='uni/foo'),
         _aci_obj('fvRsProv__Ext',
                  dn='uni/tn-t1/out-l1/instP-inet2/rsprov-k',
                  tnVzBrCPName='k'),
         _aci_obj('fvRsProv__Ext',
                  dn='uni/tn-t1/out-l1/instP-inet2/rsprov-p1',
                  tnVzBrCPName='p1'),
         _aci_obj('fvRsCons__Ext',
                  dn='uni/tn-t1/out-l1/instP-inet2/rscons-k',
                  tnVzBrCPName='k'),
         _aci_obj('fvRsCons__Ext',
                  dn='uni/tn-t1/out-l1/instP-inet2/rscons-c1',
                  tnVzBrCPName='c1')],
        [_aci_obj('fvRsProv__Ext',
                  dn='uni/tn-t1/out-l1/instP-inet1/rsprov-k',
                  tnVzBrCPName='k'),
         _aci_obj('fvRsProv__Ext',
                  dn='uni/tn-t1/out-l1/instP-inet1/rsprov-p1',
                  tnVzBrCPName='p1'),
         _aci_obj('fvRsCons__Ext',
                  dn='uni/tn-t1/out-l1/instP-inet1/rscons-k',
                  tnVzBrCPName='k'),
         _aci_obj('fvRsCons__Ext',
                  dn='uni/tn-t1/out-l1/instP-inet1/rscons-c1',
                  tnVzBrCPName='c1')],
        [_aci_obj('l3extInstP', dn='uni/tn-t1/out-l1/instP-inet1',
                  nameAlias=''),
         _aci_obj('l3extRsInstPToNatMappingEPg',
                  dn=('uni/tn-t1/out-l1/instP-inet1/'
                      'rsInstPToNatMappingEPg'),
                  tDn='uni/foo')]]
    missing_ref_input = get_example_aim_external_network(nat_epg_dn=None)
    missing_ref_output = [_aci_obj('l3extInstP',
                                   dn='uni/tn-t1/out-l1/instP-inet1',
                                   nameAlias='')]


def get_example_aim_external_subnet(**kwargs):
    example = resource.ExternalSubnet(
        tenant_name='t1', l3out_name='l1', external_network_name='inet1',
        cidr='4.20.0.0/16')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterExternalSubnet(TestAimToAciConverterBase,
                                          base.TestAimDBBase):
    sample_input = [get_example_aim_external_subnet(),
                    get_example_aim_external_subnet(
                        external_network_name='inet2',
                        cidr='2.11.0.0/16',
                        display_name='alias')]
    sample_output = [
        [_aci_obj('l3extSubnet',
                  dn='uni/tn-t1/out-l1/instP-inet1/extsubnet-[4.20.0.0/16]',
                  nameAlias="",
                  aggregate="",
                  scope="import-security")],
        [_aci_obj('l3extSubnet',
                  dn='uni/tn-t1/out-l1/instP-inet2/extsubnet-[2.11.0.0/16]',
                  nameAlias='alias',
                  aggregate="",
                  scope="import-security")]]


def get_example_aim_security_group(**kwargs):
    example = resource.SecurityGroup(tenant_name='t1', name='sg1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterSecurityGroup(TestAimToAciConverterBase,
                                         base.TestAimDBBase):
    sample_input = [get_example_aim_security_group(),
                    get_example_aim_security_group(name='sg2')]

    sample_output = [
        [_aci_obj('hostprotPol', dn='uni/tn-t1/pol-sg1', nameAlias='')],
        [_aci_obj('hostprotPol', dn='uni/tn-t1/pol-sg2', nameAlias='')]]


def get_example_aim_security_group_subject(**kwargs):
    example = resource.SecurityGroupSubject(
        tenant_name='t1', security_group_name='sg1', name='sgs1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterSecurityGroupSubject(TestAimToAciConverterBase,
                                                base.TestAimDBBase):
    sample_input = [get_example_aim_security_group_subject(),
                    get_example_aim_security_group_subject(
                        security_group_name='sg2')]

    sample_output = [
        [_aci_obj('hostprotSubj', dn='uni/tn-t1/pol-sg1/subj-sgs1',
                  nameAlias='')],
        [_aci_obj('hostprotSubj', dn='uni/tn-t1/pol-sg2/subj-sgs1',
                  nameAlias='')]]


class TestAimToAciConverterSecurityGroupRule(TestAimToAciConverterBase,
                                             base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_security_group_rule(),
                    base.TestAimDBBase._get_example_aim_security_group_rule(
                        security_group_name='sg2', ip_protocol=115,
                        from_port='80', to_port='443',
                        direction='egress', ethertype='1',
                        conn_track='normal', icmp_type='3',
                        icmp_code='0'),
                    base.TestAimDBBase._get_example_aim_security_group_rule(
                        security_group_name='sg3', ip_protocol=1,
                        from_port='80', to_port='443',
                        remote_ips=['10.0.1.0/24', '192.168.0.0/24'],
                        direction='egress', ethertype='1',
                        conn_track='normal', icmp_type='255',
                        icmp_code='0xffff'),
                    base.TestAimDBBase._get_example_aim_security_group_rule(
                        security_group_name='sg4', ip_protocol=6,
                        from_port='80', to_port='443',
                        direction='egress', ethertype='2',
                        conn_track='normal', icmp_type='unspecified',
                        icmp_code='unspecified')]

    sample_output = [
        [_aci_obj('hostprotRule',
                  dn='uni/tn-t1/pol-sg1/subj-sgs1/rule-rule1',
                  direction='ingress', protocol='unspecified',
                  fromPort='unspecified', toPort='unspecified',
                  ethertype='undefined', nameAlias='', connTrack='reflexive',
                  icmpCode='unspecified', icmpType='unspecified')],
        [_aci_obj('hostprotRule',
                  dn='uni/tn-t1/pol-sg2/subj-sgs1/rule-rule1',
                  protocol='l2tp', direction='egress',
                  fromPort='http', toPort='https',
                  ethertype='ipv4', nameAlias='', connTrack='normal',
                  icmpCode='no-code', icmpType='dst-unreach')],
        [_aci_obj('hostprotRule',
                  dn='uni/tn-t1/pol-sg3/subj-sgs1/rule-rule1',
                  protocol='icmp', direction='egress',
                  fromPort='http', toPort='https',
                  ethertype='ipv4', nameAlias='', connTrack='normal',
                  icmpCode='unspecified', icmpType='unspecified'),
         _aci_obj(
             'hostprotRemoteIp',
             dn='uni/tn-t1/pol-sg3/subj-sgs1/rule-rule1/ip-[10.0.1.0/24]',
             addr='10.0.1.0/24'),
         _aci_obj(
             'hostprotRemoteIp',
             dn='uni/tn-t1/pol-sg3/subj-sgs1/rule-rule1/ip-[192.168.0.0/24]',
             addr='192.168.0.0/24')],
        [_aci_obj('hostprotRule',
                  dn='uni/tn-t1/pol-sg4/subj-sgs1/rule-rule1',
                  protocol='tcp', direction='egress',
                  fromPort='http', toPort='https',
                  ethertype='ipv6', nameAlias='', connTrack='normal',
                  icmpCode='unspecified', icmpType='unspecified')]]


def get_example_aim_device_cluster(**kwargs):
    example = aim_service_graph.DeviceCluster(
        tenant_name='t1', name='cl1',)
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterDeviceCluster(TestAimToAciConverterBase,
                                         base.TestAimDBBase):
    sample_input = [get_example_aim_device_cluster(
                    device_type='VIRTUAL',
                    service_type='ADC',
                    context_aware='multi-Context',
                    vmm_domain_type='VMWare',
                    vmm_domain_name='vdom'),
                    get_example_aim_device_cluster(
                        name='cl2',
                        managed=False,
                        physical_domain_name='abc',
                        encap='vlan-44',
                        devices=[{'name': 'n1'},
                                 {'name': 'n2', 'path': 'foo'},
                                 {'foo': 'bar'}])]

    sample_output = [
        [_aci_obj('vnsLDevVip',
                  dn='uni/tn-t1/lDevVip-cl1',
                  devtype='VIRTUAL',
                  svcType='ADC',
                  contextAware='multi-Context',
                  managed='yes',
                  nameAlias=''),
         _aci_obj('vnsRsALDevToPhysDomP',
                  dn='uni/tn-t1/lDevVip-cl1/rsALDevToPhysDomP',
                  tDn=''),
         _aci_obj('vnsRsALDevToDomP',
                  dn='uni/tn-t1/lDevVip-cl1/rsALDevToDomP',
                  tDn='uni/vmmp-VMWare/dom-vdom')],
        [_aci_obj('vnsLDevVip',
                  dn='uni/tn-t1/lDevVip-cl2',
                  devtype='PHYSICAL',
                  svcType='OTHERS',
                  contextAware='single-Context',
                  managed='no',
                  nameAlias=''),
         _aci_obj('vnsRsALDevToPhysDomP',
                  dn='uni/tn-t1/lDevVip-cl2/rsALDevToPhysDomP',
                  tDn='uni/phys-abc'),
         _aci_obj('vnsLIf',
                  dn='uni/tn-t1/lDevVip-cl2/lIf-interface',
                  encap='vlan-44',
                  nameAlias=''),
         _aci_obj('vnsRsCIfAttN',
                  dn='uni/tn-t1/lDevVip-cl2/lIf-interface/rscIfAttN-['
                     'uni/tn-t1/lDevVip-cl2/cDev-n1/cIf-[interface]]',
                  tDn='uni/tn-t1/lDevVip-cl2/cDev-n1/cIf-[interface]'),
         _aci_obj('vnsRsCIfAttN',
                  dn='uni/tn-t1/lDevVip-cl2/lIf-interface/rscIfAttN-['
                     'uni/tn-t1/lDevVip-cl2/cDev-n2/cIf-[interface]]',
                  tDn='uni/tn-t1/lDevVip-cl2/cDev-n2/cIf-[interface]'),
         _aci_obj('vnsCDev',
                  dn='uni/tn-t1/lDevVip-cl2/cDev-n1',
                  nameAlias=''),
         _aci_obj('vnsCDev',
                  dn='uni/tn-t1/lDevVip-cl2/cDev-n2',
                  nameAlias=''),
         _aci_obj('vnsCIf',
                  dn='uni/tn-t1/lDevVip-cl2/cDev-n1/cIf-[interface]',
                  nameAlias=''),
         _aci_obj('vnsCIf',
                  dn='uni/tn-t1/lDevVip-cl2/cDev-n2/cIf-[interface]',
                  nameAlias=''),
         _aci_obj('vnsRsCIfPathAtt',
                  dn='uni/tn-t1/lDevVip-cl2/cDev-n1/cIf-[interface]/'
                     'rsCIfPathAtt',
                  tDn=''),
         _aci_obj('vnsRsCIfPathAtt',
                  dn='uni/tn-t1/lDevVip-cl2/cDev-n2/cIf-[interface]/'
                     'rsCIfPathAtt',
                  tDn='foo')]
    ]


def get_example_aim_device_cluster_if(**kwargs):
    example = aim_service_graph.DeviceClusterInterface(
        tenant_name='t1', device_cluster_name='cl1', name='if1',
        encap='vlan-55')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterDeviceClusterInterface(TestAimToAciConverterBase,
                                                  base.TestAimDBBase):
    sample_input = [get_example_aim_device_cluster_if(),
                    get_example_aim_device_cluster_if(
                        name='if2',
                        concrete_interfaces=['abc', 'xyz'])]

    sample_output = [
        [_aci_obj('vnsLIf',
                  dn='uni/tn-t1/lDevVip-cl1/lIf-if1',
                  encap='vlan-55',
                  nameAlias='')],
        [_aci_obj('vnsLIf',
                  dn='uni/tn-t1/lDevVip-cl1/lIf-if2',
                  encap='vlan-55',
                  nameAlias=''),
         _aci_obj('vnsRsCIfAttN',
                  dn='uni/tn-t1/lDevVip-cl1/lIf-if2/rscIfAttN-[abc]',
                  tDn='abc'),
         _aci_obj('vnsRsCIfAttN',
                  dn='uni/tn-t1/lDevVip-cl1/lIf-if2/rscIfAttN-[xyz]',
                  tDn='xyz')]
    ]


def get_example_aim_dev_cluster_device(**kwargs):
    example = aim_service_graph.ConcreteDevice(
        tenant_name='t1', device_cluster_name='cl1', name='node1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterConcreteDevice(TestAimToAciConverterBase,
                                          base.TestAimDBBase):
    sample_input = [get_example_aim_dev_cluster_device(),
                    get_example_aim_dev_cluster_device(name='node2')]

    sample_output = [
        [_aci_obj('vnsCDev',
                  dn='uni/tn-t1/lDevVip-cl1/cDev-node1',
                  nameAlias='')],
        [_aci_obj('vnsCDev',
                  dn='uni/tn-t1/lDevVip-cl1/cDev-node2',
                  nameAlias='')]
    ]


def get_example_aim_dev_cluster_device_if(**kwargs):
    example = aim_service_graph.ConcreteDeviceInterface(
        tenant_name='t1', device_cluster_name='cl1', device_name='node1',
        name='if1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterConcreteDeviceInterface(
        TestAimToAciConverterBase,
        base.TestAimDBBase):
    sample_input = [get_example_aim_dev_cluster_device_if(),
                    get_example_aim_dev_cluster_device_if(
                        name='if2',
                        path='foo/bar')]

    sample_output = [
        [_aci_obj('vnsCIf',
                  dn='uni/tn-t1/lDevVip-cl1/cDev-node1/cIf-[if1]',
                  nameAlias=''),
         _aci_obj('vnsRsCIfPathAtt',
                  dn='uni/tn-t1/lDevVip-cl1/cDev-node1/cIf-[if1]/'
                     'rsCIfPathAtt',
                  tDn='')],
        [_aci_obj('vnsCIf',
                  dn='uni/tn-t1/lDevVip-cl1/cDev-node1/cIf-[if2]',
                  nameAlias=''),
         _aci_obj('vnsRsCIfPathAtt',
                  dn='uni/tn-t1/lDevVip-cl1/cDev-node1/cIf-[if2]/'
                     'rsCIfPathAtt',
                  tDn='foo/bar')]
    ]


def get_example_aim_service_graph_node(**kwargs):
    example = aim_service_graph.ServiceGraphNode(
        tenant_name='t1', service_graph_name='gr1', name='N0')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterServiceGraphNode(TestAimToAciConverterBase,
                                            base.TestAimDBBase):
    sample_input = [get_example_aim_service_graph_node(display_name='N'),
                    get_example_aim_service_graph_node(
                        name='N1',
                        function_type='GoThrough', managed=False,
                        routing_mode='Redirect', connectors=['c1'],
                        device_cluster_name='cl1',
                        device_cluster_tenant_name='common',
                        sequence_number='3')]

    sample_output = [
        [_aci_obj('vnsAbsNode',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsNode-N0',
                  funcType='GoTo', managed='yes', nameAlias='N',
                  routingMode='unspecified', sequenceNumber='0'),
         _aci_obj('vnsRsNodeToLDev',
                  dn=('uni/tn-t1/AbsGraph-gr1/AbsNode-N0/rsNodeToLDev'),
                  tDn='')],
        [_aci_obj('vnsAbsNode',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsNode-N1',
                  funcType='GoThrough', managed='no', nameAlias='',
                  routingMode='Redirect', sequenceNumber='3'),
         _aci_obj('vnsAbsFuncConn',
                  dn=('uni/tn-t1/AbsGraph-gr1/AbsNode-N1/'
                      'AbsFConn-c1'),
                  name='c1'),
         _aci_obj('vnsRsNodeToLDev',
                  dn=('uni/tn-t1/AbsGraph-gr1/AbsNode-N1/rsNodeToLDev'),
                  tDn='uni/tn-common/lDevVip-cl1')]]


def get_example_aim_service_graph_connection(**kwargs):
    example = aim_service_graph.ServiceGraphConnection(
        tenant_name='t1', service_graph_name='gr1', name='C0')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterServiceGraphConnection(TestAimToAciConverterBase,
                                                  base.TestAimDBBase):
    sample_input = [get_example_aim_service_graph_connection(display_name='C'),
                    get_example_aim_service_graph_connection(
                        name='C2',
                        adjacency_type='L3',
                        connector_type='internal',
                        connector_direction='consumer',
                        unicast_route=True,
                        direct_connect=True,
                        connector_dns=['foo', 'bar'])]
    sample_output = [
        [_aci_obj('vnsAbsConnection',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsConnection-C0',
                  nameAlias='C',
                  adjType='L2', connDir='provider', connType='external',
                  directConnect='no', unicastRoute='no')],
        [_aci_obj('vnsAbsConnection',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsConnection-C2',
                  nameAlias='',
                  adjType='L3', connDir='consumer', connType='internal',
                  directConnect='yes', unicastRoute='yes'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsConnection-C2/'
                     'rsabsConnectionConns-[foo]',
                  tDn='foo'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsConnection-C2/'
                     'rsabsConnectionConns-[bar]',
                  tDn='bar')]
    ]


def get_example_aim_service_graph(**kwargs):
    example = aim_service_graph.ServiceGraph(tenant_name='t1', name='gr1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterServiceGraph(TestAimToAciConverterBase,
                                        base.TestAimDBBase):
    sample_input = [get_example_aim_service_graph(display_name='G'),
                    get_example_aim_service_graph(
                        name='gr2',
                        linear_chain_nodes=[
                            {'name': 'N0'},
                            {'name': 'N1',
                             'device_cluster_name': 'cl1'},
                            {'name': 'N2',
                             'device_cluster_name': 'cl2',
                             'device_cluster_tenant_name': 'common'},
                            {'device_cluster_name': 'cl4'}])]

    sample_output = [
        [_aci_obj('vnsAbsGraph',
                  dn='uni/tn-t1/AbsGraph-gr1', nameAlias='G'),
         _aci_obj('vnsAbsTermNodeCon',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsTermNodeCon-T1'),
         _aci_obj('vnsAbsTermConn__Con',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsTermNodeCon-T1/AbsTConn'),
         _aci_obj('vnsInTerm__Con',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsTermNodeCon-T1/intmnl'),
         _aci_obj('vnsOutTerm__Con',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsTermNodeCon-T1/outtmnl'),
         _aci_obj('vnsAbsTermNodeProv',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsTermNodeProv-T2'),
         _aci_obj('vnsAbsTermConn__Prov',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsTermNodeProv-T2/AbsTConn'),
         _aci_obj('vnsInTerm__Prov',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsTermNodeProv-T2/intmnl'),
         _aci_obj('vnsOutTerm__Prov',
                  dn='uni/tn-t1/AbsGraph-gr1/AbsTermNodeProv-T2/outtmnl')],
        [_aci_obj('vnsAbsGraph',
                  dn='uni/tn-t1/AbsGraph-gr2', nameAlias=''),
         _aci_obj('vnsAbsTermNodeCon',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsTermNodeCon-T1'),
         _aci_obj('vnsAbsTermConn__Con',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsTermNodeCon-T1/AbsTConn'),
         _aci_obj('vnsInTerm__Con',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsTermNodeCon-T1/intmnl'),
         _aci_obj('vnsOutTerm__Con',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsTermNodeCon-T1/outtmnl'),
         _aci_obj('vnsAbsTermNodeProv',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsTermNodeProv-T2'),
         _aci_obj('vnsAbsTermConn__Prov',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsTermNodeProv-T2/AbsTConn'),
         _aci_obj('vnsInTerm__Prov',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsTermNodeProv-T2/intmnl'),
         _aci_obj('vnsOutTerm__Prov',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsTermNodeProv-T2/outtmnl'),
         _aci_obj('vnsAbsNode',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsNode-N0',
                  nameAlias='',
                  managed='no', funcType='GoTo', routingMode='Redirect',
                  sequenceNumber='0'),
         _aci_obj('vnsAbsFuncConn',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsNode-N0/'
                      'AbsFConn-consumer'),
                  name='consumer'),
         _aci_obj('vnsAbsFuncConn',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsNode-N0/'
                      'AbsFConn-provider'),
                  name='provider'),
         _aci_obj('vnsRsNodeToLDev',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsNode-N0/rsNodeToLDev'),
                  tDn=''),
         _aci_obj('vnsAbsNode',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsNode-N1',
                  nameAlias='', sequenceNumber='1',
                  managed='no', funcType='GoTo', routingMode='Redirect'),
         _aci_obj('vnsAbsFuncConn',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsNode-N1/'
                      'AbsFConn-consumer'),
                  name='consumer'),
         _aci_obj('vnsAbsFuncConn',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsNode-N1/'
                      'AbsFConn-provider'),
                  name='provider'),
         _aci_obj('vnsRsNodeToLDev',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsNode-N1/'
                      'rsNodeToLDev'),
                  tDn='uni/tn-t1/lDevVip-cl1'),
         _aci_obj('vnsAbsNode',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsNode-N2',
                  nameAlias='', sequenceNumber='2',
                  managed='no', funcType='GoTo', routingMode='Redirect'),
         _aci_obj('vnsAbsFuncConn',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsNode-N2/'
                      'AbsFConn-consumer'),
                  name='consumer'),
         _aci_obj('vnsAbsFuncConn',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsNode-N2/'
                      'AbsFConn-provider'),
                  name='provider'),
         _aci_obj('vnsRsNodeToLDev',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsNode-N2/'
                      'rsNodeToLDev'),
                  tDn='uni/tn-common/lDevVip-cl2'),
         _aci_obj('vnsAbsConnection',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsConnection-C1',
                  nameAlias='',
                  adjType='L2', connDir='provider', connType='external',
                  directConnect='no', unicastRoute='yes'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsConnection-C1/'
                      'rsabsConnectionConns-[uni/tn-t1/AbsGraph-gr2/'
                      'AbsTermNodeCon-T1/AbsTConn]'),
                  tDn='uni/tn-t1/AbsGraph-gr2/'
                      'AbsTermNodeCon-T1/AbsTConn'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsConnection-C1/'
                      'rsabsConnectionConns-[uni/tn-t1/AbsGraph-gr2/'
                      'AbsNode-N0/AbsFConn-consumer]'),
                  tDn='uni/tn-t1/AbsGraph-gr2/AbsNode-N0/AbsFConn-consumer'),
         _aci_obj('vnsAbsConnection',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsConnection-C2',
                  nameAlias='',
                  adjType='L2', connDir='provider', connType='external',
                  directConnect='no', unicastRoute='yes'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsConnection-C2/'
                      'rsabsConnectionConns-[uni/tn-t1/AbsGraph-gr2/'
                      'AbsNode-N0/AbsFConn-provider]'),
                  tDn='uni/tn-t1/AbsGraph-gr2/'
                      'AbsNode-N0/AbsFConn-provider'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsConnection-C2/'
                      'rsabsConnectionConns-[uni/tn-t1/AbsGraph-gr2/'
                      'AbsNode-N1/AbsFConn-consumer]'),
                  tDn='uni/tn-t1/AbsGraph-gr2/AbsNode-N1/AbsFConn-consumer'),
         _aci_obj('vnsAbsConnection',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsConnection-C3',
                  nameAlias='',
                  adjType='L2', connDir='provider', connType='external',
                  directConnect='no', unicastRoute='yes'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsConnection-C3/'
                      'rsabsConnectionConns-[uni/tn-t1/AbsGraph-gr2/'
                      'AbsNode-N1/AbsFConn-provider]'),
                  tDn='uni/tn-t1/AbsGraph-gr2/'
                      'AbsNode-N1/AbsFConn-provider'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsConnection-C3/'
                      'rsabsConnectionConns-[uni/tn-t1/AbsGraph-gr2/'
                      'AbsNode-N2/AbsFConn-consumer]'),
                  tDn='uni/tn-t1/AbsGraph-gr2/AbsNode-N2/AbsFConn-consumer'),
         _aci_obj('vnsAbsConnection',
                  dn='uni/tn-t1/AbsGraph-gr2/AbsConnection-C4',
                  nameAlias='',
                  adjType='L2', connDir='provider', connType='external',
                  directConnect='no', unicastRoute='yes'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsConnection-C4/'
                      'rsabsConnectionConns-[uni/tn-t1/AbsGraph-gr2/'
                      'AbsNode-N2/AbsFConn-provider]'),
                  tDn='uni/tn-t1/AbsGraph-gr2/'
                      'AbsNode-N2/AbsFConn-provider'),
         _aci_obj('vnsRsAbsConnectionConns',
                  dn=('uni/tn-t1/AbsGraph-gr2/AbsConnection-C4/'
                      'rsabsConnectionConns-[uni/tn-t1/AbsGraph-gr2/'
                      'AbsTermNodeProv-T2/AbsTConn]'),
                  tDn='uni/tn-t1/AbsGraph-gr2/AbsTermNodeProv-T2/AbsTConn')
         ]
    ]


def get_example_aim_service_redirect_policy(**kwargs):
    example = aim_service_graph.ServiceRedirectPolicy(tenant_name='t1',
                                                      name='r1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterServiceRedirectPolicy(TestAimToAciConverterBase,
                                                 base.TestAimDBBase):
    sample_input = [get_example_aim_service_redirect_policy(
        display_name='R', destinations=[{'ip': '10.10.1.1',
                                         'mac': '90:E2:BA:B1:37:6C'}]),
                    get_example_aim_service_redirect_policy(
                        name='r2',
                        monitoring_policy_tenant_name='common',
                        monitoring_policy_name='mon_policy',
                        destinations=[{'ip': '10.6.1.1',
                                       'mac': '90:e2:ba:B1:36:6C',
                                       'redirect_health_group_dn': 'my/dn1'},
                                      {'ip': '10.6.1.2',
                                       'redirect_health_group_dn': 'my/dn2'},
                                      {'ip': '10.6.1.3',
                                       'mac': '90:e2:ba:B1:36:6D',
                                       'name': 'dest-name',
                                       'redirect_health_group_dn': ''},
                                      {'foo': 'bar'}])]

    sample_output = [
        [_aci_obj('vnsSvcRedirectPol',
                  dn='uni/tn-t1/svcCont/svcRedirectPol-r1',
                  nameAlias='R'),
         _aci_obj('vnsRedirectDest',
                  dn=('uni/tn-t1/svcCont/svcRedirectPol-r1/'
                      'RedirectDest_ip-[10.10.1.1]'),
                  ip='10.10.1.1',
                  mac='90:E2:BA:B1:37:6C')],
        [_aci_obj('vnsSvcRedirectPol',
                  dn='uni/tn-t1/svcCont/svcRedirectPol-r2',
                  nameAlias=''),
         _aci_obj('vnsRsIPSLAMonitoringPol',
                  dn='uni/tn-t1/svcCont/svcRedirectPol-r2/'
                     'rsIPSLAMonitoringPol',
                  tDn='uni/tn-common/ipslaMonitoringPol-mon_policy'),
         _aci_obj('vnsRedirectDest',
                  dn=('uni/tn-t1/svcCont/svcRedirectPol-r2/'
                      'RedirectDest_ip-[10.6.1.1]'),
                  ip='10.6.1.1',
                  mac='90:E2:BA:B1:36:6C'),
         _aci_obj('vnsRsRedirectHealthGroup',
                  dn='uni/tn-t1/svcCont/svcRedirectPol-r2/'
                     'RedirectDest_ip-[10.6.1.1]/rsRedirectHealthGroup',
                  tDn='my/dn1'),
         _aci_obj('vnsRedirectDest',
                  dn=('uni/tn-t1/svcCont/svcRedirectPol-r2/'
                      'RedirectDest_ip-[10.6.1.2]'),
                  ip='10.6.1.2'),
         _aci_obj('vnsRedirectDest',
                  dn=('uni/tn-t1/svcCont/svcRedirectPol-r2/'
                      'RedirectDest_ip-[10.6.1.3]'),
                  ip='10.6.1.3',
                  mac='90:E2:BA:B1:36:6D',
                  destName='dest-name'),
         _aci_obj('vnsRsRedirectHealthGroup',
                  dn='uni/tn-t1/svcCont/svcRedirectPol-r2/'
                     'RedirectDest_ip-[10.6.1.2]/rsRedirectHealthGroup',
                  tDn='my/dn2'),
         ]]

    def test_ipsla_tenant_only(self):
        example = get_example_aim_service_redirect_policy(
            display_name='R', destinations=[{'ip': '10.10.1.1',
                                             'mac': '90:E2:BA:B1:37:6C'}],
            monitoring_policy_tenant_name='common')
        result = self.converter.convert([example])
        to_aim_converter = converter.AciToAimModelConverter()
        back = to_aim_converter.convert(result)
        self.assertNotEqual(example, back[0])
        example.monitoring_policy_tenant_name = ''
        self.assertEqual(example, back[0])

    def test_ipsla_name_only(self):
        example = get_example_aim_service_redirect_policy(
            display_name='R', destinations=[{'ip': '10.10.1.1',
                                             'mac': '90:E2:BA:B1:37:6C'}],
            monitoring_policy_name='monitoring')
        result = self.converter.convert([example])
        to_aim_converter = converter.AciToAimModelConverter()
        back = to_aim_converter.convert(result)
        self.assertNotEqual(example, back[0])
        example.monitoring_policy_name = ''
        self.assertEqual(example, back[0])


class TestAimToAciConverterServiceRedirectMonitoringPolicy(
        TestAimToAciConverterBase, base.TestAimDBBase):

    sample_input = [
        aim_service_graph.ServiceRedirectMonitoringPolicy(
            tenant_name='t1', name='sla1', display_name='alias'),
        aim_service_graph.ServiceRedirectMonitoringPolicy(
            tenant_name='t1', name='sla2', tcp_port='8080',
            type='tcp', frequency='50')
    ]

    sample_output = [[_aci_obj('fvIPSLAMonitoringPol',
                               dn='uni/tn-t1/ipslaMonitoringPol-sla1',
                               nameAlias='alias',
                               slaPort='0', slaFrequency='60',
                               slaType='icmp')],
                     [_aci_obj('fvIPSLAMonitoringPol',
                               dn='uni/tn-t1/ipslaMonitoringPol-sla2',
                               nameAlias='',
                               slaPort='8080', slaType='tcp',
                               slaFrequency='50')]]


class TestAimToAciConverterServiceRedirectHealthGroup(
        TestAimToAciConverterBase, base.TestAimDBBase):

    sample_input = [
        aim_service_graph.ServiceRedirectHealthGroup(
            tenant_name='t1', name='h1', display_name='alias'),
        aim_service_graph.ServiceRedirectHealthGroup(
            tenant_name='t1', name='h2')
    ]

    sample_output = [[_aci_obj('vnsRedirectHealthGroup',
                               dn='uni/tn-t1/svcCont/redirectHealthGroup-h1',
                               nameAlias='alias')],
                     [_aci_obj('vnsRedirectHealthGroup',
                               dn='uni/tn-t1/svcCont/redirectHealthGroup-h2',
                               nameAlias='')]]


def get_example_aim_device_cluster_interface_context(**kwargs):
    example = aim_service_graph.DeviceClusterInterfaceContext(
        tenant_name='t1', contract_name='c1',
        service_graph_name='g0', node_name='N0',
        connector_name='cons')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterDeviceClusterInterfaceContext(
        TestAimToAciConverterBase,
        base.TestAimDBBase):
    sample_input = [
        get_example_aim_device_cluster_interface_context(display_name='LIC'),
        get_example_aim_device_cluster_interface_context(
            connector_name='prov',
            bridge_domain_dn='bd',
            service_redirect_policy_dn='srp',
            device_cluster_interface_dn='dci')]

    sample_output = [
        [_aci_obj('vnsLIfCtx',
                  dn='uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/lIfCtx-c-cons',
                  nameAlias='LIC'),
         _aci_obj('vnsRsLIfCtxToSvcRedirectPol',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/lIfCtx-c-cons/'
                      'rsLIfCtxToSvcRedirectPol'),
                  tDn=''),
         _aci_obj('vnsRsLIfCtxToBD',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/lIfCtx-c-cons/'
                      'rsLIfCtxToBD'),
                  tDn=''),
         _aci_obj('vnsRsLIfCtxToLIf',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/lIfCtx-c-cons/'
                      'rsLIfCtxToLIf'),
                  tDn='')],
        [_aci_obj('vnsLIfCtx',
                  dn='uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/lIfCtx-c-prov',
                  nameAlias=''),
         _aci_obj('vnsRsLIfCtxToSvcRedirectPol',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/lIfCtx-c-prov/'
                      'rsLIfCtxToSvcRedirectPol'),
                  tDn='srp'),
         _aci_obj('vnsRsLIfCtxToBD',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/lIfCtx-c-prov/'
                      'rsLIfCtxToBD'),
                  tDn='bd'),
         _aci_obj('vnsRsLIfCtxToLIf',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/lIfCtx-c-prov/'
                      'rsLIfCtxToLIf'),
                  tDn='dci')]
    ]


def get_example_aim_device_cluster_context(**kwargs):
    example = aim_service_graph.DeviceClusterContext(
        tenant_name='t1', contract_name='c1',
        service_graph_name='g0', node_name='N0')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterDeviceClusterContext(TestAimToAciConverterBase,
                                                base.TestAimDBBase):
    sample_input = [
        get_example_aim_device_cluster_context(display_name='LDC'),
        get_example_aim_device_cluster_context(
            service_graph_name='g1', node_name='N1',
            device_cluster_name='ldc1',
            bridge_domain_tenant_name='common',
            bridge_domain_name='bd',
            service_redirect_policy_name='srp')]

    sample_output = [
        [_aci_obj('vnsLDevCtx',
                  dn='uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0',
                  nameAlias='LDC'),
         _aci_obj('vnsRsLDevCtxToLDev',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g0-n-N0/rsLDevCtxToLDev'),
                  tDn='')],
        [_aci_obj('vnsLDevCtx',
                  dn='uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1',
                  nameAlias=''),
         _aci_obj('vnsRsLDevCtxToLDev',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/rsLDevCtxToLDev'),
                  tDn='uni/tn-t1/lDevVip-ldc1'),
         _aci_obj('vnsLIfCtx',
                  dn='uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/lIfCtx-c-consumer',
                  nameAlias=''),
         _aci_obj('vnsRsLIfCtxToSvcRedirectPol',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/lIfCtx-c-consumer/'
                      'rsLIfCtxToSvcRedirectPol'),
                  tDn='uni/tn-t1/svcCont/svcRedirectPol-srp'),
         _aci_obj('vnsRsLIfCtxToBD',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/lIfCtx-c-consumer/'
                      'rsLIfCtxToBD'),
                  tDn='uni/tn-common/BD-bd'),
         _aci_obj('vnsRsLIfCtxToLIf',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/lIfCtx-c-consumer/'
                      'rsLIfCtxToLIf'),
                  tDn='uni/tn-t1/lDevVip-ldc1/lIf-interface'),
         _aci_obj('vnsLIfCtx',
                  dn='uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/lIfCtx-c-provider',
                  nameAlias=''),
         _aci_obj('vnsRsLIfCtxToSvcRedirectPol',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/lIfCtx-c-provider/'
                      'rsLIfCtxToSvcRedirectPol'),
                  tDn='uni/tn-t1/svcCont/svcRedirectPol-srp'),
         _aci_obj('vnsRsLIfCtxToBD',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/lIfCtx-c-provider/'
                      'rsLIfCtxToBD'),
                  tDn='uni/tn-common/BD-bd'),
         _aci_obj('vnsRsLIfCtxToLIf',
                  dn=('uni/tn-t1/ldevCtx-c-c1-g-g1-n-N1/lIfCtx-c-provider/'
                      'rsLIfCtxToLIf'),
                  tDn='uni/tn-t1/lDevVip-ldc1/lIf-interface')]
    ]


def get_example_aim_opflex_device(**kwargs):
    example = aim_infra.OpflexDevice(
        pod_id='1', node_id='301', bridge_interface='eth1/33',
        dev_id='167776320')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterOpflexDevice(TestAimToAciConverterBase,
                                        base.TestAimDBBase):
    sample_input = [
        get_example_aim_opflex_device(),
        get_example_aim_opflex_device(
            node_id='201', bridge_interface='eth1/34', dev_id='167776321',
            host_name='f1-compute-1', ip='10.0.16.64',
            domain_name='k8s', controller_name='cluster1',
            fabric_path_dn=('topology/pod-1/protpaths-201-202/'
                            'pathep-[bundle-201-1-33-and-202-1-33]'))]

    sample_output = [
        [_aci_obj('opflexODev',
                  dn=('topology/pod-1/node-301/sys/br-[eth1/33]/'
                      'odev-167776320'),
                  hostName='', ip='', domName='', ctrlrName='',
                  fabricPathDn='')],
        [_aci_obj('opflexODev',
                  dn=('topology/pod-1/node-201/sys/br-[eth1/34]/'
                      'odev-167776321'),
                  hostName='f1-compute-1',
                  ip='10.0.16.64',
                  domName='k8s',
                  ctrlrName='cluster1',
                  fabricPathDn=('topology/pod-1/protpaths-201-202/'
                                'pathep-[bundle-201-1-33-and-202-1-33]'))]
    ]


def get_example_aim_vmm_domain(**kwargs):
    defs = dict(type='Kubernetes', name='k8s')
    defs.update(kwargs)
    example = resource.VMMDomain(**defs)
    return example


class TestAimToAciConverterVMMDomain(TestAimToAciConverterBase,
                                     base.TestAimDBBase):
    sample_input = [
        get_example_aim_vmm_domain(
            display_name='VMM_DOM', enforcement_pref='sw', mode='k8s',
            mcast_address='0.0.0.0', encap_mode='vxlan',
            pref_encap_mode='vlan', vlan_pool_name='vpool1',
            vlan_pool_type='static'),
        get_example_aim_vmm_domain(
            type='OpenStack', name='ostk', mcast_addr_pool_name='mpool3',
            mcast_address='225.1.2.3', enforcement_pref='hw',
            mode='ovs', encap_mode='vxlan')]

    sample_output = [
        [_aci_obj('vmmDomP',
                  dn='uni/vmmp-Kubernetes/dom-k8s',
                  enfPref='sw',
                  mode='k8s',
                  encapMode='vxlan',
                  prefEncapMode='vlan',
                  mcastAddr='0.0.0.0',
                  nameAlias='VMM_DOM'),
         _aci_obj('infraRsVlanNs',
                  dn='uni/vmmp-Kubernetes/dom-k8s/rsvlanNs',
                  tDn='uni/infra/vlanns-[vpool1]-static')],
        [_aci_obj('vmmDomP',
                  dn='uni/vmmp-OpenStack/dom-ostk',
                  nameAlias='',
                  mcastAddr='225.1.2.3',
                  encapMode='vxlan',
                  enfPref='hw',
                  mode='ovs',
                  prefEncapMode='vxlan'),
         _aci_obj('vmmRsDomMcastAddrNs',
                  dn=('uni/vmmp-OpenStack/dom-ostk/'
                      'rsdomMcastAddrNs'),
                  tDn='uni/infra/maddrns-mpool3')]
    ]


def get_example_aim_vmm_controller(**kwargs):
    defs = dict(domain_type='Kubernetes', domain_name='k8s',
                name='cluster1')
    defs.update(kwargs)
    example = resource.VMMController(**defs)
    return example


class TestAimToAciConverterVMMController(TestAimToAciConverterBase,
                                         base.TestAimDBBase):
    sample_input = [
        get_example_aim_vmm_controller(
            display_name='CLSTR', scope='kubernetes',
            root_cont_name='center1', host_or_ip='my.cluster.host',
            mode='ovs'),
        get_example_aim_vmm_controller(name='cluster2', scope='iaas')]

    sample_output = [
        [_aci_obj('vmmCtrlrP',
                  dn='uni/vmmp-Kubernetes/dom-k8s/ctrlr-cluster1',
                  nameAlias='CLSTR',
                  scope='kubernetes',
                  mode='ovs',
                  rootContName='center1',
                  hostOrIp='my.cluster.host')],
        [_aci_obj('vmmCtrlrP',
                  dn='uni/vmmp-Kubernetes/dom-k8s/ctrlr-cluster2',
                  nameAlias='',
                  scope='iaas',
                  mode='k8s',
                  rootContName='cluster2',
                  hostOrIp='cluster2')]
    ]


def get_example_aim_vmm_inj_namespace(**kwargs):
    example = resource.VmmInjectedNamespace(
        domain_type='Kubernetes', domain_name='k8s',
        controller_name='cluster1', name='ns1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterVmmInjNamespace(TestAimToAciConverterBase,
                                           base.TestAimDBBase):
    sample_input = [
        get_example_aim_vmm_inj_namespace(display_name='NS1'),
        get_example_aim_vmm_inj_namespace(name='ns2')]

    sample_output = [
        [_aci_obj('vmmInjectedNs',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]'),
                  nameAlias='NS1')],
        [_aci_obj('vmmInjectedNs',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns2]'),
                  nameAlias='')]
    ]


def get_example_aim_vmm_inj_deployment(**kwargs):
    example = resource.VmmInjectedDeployment(
        domain_type='Kubernetes', domain_name='k8s',
        controller_name='cluster1', namespace_name='ns1', name='depl1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterVmmInjDeployment(TestAimToAciConverterBase,
                                            base.TestAimDBBase):
    sample_input = [
        get_example_aim_vmm_inj_deployment(display_name='DEP1',
                                           replicas=3, guid='123'),
        get_example_aim_vmm_inj_deployment(name='depl2')]

    sample_output = [
        [_aci_obj('vmmInjectedDepl',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/depl-[depl1]'),
                  replicas='3',
                  guid='123',
                  nameAlias='DEP1')],
        [_aci_obj('vmmInjectedDepl',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/depl-[depl2]'),
                  replicas='0',
                  guid='',
                  nameAlias='')]
    ]


def get_example_aim_vmm_inj_replica_set(**kwargs):
    example = resource.VmmInjectedReplicaSet(
        domain_type='Kubernetes', domain_name='k8s',
        controller_name='cluster1', namespace_name='ns1', name='set1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterVmmInjReplicaSet(TestAimToAciConverterBase,
                                            base.TestAimDBBase):
    sample_input = [
        get_example_aim_vmm_inj_replica_set(display_name='RS1',
                                            deployment_name='depl1',
                                            guid='123'),
        get_example_aim_vmm_inj_replica_set(name='set2')]

    sample_output = [
        [_aci_obj('vmmInjectedReplSet',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/rs-[set1]'),
                  nameAlias='RS1',
                  deploymentName='depl1',
                  guid='123')],
        [_aci_obj('vmmInjectedReplSet',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/rs-[set2]'),
                  nameAlias='',
                  deploymentName='',
                  guid='')]
    ]


def get_example_aim_vmm_inj_service(**kwargs):
    example = resource.VmmInjectedService(
        domain_type='Kubernetes', domain_name='k8s',
        controller_name='cluster1', namespace_name='ns1', name='svc1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterVmmInjService(TestAimToAciConverterBase,
                                         base.TestAimDBBase):
    sample_input = [
        get_example_aim_vmm_inj_service(name='svc2'),
        get_example_aim_vmm_inj_service(
            display_name='SVC1', guid='123', cluster_ip='1.2.3.4',
            service_type='loadBalancer', load_balancer_ip='5.6.7.8',
            service_ports=[{'port': '443',
                            'protocol': 'tcp',
                            'target_port': 'INT_HTTP'},
                           {'port': '56',
                            'protocol': 'udp',
                            'target_port': '2056',
                            'node_port': '80'}],
            endpoints=[{'ip': '1.2.3.4', 'pod_name': 'foo'},
                       {'ip': '1.2.3.5', 'pod_name': 'bar'}]),
    ]

    sample_output = [
        [_aci_obj('vmmInjectedSvc',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/svc-[svc2]'),
                  nameAlias='',
                  type='clusterIp',
                  lbIp='0.0.0.0',
                  clusterIp='0.0.0.0',
                  guid='')],
        [_aci_obj('vmmInjectedSvc',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/svc-[svc1]'),
                  clusterIp='1.2.3.4',
                  type='loadBalancer',
                  lbIp='5.6.7.8',
                  guid='123',
                  nameAlias='SVC1',),
         _aci_obj('vmmInjectedSvcPort',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/svc-[svc1]/'
                      'p-https-prot-tcp-t-INT_HTTP'),
                  port='https',
                  protocol='tcp',
                  targetPort='INT_HTTP',
                  nodePort='unspecified'),
         _aci_obj('vmmInjectedSvcPort',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/svc-[svc1]/'
                      'p-56-prot-udp-t-2056'),
                  port='56',
                  protocol='udp',
                  targetPort='2056',
                  nodePort='http'),
         _aci_obj('vmmInjectedSvcEp',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/svc-[svc1]/ep-foo'),
                  contGrpName='foo'),
         _aci_obj('vmmInjectedSvcEp',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/svc-[svc1]/ep-bar'),
                  contGrpName='bar')]
    ]


def get_example_aim_vmm_inj_host(**kwargs):
    example = resource.VmmInjectedHost(
        domain_type='Kubernetes', domain_name='k8s',
        controller_name='cluster1', name='host1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterVmmInjHost(TestAimToAciConverterBase,
                                      base.TestAimDBBase):
    sample_input = [
        get_example_aim_vmm_inj_host(display_name='HOST1',),
        get_example_aim_vmm_inj_host(name='host2',
                                     os='RHEL', host_name='local.host',
                                     kernel_version='5.9')]

    sample_output = [
        [_aci_obj('vmmInjectedHost',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/host-[host1]'),
                  nameAlias='HOST1',
                  os='',
                  kernelVer='',
                  hostName='')],
        [_aci_obj('vmmInjectedHost',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/host-[host2]'),
                  nameAlias='',
                  os='RHEL',
                  kernelVer='5.9',
                  hostName='local.host')]
    ]


def get_example_aim_vmm_inj_cont_group(**kwargs):
    example = resource.VmmInjectedContGroup(
        domain_type='Kubernetes', domain_name='k8s',
        controller_name='cluster1', namespace_name='ns1', name='pod1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterVmmInjContGroup(TestAimToAciConverterBase,
                                           base.TestAimDBBase):
    sample_input = [
        get_example_aim_vmm_inj_cont_group(display_name='POD1',
                                           host_name='my.local.host',
                                           compute_node_name='host1',
                                           guid='123',
                                           replica_set_name='rs1'),
        get_example_aim_vmm_inj_cont_group(name='pod2')]

    sample_output = [
        [_aci_obj('vmmInjectedContGrp',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/grp-[pod1]'),
                  hostName='my.local.host',
                  computeNodeName='host1',
                  guid='123',
                  nameAlias='POD1',
                  replicaSetName='rs1')],
        [_aci_obj('vmmInjectedContGrp',
                  dn=('comp/prov-Kubernetes/ctrlr-[k8s]-cluster1/'
                      'injcont/ns-[ns1]/grp-[pod2]'),
                  hostName='',
                  computeNodeName='',
                  guid='',
                  nameAlias='',
                  replicaSetName='')]
    ]


def get_example_aci_bgpextp(**kwargs):
    attr = {'name': 'bgp',
            'dn': 'uni/tn-t1/out-inet1/bgpExtP'}
    attr.update(**kwargs)
    return _aci_obj('bgpExtP', **attr)


class TestAciToAimConverterBgpExtP(TestAciToAimConverterBase,
                                   base.TestAimDBBase):
    resource_type = resource.L3Outside
    reverse_map_output = [
        {'resource': 'l3extOut',
         'exceptions': {},
         'skip': ['vrfName', 'l3DomainDn', 'bgpEnable']},
        {'resource': 'l3extRsEctx',
         'exceptions': {'vrf_name': {'other': 'tnFvCtxName'}, },
         'to_resource': converter.default_to_resource_strict},
        {'resource': 'l3extRsL3DomAtt',
         'exceptions': {'l3_domain_dn': {'other': 'tDn'}, },
         'to_resource': converter.default_to_resource_strict},
        {'converter': converter.bgp_extp_converter,
         'exceptions': {},
         'resource': 'bgpExtP'}
    ]
    sample_input = [[get_example_aci_bgpextp(nameAlias='alias'),
                     _aci_obj('l3extOut',
                              dn='uni/tn-t1/out-inet1'),
                     ],
                    get_example_aci_l3outside(dn='uni/tn-t1/out-inet2')]
    sample_output = [
        resource.L3Outside(tenant_name='t1', name='inet1',
                           bgp_enable=True,
                           display_name=''),
        resource.L3Outside(tenant_name='t1', name='inet2', bgp_enable=False)]


class TestAimToAciConverterBgpExtP(TestAimToAciConverterBase,
                                   base.TestAimDBBase):
    resource_type = resource.L3Outside
    reverse_map_output = [
        {'resource': 'l3extOut',
         'exceptions': {},
         'skip': ['vrf_name', 'l3_domain_dn', 'bgpEnable']},
        {'converter': converter.bgp_extp_converter,
         'exceptions': {},
         'resource': 'bgpExtP'}
    ]
    sample_input = [get_example_aim_l3outside(name='inet2', vrf_name='l3p',
                                              l3_domain_dn='uni/foo',
                                              bgp_enable=True),
                    get_example_aim_l3outside(name='inet3', vrf_name='shared',
                                              l3_domain_dn='uni/foo',
                                              bgp_enable=False)]
    sample_output = [[_aci_obj('l3extOut', dn='uni/tn-t1/out-inet2',
                               nameAlias=''),
                      _aci_obj('bgpExtP', dn='uni/tn-t1/out-inet2/bgpExtP'),
                      _aci_obj('l3extRsEctx', dn='uni/tn-t1/out-inet2/rsectx',
                               tnFvCtxName='l3p'),
                      _aci_obj('l3extRsL3DomAtt', dn='uni/tn-t1/out-inet2/'
                                                     'rsl3DomAtt',
                               tDn='uni/foo'),
                      ],
                     [_aci_obj('l3extOut', dn='uni/tn-t1/out-inet2',
                               nameAlias=''),
                      _aci_obj('l3extRsEctx', dn='uni/tn-t1/out-inet2/rsectx',
                               tnFvCtxName='l3p'),
                      _aci_obj('l3extRsL3DomAtt', dn='uni/tn-t1/out-inet2/'
                                                     'rsl3DomAtt',
                               tDn='uni/foo')]]
    missing_ref_input = get_example_aim_l3outside(vrf_name=None,
                                                  l3_domain_dn=None)
    missing_ref_output = [_aci_obj('l3extOut', dn='uni/tn-t1/out-inet1',
                                   nameAlias='')]


def get_example_aci_bgpaspeerp(**kwargs):
    attr = {
        'asn': '65000',
        'dn': 'uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/rspathL3OutAtt-'
              '[topology/pod-1/paths-101/pathep-[eth1/1]]/peerP-'
              '[1.1.1.0/24]/as'}
    attr.update(**kwargs)
    return _aci_obj('bgpAsP', **attr)


def get_example_aci_bgppeerp(**kwargs):
    attr = {
        'addr': '1.1.1.0/24',
        'dn': 'uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/rspathL3OutAtt-'
              '[topology/pod-1/paths-101/pathep-[eth1/1]]/peerP-'
              '[1.1.1.0/24]'}
    attr.update(**kwargs)
    return _aci_obj('bgpPeerP', **attr)


class TestAciToAimConverterBgpAsPPeer(TestAciToAimConverterBase,
                                      base.TestAimDBBase):
    resource_type = resource.L3OutInterfaceBgpPeerP
    reverse_map_output = [
        {'exceptions': {},
         'resource': 'bgpPeerP',
         'skip': ['asn']},
        {'exceptions': {},
         'identity_converter': converter.bgp_as_id_converter,
         'resource': 'bgpAsP__Peer'}
    ]
    sample_input = [[
        {'bgpPeerP': {
         'attributes': {'rn': 'peerP-[1.1.1.0/24]',
                        'dn': 'uni/tn-test_gbp/'
                              'out-testOut1/lnodep-testNP1/lifp-testLifP1/'
                              'rspathL3OutAtt-[topology/pod-1/paths-101/'
                              'pathep-[eth1/1]]/peerP-[1.1.1.0/24]',
                        'status': 'created'}, 'children': []}},
        {'bgpAsP__Peer': {
            'attributes': {'rn': 'as',
                           'dn': 'uni/tn-test_gbp/out-testOut1/'
                                 'lnodep-testNP1/lifp-testLifP1/'
                                 'rspathL3OutAtt-[topology/pod-1/'
                                 'paths-101/pathep-[eth1/1]]/'
                                 'peerP-[1.1.1.0/24]/as',
                                 'status': 'created', 'asn': "65000"},
            'children': []}}],
        [get_example_aci_bgppeerp(),
         _aci_obj('bgpAsP',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/peerP-[1.1.1.0/24]/as',
                  asn="0")]]
    sample_output = [
        resource.L3OutInterfaceBgpPeerP(
            tenant_name='test_gbp', l3out_name='testOut1',
            node_profile_name='testNP1', interface_profile_name='testLifP1',
            interface_path='topology/pod-1/paths-101/pathep-[eth1/1]',
            addr='1.1.1.0/24',
            asn="65000"),
        resource.L3OutInterfaceBgpPeerP(
            tenant_name='t1', l3out_name='l1',
            node_profile_name='np1', interface_profile_name='ip1',
            interface_path='topology/pod-1/paths-101/pathep-[eth1/1]',
            addr='1.1.1.0/24',
            asn="0")]


def get_example_aim_bgppeerp(**kwargs):
    example = resource.L3OutInterfaceBgpPeerP(
        tenant_name='t1', l3out_name='l1',
        node_profile_name='np1', interface_profile_name='ip1',
        interface_path='topology/pod-1/paths-101/pathep-[eth1/1]',
        addr='1.1.1.0/24',
        asn="65000")
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterBgpAsPPeer(TestAimToAciConverterBase,
                                      base.TestAimDBBase):
    sample_input = [
        get_example_aim_bgppeerp(),
        get_example_aim_bgppeerp(tenant_name='t2',
                                 asn="65001"),
    ]
    sample_output = [
        [_aci_obj('bgpPeerP',
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/peerP-[1.1.1.0/24]'),
         _aci_obj('bgpAsP__Peer',
                  asn="65000",
                  dn='uni/tn-t1/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/peerP-[1.1.1.0/24]/as')],
        [_aci_obj('bgpPeerP',
                  dn='uni/tn-t2/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/peerP-[1.1.1.0/24]'),
         _aci_obj('bgpAsP__Peer',
                  asn="65001",
                  dn='uni/tn-t2/out-l1/lnodep-np1/lifp-ip1/'
                     'rspathL3OutAtt-[topology/pod-1/paths-101/'
                     'pathep-[eth1/1]]/peerP-[1.1.1.0/24]/as')]]
