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

from apicapi import apic_client

from aim.agent.aid.universes.aci.converters import utils
from aim.api import service_graph


def _dn(mo_type_name, *dn_attrs):
    mo = apic_client.ManagedObjectClass(mo_type_name)
    return mo.dn(*dn_attrs)


def _aci_obj(mo_type_name, *dn_attrs, **attrs):
    obj_attrs = {'dn': _dn(mo_type_name, *dn_attrs)}
    obj_attrs.update(attrs)
    return {mo_type_name: {'attributes': obj_attrs}}


def device_cluster_converter(object_dict, otype, helper,
                             source_identity_attributes,
                             destination_identity_attributes, to_aim=True):
    if to_aim:
        result = utils.default_converter(object_dict, otype, helper,
                                         source_identity_attributes,
                                         destination_identity_attributes,
                                         to_aim=to_aim)
    else:
        result = utils.default_converter(object_dict, otype, helper,
                                         source_identity_attributes,
                                         destination_identity_attributes,
                                         to_aim=to_aim)
        if object_dict['encap']:
            lif = service_graph.DeviceClusterInterface(
                tenant_name=object_dict['tenant_name'],
                device_cluster_name=object_dict['name'],
                name='interface',
                encap=object_dict['encap'])
            result.append(lif)
        else:
            lif = None
        nodes = []
        for node in object_dict['devices']:
            if 'name' in node:
                cdev = service_graph.ConcreteDevice(
                    tenant_name=object_dict['tenant_name'],
                    device_cluster_name=object_dict['name'],
                    name=node['name'])
                cdev_if = service_graph.ConcreteDeviceInterface(
                    tenant_name=object_dict['tenant_name'],
                    device_cluster_name=object_dict['name'],
                    device_name=node['name'],
                    name='interface')
                if 'path' in node:
                    cdev_if.path = node['path']
                nodes.extend([cdev, cdev_if])
                if lif:
                    lif.concrete_interfaces.append(cdev_if.dn)
        result.extend(nodes)
    return result


def device_cluster_context_converter(object_dict, otype, helper,
                                     source_identity_attributes,
                                     destination_identity_attributes,
                                     to_aim=True):
    if to_aim:
        result = utils.default_converter(object_dict, otype, helper,
                                         source_identity_attributes,
                                         destination_identity_attributes,
                                         to_aim=to_aim)
    else:
        object_dict1 = copy.copy(object_dict)
        if not object_dict1['device_cluster_tenant_name']:
            object_dict1['device_cluster_tenant_name'] = (
                object_dict1['tenant_name'])
        result = utils.default_converter(object_dict1, otype, helper,
                                         source_identity_attributes,
                                         destination_identity_attributes,
                                         to_aim=to_aim)
        cons_ctx = service_graph.DeviceClusterInterfaceContext(
            tenant_name=object_dict['tenant_name'],
            contract_name=object_dict['contract_name'],
            service_graph_name=object_dict['service_graph_name'],
            node_name=object_dict['node_name'],
            connector_name='consumer')
        if object_dict['device_cluster_name']:
            cons_ctx.device_cluster_interface_dn = _dn(
                'vnsLIf',
                (object_dict['device_cluster_tenant_name'] or
                 cons_ctx.tenant_name),
                object_dict['device_cluster_name'],
                'interface')
        if object_dict['bridge_domain_name']:
            cons_ctx.bridge_domain_dn = _dn(
                'fvBD',
                (object_dict['bridge_domain_tenant_name'] or
                 cons_ctx.tenant_name),
                object_dict['bridge_domain_name'])
        if object_dict['service_redirect_policy_name']:
            cons_ctx.service_redirect_policy_dn = _dn(
                'vnsSvcRedirectPol',
                (object_dict['service_redirect_policy_tenant_name'] or
                 cons_ctx.tenant_name),
                object_dict['service_redirect_policy_name'])
        if (cons_ctx.device_cluster_interface_dn and
                cons_ctx.bridge_domain_dn and
                cons_ctx.service_redirect_policy_dn):
            prov_ctx = copy.copy(cons_ctx)
            prov_ctx.connector_name = 'provider'
            result.extend([cons_ctx, prov_ctx])
    return result


def service_graph_converter(object_dict, otype, helper,
                            source_identity_attributes,
                            destination_identity_attributes, to_aim=True):
    if to_aim:
        result = utils.default_converter(object_dict, otype, helper,
                                         source_identity_attributes,
                                         destination_identity_attributes,
                                         to_aim=to_aim)
    else:
        result = utils.default_converter(object_dict, otype, helper,
                                         source_identity_attributes,
                                         destination_identity_attributes,
                                         to_aim=to_aim)
        tn = object_dict['tenant_name']
        gr = object_dict['name']
        term_cons = _aci_obj('vnsAbsTermConn__Con', tn, gr, 'T1')
        term_prov = _aci_obj('vnsAbsTermConn__Prov', tn, gr, 'T2')
        result.extend([
            _aci_obj('vnsAbsTermNodeCon', tn, gr, 'T1'),
            term_cons,
            _aci_obj('vnsInTerm__Con', tn, gr, 'T1'),
            _aci_obj('vnsOutTerm__Con', tn, gr, 'T1'),
            _aci_obj('vnsAbsTermNodeProv', tn, gr, 'T2'),
            term_prov,
            _aci_obj('vnsInTerm__Prov', tn, gr, 'T2'),
            _aci_obj('vnsOutTerm__Prov', tn, gr, 'T2')
        ])
        lc_nodes = [n for n in object_dict['linear_chain_nodes']
                    if n.get('name')]

        prev_conn = term_cons.values()[0]['attributes']['dn']
        cntr = 0
        for fn in lc_nodes:
            cntr = cntr + 1
            node = service_graph.ServiceGraphNode(
                tenant_name=tn, service_graph_name=gr, name=fn['name'],
                managed=False, routing_mode='Redirect',
                sequence_number=str(cntr - 1),
                connectors=['consumer', 'provider'])
            if fn.get('device_cluster_name'):
                node.device_cluster_name = fn['device_cluster_name']
                node.device_cluster_tenant_name = (
                    fn.get('device_cluster_tenant_name', tn))
            node_con = _dn('vnsAbsFuncConn', tn, gr, node.name, 'consumer')
            node_prov = _dn('vnsAbsFuncConn', tn, gr, node.name, 'provider')
            cxn = service_graph.ServiceGraphConnection(
                tenant_name=tn, service_graph_name=gr, name='C%s' % cntr,
                unicast_route=True,
                connector_dns=[prev_conn, node_con])
            prev_conn = node_prov
            result.extend([node, cxn])
        if cntr:
            cxn = service_graph.ServiceGraphConnection(
                tenant_name=tn, service_graph_name=gr, name='C%s' % (cntr + 1),
                unicast_route=True,
                connector_dns=[prev_conn,
                               term_prov.values()[0]['attributes']['dn']])
            result.append(cxn)
    return result


def vnsRsRedirectHealthGroup_ip_converter(input_dict, input_attr, to_aim=True):
    if to_aim:
        return utils.default_identity_converter(
            input_dict, 'vnsRsRedirectHealthGroup', {})[-1]
    else:
        return {utils.IGNORE: utils.default_attribute_converter(
            input_dict, input_attr, to_aim=to_aim)}


vnsRsALDevToPhysDomP_converter = utils.dn_decomposer(
    ['physical_domain_name'], 'physDomP')
vnsRsALDevToDomP_converter = utils.dn_decomposer(
    ['vmm_domain_type', 'vmm_domain_name'], 'vmmDomP')
vnsRsCIfAttN_converter = utils.child_list('concrete_interfaces', 'tDn')
vnsRsCIfPathAtt_converter = utils.child_list('path', 'tDn')
vnsAbsFuncConn_converter = utils.child_list('connectors', 'name')
vnsLDevVip_dn_decomposer = utils.dn_decomposer(
    ['device_cluster_tenant_name', 'device_cluster_name'],
    'vnsLDevVip')
fvIPSLAMonitoringPol_dn_decomposer = utils.dn_decomposer(
    ['monitoring_policy_tenant_name', 'monitoring_policy_name'],
    'fvIPSLAMonitoringPol')
vnsRsAbsConnectionConns_converter = utils.child_list('connector_dns', 'tDn')
vnsRedirectDest_converter = utils.list_dict(
    'destinations',
    {'ip': {'other': 'ip'},
     'mac': {'other': 'mac',
             'converter': utils.upper}},
    ['ip'])
vnsRsRedirectHealthGroup_converter = utils.list_dict(
    'destinations',
    {'redirect_health_group_dn': {'other': 'tDn'},
     'ip': {'other': 'dn',
            'converter': vnsRsRedirectHealthGroup_ip_converter}},
    ['ip'])


resource_map = {
    'vnsLDevVip': [{
        'resource': service_graph.DeviceCluster,
        'skip': ['physical_domain_name', 'encap', 'devices',
                 'vmm_domain_name', 'vmm_domain_type'],
        'exceptions': {
            'managed': {'converter': utils.boolean},
            'devtype': {'other': 'device_type'},
            'svcType': {'other': 'service_type'}
        },
        'converter': device_cluster_converter,
    }],
    'vnsRsALDevToPhysDomP': [{
        'resource': service_graph.DeviceCluster,
        'exceptions': {'tDn': {'other': 'physical_domain_name',
                               'converter': vnsRsALDevToPhysDomP_converter}},
        'to_resource': utils.default_to_resource_strict,
    }],
    'vnsRsALDevToDomP': [{
        'resource': service_graph.DeviceCluster,
        'exceptions': {'tDn': {'other': 'vmm_domain_name',
                               'converter': vnsRsALDevToDomP_converter,
                               'skip_if_empty': True}},
        'to_resource': utils.default_to_resource_strict,
    }],
    'vnsLIf': [{
        'resource': service_graph.DeviceClusterInterface,
        'skip': ['concrete_interfaces'],
        'alt_resource': service_graph.DeviceCluster
    }],
    'vnsRsCIfAttN': [{
        'resource': service_graph.DeviceClusterInterface,
        'converter': vnsRsCIfAttN_converter,
        'alt_resource': service_graph.DeviceCluster
    }],
    'vnsCDev': [{
        'resource': service_graph.ConcreteDevice,
        'alt_resource': service_graph.DeviceCluster
    }],
    'vnsCIf': [{
        'resource': service_graph.ConcreteDeviceInterface,
        'skip': ['path', 'host'],
        'alt_resource': service_graph.DeviceCluster
    }],
    'vnsRsCIfPathAtt': [{
        'resource': service_graph.ConcreteDeviceInterface,
        'exceptions': {'tDn': {'other': 'path'}},
        'skip': ['host'],
        'to_resource': utils.default_to_resource_strict,
        'alt_resource': service_graph.DeviceCluster
    }],
    'vnsAbsGraph': [{
        'resource': service_graph.ServiceGraph,
        'converter': service_graph_converter,
        'skip': ['linear_chain_nodes']
    }],
    'vnsAbsNode': [{
        'resource': service_graph.ServiceGraphNode,
        'exceptions': {
            'funcType': {'other': 'function_type'},
            'managed': {'converter': utils.boolean},
        },
        'skip': ['connectors', 'device_cluster_name',
                 'device_cluster_tenant_name'],
        'alt_resource': service_graph.ServiceGraph,
    }],
    'vnsAbsFuncConn': [{
        'resource': service_graph.ServiceGraphNode,
        'converter': vnsAbsFuncConn_converter,
        'alt_resource': service_graph.ServiceGraph,
    }],
    'vnsRsNodeToLDev': [{
        'resource': service_graph.ServiceGraphNode,
        'exceptions': {
            'tDn': {'other': 'device_cluster_name',
                    'converter': vnsLDevVip_dn_decomposer},
        },
        'to_resource': utils.default_to_resource_strict,
        'alt_resource': service_graph.ServiceGraph,
    }],
    'vnsAbsConnection': [{
        'resource': service_graph.ServiceGraphConnection,
        'exceptions': {
            'adjType': {'other': 'adjacency_type'},
            'connDir': {'other': 'connector_direction'},
            'connType': {'other': 'connector_type'},
            'directConnect': {'converter': utils.boolean},
            'unicastRoute': {'converter': utils.boolean},
        },
        'skip': ['connector_dns'],
        'alt_resource': service_graph.ServiceGraph,
    }],
    'vnsRsAbsConnectionConns': [{
        'resource': service_graph.ServiceGraphConnection,
        'converter': vnsRsAbsConnectionConns_converter,
        'alt_resource': service_graph.ServiceGraph,
    }],
    'vnsSvcRedirectPol': [{
        'resource': service_graph.ServiceRedirectPolicy,
        'skip': ['destinations', 'monitoring_policy_tenant_name',
                 'monitoring_policy_name'],
    }],
    'vnsRedirectDest': [{
        'resource': service_graph.ServiceRedirectPolicy,
        'converter': vnsRedirectDest_converter,
    }],
    'vnsRsIPSLAMonitoringPol': [{
        'resource': service_graph.ServiceRedirectPolicy,
        'exceptions': {
            'tDn': {'other': 'monitoring_policy_name',
                    'converter': fvIPSLAMonitoringPol_dn_decomposer},
        },
        'to_resource': utils.default_to_resource_strict
    }],
    'vnsRsRedirectHealthGroup': [{
        'resource': service_graph.ServiceRedirectPolicy,
        'converter': vnsRsRedirectHealthGroup_converter,
    }],
    'vnsLDevCtx': [{
        'resource': service_graph.DeviceClusterContext,
        'converter': device_cluster_context_converter,
        'skip': ['device_cluster_name', 'device_cluster_tenant_name',
                 'service_redirect_policy_name',
                 'service_redirect_policy_tenant_name',
                 'bridge_domain_name', 'bridge_domain_tenant_name'],
    }],
    'vnsRsLDevCtxToLDev': [{
        'resource': service_graph.DeviceClusterContext,
        'exceptions': {
            'tDn': {'other': 'device_cluster_name',
                    'converter': vnsLDevVip_dn_decomposer},
        },
        'to_resource': utils.default_to_resource_strict,
        'converter': device_cluster_context_converter,
    }],
    'vnsLIfCtx': [{
        'resource': service_graph.DeviceClusterInterfaceContext,
        'skip': ['device_cluster_interface_dn',
                 'service_redirect_policy_dn',
                 'bridge_domain_dn'],
        'alt_resource': service_graph.DeviceClusterContext
    }],
    'vnsRsLIfCtxToSvcRedirectPol': [{
        'resource': service_graph.DeviceClusterInterfaceContext,
        'exceptions': {
            'tDn': {'other': 'service_redirect_policy_dn'},
        },
        'to_resource': utils.default_to_resource_strict,
        'alt_resource': service_graph.DeviceClusterContext
    }],
    'vnsRsLIfCtxToBD': [{
        'resource': service_graph.DeviceClusterInterfaceContext,
        'exceptions': {
            'tDn': {'other': 'bridge_domain_dn'},
        },
        'to_resource': utils.default_to_resource_strict,
        'alt_resource': service_graph.DeviceClusterContext
    }],
    'vnsRsLIfCtxToLIf': [{
        'resource': service_graph.DeviceClusterInterfaceContext,
        'exceptions': {
            'tDn': {'other': 'device_cluster_interface_dn'},
        },
        'to_resource': utils.default_to_resource_strict,
        'alt_resource': service_graph.DeviceClusterContext
    }],
    'fvIPSLAMonitoringPol': [{
        'resource': service_graph.ServiceRedirectMonitoringPolicy,
        'exceptions': {
            'slaPort': {'other': 'tcp_port'},
            'slaType': {'other': 'type'},
            'slaFrequency': {'other': 'frequency'}
        },
    }],
    'vnsRedirectHealthGroup': [{
        'resource': service_graph.ServiceRedirectHealthGroup,
    }]
}

resource_map_post_reverse = {
    'vnsAbsTermNodeCon': [{
        'resource': service_graph.ServiceGraph,
        'skip': ['display_name', 'name_alias'],
        'to_resource': utils.default_to_resource_strict,
    }],
    'vnsAbsTermConn__Con': [{
        'resource': service_graph.ServiceGraph,
        'skip': ['display_name', 'name_alias'],
        'to_resource': utils.default_to_resource_strict
    }],
    'vnsInTerm__Con': [{
        'resource': service_graph.ServiceGraph,
        'skip': ['display_name', 'name_alias'],
        'to_resource': utils.default_to_resource_strict
    }],
    'vnsOutTerm__Con': [{
        'resource': service_graph.ServiceGraph,
        'skip': ['display_name', 'name_alias'],
        'to_resource': utils.default_to_resource_strict
    }],
    'vnsAbsTermNodeProv': [{
        'resource': service_graph.ServiceGraph,
        'skip': ['display_name', 'name_alias'],
        'to_resource': utils.default_to_resource_strict,
    }],
    'vnsAbsTermConn__Prov': [{
        'resource': service_graph.ServiceGraph,
        'skip': ['display_name', 'name_alias'],
        'to_resource': utils.default_to_resource_strict
    }],
    'vnsInTerm__Prov': [{
        'resource': service_graph.ServiceGraph,
        'skip': ['display_name', 'name_alias'],
        'to_resource': utils.default_to_resource_strict
    }],
    'vnsOutTerm__Prov': [{
        'resource': service_graph.ServiceGraph,
        'skip': ['display_name', 'name_alias'],
        'to_resource': utils.default_to_resource_strict
    }],
}
