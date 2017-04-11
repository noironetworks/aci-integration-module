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

LOG = logging.getLogger(__name__)
DELETED_STATUS = "deleted"
CLEARED_SEVERITY = "cleared"
MODIFIED_STATUS = "modified"


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
        in_ = helper['resource'] is 'vzInTerm' and converted.get('inFilters')
        out = helper['resource'] is 'vzOutTerm' and converted.get('outFilters')
        if in_ or out:
            return {
                helper['resource']: {'attributes': {'dn': converted['dn']}}}


tcp_flags = mapped_attribute(t.tcp_flags)
port = mapped_attribute(t.ports)
arp_opcode = mapped_attribute(t.arp_opcode)
ether_type = mapped_attribute(t.ether_type)
icmpv4_type = mapped_attribute(t.icmpv4_type)
icmpv6_type = mapped_attribute(t.icmpv6_type)
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
            res_dict['openstack_vmm_domain_names'] = [dom_id[-1]]
        except apic_client.DNManager.InvalidNameFormat:
            dom_id = default_identity_converter(
                {'dn': id[-1]}, 'physDomP', helper, to_aim=True)
            res_dict['physical_domain_names'] = [dom_id[0]]
        result.append(default_to_resource(res_dict, helper, to_aim=True))
    else:
        # Converting an EndpointGroup into fvRsDomAtt objects
        for phys in object_dict['physical_domain_names']:
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
                                           'tDn': phys_dn,
                                           'classPref': 'useg'}}})
        # Convert OpenStack VMMs
        for vmm in object_dict['openstack_vmm_domain_names']:
            # Get VMM DN
            vmm_dn = default_identity_converter(
                resource.VMMDomain(
                    type=aim_utils.OPENSTACK_VMM_TYPE, name=vmm).__dict__,
                resource.VMMDomain, helper, aci_mo_type='vmmDomP',
                to_aim=False)[0]
            dn = default_identity_converter(
                object_dict, otype, helper, extra_attributes=[vmm_dn],
                aci_mo_type='fvRsDomAtt', to_aim=False)[0]
            result.append({'fvRsDomAtt': {'attributes':
                                          {'dn': dn,
                                           'tDn': vmm_dn,
                                           'classPref': 'useg'}}})
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
                                                     'encap': p['encap']}}})
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
vzRsSubjFiltAtt_converter = child_list('bi_filters', 'tnVzFilterName')
vzInTerm_vzRsFiltAtt_converter = child_list('in_filters', 'tnVzFilterName',
                                            aci_mo='vzRsFiltAtt__In')
vzOutTerm_vzRsFiltAtt_converter = child_list('out_filters', 'tnVzFilterName',
                                             aci_mo='vzRsFiltAtt__Out')
fvRsProv_Ext_converter = child_list('provided_contract_names', 'tnVzBrCPName',
                                    aci_mo='fvRsProv__Ext')
fvRsCons_Ext_converter = child_list('consumed_contract_names', 'tnVzBrCPName',
                                    aci_mo='fvRsCons__Ext')

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
            }
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
                 'static_paths'],
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
                  'converter': fvRsProv_converter},
                 {'resource': resource.ExternalNetwork,
                  'converter': fvRsProv_Ext_converter,
                  'convert_pre_existing': True,
                  'convert_monitored': False}],
    'fvRsCons': [{'resource': resource.EndpointGroup,
                  'converter': fvRsCons_converter},
                 {'resource': resource.ExternalNetwork,
                  'converter': fvRsCons_Ext_converter,
                  'convert_pre_existing': True,
                  'convert_monitored': False}],
    'fvRsDomAtt': [{
        'resource': resource.EndpointGroup,
        'converter': fv_rs_dom_att_converter,
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
                 'service_graph_name'],
    }],
    'vzRsSubjFiltAtt': [{
        'resource': resource.ContractSubject,
        'converter': vzRsSubjFiltAtt_converter
    }],
    'vzRsSubjGraphAtt': [{
        'resource': resource.ContractSubject,
        'exceptions': {'tnVnsAbsGraphName': {'other': 'service_graph_name'}},
        'to_resource': default_to_resource_strict,
    }],
    'vzRsFiltAtt': [{'resource': resource.ContractSubject,
                     'converter': vzInTerm_vzRsFiltAtt_converter},
                    {'resource': resource.ContractSubject,
                     'converter': vzOutTerm_vzRsFiltAtt_converter}],
    'vzInTerm': [{
        'resource': resource.ContractSubject,
        'to_resource': to_resource_filter_container,
        'skip': ['display_name']
    }],
    'vzOutTerm': [{
        'resource': resource.ContractSubject,
        'to_resource': to_resource_filter_container,
        'skip': ['display_name']
    }],
    'l3extOut': [{
        'resource': resource.L3Outside,
        'skip': ['vrf_name', 'l3_domain_dn']
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
        'skip': ['remote_ips'],
        'exceptions': {
            'protocol': {'other': 'ip_protocol',
                         'converter': ip_protocol},
            'fromPort': {'other': 'from_port',
                         'converter': port},
            'toPort': {'other': 'to_port',
                       'converter': port},
            'ethertype': {'other': 'ethertype',
                          'converter': ethertype},
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
    }],
    'vmmProvP': [{
        'resource': resource.VMMPolicy,
    }],
    'physDomP': [{
        'resource': resource.PhysicalDomain,
    }],
    'fabricPod': [{
        'resource': resource.Pod,
    }]
}

resource_map.update(service_graph.resource_map)

# Build the reverse map for reverse translation
reverse_resource_map = {}
for apic_type, rule_list in resource_map.iteritems():
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
    'vzRsFiltAtt__In': [{'resource': resource.ContractSubject,
                         'converter': vzInTerm_vzRsFiltAtt_converter}],
    'vzRsFiltAtt__Out': [{'resource': resource.ContractSubject,
                         'converter': vzOutTerm_vzRsFiltAtt_converter}],
    'fvRsProv__Ext': [{'resource': resource.ExternalNetwork,
                       'converter': fvRsProv_Ext_converter,
                       'convert_pre_existing': True,
                       'convert_monitored': False}],
    'fvRsCons__Ext': [{'resource': resource.ExternalNetwork,
                       'converter': fvRsCons_Ext_converter,
                       'convert_pre_existing': True,
                       'convert_monitored': False}]
})

resource_map.update(service_graph.resource_map_post_reverse)


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
        LOG.debug("converting aci objects %s" % aci_objects)
        result = []
        for object in aci_objects:
            try:
                if object.keys()[0] not in resource_map:
                    # Ignore unmanaged object
                    continue
                resource = object[object.keys()[0]]['attributes']
                # Change nameAlias to allow automatic conversion
                if 'nameAlias' in resource:
                    resource['displayName'] = resource['nameAlias']
                    del resource['nameAlias']
                for helper in resource_map[object.keys()[0]]:
                    # Use the custom converter, fallback to the default one
                    converted = (
                        helper.get('converter') or self._default_converter)(
                        resource, object.keys()[0], helper,
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
                         "%s with error %s" % (object, e.message))
                LOG.debug(traceback.format_exc())
        squashed = self._squash(result)
        LOG.debug("Converted:\n %s\n into:\n %s" %
                  (aci_objects, squashed))
        return squashed

    def _squash(self, converted_list):
        """Squash objects with same identity into one

        :param converted_list:
        :return:
        """
        res_map = collections.OrderedDict()
        for res in converted_list:
            # Base for squashing is the Resource with all its defaults
            klass = type(res)
            current = res_map.setdefault(
                (res._aci_mo_name,) + tuple(res.identity),
                klass(**dict([(y, res.identity[x]) for x, y in
                              enumerate(klass.identity_attributes)])))
            for k, v in res.__dict__.iteritems():
                if isinstance(v, list):
                    current.__dict__.setdefault(k, []).extend(v)
                else:
                    setattr(current, k, v)
        return res_map.values()


class AimToAciModelConverter(BaseConverter):
    """Converts ACI model to AIM resource."""

    def convert(self, aim_objects):
        """Converter main method

        :param aim_objects: list of AIM objects
        :return: list of AIM resources
        """
        LOG.debug("converting aim objects %s" % aim_objects)
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
                         "%s with error %s" % (object.__dict__, e.message))
                LOG.error(traceback.format_exc())

        squashed = self._squash(result)
        LOG.debug("Converted:\n %s\n into:\n %s" %
                  (aim_objects, squashed))
        return squashed

    def _squash(self, converted_list):
        """Squash objects with same identity into one

        :param converted_list:
        :return:
        """
        res_map = collections.OrderedDict()
        for res in converted_list:
            current = res_map.setdefault(
                res[res.keys()[0]]['attributes']['dn'], res)
            current.update(res)
        return res_map.values()
