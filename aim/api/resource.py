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

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import timeutils

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


class Tenant(AciResourceBase):
    """Resource representing a Tenant in ACI.

    Identity attribute is RN for ACI tenant.
    """

    identity_attributes = ['name']
    other_attributes = ['display_name']

    _aci_mo_name = 'fvTenant'
    _tree_parent = None

    def __init__(self, **kwargs):
        super(Tenant, self).__init__({}, **kwargs)


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
                        'ep_move_detect_mode']

    _aci_mo_name = 'fvBD'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(BridgeDomain, self).__init__({'display_name': '',
                                            'vrf_name': '',
                                            'enable_arp_flood': False,
                                            'enable_routing': True,
                                            'limit_ip_learn_to_subnets': False,
                                            'l2_unknown_unicast_mode': 'proxy',
                                            'ep_move_detect_mode': ''},
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
    db_attributes = ['created_at',
                     'heartbeat_timestamp']

    def __init__(self, **kwargs):
        super(Agent, self).__init__({'admin_state_up': True,
                                     'beat_count': 0,
                                     'id': utils.generate_uuid()}, **kwargs)

    def __eq__(self, other):
        return self.id == other.id

    def is_down(self):
        LOG.debug("Checking whether agent %s (timestamp %s) is down" %
                  (self.id, self.heartbeat_timestamp))
        return timeutils.is_older_than(self.heartbeat_timestamp,
                                       cfg.CONF.aim.agent_down_time)


class Subnet(AciResourceBase):
    """Resource representing a Subnet in ACI.

    Identity attributes: name of ACI tenant, name of bridge-domain and
    IP-address & mask of the default gateway in CIDR format (that is
    <gateway-address>/<prefix-len>). Helper function 'to_gw_ip_mask'
    may be used to construct the IP-address & mask value.
    """

    identity_attributes = ['tenant_name', 'bd_name', 'gw_ip_mask']
    other_attributes = ['scope',
                        'display_name']

    _aci_mo_name = 'fvSubnet'
    _tree_parent = BridgeDomain

    SCOPE_PRIVATE = 'private'
    SCOPE_PUBLIC = 'public'

    def __init__(self, **kwargs):
        super(Subnet, self).__init__({'scope': self.SCOPE_PRIVATE}, **kwargs)

    @staticmethod
    def to_gw_ip_mask(gateway_ip_address, prefix_len):
        return '%s/%d' % (gateway_ip_address, prefix_len)


class VRF(AciResourceBase):
    """Resource representing a VRF (Layer3 network context) in ACI.

    Identity attributes: name of ACI tenant, name of VRF.
    """

    identity_attributes = ['tenant_name', 'name']
    other_attributes = ['display_name',
                        'policy_enforcement_pref']

    _aci_mo_name = 'fvCtx'
    _tree_parent = Tenant

    POLICY_ENFORCED = 'enforced'
    POLICY_UNENFORCED = 'unenforced'

    def __init__(self, **kwargs):
        super(VRF, self).__init__(
            {'policy_enforcement_pref': self.POLICY_ENFORCED},
            **kwargs)


class ApplicationProfile(AciResourceBase):
    """Resource representing an application-profile in ACI.

    Identity attributes: name of ACI tenant, name of app-profile.
    """

    identity_attributes = ['tenant_name', 'name']
    other_attributes = ['display_name']

    _aci_mo_name = 'fvAp'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(ApplicationProfile, self).__init__({}, **kwargs)


class EndpointGroup(AciResourceBase):
    """Resource representing an endpoint-group in ACI.

    Identity attributes: name of ACI tenant, name of application-profile
    and name of endpoint-group.
    """

    identity_attributes = ['tenant_name', 'app_profile_name', 'name']
    other_attributes = ['display_name',
                        'bd_name',
                        'provided_contract_names',
                        'consumed_contract_names']

    _aci_mo_name = 'fvAEPg'
    _tree_parent = ApplicationProfile

    def __init__(self, **kwargs):
        super(EndpointGroup, self).__init__({'bd_name': '',
                                             'provided_contract_names': [],
                                             'consumed_contract_names': []},
                                            **kwargs)
