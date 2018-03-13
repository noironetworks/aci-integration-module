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

from aim.api import resource
from aim.api import types as t


class DeviceCluster(resource.AciResourceBase):
    """Represents a device-cluster and associated ACI objects.

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('device_type', t.enum("PHYSICAL", "VIRTUAL")),
        ('service_type', t.enum("ADC", "FW", "OTHERS", "IDSIPS", "COPY")),
        ('context_aware', t.enum("single-Context", "multi-Context")),
        ('managed', t.bool),
        ('physical_domain_name', t.name),
        ('vmm_domain_type', t.enum('OpenStack', 'Kubernetes',
                                   'VMware', '')),
        ('vmm_domain_name', t.name),
        ('encap', t.string(24)),
        ('devices', t.list_of_dicts(('name', t.name),
                                    ('path', t.string(512)),
                                    ('host', t.string(512)))),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsLDevVip'
    _tree_parent = resource.Tenant

    def __init__(self, **kwargs):
        super(DeviceCluster, self).__init__(
            {'display_name': '',
             'device_type': 'PHYSICAL',
             'service_type': 'OTHERS',
             'context_aware': 'single-Context',
             'managed': True,
             'physical_domain_name': '',
             'vmm_domain_type': '',
             'vmm_domain_name': '',
             'encap': '',
             'devices': [],
             'monitored': False},
            **kwargs)


class DeviceClusterInterface(resource.AciResourceBase):
    """Resource representing logical interface of a L4-L7 device cluster.

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('device_cluster_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('encap', t.string()),
        ('concrete_interfaces', t.list_of_strings),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsLIf'
    _tree_parent = DeviceCluster

    def __init__(self, **kwargs):
        super(DeviceClusterInterface, self).__init__(
            {'display_name': '',
             'encap': '',
             'concrete_interfaces': [],
             'monitored': False},
            **kwargs)


class ConcreteDevice(resource.AciResourceBase):
    """Resource representing concrete device in a L4-L7 device cluster.

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('device_cluster_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsCDev'
    _tree_parent = DeviceCluster

    def __init__(self, **kwargs):
        super(ConcreteDevice, self).__init__(
            {'display_name': '',
             'monitored': False},
            **kwargs)


class ConcreteDeviceInterface(resource.AciResourceBase):
    """Resource representing interface of concrete device in device cluster.

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('device_cluster_name', t.name),
        ('device_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('path', t.string()),
        ('host', t.string()),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsCIf'
    _tree_parent = ConcreteDevice

    def __init__(self, **kwargs):
        super(ConcreteDeviceInterface, self).__init__(
            {'display_name': '',
             'path': '',
             'host': '',
             'monitored': False},
            **kwargs)


class ServiceGraph(resource.AciResourceBase):
    """Resource representing abstract service graph template in ACI.

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('linear_chain_nodes',
         t.list_of_dicts(('name', t.name),
                         ('device_cluster_name', t.name),
                         ('device_cluster_tenant_name', t.name))),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsAbsGraph'
    _tree_parent = resource.Tenant

    def __init__(self, **kwargs):
        super(ServiceGraph, self).__init__({'display_name': '',
                                            'linear_chain_nodes': [],
                                            'monitored': False},
                                           **kwargs)


class ServiceGraphConnection(resource.AciResourceBase):
    """Resource representing connections among function-nodes in service graph.

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('service_graph_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('adjacency_type', t.enum('L2', 'L3')),
        ('connector_direction', t.enum('consumer', 'provider')),
        ('connector_type', t.enum('internal', 'external')),
        ('direct_connect', t.bool),
        ('unicast_route', t.bool),
        ('connector_dns', t.list_of_strings),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsAbsConnection'
    _tree_parent = ServiceGraph

    def __init__(self, **kwargs):
        super(ServiceGraphConnection, self).__init__(
            {'display_name': '',
             'adjacency_type': 'L2',
             'connector_direction': 'provider',
             'connector_type': 'external',
             'direct_connect': False,
             'unicast_route': False,
             'connector_dns': [],
             'monitored': False},
            **kwargs)


class ServiceGraphNode(resource.AciResourceBase):
    """Resource representing a function-node in service graph.

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('service_graph_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('function_type', t.enum('GoTo', 'GoThrough')),
        ('managed', t.bool),
        ('routing_mode', t.enum('unspecified', 'Redirect')),
        ('connectors', t.list_of_names),
        ('device_cluster_name', t.name),
        ('device_cluster_tenant_name', t.name),
        ('sequence_number', t.string()),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsAbsNode'
    _tree_parent = ServiceGraph

    def __init__(self, **kwargs):
        super(ServiceGraphNode, self).__init__(
            {'display_name': '',
             'function_type': 'GoTo',
             'managed': True,
             'routing_mode': 'unspecified',
             'connectors': [],
             'device_cluster_name': '',
             'device_cluster_tenant_name': '',
             'sequence_number': '0',
             'monitored': False},
            **kwargs)


class ServiceRedirectPolicy(resource.AciResourceBase):
    """Resource representing a service-redirect policy.

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('destinations', t.list_of_dicts(('ip', t.string()),
                                         ('mac', t.mac_address))),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsSvcRedirectPol'
    _tree_parent = resource.Tenant

    def __init__(self, **kwargs):
        super(ServiceRedirectPolicy, self).__init__(
            {'display_name': '',
             'destinations': [],
             'monitored': False},
            **kwargs)


class DeviceClusterContext(resource.AciResourceBase):
    """Resource representing a device-cluster context.

    """

    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('contract_name', t.name),
        ('service_graph_name', t.name),
        ('node_name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('device_cluster_name', t.name),
        ('device_cluster_tenant_name', t.name),
        ('service_redirect_policy_name', t.name),
        ('service_redirect_policy_tenant_name', t.name),
        ('bridge_domain_name', t.name),
        ('bridge_domain_tenant_name', t.name),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsLDevCtx'
    _tree_parent = resource.Tenant

    def __init__(self, **kwargs):
        super(DeviceClusterContext, self).__init__(
            {'display_name': '',
             'device_cluster_name': '',
             'device_cluster_tenant_name': '',
             'service_redirect_policy_name': '',
             'service_redirect_policy_tenant_name': '',
             'bridge_domain_name': '',
             'bridge_domain_tenant_name': '',
             'monitored': False},
            **kwargs)


class DeviceClusterInterfaceContext(resource.AciResourceBase):
    """Resource representing a device-cluster logical interface context.

    """
    identity_attributes = t.identity(
        ('tenant_name', t.name),
        ('contract_name', t.name),
        ('service_graph_name', t.name),
        ('node_name', t.name),
        ('connector_name', t.name))
    other_attributes = t.other(
        ('display_name', t.name),
        ('device_cluster_interface_dn', t.string()),
        ('service_redirect_policy_dn', t.string()),
        ('bridge_domain_dn', t.string()),
        ('monitored', t.bool))

    _aci_mo_name = 'vnsLIfCtx'
    _tree_parent = DeviceClusterContext

    def __init__(self, **kwargs):
        super(DeviceClusterInterfaceContext, self).__init__(
            {'display_name': '',
             'device_cluster_interface_dn': '',
             'service_redirect_policy_dn': '',
             'bridge_domain_dn': '',
             'monitored': False},
            **kwargs)
