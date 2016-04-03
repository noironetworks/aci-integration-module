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
    def __init__(self, defaults, **kwargs):
        unset_attr = [k for k in self.identity_attributes
                      if kwargs.get(k) is None and k not in defaults]
        if unset_attr:
            raise exc.IdentityAttributesMissing(attr=unset_attr)
        for k, v in defaults.iteritems():
            setattr(self, k, v)
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    @property
    def identity(self):
        return [getattr(self, x) for x in self.identity_attributes]

    def __str__(self):
        return '%s%s' % (type(self), self.identity)


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
    db_attributes = []

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
    # Attrbutes completely managed by the DB (eg. timestamps)
    db_attributes = []

    _aci_mo_name = 'fvBD'
    _tree_parent = Tenant

    def __init__(self, **kwargs):
        super(BridgeDomain, self).__init__({}, **kwargs)


class Agent(ResourceBase):
    """Resource representing an AIM Agent"""

    identity_attributes = ['id']
    other_attributes = ['agent_type',
                        'host',
                        'binary_file',
                        'admin_state_up',
                        'description',
                        'hash_trees',
                        'beat_count']
    # Attrbutes completely managed by the DB (eg. timestamps)
    db_attributes = ['created_at',
                     'heartbeat_timestamp']

    def __init__(self, **kwargs):
        super(Agent, self).__init__({'admin_state_up': True,
                                     'beat_count': 0,
                                     'id': utils.generate_uuid()}, **kwargs)

    def is_down(self):
        LOG.debug("Checking whether agent %s (timestamp %s) is down" %
                  (self.id, self.heartbeat_timestamp))
        return timeutils.is_older_than(self.heartbeat_timestamp,
                                       cfg.CONF.aim.agent_down_time)
