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

import collections

# http://json-schema.org/draft-04/schema#

UNSPECIFIED = "unspecified"
tcp_flags = {UNSPECIFIED: ""}
ports = {'0': UNSPECIFIED, '20': 'ftpData', '25': 'smtp',
         '53': 'dns', '80': 'http', '110': 'pop3', '443': 'https',
         '554': 'rstp'}
arp_opcode = {'0': UNSPECIFIED, '1': 'req', '2': 'reply'}
ether_type = {
    '0': UNSPECIFIED, '0x22F3': 'trill', '0x806': 'arp',
    '0x8847': 'mpls_ucast', '0x88E5': 'mac_security', '0x8906': 'fcoe',
    '0xABCD': 'ip'}
icmpv4_type = {'0': 'echo-rep', '3': 'dst-unreach',
               '4': 'src-quench', '8': 'echo',
               '11': 'time-exceeded', '255': UNSPECIFIED}
icmpv4_code = {'0': 'no-code', '0xffff': UNSPECIFIED}

icmpv6_type = {'0': UNSPECIFIED, '1': 'dst-unreach', '3': 'time-exceeded',
               '128': 'echo-req', '129': 'echo-rep', '135': 'nbr-solicit',
               '136': 'nbr-advert', '137': 'redirect'}
icmpv6_code = {'0xffff': UNSPECIFIED}
ip_protocol = {'0': UNSPECIFIED, '1': 'icmp', '2': 'igmp', '6': 'tcp',
               '8': 'egp', '9': 'igp', '17': 'udp', '33': 'dccp',
               '43': 'ipv6-route', '44': 'ipv6-frag', '46': 'rsvp',
               '47': 'gre', '50': 'esp', '51': 'ah', '58': 'ipv6-icmp',
               '59': 'ipv6-nonxt', '88': 'eigrp', '89': 'ospf', '103': 'pim',
               '115': 'l2tp', '132': 'sctp', '136': 'udplite'}

ethertype = {'0': UNSPECIFIED, '1': 'ipv4', '2': 'ipv6'}
spmodes = {'0': 'regular', '1': 'native', '2': 'untagged'}


def identity(*identity_attributes):
    return collections.OrderedDict(identity_attributes)


def other(*other_attributes):
    return dict(other_attributes)


def db(*db_attributes):
    return dict(db_attributes)


def enum(*args):
    return {"type": "string", "enum": list(args)}


def string(length=None):
    s = {"type": "string"}
    if length is not None:
        s.update({"maxLength": length})
    return s


def list_of_dicts(*dict_keys_and_types):
    return {"type": "array",
            "items": {"type": "object",
                      "properties": dict(dict_keys_and_types)}}


bool = {"type": "boolean"}
integer = {"type": "integer"}
name = {"type": "string", "pattern": "^[a-zA-Z0-9_.:-]{0,63}$"}
list_of_names = {"type": "array", "items": name}
list_of_ids = {"type": "array", "items": string(36)}
list_of_strings = {"type": "array", "items": string()}
number = {"type": "number"}
positive_number = {"type": "number", "minimum": 0}
id = string(36)
ipv4 = {
    "type": "string",
    "pattern": "^([0-9]{1,3}\\.){3}[0-9]{1,3}$"}
ipv6 = {
    "type": "string",
    "pattern": "^s*((([0-9A-Fa-f]{1,4}:){7}([0-9A-Fa-f]{1,4}|:))|(([0-9A-Fa-f]"
               "{1,4}:){6}(:[0-9A-Fa-f]{1,4}|((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.("
               "25[0-5]|2[0-4]d|1dd|[1-9]?d)){3})|:))|(([0-9A-Fa-f]{1,4}:){5}("
               "((:[0-9A-Fa-f]{1,4}){1,2})|:((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.("
               "25[0-5]|2[0-4]d|1dd|[1-9]?d)){3})|:))|(([0-9A-Fa-f]{1,4}:){4}("
               "((:[0-9A-Fa-f]{1,4}){1,3})|((:[0-9A-Fa-f]{1,4})?:((25[0-5]|2[0"
               "-4]d|1dd|[1-9]?d)(.(25[0-5]|2[0-4]d|1dd|[1-9]?d)){3}))|:))|(("
               "[0-9A-Fa-f]{1,4}:){3}(((:[0-9A-Fa-f]{1,4}){1,4})|((:[0-9A-Fa-f"
               "]{1,4}){0,2}:((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.(25[0-5]|2[0-4]d|"
               "1dd|[1-9]?d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){2}(((:[0-9A-Fa-f]"
               "{1,4}){1,5})|((:[0-9A-Fa-f]{1,4}){0,3}:((25[0-5]|2[0-4]d|1dd|"
               "[1-9]?d)(.(25[0-5]|2[0-4]d|1dd|[1-9]?d)){3}))|:))|(([0-9A-Fa-f"
               "]{1,4}:){1}(((:[0-9A-Fa-f]{1,4}){1,6})|((:[0-9A-Fa-f]{1,4}){0,"
               "4}:((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.(25[0-5]|2[0-4]d|1dd|[1-9]?"
               "d)){3}))|:))|(:(((:[0-9A-Fa-f]{1,4}){1,7})|((:[0-9A-Fa-f]{1,4}"
               "){0,5}:((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.(25[0-5]|2[0-4]d|1dd|["
               "1-9]?d)){3}))|:)))(%.+)?s*$"}
ip = {"type": "string", "oneOf": [ipv4, ipv6]}
ipv4_cidr = {
    "type": "string",
    "pattern": "^([0-9]{1,3}\\.){3}[0-9]{1,3}(\/([0-9]|[1-2][0-9]|3[0-2]))?$"}
ipv6_cidr = {
    "type": "string",
    "pattern": "^s*((([0-9A-Fa-f]{1,4}:){7}([0-9A-Fa-f]{1,4}|:))|(([0-9A-Fa-f]"
               "{1,4}:){6}(:[0-9A-Fa-f]{1,4}|((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.("
               "25[0-5]|2[0-4]d|1dd|[1-9]?d)){3})|:))|(([0-9A-Fa-f]{1,4}:){5}("
               "((:[0-9A-Fa-f]{1,4}){1,2})|:((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.("
               "25[0-5]|2[0-4]d|1dd|[1-9]?d)){3})|:))|(([0-9A-Fa-f]{1,4}:){4}("
               "((:[0-9A-Fa-f]{1,4}){1,3})|((:[0-9A-Fa-f]{1,4})?:((25[0-5]|2[0"
               "-4]d|1dd|[1-9]?d)(.(25[0-5]|2[0-4]d|1dd|[1-9]?d)){3}))|:))|(("
               "[0-9A-Fa-f]{1,4}:){3}(((:[0-9A-Fa-f]{1,4}){1,4})|((:[0-9A-Fa-f"
               "]{1,4}){0,2}:((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.(25[0-5]|2[0-4]d|"
               "1dd|[1-9]?d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){2}(((:[0-9A-Fa-f]"
               "{1,4}){1,5})|((:[0-9A-Fa-f]{1,4}){0,3}:((25[0-5]|2[0-4]d|1dd|"
               "[1-9]?d)(.(25[0-5]|2[0-4]d|1dd|[1-9]?d)){3}))|:))|(([0-9A-Fa-f"
               "]{1,4}:){1}(((:[0-9A-Fa-f]{1,4}){1,6})|((:[0-9A-Fa-f]{1,4}){0,"
               "4}:((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.(25[0-5]|2[0-4]d|1dd|[1-9]?"
               "d)){3}))|:))|(:(((:[0-9A-Fa-f]{1,4}){1,7})|((:[0-9A-Fa-f]{1,4}"
               "){0,5}:((25[0-5]|2[0-4]d|1dd|[1-9]?d)(.(25[0-5]|2[0-4]d|1dd|["
               "1-9]?d)){3}))|:)))(%.+)?s*(\/([0-9]|[1-9][0-9]|1[0-1][0-9]|12"
               "[0-8]))?$"}
ip_cidr = {"type": "string", "oneOf": [ipv4_cidr, ipv6_cidr]}
port = {
    "type": "string",
    "oneOf": [enum(*ports.values()),
              {"type": "string",
               "pattern": "^([0-9]{1,4}|[1-5][0-9]{4}|6[0-4][0-9]{3}|"
                          "65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$"}]
}
mac_address = {
    "type": "string",
    "pattern": "^([0-9a-fA-F][0-9a-fA-F]:){5}([0-9a-fA-F][0-9a-fA-F])$"}
static_path = {
    "type": "object",
    "properties": {"encap": {"type": "string"},
                   "path": {"type": "string"},
                   "mode": {"type": "string",
                            "oneOf": [enum(*spmodes.values())]},
                   "host": {"type": "string"}}}
list_of_static_paths = {"type": "array", "items": static_path}
ip_cidr_obj = {
    "type": "object",
    "properties": {"addr": ip_cidr}}
list_of_ip_cidr_obj = {"type": "array", "items": ip_cidr_obj}
next_hop = {
    "type": "object",
    "properties": {"addr": ip,
                   "preference": {"type": "string"}}}
list_of_next_hop = {"type": "array", "items": next_hop}
epoch = integer
