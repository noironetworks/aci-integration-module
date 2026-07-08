# Copyright (c) 2026 Cisco Systems
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


CONSUMER = 'consumer'
PROVIDER = 'provider'

_TERMINAL_CONNECTOR_MOS = {
    CONSUMER: ('vnsAbsTermConn__Con', 'T1'),
    PROVIDER: ('vnsAbsTermConn__Prov', 'T2'),
}


def _dn(mo_type_name, *dn_attrs):
    return apic_client.ManagedObjectClass(mo_type_name).dn(*dn_attrs)


def get_node_connector_dn(tenant_name, service_graph_name, node_name,
                          connector_name):
    """Return a service graph node connector DN."""
    return _dn(
        'vnsAbsFuncConn', tenant_name, service_graph_name, node_name,
        connector_name)


def get_terminal_connector_dn(tenant_name, service_graph_name, connector_name):
    """Return a service graph terminal connector DN."""
    if connector_name not in _TERMINAL_CONNECTOR_MOS:
        raise ValueError(
            "Unsupported service graph terminal connector: %s" %
            connector_name)
    mo_type_name, terminal_name = _TERMINAL_CONNECTOR_MOS[connector_name]
    return _dn(mo_type_name, tenant_name, service_graph_name, terminal_name)


def get_connection_connector_dns(tenant_name, service_graph_name, node_name,
                                 connector_name):
    """Return connector_dns for a one-node ServiceGraphConnection."""
    if connector_name == PROVIDER:
        return [
            get_terminal_connector_dn(
                tenant_name, service_graph_name, CONSUMER),
            get_node_connector_dn(
                tenant_name, service_graph_name, node_name, CONSUMER)]
    if connector_name == CONSUMER:
        return [
            get_node_connector_dn(
                tenant_name, service_graph_name, node_name, PROVIDER),
            get_terminal_connector_dn(
                tenant_name, service_graph_name, PROVIDER)]
    raise ValueError(
        "Unsupported service graph connection connector: %s" %
        connector_name)
