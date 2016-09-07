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
from aim.api import status as aim_status
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
            self.assertTrue(item in result)
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
            item.values()[0]['status'] = 'deleted'
        for item in expected:
            item._status = 'deleted'
        result = self.converter.convert(example)
        self.assertEqual(len(expected), len(result))
        for item in expected:
            self.assertTrue(
                item in result,
                'Expected\n%s\nnot in\n%s' % (self._dump(item),
                                              self._dump(result)))

    def _test_reverse_map(self, resource_type, expected):
        reverse = converter.reverse_resource_map[resource_type]
        self.assertEqual(len(expected), len(reverse))
        for idx in xrange(len(expected)):
            self.assertTrue(expected[idx] in reverse,
                            'Expected %s not in %s' % (expected[idx], reverse))

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
                        'other': 'unkMacUcastAct', }},
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
                        dn='uni/tn-test-tenant/BD-test-1'),
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
                              l2_unknown_unicast_mode='proxy',
                              ep_move_detect_mode=''),
        resource.BridgeDomain(tenant_name='test-tenant',
                              name='test-1',
                              enable_arp_flood=False,
                              enable_routing=True,
                              limit_ip_learn_to_subnets=False,
                              l2_unknown_unicast_mode='proxy',
                              ep_move_detect_mode='',
                              vrf_name='shared',
                              l3out_names=['o1'])]
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
    reverse_map_output = [
        {'resource': 'fvAEPg',
         'exceptions': {},
         'skip': ['bdName', 'providedContractNames',
                  'consumedContractNames',
                  'openstackVmmDomainNames',
                  'physicalDomainNames']},
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
         'converter': converter.fv_rs_dom_att_converter, }
    ]
    sample_input = [[base.TestAimDBBase._get_example_aci_epg(),
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
                     ],
                    base.TestAimDBBase._get_example_aci_epg(
                        dn='uni/tn-t1/ap-a1/epg-test-1')]
    sample_output = [
        resource.EndpointGroup(tenant_name='t1',
                               app_profile_name='a1',
                               name='test', bd_name='bd1',
                               provided_contract_names=['p1', 'k'],
                               consumed_contract_names=['c1', 'k'],
                               openstack_vmm_domain_names=['op', 'op2'],
                               physical_domain_names=['phys']),
        resource.EndpointGroup(tenant_name='t1',
                               app_profile_name='a1',
                               name='test-1')]


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
                    get_example_aci_filter(dn='uni/tn-test-tenant/flt-f2')]
    sample_output = [
        resource.Filter(tenant_name='test-tenant', name='f1'),
        resource.Filter(tenant_name='test-tenant', name='f2')]


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
            'arp_opcode': {'other': 'arpOpc'},
            'ether_type': {'other': 'etherT'},
            'ip_protocol': {'other': 'prot'},
            'icmpv4_type': {'other': 'icmpv4T'},
            'icmpv6_type': {'other': 'icmpv6T'},
            'source_from_port': {'other': 'sFromPort'},
            'source_to_port': {'other': 'sToPort'},
            'dest_from_port': {'other': 'dFromPort'},
            'dest_to_port': {'other': 'dToPort'},
            'tcp_flags': {'other': 'tcpRules'},
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
                        applyToFrag='yes')]
    sample_output = [
        resource.FilterEntry(tenant_name='test-tenant', filter_name='f1',
                             name='e1', arp_opcode='req', ether_type='arp',
                             source_from_port='200', source_to_port='https',
                             dest_from_port='2000', dest_to_port='4000',
                             tcp_flags='est', stateful=True),
        resource.FilterEntry(tenant_name='test-tenant', filter_name='f1',
                             name='e2', arp_opcode='req',
                             source_from_port='200', source_to_port='https',
                             tcp_flags='est', fragment_only=True)]
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
                                             scope='tenant')]
    sample_output = [
        resource.Contract(tenant_name='test-tenant', name='c1'),
        resource.Contract(tenant_name='test-tenant', name='c2',
                          scope='tenant')]


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
         'skip': ['inFilters', 'outFilters', 'biFilters']},
        {'resource': 'vzRsSubjFiltAtt',
         'exceptions': {},
         'converter': converter.vzRsSubjFiltAtt_converter},
        {'resource': 'vzRsFiltAtt',
         'exceptions': {},
         'converter': converter.vzInTerm_vzRsFiltAtt_converter},
        {'resource': 'vzRsFiltAtt',
         'exceptions': {},
         'converter': converter.vzOutTerm_vzRsFiltAtt_converter}]
    sample_input = [[get_example_aci_subject(),
                     _aci_obj('vzRsSubjFiltAtt',
                              dn='uni/tn-t1/brc-c/subj-s/rssubjFiltAtt-f1',
                              tnVzFilterName='f1'),
                     _aci_obj('vzRsSubjFiltAtt',
                              dn='uni/tn-t1/brc-c/subj-s/rssubjFiltAtt-f2',
                              tnVzFilterName='f2'),
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
                              tnVzFilterName='o2')],
                    [get_example_aci_subject(dn='uni/tn-t1/brc-c/subj-s2'),
                     _aci_obj('vzRsFiltAtt',
                              dn='uni/tn-t1/brc-c/subj-s2/intmnl/rsfiltAtt-i1',
                              tnVzFilterName='i1')]]
    sample_output = [
        resource.ContractSubject(tenant_name='t1', contract_name='c', name='s',
                                 in_filters=['i1', 'i2'],
                                 out_filters=['o1', 'o2'],
                                 bi_filters=['f1', 'f2']),
        resource.ContractSubject(tenant_name='t1', contract_name='c',
                                 name='s2', in_filters=['i1'])]


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
                        code='500')]
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
            cause='resolution-failed')]


def get_example_aci_l3outside(**kwargs):
    attr = {'name': 'inet1',
            'dn': 'uni/tn-t1/out-inet1'}
    attr.update(**kwargs)
    return _aci_obj('l3extOut', **attr)


class TestAciToAimConverterL3Outside(TestAciToAimConverterBase,
                                     base.TestAimDBBase):
    resource_type = resource.L3Outside
    reverse_map_output = [
        {'exceptions': {},
         'resource': 'l3extOut',
         'skip': ['vrfName', 'l3DomainDn']},
        {'resource': 'l3extRsEctx',
         'exceptions': {'vrf_name': {'other': 'tnFvCtxName'}, },
         'to_resource': converter.default_to_resource_strict,
         'convert_pre_existing': True},
        {'resource': 'l3extRsL3DomAtt',
         'exceptions': {'l3_domain_dn': {'other': 'tDn'}, },
         'to_resource': converter.default_to_resource_strict}
    ]
    sample_input = [[get_example_aci_l3outside(),
                     _aci_obj('l3extRsEctx',
                              dn='uni/tn-t1/out-inet1/rsectx',
                              tnFvCtxName='shared'),
                     _aci_obj('l3extRsL3DomAtt',
                              dn='uni/tn-t1/out-inet1/rsL3DomAtt',
                              tDn='uni/l3dom-l3ext')],
                    get_example_aci_l3outside(dn='uni/tn-t1/out-inet2')]
    sample_output = [
        resource.L3Outside(tenant_name='t1', name='inet1',
                           vrf_name='shared', l3_domain_dn='uni/l3dom-l3ext'),
        resource.L3Outside(tenant_name='t1', name='inet2')]


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
         'to_resource': converter.default_to_resource_strict,
         'convert_pre_existing': True},
        {'resource': 'fvRsProv',
         'exceptions': {},
         'converter': converter.fvRsProv_Ext_converter,
         'convert_pre_existing': True},
        {'resource': 'fvRsCons',
         'exceptions': {},
         'converter': converter.fvRsCons_Ext_converter,
         'convert_pre_existing': True}
    ]
    sample_input = [[get_example_aci_external_network(),
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
                                 consumed_contract_names=['c1', 'k']),
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
                            'extsubnet-[30.0.0.0/16]'))]
    sample_output = [
        resource.ExternalSubnet(tenant_name='t1', l3out_name='o1',
                                external_network_name='inet1',
                                cidr='20.0.0.0/8'),
        resource.ExternalSubnet(tenant_name='t1', l3out_name='o2',
                                external_network_name='inet2',
                                cidr='30.0.0.0/16')]


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
        self._test_convert(self.sample_input[0], self.sample_output[0],
                           self.sample_input[1], self.sample_output[1])


class TestAimToAciConverterBD(TestAimToAciConverterBase, base.TestAimDBBase):
    sample_input = [base.TestAimDBBase._get_example_aim_bd(l3out_names=[
                                                           'l1', 'l2']),
                    base.TestAimDBBase._get_example_aim_bd(name='test-1',
                                                           vrf_name='common')]
    sample_output = [
        [_aci_obj('fvBD', dn="uni/tn-test-tenant/BD-test",
                  arpFlood='no', epMoveDetectMode="",
                  limitIpLearnToSubnets="no", unicastRoute="yes",
                  unkMacUcastAct="proxy"),
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
                        name='test-1', bd_name='net2',
                        provided_contract_names=['k', 'p1'],
                        consumed_contract_names=['c1', 'k'],
                        openstack_vmm_domain_names=['op', 'op2'],
                        physical_domain_names=['phys'])]
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
                    'tDn': 'uni/vmmp-OpenStack/dom-op'}}}, {
            'fvRsDomAtt': {
                'attributes': {
                    'dn': 'uni/tn-t1/ap-a1/epg-test-1/'
                          'rsdomAtt-[uni/vmmp-OpenStack/dom-op2]',
                    'tDn': 'uni/vmmp-OpenStack/dom-op2'}}}]]
    missing_ref_input = base.TestAimDBBase._get_example_aim_epg(bd_name=None)
    missing_ref_output = [{
        "fvAEPg": {"attributes": {"dn": "uni/tn-t1/ap-a1/epg-test", }}}]


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
                    get_example_aim_filter(name='f2')]
    sample_output = [
        [_aci_obj('vzFilter', dn='uni/tn-test-tenant/flt-f1')],
        [_aci_obj('vzFilter', dn='uni/tn-test-tenant/flt-f2')]
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
    sample_input = [get_example_aim_filter_entry(),
                    get_example_aim_filter_entry(
                        name='e2', tcp_flags='ack', fragment_only=True)]
    sample_output = [
        [_aci_obj('vzEntry', dn='uni/tn-test-tenant/flt-f1/e-e1',
                  arpOpc='req', etherT='arp', prot='unspecified',
                  icmpv4T='unspecified', icmpv6T='unspecified',
                  sFromPort='200', sToPort='https',
                  dFromPort='2000', dToPort='4000',
                  tcpRules='est', stateful='yes', applyToFrag='no')],
        [_aci_obj('vzEntry', dn='uni/tn-test-tenant/flt-f1/e-e2',
                  arpOpc='req', etherT='arp', prot='unspecified',
                  icmpv4T='unspecified', icmpv6T='unspecified',
                  sFromPort='200', sToPort='https',
                  dFromPort='2000', dToPort='4000',
                  tcpRules='ack', stateful='yes', applyToFrag='yes')]
    ]


def get_example_aim_contract(**kwargs):
    example = resource.Contract(tenant_name='test-tenant', name='c1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterContract(TestAimToAciConverterBase,
                                    base.TestAimDBBase):
    sample_input = [get_example_aim_contract(),
                    get_example_aim_contract(
                        name='c2', scope=resource.Contract.SCOPE_TENANT)]
    sample_output = [
        [_aci_obj('vzBrCP', dn='uni/tn-test-tenant/brc-c1', scope='context')],
        [_aci_obj('vzBrCP', dn='uni/tn-test-tenant/brc-c2', scope='tenant')]
    ]


def get_example_aim_contract_subject(**kwargs):
    example = resource.ContractSubject(tenant_name='test-tenant',
                                       contract_name='c1', name='s1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterContractSubject(TestAimToAciConverterBase,
                                           base.TestAimDBBase):
    sample_input = [get_example_aim_contract_subject(in_filters=['i1', 'i2'],
                                                     out_filters=['o1', 'o2'],
                                                     bi_filters=['f1', 'f2']),
                    get_example_aim_contract_subject(name='s2')]
    sample_output = [
        [_aci_obj('vzSubj', dn='uni/tn-test-tenant/brc-c1/subj-s1'),
         _aci_obj('vzRsSubjFiltAtt',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/rssubjFiltAtt-f1',
                  tnVzFilterName='f1'),
         _aci_obj('vzRsSubjFiltAtt',
                  dn='uni/tn-test-tenant/brc-c1/subj-s1/rssubjFiltAtt-f2',
                  tnVzFilterName='f2'),
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
                  tnVzFilterName='o2')],
        [_aci_obj('vzSubj', dn='uni/tn-test-tenant/brc-c1/subj-s2')]]


def get_example_aim_l3outside(**kwargs):
    example = resource.L3Outside(tenant_name='t1',
                                 name='inet1')
    example.__dict__.update(kwargs)
    return example


class TestAimToAciConverterL3Outside(TestAimToAciConverterBase,
                                     base.TestAimDBBase):
    sample_input = [get_example_aim_l3outside(name='inet2', vrf_name='l3p',
                                              l3_domain_dn='uni/foo'),
                    get_example_aim_l3outside(vrf_name='shared',
                                              l3_domain_dn='uni/foo',
                                              pre_existing=True)]
    sample_output = [
        [_aci_obj('l3extOut', dn='uni/tn-t1/out-inet2'),
         _aci_obj('l3extRsEctx', dn='uni/tn-t1/out-inet2/rsectx',
                  tnFvCtxName='l3p'),
         _aci_obj('l3extRsL3DomAtt',
                  dn='uni/tn-t1/out-inet2/rsL3DomAtt',
                  tDn='uni/foo')],
        [_aci_obj('l3extRsEctx', dn='uni/tn-t1/out-inet1/rsectx',
                  tnFvCtxName='shared')]]
    missing_ref_input = get_example_aim_l3outside(vrf_name=None,
                                                  l3_domain_dn=None)
    missing_ref_output = [_aci_obj('l3extOut', dn='uni/tn-t1/out-inet1')]


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
            consumed_contract_names=['c1', 'k']),
        get_example_aim_external_network(
            nat_epg_dn='uni/foo',
            provided_contract_names=['k', 'p1'],
            consumed_contract_names=['c1', 'k'],
            pre_existing=True)]
    sample_output = [
        [_aci_obj('l3extInstP', dn='uni/tn-t1/out-l1/instP-inet2'),
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
        [_aci_obj('l3extRsInstPToNatMappingEPg',
                  dn=('uni/tn-t1/out-l1/instP-inet1/'
                      'rsInstPToNatMappingEPg'),
                  tDn='uni/foo'),
         _aci_obj('fvRsProv__Ext',
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
                  tnVzBrCPName='c1')]]
    missing_ref_input = get_example_aim_external_network(nat_epg_dn=None)
    missing_ref_output = [_aci_obj('l3extInstP',
                                   dn='uni/tn-t1/out-l1/instP-inet1')]


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
                        cidr='2.11.0.0/16')]
    sample_output = [
        [_aci_obj('l3extSubnet',
                  dn='uni/tn-t1/out-l1/instP-inet1/extsubnet-[4.20.0.0/16]')],
        [_aci_obj('l3extSubnet',
                  dn='uni/tn-t1/out-l1/instP-inet2/extsubnet-[2.11.0.0/16]')]]
