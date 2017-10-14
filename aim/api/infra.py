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

from aim.api import resource
from aim.api import types as t


class HostLink(resource.ResourceBase):
    """Switch-port connection information for a host node."""

    identity_attributes = t.identity(
        ('host_name', t.string(36)),
        ('interface_name', t.string(36)))
    other_attributes = t.other(
        ('interface_mac', t.mac_address),
        ('switch_id', t.string()),
        ('module', t.string()),
        ('port', t.string()),
        ('path', t.string()))

    def __init__(self, **kwargs):
        super(HostLink, self).__init__({'interface_mac': '',
                                        'switch_id': '',
                                        'module': '',
                                        'port': '',
                                        'path': ''}, **kwargs)


class OpflexDevice(resource.AciResourceBase):
    """Information about Opflex device reported by ACI. Read-only."""
    root = 'topology'

    identity_attributes = t.identity(
        ('pod_id', t.id),
        ('node_id', t.id),
        ('bridge_interface', t.id),
        ('dev_id', t.id))
    other_attributes = t.other(
        ('host_name', t.string(128)),
        ('ip', t.string(64)),
        ('fabric_path_dn', t.string()),
        ('domain_name', t.string(64)),
        ('controller_name', t.string(64)))

    _aci_mo_name = 'opflexODev'
    _tree_parent = resource.Pod

    def __init__(self, **kwargs):
        super(OpflexDevice, self).__init__({'host_name': '',
                                            'ip': '',
                                            'fabric_path_dn': '',
                                            'domain_name': '',
                                            'controller_name': ''},
                                           **kwargs)
        # force read-only object to be in monitored tree
        self.monitored = True


class HostDomainMapping(resource.ResourceBase):
    """host to VMM and phys-dom mapping"""

    identity_attributes = t.identity(
        ('host_name', t.string(128)))
    other_attributes = t.other(
        ('vmm_domain_name', t.string(64)),
        ('physical_domain_name', t.string(64)))

    def __init__(self, **kwargs):
        super(HostDomainMapping, self).__init__({'vmm_domain_name': '',
                                                 'physical_domain_name': ''},
                                                **kwargs)


class HostLinkNetworkLabel(resource.ResourceBase):
    """A network label to host link"""

    identity_attributes = t.identity(
        ('host_name', t.string(128)),
        ('network_label', t.string(64)),
        ('interface_name', t.string(32)))
    other_attributes = t.other()

    def __init__(self, **kwargs):
        super(HostLinkNetworkLabel, self).__init__({}, **kwargs)
