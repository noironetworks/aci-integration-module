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

import datetime

from oslo_config import cfg
from oslo_log import log as logging
from sqlalchemy.sql.expression import func

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

    db_attributes = []

    def __init__(self, defaults, **kwargs):
        unset_attr = [k for k in self.identity_attributes
                      if kwargs.get(k) is None and k not in defaults]
        if unset_attr:
            raise exc.IdentityAttributesMissing(attr=unset_attr)
        if kwargs.pop('_set_default', True):
            for k, v in defaults.iteritems():
                setattr(self, k, v)
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    @property
    def identity(self):
        return [getattr(self, x) for x in self.identity_attributes]

    @classmethod
    def attributes(cls):
        return (cls.identity_attributes + cls.other_attributes +
                cls.db_attributes)

    def __str__(self):
        return '%s(%s)' % (type(self).__name__, ','.join(self.identity))

    def __eq__(self, other):
        return self.__dict__ == other.__dict__


class AciResourceBase(ResourceBase):
    """Base class for AIM resources that map to ACI objects.

    Child classes must define the following class attributes:
    * _tree_parent: Type of parent class in ACI tree structure
    * _aci_mo_name: ManagedObjectClass name of corresponding ACI object
    """

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

    @classmethod
    def from_dn(cls, dn):
        DNMgr = apic_client.DNManager
        try:
            rns = DNMgr().aci_decompose(dn, cls._aci_mo_name)
            if len(rns) < len(cls.identity_attributes):
                raise exc.InvalidDNForAciResource(dn=dn, cls=cls)
            attr = {p[0]: p[1] for p in zip(cls.identity_attributes, rns)}
            return cls(**attr)
        except DNMgr.InvalidNameFormat:
            raise exc.InvalidDNForAciResource(dn=dn, cls=cls)


class Tenant(AciResourceBase):
    """Resource representing a Tenant in ACI.

    Identity attribute is RN for ACI tenant.
    """

    identity_attributes = ['name']
    other_attributes = ['display_name', 'monitored']

    _aci_mo_name = 'fvTenant'
    _tree_parent = None

    def __init__(self, **kwargs):
        super(Tenant, self).__init__({'monitored': False}, **kwargs)


class BridgeDomain(AciResourceBase):
    """Resource representing a BridgeDomain in ACI.

    Identity attributes are RNs for ACI tenant and bridge-domain.
    """

    identity_attributes = ['tenant_name', 'name']
    other_attributes = ['display_name',
                        'vrf_name',
                        'enable_arp_flood',
                        'enable_routing',
                        'limit_ip_learn_to_subnets',
                        'l2_unknown_unicast_mode',
                        'ep_move_detect_mode',
                        'l3out_names',
                        'monitored']

    _aci_mo_name = 'fvBD'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(BridgeDomain, self).__init__({'display_name': '',
                                            'vrf_name': '',
                                            'enable_arp_flood': False,
                                            'enable_routing': True,
                                            'limit_ip_learn_to_subnets': False,
                                            'l2_unknown_unicast_mode': 'proxy',
                                            'ep_move_detect_mode': '',
                                            'l3out_names': [],
                                            'monitored': False},
                                           **kwargs)


class Agent(ResourceBase):
    """Resource representing an AIM Agent"""

    identity_attributes = ['id']
    other_attributes = ['agent_type',
                        'host',
                        'binary_file',
                        'admin_state_up',
                        'description',
                        'hash_trees',
                        'beat_count',
                        'version']
    # Attrbutes completely managed by the DB (eg. timestamps)
    db_attributes = ['heartbeat_timestamp']

    def __init__(self, **kwargs):
        super(Agent, self).__init__({'admin_state_up': True,
                                     'beat_count': 0,
                                     'id': utils.generate_uuid()}, **kwargs)

    def __eq__(self, other):
        return self.id == other.id

    def is_down(self, context):
        LOG.debug("Checking whether agent %s (timestamp %s) is down" %
                  (self.id, self.heartbeat_timestamp))
        current = context.db_session.query(func.now()).scalar()
        result = current - self.heartbeat_timestamp >= datetime.timedelta(
            seconds=cfg.CONF.aim.agent_down_time)
        LOG.debug("Agent %s is down: %s" % (self.id, result))
        return result


class Subnet(AciResourceBase):
    """Resource representing a Subnet in ACI.

    Identity attributes: name of ACI tenant, name of bridge-domain and
    IP-address & mask of the default gateway in CIDR format (that is
    <gateway-address>/<prefix-len>). Helper function 'to_gw_ip_mask'
    may be used to construct the IP-address & mask value.
    """

    identity_attributes = ['tenant_name', 'bd_name', 'gw_ip_mask']
    other_attributes = ['scope',
                        'display_name',
                        'monitored']

    _aci_mo_name = 'fvSubnet'
    _tree_parent = BridgeDomain

    SCOPE_PRIVATE = 'private'
    SCOPE_PUBLIC = 'public'

    def __init__(self, **kwargs):
        super(Subnet, self).__init__({'scope': self.SCOPE_PRIVATE,
                                      'monitored': False}, **kwargs)

    @staticmethod
    def to_gw_ip_mask(gateway_ip_address, prefix_len):
        return '%s/%d' % (gateway_ip_address, prefix_len)


class VRF(AciResourceBase):
    """Resource representing a VRF (Layer3 network context) in ACI.

    Identity attributes: name of ACI tenant, name of VRF.
    """

    identity_attributes = ['tenant_name', 'name']
    other_attributes = ['display_name',
                        'policy_enforcement_pref',
                        'monitored']

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

    identity_attributes = ['tenant_name', 'name']
    other_attributes = ['display_name', 'monitored']

    _aci_mo_name = 'fvAp'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(ApplicationProfile, self).__init__({'monitored': False},
                                                 **kwargs)


class EndpointGroup(AciResourceBase):
    """Resource representing an endpoint-group in ACI.

    Identity attributes: name of ACI tenant, name of application-profile
    and name of endpoint-group.
    """

    identity_attributes = ['tenant_name', 'app_profile_name', 'name']
    other_attributes = ['display_name',
                        'bd_name',
                        'provided_contract_names',
                        'consumed_contract_names',
                        'openstack_vmm_domain_names',
                        'physical_domain_names',
                        'monitored']

    _aci_mo_name = 'fvAEPg'
    _tree_parent = ApplicationProfile

    def __init__(self, **kwargs):
        super(EndpointGroup, self).__init__({'bd_name': '',
                                             'provided_contract_names': [],
                                             'consumed_contract_names': [],
                                             'openstack_vmm_domain_names': [],
                                             'physical_domain_names': [],
                                             'monitored': False},
                                            **kwargs)


class Filter(AciResourceBase):
    """Resource representing a contract filter in ACI.

    Identity attributes: name of ACI tenant and name of filter.
    """

    identity_attributes = ['tenant_name', 'name']
    other_attributes = ['display_name', 'monitored']

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

    identity_attributes = ['tenant_name', 'filter_name', 'name']
    other_attributes = ['display_name',
                        'arp_opcode', 'ether_type', 'ip_protocol',
                        'icmpv4_type', 'icmpv6_type',
                        'source_from_port', 'source_to_port',
                        'dest_from_port', 'dest_to_port',
                        'tcp_flags', 'stateful', 'fragment_only', 'monitored']

    _aci_mo_name = 'vzEntry'
    _tree_parent = Filter

    UNSPECIFIED = 'unspecified'

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

    identity_attributes = ['tenant_name', 'name']
    other_attributes = ['display_name', 'scope', 'monitored']

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

    identity_attributes = ['tenant_name', 'contract_name', 'name']
    other_attributes = ['display_name',
                        'in_filters', 'out_filters', 'bi_filters',
                        'monitored']

    _aci_mo_name = 'vzSubj'
    _tree_parent = Contract

    def __init__(self, **kwargs):
        super(ContractSubject, self).__init__(
            {'in_filters': [], 'out_filters': [], 'bi_filters': [],
             'monitored': False}, **kwargs)


class Endpoint(ResourceBase):
    """Resource representing an endpoint.

    Identity attribute: UUID of the endpoint.
    """

    identity_attributes = ['uuid']
    other_attributes = ['display_name',
                        'epg_tenant_name', 'epg_app_profile_name', 'epg_name']

    def __init__(self, **kwargs):
        super(Endpoint, self).__init__({}, **kwargs)


class VMMDomain(ResourceBase):
    """Resource representing a VMM domain.

    Identity attributes: VMM type (eg. Openstack) and name
    """

    identity_attributes = ['type', 'name']
    # REVISIT(ivar): A VMM has a plethora of attributes, references and child
    # objects that needs to be created. For now, this will however be just
    # the stub connecting what is explicitly created through the Infra and
    # what is managed by AIM, therefore we keep the stored information to
    # the very minimum
    other_attributes = []
    _aci_mo_name = 'vmmDomP'
    _tree_parent = None

    def __init__(self, **kwargs):
        super(VMMDomain, self).__init__({}, **kwargs)


class PhysicalDomain(ResourceBase):
    """Resource representing a Physical domain.

    Identity attributes: name
    """

    identity_attributes = ['name']
    # REVISIT(ivar): A Physical Domain has a plethora of attributes, references
    # and child objects that needs to be created. For now, this will however be
    # just the stub connecting what is explicitly created through the Infra and
    # what is managed by AIM, therefore we keep the stored information to
    # the very minimum
    other_attributes = []
    _aci_mo_name = 'physDomP'
    _tree_parent = None

    def __init__(self, **kwargs):
        super(PhysicalDomain, self).__init__({}, **kwargs)


class L3Outside(AciResourceBase):
    """Resource representing an L3 Outside.

    Identity attributes: name of ACI tenant, name of L3Out.
    """

    identity_attributes = ['tenant_name', 'name']
    other_attributes = ['display_name', 'vrf_name',
                        'l3_domain_dn', 'monitored']

    _aci_mo_name = 'l3extOut'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(L3Outside, self).__init__(
            {'vrf_name': '', 'l3_domain_dn': '',
             'monitored': False}, **kwargs)


class ExternalNetwork(AciResourceBase):
    """Resource representing an external network instance profile.

    External network is a group of external subnets that have the same
    security behavior.

    Identity attributes: name of ACI tenant, name of L3Out, name of external
    network.
    """

    identity_attributes = ['tenant_name', 'l3out_name', 'name']
    other_attributes = ['display_name', 'nat_epg_dn',
                        'provided_contract_names', 'consumed_contract_names',
                        'monitored']

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

    identity_attributes = ['tenant_name', 'l3out_name',
                           'external_network_name', 'cidr']
    other_attributes = ['display_name', 'monitored']

    _aci_mo_name = 'l3extSubnet'
    _tree_parent = ExternalNetwork

    def __init__(self, **kwargs):
        super(ExternalSubnet, self).__init__({'monitored': False}, **kwargs)
