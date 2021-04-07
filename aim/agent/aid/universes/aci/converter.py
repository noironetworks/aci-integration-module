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

import collections
import copy
import traceback

from apicapi import apic_client
from oslo_log import log as logging

from aim.agent.aid.universes.aci.converters import service_graph
from aim.agent.aid.universes.aci.converters import utils
from aim.api import infra as aim_infra
from aim.api import resource
from aim.api import status as aim_status
from aim.api import types as t
from aim.common import utils as aim_utils
from aim import config as aim_cfg

LOG = logging.getLogger(__name__)
DELETED_STATUS = "deleted"
CLEARED_SEVERITY = "cleared"
MODIFIED_STATUS = "modified"
CREATED_STATUS = "created"

# TODO(amitbose) Instead of aliasing, replace local references with the
# ones from utils
default_identity_converter = utils.default_identity_converter
default_attribute_converter = utils.default_attribute_converter
convert_attribute = utils.convert_attribute
default_to_resource = utils.default_to_resource
default_to_resource_strict = utils.default_to_resource_strict
boolean = utils.boolean
mapped_attribute = utils.mapped_attribute
child_list = utils.child_list


def fault_identity_converter(object_dict, otype, helper,
                             to_aim=True):
    if to_aim:
        return object_dict['code'], object_dict['dn']
    else:
        return [object_dict['external_identifier']]


def to_resource_filter_container(converted, helper, to_aim=True):
    if to_aim:
        return default_to_resource(converted, helper, to_aim=to_aim)
    else:
        in_ = (helper['resource'] is 'vzInTerm' and
               (converted.get('inFilters') or
                converted.get('inServiceGraphName')))
        out = (helper['resource'] is 'vzOutTerm' and
               (converted.get('outFilters') or
                converted.get('outServiceGraphName')))
        if in_ or out:
            return {
                helper['resource']: {'attributes': {'dn': converted['dn']}}}


tcp_flags = mapped_attribute(t.tcp_flags)
port = mapped_attribute(t.ports)
arp_opcode = mapped_attribute(t.arp_opcode)
ether_type = mapped_attribute(t.ether_type)
icmpv4_type = mapped_attribute(t.icmpv4_type)
icmpv4_code = mapped_attribute(t.icmpv4_code)
icmpv6_type = mapped_attribute(t.icmpv6_type)
icmpv6_code = mapped_attribute(t.icmpv6_code)
ip_protocol = mapped_attribute(t.ip_protocol)
ethertype = mapped_attribute(t.ethertype)


def fault_inst_to_resource(converted, helper, to_aim=True):
    fault_prefix = 'fault-'
    if to_aim:
        # Nothing fancy to do
        return default_to_resource(converted, helper, to_aim=to_aim)
    else:
        # Exclude status_id, last_update_timestamp
        result = default_to_resource(converted, helper, to_aim=to_aim)
        attr = result[helper['resource']]['attributes']
        attr.pop('statusId', None)
        attr.pop('lastUpdateTimestamp', None)
        attr.pop('lifecycleStatus', None)
        attr['code'] = attr['dn'].split('/')[-1][len(fault_prefix):]
        return result


def fv_rs_dom_att_converter(object_dict, otype, helper,
                            source_identity_attributes,
                            destination_identity_attributes, to_aim=True):
    result = []
    if to_aim:
        # Converting a fvRsDomAtt into an EPG
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, 'fvRsDomAtt', helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        # fvRsDomAtt can be either referring to a physDomP or a vmmDomP type
        try:
            dom_id = default_identity_converter(
                {'dn': id[-1]}, 'vmmDomP', helper, to_aim=True)
            if dom_id[0] == aim_utils.OPENSTACK_VMM_TYPE:
                res_dict['openstack_vmm_domain_names'] = [dom_id[-1]]
            res_dict['vmm_domains'] = [{'type': dom_id[0], 'name': dom_id[1]}]
        except apic_client.DNManager.InvalidNameFormat:
            dom_id = default_identity_converter(
                {'dn': id[-1]}, 'physDomP', helper, to_aim=True)
            res_dict['physical_domain_names'] = [dom_id[0]]
            res_dict['physical_domains'] = [{'name': dom_id[0]}]
        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        # Converting an EndpointGroup into fvRsDomAtt objects
        for phys in set(object_dict['physical_domain_names'] + [
                x['name'] for x in object_dict['physical_domains']]):
            # Get Physdom DN
            phys_dn = default_identity_converter(
                resource.PhysicalDomain(name=phys).__dict__,
                resource.PhysicalDomain, helper, aci_mo_type='physDomP',
                to_aim=False)[0]
            dn = default_identity_converter(
                object_dict, otype, helper, extra_attributes=[phys_dn],
                aci_mo_type='fvRsDomAtt', to_aim=False)[0]
            result.append({'fvRsDomAtt': {'attributes':
                                          {'dn': dn,
                                           'tDn': phys_dn}}})
        # Convert OpenStack VMMs
        vmms_by_name = [(aim_utils.OPENSTACK_VMM_TYPE, x) for x in
                        object_dict['openstack_vmm_domain_names']]
        for vmm in set([(x['type'], x['name']) for x in
                        object_dict['vmm_domains']] + vmms_by_name):
            # Get VMM DN
            vmm_dn = default_identity_converter(
                resource.VMMDomain(type=vmm[0], name=vmm[1]).__dict__,
                resource.VMMDomain, helper, aci_mo_type='vmmDomP',
                to_aim=False)[0]
            dn = default_identity_converter(
                object_dict, otype, helper, extra_attributes=[vmm_dn],
                aci_mo_type='fvRsDomAtt', to_aim=False)[0]
            dom_ref = {'fvRsDomAtt': {'attributes': {'dn': dn,
                                                     'tDn': vmm_dn,
                                                     'instrImedcy': 'lazy'}}}
            if not aim_cfg.CONF.aim.disable_micro_segmentation:
                dom_ref['fvRsDomAtt']['attributes'].update({'classPref':
                                                            'useg'})
            if vmm[0].lower() == aim_utils.VMWARE_VMM_TYPE.lower():
                dom_ref['fvRsDomAtt']['attributes'][
                    'instrImedcy'] = 'immediate'
            result.append(dom_ref)
    return result


def fv_rs_path_att_converter(object_dict, otype, helper,
                             source_identity_attributes,
                             destination_identity_attributes, to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        if object_dict.get('tDn') and object_dict.get('encap'):
            res_dict['static_paths'] = [{'path': object_dict['tDn'],
                                         'mode': object_dict.get('mode',
                                                                 'regular'),
                                         'encap': object_dict['encap']}]
        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        for p in object_dict['static_paths']:
            if p.get('path') and p.get('encap'):
                dn = default_identity_converter(
                    object_dict, otype, helper, extra_attributes=[p['path']],
                    aci_mo_type=helper['resource'], to_aim=False)[0]
                result.append({helper['resource']: {'attributes':
                                                    {'dn': dn,
                                                     'tDn': p['path'],
                                                     'mode':
                                                         p.get('mode',
                                                               'regular'),
                                                     'encap': p['encap']}}})
    return result


def qos_rs_ingress_dpp_pol(object_dict, otype, helper,
                           source_identity_attributes,
                           destination_identity_attributes, to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        if 'tnQosDppPolName' in object_dict:
            res_dict['ingress_dpp_pol'] = object_dict.get('tnQosDppPolName')

        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        if object_dict.get('tenant_name') and object_dict.get('name') \
           and object_dict.get('ingress_dpp_pol'):
            attrs = [object_dict.get('tenant_name'),
                     object_dict.get('name')]
            try:
                dn = apic_client.ManagedObjectClass(
                    'qosRsIngressDppPol').dn(*attrs)
            except Exception as e:
                LOG.error('Failed to make DN for %s with %s: %s',
                          helper['resource'], attrs, e)
                raise
            result.append(
                {helper['resource']:
                 {'attributes':
                  {'dn': dn,
                   'tnQosDppPolName': object_dict.get('ingress_dpp_pol')}}})
    return result


def qos_rs_egress_dpp_pol(object_dict, otype, helper,
                          source_identity_attributes,
                          destination_identity_attributes, to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        if 'tnQosDppPolName' in object_dict:
            res_dict['egress_dpp_pol'] = object_dict.get('tnQosDppPolName')

        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        if object_dict.get('tenant_name') and object_dict.get('name') \
           and object_dict.get('egress_dpp_pol'):
            attrs = [object_dict.get('tenant_name'),
                     object_dict.get('name')]
            try:
                dn = apic_client.ManagedObjectClass(
                    'qosRsEgressDppPol').dn(*attrs)
            except Exception as e:
                LOG.error('Failed to make DN for %s with %s: %s',
                          helper['resource'], attrs, e)
                raise
            result.append(
                {helper['resource']:
                 {'attributes':
                  {'dn': dn,
                   'tnQosDppPolName': object_dict.get('egress_dpp_pol')}}})
    return result


def qos_ep_dscp_marking(object_dict, otype, helper,
                        source_identity_attributes,
                        destination_identity_attributes, to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        res_dict['dscp'] = object_dict.get('mark', None)
        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        if object_dict.get('tenant_name') and object_dict.get('name') and \
           object_dict.get('dscp'):
            attrs = [object_dict.get('tenant_name'),
                     object_dict.get('name')]
            try:
                dn = apic_client.ManagedObjectClass(
                    'qosEpDscpMarking').dn(*attrs)
            except Exception as e:
                LOG.error('Failed to make DN for %s with %s: %s',
                          helper['resource'], attrs, e)
                raise
            result.append({
                helper['resource']:
                    {'attributes': {'dn': dn, 'mark': object_dict['dscp']}}})
    return result


def qos_rs_req(object_dict, otype, helper,
               source_identity_attributes,
               destination_identity_attributes, to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        if object_dict.get('tnQosRequirementName'):
            res_dict['qos_name'] = object_dict['tnQosRequirementName']

        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        qos_name = object_dict.get('qos_name', '')
        if object_dict.get('tenant_name') and object_dict.get('name') and \
           object_dict.get('app_profile_name') and \
           qos_name and qos_name != '':
            attrs = [object_dict.get('tenant_name'),
                     object_dict.get('app_profile_name'),
                     object_dict.get('name')]
            try:
                dn = apic_client.ManagedObjectClass(
                    'fvRsQosRequirement').dn(*attrs)
            except Exception as e:
                LOG.error('Failed to make DN for %s with %s: %s',
                          helper['resource'], attrs, e)
                raise
            result.append({helper['resource']:
                           {'attributes':
                            {'dn': dn,
                             'tnQosRequirementName': qos_name}}})
    return result


def fv_rs_master_epg_converter(object_dict, otype, helper,
                               source_identity_attributes,
                               destination_identity_attributes, to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        if object_dict.get('tDn'):
            master_id = apic_client.DNManager().aci_decompose_with_type(
                object_dict['tDn'], 'fvAEPg')
            res_dict['epg_contract_masters'] = [
                {'app_profile_name': master_id[1][1], 'name': master_id[2][1]}]
        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        for p in object_dict['epg_contract_masters']:
            if p.get('app_profile_name') and p.get('name'):
                try:
                    attr = [object_dict.get('tenant_name'),
                            p.get('app_profile_name'), p.get('name')]
                    path = apic_client.ManagedObjectClass('fvAEPg').dn(*attr)
                except Exception as e:
                    LOG.error('Failed to make DN for %s with %s: %s',
                              helper['resource'], attr, e)
                    raise
                dn = default_identity_converter(
                    object_dict, otype, helper, extra_attributes=[path],
                    aci_mo_type=helper['resource'], to_aim=False)[0]
                result.append({helper['resource']: {'attributes':
                                                    {'dn': dn, 'tDn': path}}})
    return result


def l3ext_next_hop_converter(object_dict, otype, helper,
                             source_identity_attributes,
                             destination_identity_attributes,
                             to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        if (object_dict.get('type') == 'prefix' and object_dict.get('nhAddr')
                and object_dict.get('pref')):
            res_dict['next_hop_list'] = [{'addr': object_dict['nhAddr'],
                                          'preference': object_dict['pref']}]
        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        for p in object_dict.get('next_hop_list'):
            if p.get('addr') and p.get('preference'):
                dn = default_identity_converter(
                    object_dict, otype, helper, extra_attributes=[p['addr']],
                    aci_mo_type=helper['resource'], to_aim=False)[0]
                result.append({helper['resource']: {
                    'attributes': {'dn': dn,
                                   'nhAddr': p['addr'],
                                   'pref': p['preference'],
                                   'type': 'prefix'}}})
    return result


def l3ext_ip_converter(object_dict, otype, helper,
                       source_identity_attributes,
                       destination_identity_attributes,
                       to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        is_vpc = False
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            id = default_identity_converter(object_dict, otype, helper,
                                            aci_mo_type='l3extIp__Member',
                                            to_aim=True)
            is_vpc = True
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        if object_dict.get('addr'):
            if is_vpc or otype == 'l3extIp__Member':
                if id[5] == 'A':
                    res_dict['secondary_addr_a_list'] = [{'addr':
                                                         object_dict['addr']}]
                elif id[5] == 'B':
                    res_dict['secondary_addr_b_list'] = [{'addr':
                                                         object_dict['addr']}]
            else:
                res_dict['secondary_addr_a_list'] = [{'addr':
                                                     object_dict['addr']}]
        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        # always need the primary_addr_a
        if not object_dict.get('primary_addr_a'):
            return result
        # vpc case
        if object_dict.get('primary_addr_b'):
            for p in object_dict.get('secondary_addr_a_list'):
                if p.get('addr'):
                    dn = default_identity_converter(
                        object_dict, otype, helper,
                        extra_attributes=['A', p['addr']],
                        aci_mo_type='l3extIp__Member', to_aim=False)[0]
                    result.append({'l3extIp__Member': {
                        'attributes': {'dn': dn,
                                       'addr': p['addr']}}})
            for p in object_dict.get('secondary_addr_b_list'):
                if p.get('addr'):
                    dn = default_identity_converter(
                        object_dict, otype, helper,
                        extra_attributes=['B', p['addr']],
                        aci_mo_type='l3extIp__Member', to_aim=False)[0]
                    result.append({'l3extIp__Member': {
                        'attributes': {'dn': dn,
                                       'addr': p['addr']}}})
        else:
            for p in object_dict.get('secondary_addr_a_list'):
                if p.get('addr'):
                    dn = default_identity_converter(
                        object_dict, otype, helper,
                        extra_attributes=[p['addr']],
                        aci_mo_type='l3extIp', to_aim=False)[0]
                    result.append({'l3extIp': {
                        'attributes': {'dn': dn,
                                       'addr': p['addr']}}})
    return result


def l3ext_member_converter(object_dict, otype, helper,
                           source_identity_attributes,
                           destination_identity_attributes,
                           to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        if object_dict.get('side') and object_dict.get('addr'):
            if object_dict['side'] == 'A':
                res_dict['primary_addr_a'] = object_dict['addr']
            elif object_dict['side'] == 'B':
                res_dict['primary_addr_b'] = object_dict['addr']
        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        if (object_dict.get('primary_addr_a') and
                object_dict.get('primary_addr_b')):
            dn_a = default_identity_converter(
                object_dict, otype, helper, extra_attributes=['A'],
                aci_mo_type=helper['resource'], to_aim=False)[0]
            result.append({helper['resource']: {
                'attributes': {'dn': dn_a,
                               'side': 'A',
                               'addr': object_dict['primary_addr_a']}}})
            dn_b = default_identity_converter(
                object_dict, otype, helper, extra_attributes=['B'],
                aci_mo_type=helper['resource'], to_aim=False)[0]
            result.append({helper['resource']: {
                'attributes': {'dn': dn_b,
                               'side': 'B',
                               'addr': object_dict['primary_addr_b']}}})
    return result


def bgp_extp_converter(object_dict, otype, helper,
                       source_identity_attributes,
                       destination_identity_attributes,
                       to_aim=True):
    result = []
    if to_aim:
        res_dict = {}
        try:
            id = default_identity_converter(object_dict, otype, helper,
                                            to_aim=True)
        except apic_client.DNManager.InvalidNameFormat:
            return []
        for index, attr in enumerate(destination_identity_attributes):
            res_dict[attr] = id[index]
        res_dict['bgp_enable'] = True
        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        if object_dict.get('bgp_enable'):
            dn = default_identity_converter(object_dict, otype, helper,
                                            aci_mo_type=helper['resource'],
                                            to_aim=False)[0]
            result.append({helper['resource']: {
                'attributes': {'dn': dn}
            }})
    return result


def rsFilt_converter(aci_mo=None):
    def func(object_dict, otype, helper, source_identity_attributes,
             destination_identity_attributes, to_aim=True):
        result = []
        id_conv = (helper.get('identity_converter') or
                   default_identity_converter)
        if to_aim:
            res_dict = {}
            aci_type = aci_mo or otype
            try:
                id = id_conv(object_dict, aci_type, helper, to_aim=True)
            except apic_client.DNManager.InvalidNameFormat:
                return []
            for index, attr in enumerate(destination_identity_attributes):
                res_dict[attr] = id[index]
            if object_dict.get('action'):
                res_dict['action'] = object_dict['action']
            result.append(default_to_resource(res_dict, helper, to_aim=True))
        else:
            aci_type = aci_mo or helper['resource']
            dn = id_conv(object_dict, otype, helper,
                         aci_mo_type=aci_type, to_aim=False)[0]
            action = 'permit'
            if object_dict.get('action'):
                action = object_dict['action']
            result.append({aci_type:
                           {'attributes':
                            {'dn': dn,
                             'action': action,
                             'tnVzFilterName': object_dict['filter_name']}}})
        return result
    return func


def vzterm_converter(object_dict, otype, helper, source_identity_attributes,
                     destination_identity_attributes, to_aim=True):
    result = []
    id_conv = (helper.get('identity_converter') or
               default_identity_converter)
    if to_aim:
        pass
    else:
        aci_type = helper['resource']
        dn = id_conv(object_dict, otype, helper,
                     aci_mo_type=aci_type, to_aim=False)[0]
        result.append({aci_type:
                       {'attributes':
                        {'dn': dn}}})
    return result

# Resource map maps APIC objects into AIM ones. the key of this map is the
# object APIC type, while the values contain the followings:
# - Resource: AIM resource when direct mapping is applicable
# - Exceptions: The converter will do its best to figure out which resource
# attribute has a direct mapping with the ACI attributes. When this is not
# possible, an exceptions should be set (an exception can be either a string
# mapping AIM to ACI attributes, or a method usable for making the conversion)
# - Identity Converter: When the identity_attributes of the AIM resources are
# not represented exactly by the DN values, a method can be specified for
# making the conversion
# - Converter: The APIC object is completely unmappable to a single AIM
# resource, then a functor can be set here for handling this special case
# - To Resource: None or method for filtering unwanted attributes at the end
# of the conversion for obtaining the final result
# - convert_pre_existing: If True, AIM-to-ACI conversion of the object will
# be performed when the AIM object is marked "pre-existing". Default is False.
# - convert_monitored: If False, AIM-to-ACI conversion of the object will
# not be performed when the AIM object is marked "monitored". Default is True.
# - skip: list of AIM resource attributes that should not be converted

hostprotRemoteIp_converter = child_list('remote_ips', 'addr')
fvRsBDToOut_converter = child_list('l3out_names', 'tnL3extOutName')
fvRsProv_converter = child_list('provided_contract_names', 'tnVzBrCPName')
fvRsCons_converter = child_list('consumed_contract_names', 'tnVzBrCPName')
infraRsSpanVSrcGrp_converter = child_list('span_vsource_group_names',
                                          'tnSpanVSrcGrpName')
infraRsSpanVDestGrp_converter = child_list('span_vdest_group_names',
                                           'tnSpanVDestGrpName')
vzRsSubjFiltAtt_converter = rsFilt_converter()
vzRsFiltAtt_in_converter = rsFilt_converter(aci_mo='vzRsFiltAtt__In')
vzRsFiltAtt_out_converter = rsFilt_converter(aci_mo='vzRsFiltAtt__Out')
fvRsProv_Ext_converter = child_list('provided_contract_names', 'tnVzBrCPName',
                                    aci_mo='fvRsProv__Ext')
fvRsCons_Ext_converter = child_list('consumed_contract_names', 'tnVzBrCPName',
                                    aci_mo='fvRsCons__Ext')
infraRsSpanVSrcGrp_ap_converter = child_list('span_vsource_group_names',
                                             'tnSpanVSrcGrpName',
                                             aci_mo='infraRsSpanVSrcGrp__ap')
infraRsSpanVDestGrp_ap_converter = child_list('span_vdest_group_names',
                                              'tnSpanVDestGrpName',
                                              aci_mo='infraRsSpanVDestGrp__ap')
spanRsSrcToVPort_converter = child_list('src_paths', 'tDn')
vmmInjectedSvcPort_converter = utils.list_dict(
    'service_ports',
    {'port': {'other': 'port',
              'converter': port},
     'protocol': {'other': 'protocol'},
     'target_port': {'other': 'targetPort'},
     'node_port': {'other': 'nodePort',
                   'converter': port,
                   'default': '0'}, },
    ['port', 'protocol', 'target_port'])
vmmInjectedSvcEp_converter = utils.list_dict(
    'endpoints',
    {'pod_name': {'other': 'contGrpName'}},
    ['pod_name'])
infraRsVlanNs_vmm_converter = utils.dn_decomposer(['vlan_pool_name',
                                                   'vlan_pool_type'],
                                                  'fvnsVlanInstP')
vmmRsDomMcastAddrNs_converter = utils.dn_decomposer(['mcast_addr_pool_name'],
                                                    'fvnsMcastAddrInstP')


def infraRsVlan_vmm_id_converter(object_dict, otype, helper, to_aim=True):
    return utils.default_identity_converter(object_dict, otype, helper,
                                            aci_mo_type='infraRsVlanNs__vmm',
                                            to_aim=to_aim)


def bgp_as_id_converter(object_dict, otype, helper, to_aim=True):
    return default_identity_converter(object_dict, otype, helper,
                                      aci_mo_type='bgpAsP__Peer',
                                      to_aim=to_aim)


resource_map = {
    'fvBD': [{
        'resource': resource.BridgeDomain,
        'exceptions': {
            'arpFlood': {
                'other': 'enable_arp_flood',
                'converter': boolean
            },
            'unicastRoute': {
                'other': 'enable_routing',
                'converter': boolean
            },
            'limitIpLearnToSubnets': {
                'converter': boolean
            },
            'unkMacUcastAct': {
                'other': 'l2_unknown_unicast_mode',
            },
            'ipLearning': {
                'converter': boolean
            },
        },
        'identity_converter': None,
        'converter': None,
        'skip': ['vrf_name', 'l3out_names']
    }],
    # Extra Object for BridgeDomain reference to tenant context
    'fvRsCtx': [{
        'resource': resource.BridgeDomain,
        'exceptions': {
            'tnFvCtxName': {
                'other': 'vrf_name',
            }
        },
        'to_resource': default_to_resource_strict,
    }],
    'fvRsBDToOut': [{
        'resource': resource.BridgeDomain,
        'converter': fvRsBDToOut_converter,
    }],
    'fvTenant': [{
        'resource': resource.Tenant,
    }],
    'fvSubnet': [{
        'resource': resource.Subnet,
    }],
    'fvCtx': [{
        'resource': resource.VRF,
        'exceptions': {
            'pcEnfPref': {
                'other': 'policy_enforcement_pref',
            }
        },
    }],
    'fvAp': [{
        'resource': resource.ApplicationProfile,
    }],
    'fvAEPg': [{
        'resource': resource.EndpointGroup,
        'exceptions': {
            'pcEnfPref': {
                'other': 'policy_enforcement_pref',
            },
        },
        'skip': ['bd_name', 'provided_contract_names',
                 'consumed_contract_names',
                 'openstack_vmm_domain_names',
                 'physical_domain_names',
                 'physical_domains',
                 'vmm_domains',
                 'static_paths',
                 'qos_name',
                 'epg_contract_masters'],
    }],
    'fvRsBd': [{
        'resource': resource.EndpointGroup,
        'exceptions': {
            'tnFvBDName': {
                'other': 'bd_name',
            }
        },
        'to_resource': default_to_resource_strict,
    }],
    'faultInst': [{
        'resource': aim_status.AciFault,
        'exceptions': {
            'code': {
                'other': 'fault_code'
            },
            'descr': {
                'other': 'description'
            }
        },
        'identity_converter': fault_identity_converter,
        'to_resource': fault_inst_to_resource,
    }],
    'fvRsProv': [{'resource': resource.EndpointGroup,
                  'converter': fvRsProv_converter,
                  'skip_for_managed': True},
                 {'resource': resource.ExternalNetwork,
                  'converter': fvRsProv_Ext_converter,
                  'convert_pre_existing': True,
                  'convert_monitored': False}],
    'fvRsCons': [{'resource': resource.EndpointGroup,
                  'converter': fvRsCons_converter,
                  'skip_for_managed': True},
                 {'resource': resource.ExternalNetwork,
                  'converter': fvRsCons_Ext_converter,
                  'convert_pre_existing': True,
                  'convert_monitored': False}],
    'fvRsDomAtt': [{
        'resource': resource.EndpointGroup,
        'converter': fv_rs_dom_att_converter,
    }],
    'fvRsSecInherited': [{
        'resource': resource.EndpointGroup,
        'converter': fv_rs_master_epg_converter,
    }],
    'vzFilter': [{
        'resource': resource.Filter,
    }],
    'vzEntry': [{
        'resource': resource.FilterEntry,
        'exceptions': {
            'arpOpc': {'other': 'arp_opcode',
                       'converter': arp_opcode},
            'etherT': {'other': 'ether_type',
                       'converter': ether_type},
            'prot': {'other': 'ip_protocol',
                     'converter': ip_protocol},
            'icmpv4T': {'other': 'icmpv4_type',
                        'converter': icmpv4_type},
            'icmpv6T': {'other': 'icmpv6_type',
                        'converter': icmpv6_type},
            'sFromPort': {'other': 'source_from_port',
                          'converter': port},
            'sToPort': {'other': 'source_to_port',
                        'converter': port},
            'dFromPort': {'other': 'dest_from_port',
                          'converter': port},
            'dToPort': {'other': 'dest_to_port',
                        'converter': port},
            'tcpRules': {'other': 'tcp_flags',
                         'converter': tcp_flags},
            'stateful': {'converter': boolean},
            'applyToFrag': {'other': 'fragment_only',
                            'converter': boolean}
        },
    }],
    'vzBrCP': [{
        'resource': resource.Contract,
    }],
    'vzSubj': [{
        'resource': resource.ContractSubject,
        'skip': ['in_filters', 'out_filters', 'bi_filters',
                 'service_graph_name', 'in_service_graph_name',
                 'out_service_graph_name'],
    }],
    'vzRsSubjFiltAtt': [{
        'resource': resource.ContractSubjFilter,
        'converter': vzRsSubjFiltAtt_converter,
    }],
    'vzRsSubjGraphAtt': [{
        'resource': resource.ContractSubjGraph,
        'exceptions': {'tnVnsAbsGraphName': {'other': 'graph_name'}},
        'to_resource': default_to_resource_strict,
    }],
    'vzRsFiltAtt': [{'resource': resource.ContractSubjInFilter,
                     'converter': vzRsFiltAtt_in_converter},
                    {'resource': resource.ContractSubjOutFilter,
                     'converter': vzRsFiltAtt_out_converter}],
    'vzInTerm': [{'resource': resource.ContractSubjInFilter,
                  'converter': vzterm_converter},
                 {'resource': resource.ContractSubjInGraph,
                  'converter': vzterm_converter}],
    'vzOutTerm': [{'resource': resource.ContractSubjOutFilter,
                   'converter': vzterm_converter},
                  {'resource': resource.ContractSubjOutGraph,
                   'converter': vzterm_converter}],
    'vzRsInTermGraphAtt': [{
        'resource': resource.ContractSubjInGraph,
        'exceptions': {'tnVnsAbsGraphName': {'other': 'graph_name'}},
        'to_resource': default_to_resource_strict,
    }],
    'vzRsOutTermGraphAtt': [{
        'resource': resource.ContractSubjOutGraph,
        'exceptions': {'tnVnsAbsGraphName': {'other': 'graph_name'}},
        'to_resource': default_to_resource_strict,
    }],
    'l3extOut': [{
        'resource': resource.L3Outside,
        'skip': ['vrf_name', 'l3_domain_dn', 'bgp_enable']
    }],
    'bgpExtP': [{
        'resource': resource.L3Outside,
        'converter': bgp_extp_converter
    }],
    'l3extRsEctx': [{
        'resource': resource.L3Outside,
        'exceptions': {'tnFvCtxName': {'other': 'vrf_name'}},
        'to_resource': default_to_resource_strict,
    }],
    'l3extRsL3DomAtt': [{
        'resource': resource.L3Outside,
        'exceptions': {'tDn': {'other': 'l3_domain_dn'}},
        'to_resource': default_to_resource_strict,
    }],
    'l3extLNodeP': [{
        'resource': resource.L3OutNodeProfile,
    }],
    'l3extRsNodeL3OutAtt': [{
        'resource': resource.L3OutNode,
        'exceptions': {'rtrId': {'other': 'router_id'},
                       'rtrIdLoopBack': {'other': 'router_id_loopback',
                                         'converter': boolean}}
    }],
    'ipRouteP': [{
        'resource': resource.L3OutStaticRoute,
        'exceptions': {'pref': {'other': 'preference'}},
        'skip': ['next_hop_list'],
    }],
    'ipNexthopP': [{
        'resource': resource.L3OutStaticRoute,
        'converter': l3ext_next_hop_converter,
    }],
    'l3extLIfP': [{
        'resource': resource.L3OutInterfaceProfile,
    }],
    'l3extRsPathL3OutAtt': [{
        'resource': resource.L3OutInterface,
        'exceptions': {'ifInstT': {'other': 'type'},
                       'addr': {'other': 'primary_addr_a'}},
        'skip': ['primary_addr_b', 'secondary_addr_a_list',
                 'secondary_addr_b_list', 'host'],
    }],
    'bgpPeerP': [{
        'resource': resource.L3OutInterfaceBgpPeerP,
        'skip': ['asn']
    }],
    'bgpAsP': [{
        'resource': resource.L3OutInterfaceBgpPeerP,
        'identity_converter': bgp_as_id_converter,
    }],
    'l3extIp': [{
        'resource': resource.L3OutInterface,
        'skip': ['host'],
        'converter': l3ext_ip_converter,
    }],
    'l3extIp__Member': [{
        'resource': resource.L3OutInterface,
        'skip': ['host'],
        'converter': l3ext_ip_converter,
    }],
    'l3extMember': [{
        'resource': resource.L3OutInterface,
        'skip': ['host'],
        'converter': l3ext_member_converter,
    }],
    'l3extInstP': [{
        'resource': resource.ExternalNetwork,
        'skip': ['nat_epg_dn', 'provided_contract_names',
                 'consumed_contract_names'],
    }],
    'l3extRsInstPToNatMappingEPg': [{
        'resource': resource.ExternalNetwork,
        'exceptions': {'tDn': {'other': 'nat_epg_dn'}},
        'to_resource': default_to_resource_strict,
    }],
    'l3extSubnet': [{
        'resource': resource.ExternalSubnet,
    }],
    'fvRsPathAtt': [{
        'resource': resource.EndpointGroup,
        'converter': fv_rs_path_att_converter,
    }],
    'hostprotPol': [{
        'resource': resource.SecurityGroup,
    }],
    'hostprotSubj': [{
        'resource': resource.SecurityGroupSubject,
    }],
    'hostprotRule': [{
        'resource': resource.SecurityGroupRule,
        'skip': ['remote_ips', 'remote_group_id'],
        'exceptions': {
            'protocol': {'other': 'ip_protocol',
                         'converter': ip_protocol},
            'fromPort': {'other': 'from_port',
                         'converter': port},
            'toPort': {'other': 'to_port',
                       'converter': port},
            'ethertype': {'other': 'ethertype',
                          'converter': ethertype},
            'icmpType': {'other': 'icmp_type'},
            'icmpCode': {'other': 'icmp_code',
                         'converter': icmpv4_code},
        }
    }],
    'hostprotRemoteIp': [{
        'resource': resource.SecurityGroupRule,
        'converter': hostprotRemoteIp_converter,
    }],
    'opflexODev': [{
        'resource': aim_infra.OpflexDevice,
        'exceptions': {'domName': {'other': 'domain_name'},
                       'ctrlrName': {'other': 'controller_name'}, }
    }],
    'vmmDomP': [{
        'resource': resource.VMMDomain,
        'skip': ['vlan_pool_name', 'vlan_pool_type',
                 'mcast_addr_pool_name'],
        'exceptions': {'mcastAddr': {'other': 'mcast_address'},
                       'enfPref': {'other': 'enforcement_pref'}},
    }],
    'infraRsVlanNs': [{
        'resource': resource.VMMDomain,
        'exceptions': {'tDn': {'other': 'vlan_pool_name',
                               'converter': infraRsVlanNs_vmm_converter,
                               'skip_if_empty': True}},
        'identity_converter': infraRsVlan_vmm_id_converter,
        'to_resource': utils.default_to_resource_strict,
    }],
    'vmmRsDomMcastAddrNs': [{
        'resource': resource.VMMDomain,
        'exceptions': {'tDn': {'other': 'mcast_addr_pool_name',
                               'converter': vmmRsDomMcastAddrNs_converter,
                               'skip_if_empty': True}},
        'to_resource': utils.default_to_resource_strict,
    }],
    'vmmProvP': [{
        'resource': resource.VMMPolicy,
        # temporarily disable nameAlias sync due to ACI bug
        'skip': ['display_name', 'name_alias'],
    }],
    'physDomP': [{
        'resource': resource.PhysicalDomain,
    }],
    'fabricPod': [{
        'resource': resource.Pod,
    }],
    'fabricTopology': [{
        'resource': resource.Topology,
    }],
    'vmmCtrlrP': [{
        'resource': resource.VMMController,
    }],
    'vmmInjectedNs': [{
        'resource': resource.VmmInjectedNamespace,
    }],
    'vmmInjectedDepl': [{
        'resource': resource.VmmInjectedDeployment,
        'exceptions': {'replicas': {'converter': utils.integer_str}}
    }],
    'vmmInjectedReplSet': [{
        'resource': resource.VmmInjectedReplicaSet,
    }],
    'vmmInjectedSvc': [{
        'resource': resource.VmmInjectedService,
        'skip': ['service_ports', 'endpoints'],
        'exceptions': {'type': {'other': 'service_type'},
                       'lbIp': {'other': 'load_balancer_ip'}},
    }],
    'vmmInjectedSvcPort': [{
        'resource': resource.VmmInjectedService,
        'converter': vmmInjectedSvcPort_converter,
    }],
    'vmmInjectedSvcEp': [{
        'resource': resource.VmmInjectedService,
        'converter': vmmInjectedSvcEp_converter,
    }],
    'vmmInjectedHost': [{
        'resource': resource.VmmInjectedHost,
        'exceptions': {'kernelVer': {'other': 'kernel_version'}}
    }],
    'vmmInjectedContGrp': [{
        'resource': resource.VmmInjectedContGroup,
    }],
    'infraInfra': [{
        'resource': resource.Infra,
    }],
    'netflowVmmExporterPol': [{
        'resource': resource.NetflowVMMExporterPol,
    }],
    'qosRequirement': [{
        'resource': resource.QosRequirement,
        'skip': ['dscp', 'ingress_dpp_pol', 'egress_dpp_pol'],
    }],
    'qosDppPol': [{
        'resource': resource.QosDppPol,
    }],
    'qosRsIngressDppPol': [{
        'resource': resource.QosRequirement,
        'converter': qos_rs_ingress_dpp_pol,
        'skip': ['dscp']
    }],
    'qosRsEgressDppPol': [{
        'resource': resource.QosRequirement,
        'converter': qos_rs_egress_dpp_pol,
        'skip': ['dscp']
    }],
    'qosEpDscpMarking': [{
        'resource': resource.QosRequirement,
        'converter': qos_ep_dscp_marking,
    }],
    'fvRsQosRequirement': [{
        'resource': resource.EndpointGroup,
        'converter': qos_rs_req,
    }],
    'vmmVSwitchPolicyCont': [{
        'resource': resource.VmmVswitchPolicyGroup,
    }],
    'vmmRsVswitchExporterPol': [{
        'resource': resource.VmmRelationToExporterPol,
    }],
    'spanVSrcGrp': [{
        'resource': resource.SpanVsourceGroup,
    }],
    'spanVSrc': [{
        'resource': resource.SpanVsource,
        'skip': ['src_paths'],
    }],
    'spanVDestGrp': [{
        'resource': resource.SpanVdestGroup,
    }],
    'spanVDest': [{
        'resource': resource.SpanVdest,
    }],
    'spanVEpgSummary': [{
        'resource': resource.SpanVepgSummary,
    }],
    'spanRsSrcToVPort': [{
        'resource': resource.SpanVsource,
        'converter': spanRsSrcToVPort_converter,
    }],
    'infraAccBndlGrp': [{
        'resource': resource.InfraAccBundleGroup,
        'skip': ['span_vsource_group_names', 'span_vdest_group_names'],
    }],
    'infraAccPortGrp': [{
        'resource': resource.InfraAccPortGroup,
        'skip': ['span_vsource_group_names', 'span_vdest_group_names'],
    }],
    'infraRsSpanVSrcGrp': [{
        'resource': resource.InfraAccBundleGroup,
        'converter': infraRsSpanVSrcGrp_converter,
        'convert_pre_existing': True,
        'convert_monitored': False}],
    'infraRsSpanVSrcGrp__ap': [{
        'resource': resource.InfraAccPortGroup,
        'converter': infraRsSpanVSrcGrp_ap_converter,
        'convert_pre_existing': True,
        'convert_monitored': False}],
    'infraRsSpanVDestGrp': [{
        'resource': resource.InfraAccBundleGroup,
        'converter': infraRsSpanVDestGrp_converter,
        'convert_pre_existing': True,
        'convert_monitored': False}],
    'infraRsSpanVDestGrp__ap': [{
        'resource': resource.InfraAccPortGroup,
        'converter': infraRsSpanVDestGrp_ap_converter,
        'convert_pre_existing': True,
        'convert_monitored': False}],
    'spanSpanLbl': [{
        'resource': resource.SpanSpanlbl,
    }],
}

resource_map.update(service_graph.resource_map)

# Build the reverse map for reverse translation
reverse_resource_map = {}
for apic_type, rule_list in resource_map.items():
    for rules in rule_list:
        klass = rules['resource']
        mapped_klass = reverse_resource_map.setdefault(klass, [])
        mapped_rules = {}
        mapped_rules['resource'] = apic_type
        if 'identity_converter' in rules:
            mapped_rules['identity_converter'] = rules['identity_converter']
        if 'converter' in rules:
            mapped_rules['converter'] = rules['converter']
        if 'to_resource' in rules:
            mapped_rules['to_resource'] = rules['to_resource']
        if 'convert_pre_existing' in rules:
            mapped_rules['convert_pre_existing'] = (
                rules['convert_pre_existing'])
        if 'convert_monitored' in rules:
            mapped_rules['convert_monitored'] = rules['convert_monitored']
        if 'skip' in rules:
            mapped_rules['skip'] = [convert_attribute(s, to_aim=False)
                                    for s in rules['skip']]
        # Revert Exceptions
        mapped_rules['exceptions'] = {}
        mapped_rules['exceptions'] = (
            utils.reverse_attribute_mapping_info(rules.get('exceptions', {})))
        mapped_klass.append(mapped_rules)

# Special changes to map and the reverse map can be made here

# Rules for these classes are present for UTs related to back-and-forth
# conversions:
#  vzRsFiltAtt__In, vzRsFiltAtt__Out
#  fvRsProv__Ext, fvRsCons__Ext
resource_map.update({
    'vzRsFiltAtt__In': [{'resource': resource.ContractSubjInFilter,
                         'converter': vzRsFiltAtt_in_converter}],
    'vzRsFiltAtt__Out': [{'resource': resource.ContractSubjOutFilter,
                          'converter': vzRsFiltAtt_out_converter}],
    'fvRsProv__Ext': [{'resource': resource.ExternalNetwork,
                       'converter': fvRsProv_Ext_converter,
                       'convert_pre_existing': True,
                       'convert_monitored': False}],
    'fvRsCons__Ext': [{'resource': resource.ExternalNetwork,
                       'converter': fvRsCons_Ext_converter,
                       'convert_pre_existing': True,
                       'convert_monitored': False}],
    'infraRsVlanNs__vmm': [resource_map['infraRsVlanNs'][0]],
    'bgpAsP__Peer': [{
        'resource': resource.L3OutInterfaceBgpPeerP,
        'identity_converter': bgp_as_id_converter,
    }]
})

resource_map.update(service_graph.resource_map_post_reverse)

for item in reverse_resource_map[resource.L3OutInterfaceBgpPeerP]:
    if item['resource'] == 'bgpAsP':
        item['resource'] = 'bgpAsP__Peer'


class BaseConverter(object):

    def __init__(self):
        pass

    def convert(self, objects):
        """Converter AIM/ACI main method

        :param objects: list of AIM/ACI objects
        :return: list of converted resources
        """

    def _default_converter(self, object_dict, otype, helper,
                           source_identity_attributes,
                           destination_identity_attributes, to_aim=True):
        return utils.default_converter(object_dict, otype, helper,
                                       source_identity_attributes,
                                       destination_identity_attributes, to_aim)


class AciToAimModelConverter(BaseConverter):
    """Converts ACI model to AIM resource."""

    def convert(self, aci_objects):
        """Converter main method

        :param aci_objects: list of ACI objects in the form of a dictionary
        which has the object type as the first key
        :return: list of AIM resources
        """
        result = []
        for object in aci_objects:
            try:
                if list(object.keys())[0] not in resource_map:
                    # Ignore unmanaged object
                    continue
                resource = object[list(object.keys())[0]]['attributes']
                # Change nameAlias to allow automatic conversion
                if 'nameAlias' in resource:
                    resource['displayName'] = resource['nameAlias']
                    del resource['nameAlias']
                for helper in resource_map[list(object.keys())[0]]:
                    # Use the custom converter, fallback to the default one
                    converted = (
                        helper.get('converter') or self._default_converter)(
                        resource, list(object.keys())[0], helper,
                        ['dn'], helper['resource'].identity_attributes,
                        to_aim=True)
                    if resource.get('status') == DELETED_STATUS:
                        for x in converted:
                            # Set deleted status for updating the tree
                            # correctly
                            x.__dict__['_status'] = 'deleted'
                    result.extend(converted)
                # Change displayName back to original
                if 'displayName' in resource:
                    resource['nameAlias'] = resource['displayName']
                    del resource['displayName']
            except Exception as e:
                LOG.warn("Could not convert object"
                         "%s with error %s" % (object, str(e)))
                LOG.debug(traceback.format_exc())
        squashed = self._squash(result)
        if aci_objects:
            LOG.debug("Converted: %s into: %s" % (aci_objects, squashed))
        return squashed

    def _squash(self, converted_list):
        """Squash objects with same identity into one

        :param converted_list:
        :return:
        """

        res_map = collections.OrderedDict()
        list_dict_by_id = {}
        for res in converted_list:
            # Base for squashing is the Resource with all its defaults
            klass = type(res)
            current = res_map.setdefault(
                (res._aci_mo_name,) + tuple(res.identity),
                klass(**dict([(y, res.identity[x]) for x, y in
                              enumerate(klass.identity_attributes)])))
            for k, v in res.__dict__.items():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and '_converter_id' in item:
                            id_ = (klass.__name__, k) + item.pop(
                                '_converter_id')
                            if id_ in list_dict_by_id:
                                list_dict_by_id[id_].update(item)
                                continue
                            else:
                                list_dict_by_id[id_] = item
                        current.__dict__.setdefault(k, []).append(item)
                else:
                    setattr(current, k, v)
        return list(res_map.values())


class AimToAciModelConverter(BaseConverter):
    """Converts ACI model to AIM resource."""

    def convert(self, aim_objects):
        """Converter main method

        :param aim_objects: list of AIM objects
        :return: list of AIM resources
        """
        result = []
        in_objects = copy.copy(aim_objects)
        for object in in_objects:
            try:
                klass = type(object)
                if klass not in reverse_resource_map:
                    # Ignore unmanaged object
                    continue
                is_pre = getattr(object, 'pre_existing', False)
                is_mon = getattr(object, 'monitored', False)
                if 'display_name' in object.__dict__:
                    object.__dict__['name_alias'] = object.display_name
                    del object.__dict__['display_name']
                for helper in reverse_resource_map[klass]:
                    if is_pre and not helper.get('convert_pre_existing',
                                                 False):
                        continue
                    if is_mon and not helper.get('convert_monitored', True):
                        continue
                    # Use the custom converter, fallback to the default one
                    converted = (
                        helper.get('converter') or self._default_converter)(
                        object.__dict__, klass, helper,
                        klass.identity_attributes,
                        ['dn'], to_aim=False)
                    for c in converted:
                        # Some converters generate other AIM objects, pass
                        # them through their converters to get the ACI objects.
                        if isinstance(c, resource.ResourceBase):
                            in_objects.append(c)
                        else:
                            result.append(c)
                # Set name alias back to original
                if 'name_alias' in object.__dict__:
                    object.__dict__['display_name'] = object.name_alias
                    del object.__dict__['name_alias']
            except Exception as e:
                LOG.warn("Could not convert object"
                         "%s with error %s" % (object.__dict__, str(e)))
                LOG.debug(traceback.format_exc())

        squashed = self._squash(result)
        if aim_objects:
            LOG.debug("Converted: %s into: %s" % (aim_objects, squashed))
        return squashed

    def _squash(self, converted_list):
        """Squash objects with same identity into one

        :param converted_list:
        :return:
        """
        res_map = collections.OrderedDict()
        for res in converted_list:
            current = res_map.setdefault(
                res[list(res.keys())[0]]['attributes']['dn'], res)
            current.update(res)
        return list(res_map.values())
