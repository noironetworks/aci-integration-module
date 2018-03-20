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

import base64
import collections
import datetime
from hashlib import md5

from oslo_config import cfg
from oslo_log import log as logging

from aim.api import types as t
from aim.common import utils
from aim import exceptions as exc

# TODO(amitbose) Move ManagedObjectClass definitions to AIM
from apicapi import apic_client


LOG = logging.getLogger(__name__)


class ResourceBase(object):
    """Base class for AIM resource.

    Class property 'identity_attributes' gives a list of resource
    attributes that uniquely identify the resource. The values of
    these attributes directly determines the corresponding ACI
    object identifier (DN). These attributes must always be specified.
    Class property 'other_attributes' gives a list of additional
    resource attributes that are defined on the resource.
    Class property 'db_attributes' gives a list of resource attributes
    that are managed by the database layer, eg: timestamp, incremental counter.
    """

    db_attributes = t.db()

    def __init__(self, defaults, **kwargs):
        unset_attr = [k for k in self.identity_attributes
                      if kwargs.get(k) is None and k not in defaults]
        if 'display_name' in self.other_attributes:
            defaults.setdefault('display_name', '')
        if unset_attr:
            raise exc.IdentityAttributesMissing(klass=type(self).__name__,
                                                attr=unset_attr)
        if kwargs.pop('_set_default', True):
            for k, v in defaults.iteritems():
                setattr(self, k, v)
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    @property
    def identity(self):
        return [str(getattr(self, x)) for x in self.identity_attributes.keys()]

    @classmethod
    def attributes(cls):
        return (cls.identity_attributes.keys() + cls.other_attributes.keys() +
                cls.db_attributes.keys())

    @property
    def members(self):
        return {x: self.__dict__[x] for x in self.attributes() +
                ['pe_existing', '_error', '_pending'] if x in self.__dict__}

    @property
    def hash(self):
        parts = collections.OrderedDict()
        parts.update(self.members)
        return int(md5(base64.b64encode(
            '|'.join(['%s=%s' % (x, y)
                      for x, y in parts.iteritems()]))).hexdigest(), 16)

    def __str__(self):
        return '%s(%s)' % (type(self).__name__, ','.join(self.identity))

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __repr__(self):
        return '%s(%s)' % (super(ResourceBase, self).__repr__(), self.members)


class AciResourceBase(ResourceBase):
    """Base class for AIM resources that map to ACI objects.

    Child classes must define the following class attributes:
    * _tree_parent: Type of parent class in ACI tree structure
    * _aci_mo_name: ManagedObjectClass name of corresponding ACI object
    """

    UNSPECIFIED = t.UNSPECIFIED

    def __init__(self, defaults, **kwargs):
        cls = type(self)
        for ra in ['_tree_parent', '_aci_mo_name']:
            if not hasattr(cls, ra):
                raise exc.AciResourceDefinitionError(attr=ra, klass=cls)
        super(AciResourceBase, self).__init__(defaults, **kwargs)

    @property
    def dn(self):
        return apic_client.ManagedObjectClass(self._aci_mo_name).dn(
            *self.identity)

    @property
    def rn(self):
        mo = apic_client.ManagedObjectClass(self._aci_mo_name)
        if mo.rn_param_count > 0:
            return mo.rn(*self.identity[-mo.rn_param_count:])
        else:
            return mo.rn()

    @classmethod
    def from_dn(cls, dn):
        dn_mgr = apic_client.DNManager()
        try:
            mos_and_rns = dn_mgr.aci_decompose_with_type(dn, cls._aci_mo_name)
            rns = dn_mgr.filter_rns(mos_and_rns)
            if len(rns) < len(cls.identity_attributes):
                raise exc.InvalidDNForAciResource(dn=dn, cls=cls)
            attr = {p[0]: p[1] for p in zip(cls.identity_attributes, rns)}
            return cls(**attr)
        except apic_client.DNManager.InvalidNameFormat:
            raise exc.InvalidDNForAciResource(dn=dn, cls=cls)

    @property
    def root(self):
        mos_and_types = utils.decompose_dn(self._aci_mo_name, self.dn)
        mo = apic_client.ManagedObjectClass(mos_and_types[0][0])
        if mo.rn_param_count > 0:
            return mo.rn(mos_and_types[0][1])
        else:
            return mo.rn()

    @classmethod
    def root_ref_attribute(cls):
        return cls.identity_attributes.keys()[0]


class AciRoot(AciResourceBase):

    @property
    def root(self):
        return self.rn


class Tenant(AciRoot):
    """Resource representing a Tenant in ACI.

    Identity attribute is RN for ACI tenant.
    """

    identity_attributes = t.identity(
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('monitored', t.bool),
        ('descr', t.string()))

    _aci_mo_name = 'fvTenant'
    _tree_parent = None

    def __init__(self, **kwargs):
        super(Tenant, self).__init__({'monitored': False, 'descr': ''},
                                     **kwargs)


class BridgeDomain(AciResourceBase):
    """Resource representing a BridgeDomain in ACI.

    Identity attributes are RNs for ACI tenant and bridge-domain.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('vrf_name', t.name),
        ('enable_arp_flood', t.bool),
        ('enable_routing', t.bool),
        ('limit_ip_learn_to_subnets', t.bool),
        ('ip_learning', t.bool),
        ('l2_unknown_unicast_mode', t.enum("", "flood", "proxy")),
        ('ep_move_detect_mode', t.enum("", "garp")),
        ('l3out_names', t.list_of_names),
        ('monitored', t.bool))

    _aci_mo_name = 'fvBD'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(BridgeDomain, self).__init__({'vrf_name': '',
                                            'enable_arp_flood': True,
                                            'enable_routing': True,
                                            'limit_ip_learn_to_subnets': False,
                                            'ip_learning': True,
                                            'l2_unknown_unicast_mode': 'proxy',
                                            'ep_move_detect_mode': 'garp',
                                            'l3out_names': [],
                                            'monitored': False},
                                           **kwargs)


class Agent(ResourceBase):
    """Resource representing an AIM Agent"""

    identity_attributes = t.identity(('id', t.id))
    other_attributes = t.other(
        ('agent_type', t.string(255)),
        ('host', t.string(255)),
        ('binary_file', t.string(255)),
        ('admin_state_up', t.bool),
        ('description', t.string(255)),
        ('hash_trees', t.list_of_ids),
        ('beat_count', t.number),
        ('version', t.string()))
    # Attrbutes completely managed by the DB (eg. timestamps)
    db_attributes = t.db(('heartbeat_timestamp', t.string()))

    def __init__(self, **kwargs):
        super(Agent, self).__init__({'admin_state_up': True,
                                     'beat_count': 0,
                                     'id': utils.generate_uuid()}, **kwargs)

    def __eq__(self, other):
        return self.id == other.id

    def is_down(self, context):
        current = context.store.current_timestamp
        # When the store doesn't support timestamps the agent can never
        # be considered down.
        if current is None:
            return False
        result = current - self.heartbeat_timestamp >= datetime.timedelta(
            seconds=cfg.CONF.aim.agent_down_time)
        if result:
            LOG.warn("Agent %s is down. Last heartbeat was %s" %
                     (self.id, self.heartbeat_timestamp))
        else:
            LOG.debug("Agent %s is alive, its last heartbeat was %s" %
                      (self.id, self.heartbeat_timestamp))
        return result

    def down_time(self, context):
        if self.is_down(context):
            current = context.store.current_timestamp
            return (current - self.heartbeat_timestamp).seconds


class Subnet(AciResourceBase):
    """Resource representing a Subnet in ACI.

    Identity attributes: name of ACI tenant, name of bridge-domain and
    IP-address & mask of the default gateway in CIDR format (that is
    <gateway-address>/<prefix-len>). Helper function 'to_gw_ip_mask'
    may be used to construct the IP-address & mask value.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('bd_name', t.name),
        ('gw_ip_mask', t.ip_cidr))
    other_attributes = t.other(
        ('scope', t.enum("", "public", "private", "shared")),
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'fvSubnet'
    _tree_parent = BridgeDomain

    SCOPE_PRIVATE = 'private'
    SCOPE_PUBLIC = 'public'

    def __init__(self, **kwargs):
        super(Subnet, self).__init__({'scope': self.SCOPE_PUBLIC,
                                      'monitored': False}, **kwargs)

    @staticmethod
    def to_gw_ip_mask(gateway_ip_address, prefix_len):
        return '%s/%d' % (gateway_ip_address, prefix_len)


class VRF(AciResourceBase):
    """Resource representing a VRF (Layer3 network context) in ACI.

    Identity attributes: name of ACI tenant, name of VRF.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('policy_enforcement_pref', t.enum("", "enforced", "unenforced")),
        ('monitored', t.bool))

    _aci_mo_name = 'fvCtx'
    _tree_parent = Tenant

    POLICY_ENFORCED = 'enforced'
    POLICY_UNENFORCED = 'unenforced'

    def __init__(self, **kwargs):
        super(VRF, self).__init__(
            {'policy_enforcement_pref': self.POLICY_ENFORCED,
             'monitored': False},
            **kwargs)


class ApplicationProfile(AciResourceBase):
    """Resource representing an application-profile in ACI.

    Identity attributes: name of ACI tenant, name of app-profile.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'fvAp'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(ApplicationProfile, self).__init__({'monitored': False},
                                                 **kwargs)


class EndpointGroup(AciResourceBase):
    """Resource representing an endpoint-group in ACI.

    Identity attributes: name of ACI tenant, name of application-profile
    and name of endpoint-group.

    Attribute 'static_paths' is a list of dicts with the following keys:
    * path: (Required) path-name of the switch-port which is bound to
            EndpointGroup
    * encap: (Required) encapsulation mode and identifier for
            this EndpointGroup on the specified switch-port. Must be specified
            in the format 'vlan-<vlan-id>' for VLAN encapsulation
    """
    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('app_profile_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('bd_name', t.name),
        ('policy_enforcement_pref', t.enum("", "enfFAorced", "unenforced")),
        ('provided_contract_names', t.list_of_names),
        ('consumed_contract_names', t.list_of_names),
        ('openstack_vmm_domain_names', t.list_of_names),
        ('physical_domain_names', t.list_of_names),
        ('vmm_domains', t.list_of_dicts(('type', t.name), ('name', t.name))),
        ('physical_domains', t.list_of_dicts(('name', t.name))),
        ('static_paths', t.list_of_static_paths),
        ('epg_contract_masters', t.list_of_dicts(('app_profile_name', t.name),
                                                 ('name', t.name))),
        ('monitored', t.bool),
        ('sync', t.bool))

    _aci_mo_name = 'fvAEPg'
    _tree_parent = ApplicationProfile

    POLICY_UNENFORCED = 'unenforced'
    POLICY_ENFORCED = 'enforced'

    def __init__(self, **kwargs):
        super(EndpointGroup, self).__init__({'bd_name': '',
                                             'provided_contract_names': [],
                                             'consumed_contract_names': [],
                                             'openstack_vmm_domain_names': [],
                                             'physical_domain_names': [],
                                             'vmm_domains': [],
                                             'physical_domains': [],
                                             'policy_enforcement_pref':
                                             self.POLICY_UNENFORCED,
                                             'static_paths': [],
                                             'epg_contract_masters': [],
                                             'monitored': False,
                                             'sync': True},
                                            **kwargs)


class Filter(AciResourceBase):
    """Resource representing a contract filter in ACI.

    Identity attributes: name of ACI tenant and name of filter.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'vzFilter'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(Filter, self).__init__({'monitored': False}, **kwargs)


class FilterEntry(AciResourceBase):
    """Resource representing a classifier entry of a filter in ACI.

    Identity attributes: name of ACI tenant, name of filter and name of entry.

    Values for classification fields may be integers as per standards
    (e.g. ip_protocol = 6 for TCP, 17 for UDP), or special strings listed
    below. UNSPECIFIED may be used to indicate that a particular
    field should be ignored.

    Field             | Special string values
    --------------------------------------------------------------------------
    arp_opcode        | req, reply
    ether_type        | trill, arp, mpls_ucast, mac_security, fcoe, ip
    ip_protocol       | icmp, igmp, tcp, egp, igp, udp, icmpv6, eigrp, ospfigp
    icmpv4_type       | echo-rep, dst-unreach, src-quench, echo, time-exceeded
    icmpv6_type       | dst-unreach, time-exceeded, echo-req, echo-rep,
                      | nbr-solicit, nbr-advert, redirect
    source_from_port, | ftpData, smtp, dns, http, pop3, https, rtsp
    source_to_port,   |
    dest_from_port,   |
    dest_to_port      |
    tcp_flags         | est, syn, ack, fin, rst

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('filter_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('arp_opcode', t.string()),
        ('ether_type', t.string()),
        ('ip_protocol', t.string()),
        ('icmpv4_type', t.string()),
        ('icmpv6_type', t.string()),
        ('source_from_port', t.port),
        ('source_to_port', t.port),
        ('dest_from_port', t.port),
        ('dest_to_port', t.port),
        ('tcp_flags', t.string()),
        ('stateful', t.bool),
        ('fragment_only', t.bool),
        ('monitored', t.bool))

    _aci_mo_name = 'vzEntry'
    _tree_parent = Filter

    def __init__(self, **kwargs):
        super(FilterEntry, self).__init__(
            {'arp_opcode': self.UNSPECIFIED,
             'ether_type': self.UNSPECIFIED,
             'ip_protocol': self.UNSPECIFIED,
             'icmpv4_type': self.UNSPECIFIED,
             'icmpv6_type': self.UNSPECIFIED,
             'source_from_port': self.UNSPECIFIED,
             'source_to_port': self.UNSPECIFIED,
             'dest_from_port': self.UNSPECIFIED,
             'dest_to_port': self.UNSPECIFIED,
             'tcp_flags': self.UNSPECIFIED,
             'stateful': False,
             'fragment_only': False,
             'monitored': False},
            **kwargs)


class Contract(AciResourceBase):
    """Resource representing a contract in ACI.

    Identity attributes: name of ACI tenant and name of contract.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('scope', t.enum("", "tenant", "context", "global",
                         "application-profile")),
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'vzBrCP'
    _tree_parent = Tenant

    SCOPE_APP_PROFILE = 'application-profile'
    SCOPE_TENANT = 'tenant'
    SCOPE_CONTEXT = 'context'
    SCOPE_GLOBAL = 'global'

    def __init__(self, **kwargs):
        super(Contract, self).__init__({'scope': self.SCOPE_CONTEXT,
                                        'monitored': False}, **kwargs)


class ContractSubject(AciResourceBase):
    """Resource representing a subject within a contract in ACI.

    Identity attributes: name of ACI tenant, name of contract and
    name of subject.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('contract_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('in_filters', t.list_of_names),
        ('out_filters', t.list_of_names),
        ('bi_filters', t.list_of_names),
        ('service_graph_name', t.name),
        ('in_service_graph_name', t.name),
        ('out_service_graph_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'vzSubj'
    _tree_parent = Contract

    def __init__(self, **kwargs):
        super(ContractSubject, self).__init__(
            {'in_filters': [], 'out_filters': [], 'bi_filters': [],
             'service_graph_name': '',
             'in_service_graph_name': '',
             'out_service_graph_name': '',
             'monitored': False}, **kwargs)


class Endpoint(ResourceBase):
    """Resource representing an endpoint.

    Identity attribute: UUID of the endpoint.
    """

    identity_attributes = t.identity(
        ('uuid', t.id))
    other_attributes = t.other(
        ('display_name', t.name),
        ('epg_tenant_name', t.name),
        ('epg_app_profile_name', t.name),
        ('epg_name', t.name))

    def __init__(self, **kwargs):
        super(Endpoint, self).__init__({'epg_name': None,
                                        'epg_tenant_name': None,
                                        'epg_app_profile_name': None},
                                       **kwargs)


class VMMPolicy(AciRoot):

    identity_attributes = t.identity(
        ('type', t.enum("VMWare", "OpenStack", "Kubernetes")))
    other_attributes = t.other(
        ('monitored', t.bool),
        ('display_name', t.name))

    _aci_mo_name = 'vmmProvP'
    _tree_parent = None

    def __init__(self, **kwargs):
        super(VMMPolicy, self).__init__({'monitored': False}, **kwargs)


class VMMDomain(AciResourceBase):
    """Resource representing a VMM domain.

    Identity attributes: VMM type (eg. Openstack) and name
    """

    identity_attributes = t.identity(
        ('type', t.enum("VMWare", "OpenStack", "Kubernetes")),
        ('name', t.name))
    other_attributes = t.other(
        ('monitored', t.bool),
        ('display_name', t.name),
        ('enforcement_pref', t.enum('sw', 'hw', 'unknown')),
        ('mode', t.enum('default', 'n1kv', 'unknown', 'ovs', 'k8s')),
        ('mcast_address', t.string()),
        ('encap_mode', t.enum('unknown', 'vlan', 'vxlan')),
        ('pref_encap_mode', t.enum('unspecified', 'vlan', 'vxlan')),
        ('vlan_pool_name', t.name),
        ('vlan_pool_type', t.enum('static', 'dynamic')),
        ('mcast_addr_pool_name', t.name))

    _aci_mo_name = 'vmmDomP'
    _tree_parent = VMMPolicy

    def __init__(self, **kwargs):
        defaults = {'monitored': False,
                    'enforcement_pref': 'hw',
                    'mode': 'default',
                    'mcast_address': '0.0.0.0',
                    'encap_mode': 'unknown',
                    'pref_encap_mode': 'unspecified',
                    'vlan_pool_name': '',
                    'vlan_pool_type': 'dynamic',
                    'mcast_addr_pool_name': ''}
        vmm_type = kwargs.get('type')
        if vmm_type == 'Kubernetes':
            defaults['enforcement_pref'] = 'sw'
            defaults['mode'] = 'k8s'
        elif vmm_type == 'OpenStack':
            defaults['enforcement_pref'] = 'sw'
            defaults['mode'] = 'ovs'
        if kwargs.get('encap_mode') and kwargs['encap_mode'] != 'unknown':
            defaults['pref_encap_mode'] = kwargs['encap_mode']
        super(VMMDomain, self).__init__(defaults, **kwargs)


class PhysicalDomain(AciRoot):
    """Resource representing a Physical domain.

    Identity attributes: name
    """

    identity_attributes = t.identity(
        ('name', t.name))
    other_attributes = t.other(
        ('monitored', t.bool),
        ('display_name', t.name))

    _aci_mo_name = 'physDomP'
    _tree_parent = None

    def __init__(self, **kwargs):
        super(PhysicalDomain, self).__init__({'monitored': False}, **kwargs)


class L3Outside(AciResourceBase):
    """Resource representing an L3 Outside.

    Identity attributes: name of ACI tenant, name of L3Out.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('vrf_name', t.name),
        ('l3_domain_dn', t.string()),
        ('bgp_enable', t.bool),
        ('monitored', t.bool))

    _aci_mo_name = 'l3extOut'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(L3Outside, self).__init__(
            {'vrf_name': '', 'l3_domain_dn': '',
             'bgp_enable': False,
             'monitored': False}, **kwargs)


class L3OutNodeProfile(AciResourceBase):
    """Resource representing a logical node profile.

    Identity attributes: name of ACI tenant, name of L3Out, name of node
    profile.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('l3out_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'l3extLNodeP'
    _tree_parent = L3Outside

    def __init__(self, **kwargs):
        super(L3OutNodeProfile, self).__init__(
            {'monitored': False}, **kwargs)


class L3OutNode(AciResourceBase):
    """Resource representing a logical node.

    Identity attributes: name of ACI tenant, name of L3Out, name of node
    profile, node_path of the node.
    """
    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('l3out_name', t.name),
        ('node_profile_name', t.name),
        ('node_path', t.string()))
    other_attributes = t.other(
        ('router_id', t.ipv4),
        ('router_id_loopback', t.bool),
        ('monitored', t.bool))

    _aci_mo_name = 'l3extRsNodeL3OutAtt'
    _tree_parent = L3OutNodeProfile

    def __init__(self, **kwargs):
        super(L3OutNode, self).__init__(
            {'router_id': '', 'router_id_loopback': True,
             'monitored': False}, **kwargs)


class L3OutStaticRoute(AciResourceBase):
    """Resource representing a static route.

    Identity attributes: name of ACI tenant, name of L3Out, name of node
    profile, node_path of the node, cidr of the static route.
    """
    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('l3out_name', t.name),
        ('node_profile_name', t.name),
        ('node_path', t.string()),
        ('cidr', t.ip_cidr))
    other_attributes = t.other(
        ('next_hop_list', t.list_of_next_hop),
        ('preference', t.string()),
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'ipRouteP'
    _tree_parent = L3OutNode

    def __init__(self, **kwargs):
        super(L3OutStaticRoute, self).__init__(
            {'next_hop_list': [], 'preference': '1',
             'monitored': False}, **kwargs)


class L3OutInterfaceProfile(AciResourceBase):
    """Resource representing a logical interface profile.

    Identity attributes: name of ACI tenant, name of L3Out, name of node
    profile, name of interface profile.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('l3out_name', t.name),
        ('node_profile_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'l3extLIfP'
    _tree_parent = L3OutNodeProfile

    def __init__(self, **kwargs):
        super(L3OutInterfaceProfile, self).__init__(
            {'monitored': False}, **kwargs)


class L3OutInterface(AciResourceBase):
    """Resource representing a logical interface.

    Identity attributes: name of ACI tenant, name of L3Out, name of node
    profile, name of interface profile, interface_path.
    """
    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('l3out_name', t.name),
        ('node_profile_name', t.name),
        ('interface_profile_name', t.name),
        ('interface_path', t.string()))
    other_attributes = t.other(
        ('primary_addr_a', t.ip_cidr),
        ('secondary_addr_a_list', t.list_of_ip_cidr_obj),
        ('primary_addr_b', t.ip_cidr),
        ('secondary_addr_b_list', t.list_of_ip_cidr_obj),
        ('encap', t.string()),
        ('host', t.string()),
        ('type', t.enum("ext-svi")),
        ('monitored', t.bool))

    _aci_mo_name = 'l3extRsPathL3OutAtt'
    _tree_parent = L3OutInterfaceProfile

    def __init__(self, **kwargs):
        super(L3OutInterface, self).__init__(
            {'primary_addr_a': '', 'secondary_addr_a_list': [],
             'primary_addr_b': '', 'secondary_addr_b_list': [],
             'encap': '', 'type': 'ext-svi',
             'monitored': False, 'host': ''}, **kwargs)


class L3OutInterfaceBgpPeerP(AciResourceBase):
    """Resource representing a bgp peer prefix.

    Identity attributes: name of ACI tenant, name of L3Out, name of node
    profile, name of interface profile, interface_path, bgp peer prefix.
    """
    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('l3out_name', t.name),
        ('node_profile_name', t.name),
        ('interface_profile_name', t.name),
        ('interface_path', t.string()),
        ('addr', t.ip_cidr))
    other_attributes = t.other(
        ('asn', t.string()),
        ('monitored', t.bool))

    _aci_mo_name = 'bgpPeerP'
    _tree_parent = L3OutInterface

    def __init__(self, **kwargs):
        super(L3OutInterfaceBgpPeerP, self).__init__(
            {'asn': "0", 'monitored': False}, **kwargs)


class ExternalNetwork(AciResourceBase):
    """Resource representing an external network instance profile.

    External network is a group of external subnets that have the same
    security behavior.

    Identity attributes: name of ACI tenant, name of L3Out, name of external
    network.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('l3out_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('nat_epg_dn', t.string()),
        ('provided_contract_names', t.list_of_names),
        ('consumed_contract_names', t.list_of_names),
        ('monitored', t.bool))

    _aci_mo_name = 'l3extInstP'
    _tree_parent = L3Outside

    def __init__(self, **kwargs):
        super(ExternalNetwork, self).__init__(
            {'nat_epg_dn': '',
             'provided_contract_names': [], 'consumed_contract_names': [],
             'monitored': False},
            **kwargs)


class ExternalSubnet(AciResourceBase):
    """Resource representing an external subnet.

    Identity attributes: name of ACI tenant, name of L3Out, name of external
    network, network CIDR of the subnet.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('l3out_name', t.name),
        ('external_network_name', t.name),
        ('cidr', t.ip_cidr))
    other_attributes = t.other(
        ('display_name', t.name),
        ('aggregate', t.string()),
        ('scope', t.string()),
        ('monitored', t.bool))

    _aci_mo_name = 'l3extSubnet'
    _tree_parent = ExternalNetwork

    def __init__(self, **kwargs):
        super(ExternalSubnet, self).__init__({'monitored': False,
                                              'aggregate': "",
                                              'scope': "import-security"},
                                             **kwargs)


class SecurityGroup(AciResourceBase):
    """Resource representing a Security Group in ACI.

    Identity attributes: name of ACI tenant and name of security group
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'hostprotPol'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(SecurityGroup, self).__init__({'monitored': False}, **kwargs)


class SecurityGroupSubject(AciResourceBase):
    """Resource representing a subject within a security group in ACI.

    Identity attributes: name of ACI tenant, name of security group and
    name of subject.
    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('security_group_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'hostprotSubj'
    _tree_parent = SecurityGroup

    def __init__(self, **kwargs):
        super(SecurityGroupSubject, self).__init__({'monitored': False},
                                                   **kwargs)


class SecurityGroupRule(AciResourceBase):
    """Resource representing a SG subject's rule in ACI.

    Identity attributes: name of ACI tenant, name of security group, name of
    subject and name of rule
    """
    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('security_group_name', t.name),
        ('security_group_subject_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('direction', t.enum("", "ingress", "egress")),
        ('ethertype', t.enum("", "undefined", "ipv4", "ipv6")),
        ('remote_ips', t.list_of_strings),
        ('ip_protocol', t.string()),
        ('from_port', t.port),
        ('to_port', t.port),
        ('conn_track', t.enum('normal', 'reflexive')),
        ('monitored', t.bool))

    _aci_mo_name = 'hostprotRule'
    _tree_parent = SecurityGroupSubject

    def __init__(self, **kwargs):
        super(SecurityGroupRule, self).__init__(
            {'direction': 'ingress',
             'ethertype': "undefined",
             'remote_ips': [],
             'ip_protocol': self.UNSPECIFIED,
             'from_port': self.UNSPECIFIED,
             'to_port': self.UNSPECIFIED,
             'conn_track': 'reflexive',
             'monitored': False}, **kwargs)


class Configuration(ResourceBase):

    identity_attributes = t.identity(
        ('key', t.string(52)),
        ('host', t.string(52)),
        ('group', t.string(52))
    )
    other_attributes = t.other(('value', t.string(512)))
    db_attributes = t.db(('version', t.string(36)))

    def __init__(self, **kwargs):
        super(Configuration, self).__init__({}, **kwargs)


class Topology(AciRoot):
    identity_attributes = t.identity()
    other_attributes = t.other(
        ('name', t.name))

    _aci_mo_name = 'fabricTopology'
    _tree_parent = None

    def __init__(self, **kwargs):
        super(Topology, self).__init__({}, name='topology', monitored=True)


class Pod(AciResourceBase):

    root = 'topology'

    identity_attributes = t.identity(
        ('name', t.name))
    other_attributes = t.other(
        ('monitored', t.bool))

    _aci_mo_name = 'fabricPod'
    _tree_parent = Topology

    def __init__(self, **kwargs):
        super(Pod, self).__init__({'monitored': False}, **kwargs)


class VMMController(AciResourceBase):
    """Resource representing a VMM controller profile in ACI.

    Identity attributes: VMM domain type, VMM domain name, controller name.
    """
    identity_attributes = t.identity(
        ('domain_type', t.name),
        ('domain_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('scope', t.enum('unmanaged', 'vm', 'iaas', 'network',
                         'MicrosoftSCVMM', 'openstack', 'kubernetes')),
        ('root_cont_name', t.name),
        ('host_or_ip', t.name),
        ('mode', t.enum('default', 'n1kv', 'unknown', 'ovs', 'k8s')),
        ('monitored', t.bool))

    _aci_mo_name = 'vmmCtrlrP'
    _tree_parent = VMMDomain

    def __init__(self, **kwargs):
        defaults = {'monitored': False,
                    'scope': 'vm',
                    'root_cont_name': '',
                    'host_or_ip': '',
                    'mode': 'default'}
        vmm_type = kwargs.get('domain_type')
        if vmm_type == 'Kubernetes':
            defaults['scope'] = 'kubernetes'
            defaults['mode'] = 'k8s'
        elif vmm_type == 'OpenStack':
            defaults['scope'] = 'openstack'
            defaults['mode'] = 'ovs'
        name = kwargs.get('name')
        if name:
            defaults['root_cont_name'] = name
            defaults['host_or_ip'] = name
        super(VMMController, self).__init__(defaults, **kwargs)


class VmmInjectedNamespace(AciResourceBase):
    """Resource representing a VMM injected namespace in ACI.

    Identity attributes: VMM domain type, VMM domain name, controller name,
    and namespace name.
    """
    identity_attributes = t.identity(
        ('domain_type', t.name),
        ('domain_name', t.name),
        ('controller_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name))

    _aci_mo_name = 'vmmInjectedNs'
    _tree_parent = VMMController

    def __init__(self, **kwargs):
        super(VmmInjectedNamespace, self).__init__({}, **kwargs)


class VmmInjectedDeployment(AciResourceBase):
    """Resource representing a VMM injected deployment in ACI.

    Identity attributes: VMM domain type, VMM domain name, controller name,
    namespace name and deployment name.
    """
    identity_attributes = t.identity(
        ('domain_type', t.name),
        ('domain_name', t.name),
        ('controller_name', t.name),
        ('namespace_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('replicas', t.integer))
    db_attributes = t.db(('guid', t.string()))

    _aci_mo_name = 'vmmInjectedDepl'
    _tree_parent = VmmInjectedNamespace

    def __init__(self, **kwargs):
        super(VmmInjectedDeployment, self).__init__({'replicas': 0,
                                                     'guid': ''},
                                                    **kwargs)


class VmmInjectedReplicaSet(AciResourceBase):
    """Resource representing a VMM injected replica-set in ACI.

    Identity attributes: VMM domain type, VMM domain name, controller name,
    namespace name, deployment name and replica-set name.
    """
    identity_attributes = t.identity(
        ('domain_type', t.name),
        ('domain_name', t.name),
        ('controller_name', t.name),
        ('namespace_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('deployment_name', t.name))
    db_attributes = t.db(('guid', t.string()))

    _aci_mo_name = 'vmmInjectedReplSet'
    _tree_parent = VmmInjectedNamespace

    def __init__(self, **kwargs):
        super(VmmInjectedReplicaSet, self).__init__({'deployment_name': '',
                                                     'guid': ''},
                                                    **kwargs)


class VmmInjectedService(AciResourceBase):
    """Resource representing a VMM injected service in ACI.

    Identity attributes: VMM domain type, VMM domain name, controller name,
    namespace name and service name.
    """
    identity_attributes = t.identity(
        ('domain_type', t.name),
        ('domain_name', t.name),
        ('controller_name', t.name),
        ('namespace_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('service_type', t.enum('clusterIp', 'externalName', 'nodePort',
                                'loadBalancer')),
        ('cluster_ip', t.string()),
        ('load_balancer_ip', t.string()),
        ('service_ports', t.list_of_dicts(('port', t.ports),
                                          ('protocol', t.string(32)),
                                          ('target_port', t.string(32)),
                                          ('node_port', t.ports))),
        ('endpoints', t.list_of_dicts(('ip', t.string()),
                                      ('pod_name', t.name))))
    db_attributes = t.db(('guid', t.string()))

    _aci_mo_name = 'vmmInjectedSvc'
    _tree_parent = VmmInjectedNamespace

    def __init__(self, **kwargs):
        super(VmmInjectedService, self).__init__(
            {'service_type': 'clusterIp',
             'cluster_ip': '0.0.0.0',
             'load_balancer_ip': '0.0.0.0',
             'service_ports': [],
             'endpoints': [],
             'guid': ''},
            **kwargs)


class VmmInjectedHost(AciResourceBase):
    """Resource representing a VMM injected host in ACI.

    Identity attributes: VMM domain type, VMM domain name, controller name
    and host name.
    """
    identity_attributes = t.identity(
        ('domain_type', t.name),
        ('domain_name', t.name),
        ('controller_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('host_name', t.string()),
        ('kernel_version', t.string()),
        ('os', t.string()))

    _aci_mo_name = 'vmmInjectedHost'
    _tree_parent = VMMController

    def __init__(self, **kwargs):
        super(VmmInjectedHost, self).__init__({'host_name': '',
                                               'kernel_version': '',
                                               'os': ''},
                                              **kwargs)


class VmmInjectedContGroup(AciResourceBase):
    """Resource representing a VMM injected container group in ACI.

    Identity attributes: VMM domain type, VMM domain name, controller name,
    namespace name and group name.
    """
    identity_attributes = t.identity(
        ('domain_type', t.name),
        ('domain_name', t.name),
        ('controller_name', t.name),
        ('namespace_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('host_name', t.name),
        ('compute_node_name', t.name),
        ('replica_set_name', t.name))
    db_attributes = t.db(('guid', t.string()))

    _aci_mo_name = 'vmmInjectedContGrp'
    _tree_parent = VmmInjectedNamespace

    def __init__(self, **kwargs):
        super(VmmInjectedContGroup, self).__init__({'host_name': '',
                                                    'compute_node_name': '',
                                                    'replica_set_name': '',
                                                    'guid': ''},
                                                   **kwargs)
