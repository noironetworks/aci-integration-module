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

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy import orm

from aim.db import model_base


class DeviceClusterDevice(model_base.Base):
    """DB model for Devices used by DeviceCluster."""

    __tablename__ = 'aim_device_cluster_devices'

    dc_aim_id = sa.Column(sa.Integer,
                          sa.ForeignKey('aim_device_clusters.aim_id'),
                          primary_key=True)
    name = model_base.name_column(primary_key=True)
    path = sa.Column(sa.String(512))


class DeviceCluster(model_base.Base, model_base.HasAimId,
                    model_base.HasName, model_base.HasDisplayName,
                    model_base.HasTenantName, model_base.AttributeMixin,
                    model_base.IsMonitored):
    """DB model for DeviceCluster."""

    __tablename__ = 'aim_device_clusters'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    device_type = sa.Column(sa.Enum("PHYSICAL", "VIRTUAL"))
    service_type = sa.Column(sa.Enum("ADC", "FW", "OTHERS", "IDSIPS", "COPY"))
    context_aware = sa.Column(sa.Enum("single-Context", "multi-Context"))
    managed = sa.Column(sa.Boolean)
    physical_domain_name = model_base.name_column()
    vmm_domain_type = sa.Column(sa.Enum('OpenStack', 'Kubernetes',
                                        'VMware', ''))
    vmm_domain_name = model_base.name_column()
    encap = sa.Column(sa.String(24))
    devices = orm.relationship(DeviceClusterDevice,
                               backref='cluster',
                               cascade='all, delete-orphan',
                               lazy='joined')

    def from_attr(self, session, res_attr):
        if 'devices' in res_attr:
            devs = []
            for d in (res_attr.pop('devices', []) or []):
                devs.append(DeviceClusterDevice(name=d['name'],
                                                path=d.get('path', None)))
            self.devices = devs
        # map remaining attributes to model
        super(DeviceCluster, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(DeviceCluster, self).to_attr(session)
        for f in res_attr.pop('devices', []):
            d = {'name': f.name}
            if f.path is not None:
                d['path'] = f.path
            res_attr.setdefault('devices', []).append(d)
        return res_attr


class DeviceClusterInterfaceConcreteIfs(model_base.Base):
    """DB model for concrete interfaces used by DeviceClusterInterface."""

    __tablename__ = 'aim_device_cluster_if_concrete_ifs'

    dci_aim_id = sa.Column(sa.Integer,
                           sa.ForeignKey('aim_device_cluster_ifs.aim_id'),
                           primary_key=True)
    interface = model_base.dn_column(primary_key=True)


class DeviceClusterInterface(model_base.Base, model_base.HasAimId,
                             model_base.HasName, model_base.HasDisplayName,
                             model_base.HasTenantName,
                             model_base.AttributeMixin,
                             model_base.IsMonitored):
    """DB model for DeviceClusterInterface."""

    __tablename__ = 'aim_device_cluster_ifs'
    __table_args__ = (
        model_base.uniq_column(__tablename__,
                               'tenant_name', 'device_cluster_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    device_cluster_name = model_base.name_column(nullable=False)
    encap = sa.Column(sa.String(24))

    concrete_ifs = orm.relationship(DeviceClusterInterfaceConcreteIfs,
                                    backref='cluster_interface',
                                    cascade='all, delete-orphan',
                                    lazy='joined')

    def from_attr(self, session, res_attr):
        if 'concrete_interfaces' in res_attr:
            ifs = []
            for i in (res_attr.pop('concrete_interfaces', []) or []):
                ifs.append(DeviceClusterInterfaceConcreteIfs(interface=i))
            self.concrete_ifs = ifs
        # map remaining attributes to model
        super(DeviceClusterInterface, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(DeviceClusterInterface, self).to_attr(session)
        for f in res_attr.pop('concrete_ifs', []):
            res_attr.setdefault('concrete_interfaces', []).append(f.interface)
        return res_attr


class ConcreteDevice(model_base.Base, model_base.HasAimId,
                     model_base.HasName, model_base.HasDisplayName,
                     model_base.HasTenantName,
                     model_base.AttributeMixin,
                     model_base.IsMonitored):
    """DB model for ConcreteDevice."""

    __tablename__ = 'aim_concrete_devices'
    __table_args__ = (
        model_base.uniq_column(__tablename__,
                               'tenant_name', 'device_cluster_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    device_cluster_name = model_base.name_column(nullable=False)


class ConcreteDeviceInterface(model_base.Base, model_base.HasAimId,
                              model_base.HasName, model_base.HasDisplayName,
                              model_base.HasTenantName,
                              model_base.AttributeMixin,
                              model_base.IsMonitored):
    """DB model for ConcreteDeviceInterface."""

    __tablename__ = 'aim_concrete_device_ifs'
    __table_args__ = (
        model_base.uniq_column(__tablename__,
                               'tenant_name', 'device_cluster_name',
                               'device_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    device_cluster_name = model_base.name_column(nullable=False)
    device_name = model_base.name_column(nullable=False)
    path = sa.Column(sa.String(512))


class ServiceGraphConnectionConnector(model_base.Base):
    """DB model for connectors used by ServiceGraphConnection."""

    __tablename__ = 'aim_service_graph_connection_conns'

    sgc_aim_id = sa.Column(
        sa.Integer,
        sa.ForeignKey('aim_service_graph_connections.aim_id'),
        primary_key=True)
    # Use VARCHAR with ASCII encoding to work-around MySQL limitations
    # on the length of primary keys
    connector = sa.Column(VARCHAR(512, charset='latin1'), primary_key=True)


class ServiceGraphConnection(model_base.Base, model_base.HasAimId,
                             model_base.HasName, model_base.HasDisplayName,
                             model_base.HasTenantName,
                             model_base.AttributeMixin,
                             model_base.IsMonitored):
    """DB model for ServiceGraphConnection."""

    __tablename__ = 'aim_service_graph_connections'
    __table_args__ = (
        model_base.uniq_column(__tablename__,
                               'tenant_name', 'service_graph_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    service_graph_name = model_base.name_column(nullable=False)
    adjacency_type = sa.Column(sa.Enum('L2', 'L3'))
    connector_direction = sa.Column(sa.Enum('consumer', 'provider'))
    connector_type = sa.Column(sa.Enum('internal', 'external'))
    direct_connect = sa.Column(sa.Boolean)
    unicast_route = sa.Column(sa.Boolean)

    connectors = orm.relationship(ServiceGraphConnectionConnector,
                                  backref='graph_connection',
                                  cascade='all, delete-orphan',
                                  lazy='joined')

    def from_attr(self, session, res_attr):
        if 'connector_dns' in res_attr:
            conns = []
            for c in (res_attr.pop('connector_dns', []) or []):
                conns.append(ServiceGraphConnectionConnector(connector=c))
            self.connectors = conns
        # map remaining attributes to model
        super(ServiceGraphConnection, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(ServiceGraphConnection, self).to_attr(session)
        for c in res_attr.pop('connectors', []):
            res_attr.setdefault('connector_dns', []).append(c.connector)
        return res_attr


class ServiceGraphNodeConnector(model_base.Base):
    """DB model for connectors used by ServiceGraphNode."""

    __tablename__ = 'aim_service_graph_node_conns'

    sgn_aim_id = sa.Column(
        sa.Integer,
        sa.ForeignKey('aim_service_graph_nodes.aim_id'),
        primary_key=True)
    # Use VARCHAR with ASCII encoding to work-around MySQL limitations
    # on the length of primary keys
    connector = sa.Column(VARCHAR(512, charset='latin1'), primary_key=True)


class ServiceGraphNode(model_base.Base, model_base.HasAimId,
                       model_base.HasName, model_base.HasDisplayName,
                       model_base.HasTenantName,
                       model_base.AttributeMixin,
                       model_base.IsMonitored):
    """DB model for ServiceGraphNode."""

    __tablename__ = 'aim_service_graph_nodes'
    __table_args__ = (
        model_base.uniq_column(__tablename__,
                               'tenant_name', 'service_graph_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    service_graph_name = model_base.name_column(nullable=False)
    function_type = sa.Column(sa.Enum('GoTo', 'GoThrough'))
    managed = sa.Column(sa.Boolean)
    routing_mode = sa.Column(sa.Enum('unspecified', 'Redirect'))
    device_cluster_name = model_base.name_column()
    device_cluster_tenant_name = model_base.name_column()
    sequence_number = sa.Column(sa.Integer)
    conns = orm.relationship(ServiceGraphNodeConnector,
                             backref='graph_node',
                             cascade='all, delete-orphan',
                             lazy='joined')

    def from_attr(self, session, res_attr):
        if 'connectors' in res_attr:
            conns = []
            for c in (res_attr.pop('connectors', []) or []):
                conns.append(ServiceGraphNodeConnector(connector=c))
            self.conns = conns
        # map remaining attributes to model
        super(ServiceGraphNode, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(ServiceGraphNode, self).to_attr(session)
        for c in res_attr.pop('conns', []):
            res_attr.setdefault('connectors', []).append(c.connector)
        if 'sequence_number' in res_attr:
            res_attr['sequence_number'] = str(res_attr['sequence_number'])
        return res_attr


class ServiceGraphLinearChainNode(model_base.Base):
    """DB model for linear-chain nodes used by ServiceGraph."""

    __tablename__ = 'aim_service_graph_linear_chain_nodes'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'sg_aim_id', 'name',
                               'sequence_number') +
        model_base.to_tuple(model_base.Base.__table_args__))
    sg_aim_id = sa.Column(sa.Integer,
                          sa.ForeignKey('aim_service_graphs.aim_id'),
                          primary_key=True)
    name = model_base.name_column(primary_key=True)
    device_cluster_name = model_base.name_column()
    device_cluster_tenant_name = model_base.name_column()
    sequence_number = sa.Column(sa.Integer)


class ServiceGraph(model_base.Base, model_base.HasAimId,
                   model_base.HasName, model_base.HasDisplayName,
                   model_base.HasTenantName, model_base.AttributeMixin,
                   model_base.IsMonitored):
    """DB model for ServiceGraph."""

    __tablename__ = 'aim_service_graphs'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    linear_chain = orm.relationship(ServiceGraphLinearChainNode,
                                    backref='service_graph',
                                    cascade='all, delete-orphan',
                                    lazy='joined')

    def from_attr(self, session, res_attr):
        if 'linear_chain_nodes' in res_attr:
            nodes = []
            for i, n in enumerate((res_attr.pop('linear_chain_nodes', [])
                                   or [])):
                if not n.get('name'):
                    continue
                nodes.append(
                    ServiceGraphLinearChainNode(
                        name=n['name'],
                        device_cluster_name=n.get('device_cluster_name', None),
                        device_cluster_tenant_name=(
                            n.get('device_cluster_tenant_name', None)),
                        sequence_number=i))
            self.linear_chain = nodes
        # map remaining attributes to model
        super(ServiceGraph, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(ServiceGraph, self).to_attr(session)
        for n in sorted(res_attr.pop('linear_chain', []),
                        key=lambda x: x.sequence_number):
            d = {'name': n.name}
            if n.device_cluster_name is not None:
                d['device_cluster_name'] = n.device_cluster_name
            if n.device_cluster_tenant_name is not None:
                d['device_cluster_tenant_name'] = n.device_cluster_tenant_name
            res_attr.setdefault('linear_chain_nodes', []).append(d)
        return res_attr


class ServiceRedirectPolicyDestination(model_base.Base):
    """DB model for destinations used by ServiceRedirectPolicy."""

    __tablename__ = 'aim_service_redirect_policy_destinations'

    srp_aim_id = sa.Column(
        sa.Integer,
        sa.ForeignKey('aim_service_redirect_policies.aim_id'),
        primary_key=True)
    ip = sa.Column(sa.String(64), primary_key=True)
    mac = sa.Column(sa.String(24))


class ServiceRedirectPolicy(model_base.Base, model_base.HasAimId,
                            model_base.HasName, model_base.HasDisplayName,
                            model_base.HasTenantName,
                            model_base.AttributeMixin,
                            model_base.IsMonitored):
    """DB model for ServiceRedirectPolicy."""

    __tablename__ = 'aim_service_redirect_policies'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    dest = orm.relationship(ServiceRedirectPolicyDestination,
                            backref='redirect_policy',
                            cascade='all, delete-orphan',
                            lazy='joined')

    def from_attr(self, session, res_attr):
        if 'destinations' in res_attr:
            dests = []
            for d in (res_attr.pop('destinations', []) or []):
                if not d.get('ip'):
                    continue
                dests.append(
                    ServiceRedirectPolicyDestination(ip=d['ip'],
                                                     mac=d.get('mac')))
            self.dest = dests
        # map remaining attributes to model
        super(ServiceRedirectPolicy, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(ServiceRedirectPolicy, self).to_attr(session)
        for d in res_attr.pop('dest', []):
            dst = {'ip': d.ip}
            if d.mac is not None:
                dst['mac'] = d.mac
            res_attr.setdefault('destinations', []).append(dst)
        return res_attr


class DeviceClusterContext(model_base.Base, model_base.HasAimId,
                           model_base.HasDisplayName,
                           model_base.HasTenantName,
                           model_base.AttributeMixin,
                           model_base.IsMonitored):
    """DB model for DeviceClusterContext."""

    __tablename__ = 'aim_device_cluster_contexts'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name',
                               'contract_name', 'service_graph_name',
                               'node_name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    contract_name = model_base.name_column(nullable=False)
    service_graph_name = model_base.name_column(nullable=False)
    node_name = model_base.name_column(nullable=False)

    device_cluster_name = model_base.name_column()
    device_cluster_tenant_name = model_base.name_column()
    service_redirect_policy_name = model_base.name_column()
    service_redirect_policy_tenant_name = model_base.name_column()
    bridge_domain_name = model_base.name_column()
    bridge_domain_tenant_name = model_base.name_column()


class DeviceClusterInterfaceContext(model_base.Base, model_base.HasAimId,
                                    model_base.HasDisplayName,
                                    model_base.HasTenantName,
                                    model_base.AttributeMixin,
                                    model_base.IsMonitored):
    """DB model for DeviceClusterContextInterface."""

    __tablename__ = 'aim_device_cluster_if_contexts'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name',
                               'contract_name', 'service_graph_name',
                               'node_name', 'connector_name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    contract_name = model_base.name_column(nullable=False)
    service_graph_name = model_base.name_column(nullable=False)
    node_name = model_base.name_column(nullable=False)
    connector_name = model_base.name_column(nullable=False)

    device_cluster_interface_dn = sa.Column(sa.String(1024))
    service_redirect_policy_dn = sa.Column(sa.String(1024))
    bridge_domain_dn = sa.Column(sa.String(1024))
