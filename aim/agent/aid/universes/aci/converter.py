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

from apicapi import apic_client
from oslo_log import log as logging

from aim.api import resource
from aim.api import status as aim_status

LOG = logging.getLogger(__name__)
DELETED_STATUS = "deleted"
CLEARED_SEVERITY = "cleared"
MODIFIED_STATUS = "modified"


def default_identity_converter(object_dict, otype, helper,
                               to_aim=True):
    """Default identity converter

    This converter uses the DN and splits it in its fundamental parts to
    retrieve the identity names.

    :param object_dict: dictionarty of the resource to be converted
    :param otype: Type of the object. Can be an AIM resource class or a
                  APIC class name.
    :param to_aim: Boolean indicating whether we are converting
                   ACI/AIM (True) or AIM/ACi (False)
    :return: list with exactly all the attributes that need to be assigned
    to the resource class 'identity_attributes'
    """
    if to_aim:
        return apic_client.DNManager().aci_decompose(object_dict['dn'], otype)
    else:
        return [apic_client.ManagedObjectClass(helper['resource']).dn(
            *[object_dict[x] for x in otype.identity_attributes])]


def fault_identity_converter(object_dict, otype, helper,
                             to_aim=True):
    if to_aim:
        return object_dict['code'], object_dict['dn']
    else:
        return [object_dict['external_identifier']]


def default_attribute_converter(object_dict, attribute,
                                to_aim=True):
    return object_dict[attribute]


def default_to_resource(converted, helper, to_aim=True):
    klass = helper['resource']
    if to_aim:
        # APIC to AIM
        return klass(
            _set_default=False,
            **dict([(k, v) for k, v in converted.iteritems() if k in
                    (klass.identity_attributes + klass.db_attributes +
                     klass.other_attributes)]))
    else:
        result = {klass: {'attributes': converted}}
        result[klass]['attributes'].pop('displayName', None)
        return result


def convert_attribute(aim_attribute, to_aim=True):
    """Convert attribute name from AIM to ACI format

    converts from this_format to thisFormat
    :param aim_attribute:
    :return:
    """
    if to_aim:
        # Camel to _ (APIC to AIM)
        result = []
        for x in aim_attribute:
            if x.isupper():
                result.append('_')
            result.append(x.lower())
        return ''.join(result)
    else:
        # _ to Camel (AIM to APIC)
        parts = aim_attribute.split('_')
        result = parts[0]
        for part in parts[1:]:
            result += part[0].upper() + part[1:]
        return result


def boolean(resource, attribute, to_aim=True):
    if to_aim:
        # APIC to AIM
        aci_value = resource[attribute]
        return bool(aci_value is True or aci_value.lower() == 'yes')
    else:
        # AIM to APIC
        return 'yes' if resource[attribute] is True else 'no'


def fv_bd_to_resource(converted, helper, to_aim=True):
    if to_aim:
        # Nothing fancy to do
        return default_to_resource(converted, helper, to_aim=to_aim)
    else:
        # Exclude vrf_name
        result = default_to_resource(converted, helper, to_aim=to_aim)
        result[helper['resource']]['attributes'].pop('vrfName', None)
        return result


def fv_rs_ctx_to_resource(converted, helper, to_aim=True):
    if to_aim:
        # Nothing fancy to do
        return default_to_resource(converted, helper, to_aim=to_aim)
    else:
        # Only include vrf_name
        if converted['tnFvCtxName'] is not None:
            return {helper['resource']: {'attributes': {
                'dn': converted['dn'],
                'tnFvCtxName': converted['tnFvCtxName']}}}
        else:
            return None


def fv_aepg_to_resource(converted, helper, to_aim=True):
    if to_aim:
        # Nothing fancy to do
        return default_to_resource(converted, helper, to_aim=to_aim)
    else:
        # Exclude bd_name, provided_contract_names, consumed_contract_names
        result = default_to_resource(converted, helper, to_aim=to_aim)
        attr = result[helper['resource']]['attributes']
        attr.pop('bdName', None)
        attr.pop('providedContractNames', None)
        attr.pop('consumedContractNames', None)
        return result


def fv_rs_bd_to_resource(converted, helper, to_aim=True):
    if to_aim:
        # Nothing fancy to do
        return default_to_resource(converted, helper, to_aim=to_aim)
    else:
        # Only include bd_name
        if converted['tnFvBDName'] is not None:
            return {helper['resource']: {'attributes': {
                'dn': converted['dn'],
                'tnFvBDName': converted['tnFvBDName']}}}
        else:
            return None


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
        'to_resource': fv_bd_to_resource,
    }],
    # Extra Object for BridgeDomain reference to tenant context
    'fvRsCtx': [{
        'resource': resource.BridgeDomain,
        'exceptions': {
            'tnFvCtxName': {
                'other': 'vrf_name',
            }
        },
        'to_resource': fv_rs_ctx_to_resource,
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
        'to_resource': fv_aepg_to_resource,
    }],
    'fvRsBd': [{
        'resource': resource.EndpointGroup,
        'exceptions': {
            'tnFvBDName': {
                'other': 'bd_name',
            }
        },
        'to_resource': fv_rs_bd_to_resource,
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
    'healthInst': [{
        'resource': aim_status.AciStatus,
        'exceptions': {
            'cur': {
                'other': 'health_score'
            }
        },
        'identity_converter': fault_identity_converter,
        'to_resource': fault_inst_to_resource,
    }]
}

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
        # Revert Exceptions
        mapped_rules['exceptions'] = {}
        for exception, value in rules.get('exceptions', {}).iteritems():
            aci_name = value.get(
                'other', convert_attribute(exception))
            mapped_rules['exceptions'][aci_name] = {}
            mapped_rules['exceptions'][aci_name]['other'] = exception
            if 'converter' in value:
                mapped_rules['exceptions'][
                    aci_name]['converter'] = value['converter']
        mapped_klass.append(mapped_rules)

# Special changes to map and the reverse map can be made here


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
        """Default AIM/ACI and ACI/AIM converter

        :param object_dict: Object to be converted in the form of a dictionary
        :param otype: Type of the object. Can be an AIM resource class or a
                      APIC class name.
        :param helper: Mapping help from the (reverse_)resource_map
        :param source_identity_attributes: ID attributes of the src object
        :param destination_identity_attributes: ID attributes of the dst object
        :param to_aim: Boolean indicating whether we are converting
                       ACI/AIM (True) or AIM/ACI (False)
        :return: list containing the resulting objects
        """
        # translate identity
        res_dict = {}
        identity = (helper.get('identity_converter') or
                    default_identity_converter)(object_dict, otype, helper,
                                                to_aim=to_aim)
        for index, part in enumerate(destination_identity_attributes):
            res_dict[part] = identity[index]
        for attribute in object_dict:
            if attribute in source_identity_attributes:
                continue
            # Verify if it is an exception
            if attribute in helper.get('exceptions', {}):
                LOG.debug("attribute %s is an exception" % attribute)
                other = helper['exceptions'][attribute].get(
                    'other', convert_attribute(attribute, to_aim=to_aim))
                conv = (helper['exceptions'][attribute].get(
                    'converter') or default_attribute_converter)
                converted = conv(object_dict, attribute, to_aim=to_aim)
            else:
                # Transform in Other format
                other = convert_attribute(attribute, to_aim=to_aim)
                converted = object_dict.get(attribute)
            # Identity was already converted
            if other not in destination_identity_attributes:
                res_dict[other] = converted
        result = (helper.get('to_resource') or default_to_resource)(
            res_dict, helper, to_aim=to_aim)
        return [result] if result else []


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
            if object.keys()[0] not in resource_map:
                # Ignore unmanaged object
                continue
            for helper in resource_map[object.keys()[0]]:
                resource = object[object.keys()[0]]['attributes']
                # Use the custom converter, fallback to the default one
                converted = (
                    helper.get('converter') or self._default_converter)(
                    resource, object.keys()[0], helper,
                    ['dn'], helper['resource'].identity_attributes,
                    to_aim=True)
                if resource.get('status') == DELETED_STATUS:
                    for x in converted:
                        # Set deleted status for updating the tree correctly
                        x.__dict__['_status'] = 'deleted'
                result.extend(converted)
        squashed = self._squash(result)
        LOG.debug("Converted:\n %s\n into:\n %s" %
                  (aci_objects, squashed))
        return squashed

    def _squash(self, converted_list):
        """Squash objects with same identity into one

        :param converted_list:
        :return:
        """
        res_map = {}
        for res in converted_list:
            # Base for squashing is the Resource with all its defaults
            klass = type(res)
            current = res_map.setdefault(
                tuple(res.identity),
                klass(**dict([(y, res.identity[x]) for x, y in
                              enumerate(klass.identity_attributes)])))
            current.__dict__.update(res.__dict__)
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
        for object in aim_objects:
            klass = type(object)
            if klass not in reverse_resource_map:
                # Ignore unmanaged object
                continue
            for helper in reverse_resource_map[klass]:
                # Use the custom converter, fallback to the default one
                converted = (
                    helper.get('converter') or self._default_converter)(
                    object.__dict__, klass, helper, klass.identity_attributes,
                    ['dn'], to_aim=False)
                result.extend(converted)

        squashed = self._squash(result)
        LOG.debug("Converted:\n %s\n into:\n %s" %
                  (aim_objects, squashed))
        return squashed

    def _squash(self, converted_list):
        """Squash objects with same identity into one

        :param converted_list:
        :return:
        """
        res_map = {}
        for res in converted_list:
            current = res_map.setdefault(
                res[res.keys()[0]]['attributes']['dn'], res)
            current.update(res)
        return res_map.values()
