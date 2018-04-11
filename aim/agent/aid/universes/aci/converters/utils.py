# Copyright (c) 2017 Cisco Systems
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

import copy

from oslo_log import log as logging

from apicapi import apic_client

LOG = logging.getLogger(__name__)
IGNORE = object()


def boolean(resource, attribute, to_aim=True):
    if to_aim:
        # APIC to AIM
        aci_value = resource[attribute]
        return bool(aci_value is True or aci_value.lower() == 'yes')
    else:
        # AIM to APIC
        return 'yes' if resource[attribute] is True else 'no'


def upper(object_dict, attribute_name, to_aim=True):
    return object_dict[attribute_name].upper()


def integer_str(object_dict, attribute_name, to_aim=True):
    if to_aim:
        return int(object_dict[attribute_name])
    else:
        return str(object_dict[attribute_name])


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


def mapped_attribute(value_map):
    def mapped(object_dict, attribute, to_aim=True):
        curr = default_attribute_converter(object_dict, attribute,
                                           to_aim=to_aim)
        if to_aim:
            return curr
        else:
            # ACI only accepts certain parameters
            return value_map.get(str(curr), str(curr))
    return mapped


def default_attribute_converter(object_dict, attribute,
                                to_aim=True):
    return object_dict[attribute]


def default_to_resource(converted, helper, to_aim=True):
    klass = helper['resource']
    default_skip = ['preExisting', 'monitored', 'Error', 'Pending',
                    'InjectedAimId', 'sync', 'epoch']
    skip = helper.get('skip', [])
    if to_aim:
        # APIC to AIM
        return klass(
            _set_default=False,
            **dict([(k, v) for k, v in converted.iteritems() if k in
                    klass.attributes() and k not in skip]))
    else:
        for s in default_skip + skip:
            converted.pop(s, None)
        result = {klass: {'attributes': converted}}
        return result


def default_to_resource_strict(converted, helper, to_aim=True):
    if to_aim:
        return default_to_resource(converted, helper, to_aim=to_aim)
    else:
        # Only include explicitly mentioned attributes
        values = {}
        for k, v in helper.get('exceptions', {}).iteritems():
            attr = v.get('other') or k
            skip_if_empty = v.get('skip_if_empty', False)
            conv_value = converted.get(attr)
            if conv_value or (conv_value is not None and not skip_if_empty):
                values[attr] = conv_value
        if values:
            values['dn'] = converted['dn']
            return {helper['resource']: {'attributes': values}}


def no_op_to_resource(converted, helper, to_aim=True):
    # to aim -> same as default_to_resource
    # to aci -> keep only DN
    if to_aim:
        return default_to_resource(converted, helper, to_aim=to_aim)
    else:
        return {helper['resource']: {'attributes': {'dn': converted['dn']}}}


def default_identity_converter(object_dict, otype, helper,
                               extra_attributes=None, aci_mo_type=None,
                               to_aim=True):
    """Default identity converter

    This converter uses the DN and splits it in its fundamental parts to
    retrieve the identity names.

    :param object_dict: dictionarty of the resource to be converted
    :param otype: Type of the object. Can be an AIM resource class or a
                  APIC class name.
    :param extra_attributes: Ordered list of additional attribute values needed
                             to create the identity attribute
    :param aci_mo_type: ACI ManagedObjectType to use when creating ACI identity
                        attribute
    :param to_aim: Boolean indicating whether we are converting
                   ACI/AIM (True) or AIM/ACI (False)
    :return: list with exactly all the attributes that need to be assigned
    to the resource class 'identity_attributes'
    """
    if to_aim:
        dn_mgr = apic_client.DNManager()
        aci_type = aci_mo_type or otype
        mos_and_rns = dn_mgr.aci_decompose_with_type(object_dict['dn'],
                                                     aci_type)
        return dn_mgr.filter_rns(mos_and_rns)
    else:
        attr = [object_dict[x] for x in otype.identity_attributes]
        if extra_attributes:
            attr.extend(extra_attributes)
        mo_type = aci_mo_type or helper['resource']
        try:
            return [apic_client.ManagedObjectClass(mo_type).dn(*attr)]
        except Exception as e:
            LOG.error('Failed to make DN for %s with %s: %s',
                      mo_type, attr, e)
            raise


def do_attribute_conversion(input_dict, input_attr, mapping_info, to_aim=True):
    """Returns a dict of converted attribute-value pairs"""
    # Check if it is an exception
    if input_attr in mapping_info:
        other = mapping_info[input_attr].get(
            'other', convert_attribute(input_attr, to_aim=to_aim))
        conv = (mapping_info[input_attr].get(
            'converter') or default_attribute_converter)
        converted = conv(input_dict, input_attr, to_aim=to_aim)
    else:
        # Transform in Other format
        other = convert_attribute(input_attr, to_aim=to_aim)
        converted = input_dict.get(input_attr)

    if isinstance(converted, dict):
        others = converted
    else:
        others = {other: converted}
    return others


def default_converter(object_dict, otype, helper,
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
            others = do_attribute_conversion(object_dict, attribute,
                                             helper.get('exceptions', {}),
                                             to_aim=to_aim)
            for other_k, other_v in others.iteritems():
                # Identity was already converted
                if other_k not in destination_identity_attributes:
                    res_dict[other_k] = other_v
        result = (helper.get('to_resource') or default_to_resource)(
            res_dict, helper, to_aim=to_aim)
        return [result] if result else []


def child_list(aim_attr, aci_attr, aci_mo=None):
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
            if object_dict.get(aci_attr):
                res_dict[aim_attr] = [object_dict[aci_attr]]
            result.append(default_to_resource(res_dict, helper, to_aim=True))
        else:
            aci_type = aci_mo or helper['resource']
            child_objs = object_dict[aim_attr]
            for c in child_objs:
                dn = id_conv(object_dict, otype, helper, extra_attributes=[c],
                             aci_mo_type=aci_type, to_aim=False)[0]
                result.append({aci_type: {'attributes':
                                          {'dn': dn, aci_attr: c}}})
        return result
    return func


def reverse_attribute_mapping_info(mapping_info, to_aim=True):
    result = {}
    for exception, value in mapping_info.iteritems():
        other_name = value.get(
            'other', convert_attribute(exception, to_aim=to_aim))
        result[other_name] = {'other': exception}
        if 'converter' in value:
            result[other_name]['converter'] = value['converter']
        if 'skip_if_empty' in value:
            result[other_name]['skip_if_empty'] = value['skip_if_empty']
    return result


def list_dict(aim_attr, mapping_info, id_attr, aci_mo=None, requires=None):
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
            rev_mapping_info = reverse_attribute_mapping_info(mapping_info,
                                                              to_aim=False)
            aim_list_item = {}
            for aci_attr in rev_mapping_info:
                if aci_attr in object_dict:
                    others = do_attribute_conversion(object_dict, aci_attr,
                                                     rev_mapping_info,
                                                     to_aim=True)
                    others.pop(IGNORE, None)
                    aim_list_item.update(others)
            if all(id_ in aim_list_item for id_ in id_attr):
                aim_list_item['_converter_id'] = tuple([aim_list_item[k] for k
                                                        in sorted(id_attr)])
            res_dict[aim_attr] = [aim_list_item]
            result.append(default_to_resource(res_dict, helper, to_aim=True))
        else:
            aci_type = aci_mo or helper['resource']
            req = requires or []
            for aim_list_item in object_dict[aim_attr]:
                aim_list_item = copy.copy(aim_list_item)
                if set(req) - set(aim_list_item.keys()):
                    continue
                # fill out the defaults
                for aim_d_a, map_info in mapping_info.iteritems():
                    if aim_d_a not in aim_list_item and 'default' in map_info:
                        aim_list_item[aim_d_a] = map_info['default']
                extra_attr = []
                for a in id_attr:
                    if a in aim_list_item:
                        conv = do_attribute_conversion(aim_list_item, a,
                                                       mapping_info,
                                                       to_aim=False)
                        if conv:
                            extra_attr.append(conv.values()[0])
                if len(extra_attr) == len(id_attr):
                    dn = id_conv(object_dict, otype, helper,
                                 extra_attributes=extra_attr,
                                 aci_mo_type=aci_type, to_aim=False)[0]
                    aci_obj = {'dn': dn}
                    for aim_d_a in mapping_info:
                        if aim_d_a in aim_list_item:
                            others = do_attribute_conversion(aim_list_item,
                                                             aim_d_a,
                                                             mapping_info,
                                                             to_aim=False)
                            others.pop(IGNORE, None)
                            aci_obj.update(others)
                    result.append({aci_type: {'attributes': aci_obj}})
        return result
    return func


def dn_decomposer(aim_attr_list, aci_mo):
    def func(object_dict, attribute, to_aim=True):
        if to_aim:
            dn = object_dict.get(attribute)
            if dn:
                dnm = apic_client.DNManager()
                mos_and_rns = dnm.aci_decompose_with_type(dn, aci_mo)
                rns = dnm.filter_rns(mos_and_rns)
                return dict(zip(aim_attr_list, rns))
            else:
                return {}
        else:
            dn_attrs = [object_dict[a] for a in aim_attr_list
                        if object_dict.get(a)]
            if len(dn_attrs) == len(aim_attr_list):
                dn = apic_client.ManagedObjectClass(aci_mo).dn(*dn_attrs)
            else:
                dn = ''
            return dn
    return func
