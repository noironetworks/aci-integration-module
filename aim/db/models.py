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

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy import orm

from aim.common import utils
from aim.db import model_base


class Tenant(model_base.Base, model_base.HasDisplayName,
             model_base.HasAimId, model_base.HasDescription,
             model_base.AttributeMixin, model_base.IsMonitored,
             model_base.HasName):
    """DB model for Tenant."""

    __tablename__ = 'aim_tenants'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))


class Infra(model_base.Base, model_base.AttributeMixin,
            model_base.HasAimId, model_base.HasName):
    __tablename__ = 'aim_infra'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))


class BridgeDomainL3Out(model_base.Base):
    """DB model for L3Outs used by a BridgeDomain."""

    __tablename__ = 'aim_bridge_domain_l3outs'

    bd_aim_id = sa.Column(sa.Integer,
                          sa.ForeignKey('aim_bridge_domains.aim_id'),
                          primary_key=True)
    name = model_base.name_column(primary_key=True)


class BridgeDomain(model_base.Base, model_base.HasAimId,
                   model_base.HasName, model_base.HasDisplayName,
                   model_base.HasTenantName,
                   model_base.AttributeMixin, model_base.IsMonitored):
    """DB model for BridgeDomain."""

    __tablename__ = 'aim_bridge_domains'
    __table_args__ = (model_base.uniq_column(__tablename__, 'tenant_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    vrf_name = model_base.name_column()
    enable_arp_flood = sa.Column(sa.Boolean)
    enable_routing = sa.Column(sa.Boolean)
    limit_ip_learn_to_subnets = sa.Column(sa.Boolean)
    ip_learning = sa.Column(sa.Boolean)
    l2_unknown_unicast_mode = sa.Column(sa.String(16))
    ep_move_detect_mode = sa.Column(sa.String(16))

    l3outs = orm.relationship(BridgeDomainL3Out,
                              backref='bd',
                              cascade='all, delete-orphan',
                              lazy='joined')

    def from_attr(self, session, res_attr):
        if 'l3out_names' in res_attr:
            l3out_names = []
            for l in (res_attr.pop('l3out_names', []) or []):
                l3out_names.append(BridgeDomainL3Out(name=l))
            self.l3outs = l3out_names
        # map remaining attributes to model
        super(BridgeDomain, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(BridgeDomain, self).to_attr(session)
        for l in res_attr.pop('l3outs', []):
            res_attr.setdefault('l3out_names', []).append(l.name)
        return res_attr


class NetflowVMMExporterPol(model_base.Base, model_base.HasDisplayName,
                            model_base.HasAimId, model_base.AttributeMixin,
                            model_base.IsMonitored, model_base.HasName):
    """DB model for Netflow VMM Exporter"""
    __tablename__ = 'aim_netflow_exporter_pol'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    dst_addr = sa.Column(sa.String(64))
    dst_port = sa.Column(sa.String(16))
    src_addr = sa.Column(sa.String(64))
    ver = sa.Column(sa.String(16))


class VmmVswitchPolicyGroup(model_base.Base, model_base.AttributeMixin,
                            model_base.HasAimId, model_base.IsMonitored,
                            model_base.HasDisplayName):
    """DB model for VSwitch Policy Group."""
    __tablename__ = 'aim_vmm_vswitch_pol_grp'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'domain_type', 'domain_name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    domain_name = model_base.name_column(nullable=False)
    domain_type = model_base.name_column(nullable=False)


class VmmRelationToExporterPol(model_base.Base, model_base.AttributeMixin,
                               model_base.HasAimId, model_base.IsMonitored):
    """DB model for Vmm Relation to Exporter Pol."""
    __tablename__ = 'aim_vmm_reln_exporter_pol'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'domain_type', 'domain_name',
                               'netflow_path') +
        model_base.to_tuple(model_base.Base.__table_args__))

    domain_name = model_base.name_column(nullable=False)
    domain_type = model_base.name_column(nullable=False)
    netflow_path = sa.Column(VARCHAR(512, charset='latin1'), nullable=False)
    active_flow_time_out = sa.Column(sa.Integer)
    idle_flow_time_out = sa.Column(sa.Integer)
    sampling_rate = sa.Column(sa.Integer)


class Subnet(model_base.Base, model_base.HasAimId,
             model_base.HasDisplayName,
             model_base.HasTenantName,
             model_base.AttributeMixin, model_base.IsMonitored):
    """DB model for Subnet."""

    __tablename__ = 'aim_subnets'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'bd_name',
                               'gw_ip_mask') +
        model_base.to_tuple(model_base.Base.__table_args__))

    bd_name = model_base.name_column(nullable=False)
    gw_ip_mask = sa.Column(sa.String(64), nullable=False)

    scope = sa.Column(sa.String(16))


class VRF(model_base.Base, model_base.HasAimId,
          model_base.HasName, model_base.HasDisplayName,
          model_base.HasTenantName,
          model_base.AttributeMixin, model_base.IsMonitored):
    """DB model for BridgeDomain."""

    __tablename__ = 'aim_vrfs'
    __table_args__ = (model_base.uniq_column(__tablename__, 'tenant_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    policy_enforcement_pref = sa.Column(sa.String(16))


class ApplicationProfile(model_base.Base, model_base.HasAimId,
                         model_base.HasName, model_base.HasDisplayName,
                         model_base.HasTenantName,
                         model_base.AttributeMixin,
                         model_base.IsMonitored):
    """DB model for ApplicationProfile."""

    __tablename__ = 'aim_app_profiles'
    __table_args__ = (model_base.uniq_column(__tablename__, 'tenant_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))


class EndpointGroupContract(model_base.Base):
    """DB model for Contracts used by EndpointGroup."""
    __tablename__ = 'aim_endpoint_group_contracts'

    epg_aim_id = sa.Column(sa.Integer,
                           sa.ForeignKey('aim_endpoint_groups.aim_id'),
                           primary_key=True)
    name = model_base.name_column(primary_key=True)
    provides = sa.Column(sa.Boolean, primary_key=True)


class VMMPolicy(model_base.Base, model_base.HasDisplayName,
                model_base.HasAimId, model_base.AttributeMixin,
                model_base.IsMonitored):
    """DB model for VMM Domain."""
    __tablename__ = 'aim_vmm_policies'
    __table_args__ = (model_base.uniq_column(__tablename__, 'type') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    type = sa.Column(sa.String(64))


class VMMDomain(model_base.Base, model_base.HasDisplayName,
                model_base.HasAimId, model_base.AttributeMixin,
                model_base.IsMonitored, model_base.HasName):
    """DB model for VMM Domain."""
    __tablename__ = 'aim_vmm_domains'
    __table_args__ = (model_base.uniq_column(__tablename__, 'type', 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    type = sa.Column(sa.String(64))
    enforcement_pref = sa.Column(sa.Enum('sw', 'hw', 'unknown'))
    mode = sa.Column(sa.Enum('default', 'n1kv', 'unknown', 'ovs', 'k8s'))
    mcast_address = sa.Column(sa.String(64))
    encap_mode = sa.Column(sa.Enum('unknown', 'vlan', 'vxlan'))
    pref_encap_mode = sa.Column(sa.Enum('unspecified', 'vlan', 'vxlan'))
    vlan_pool_name = model_base.name_column()
    vlan_pool_type = sa.Column(sa.Enum('static', 'dynamic'))
    mcast_addr_pool_name = model_base.name_column()


class PhysicalDomain(model_base.Base, model_base.HasDisplayName,
                     model_base.HasAimId, model_base.AttributeMixin,
                     model_base.IsMonitored, model_base.HasName):
    """DB model for VMM Domain."""
    __tablename__ = 'aim_physical_domains'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))


class EndpointGroupVMMDomain(model_base.Base):
    """DB model for Contracts used by EndpointGroup."""
    __tablename__ = 'aim_endpoint_group_vmm_domains'

    epg_aim_id = sa.Column(sa.Integer,
                           sa.ForeignKey('aim_endpoint_groups.aim_id'),
                           primary_key=True)
    vmm_type = sa.Column(sa.String(64), primary_key=True)
    vmm_name = model_base.name_column(primary_key=True)


class EndpointGroupPhysicalDomain(model_base.Base):
    """DB model for Contracts used by EndpointGroup."""
    __tablename__ = 'aim_endpoint_group_physical_domains'

    epg_aim_id = sa.Column(sa.Integer,
                           sa.ForeignKey('aim_endpoint_groups.aim_id'),
                           primary_key=True)
    physdom_name = model_base.name_column(primary_key=True)


class ContractRelationMixin(model_base.AttributeMixin):
    """Mixin for model classes that provide/consume contracts."""
    _contract_relation_class = None

    def from_attr(self, session, res_attr):
        provided = [c for c in self.contracts if c.provides]
        consumed = [c for c in self.contracts if not c.provides]

        if 'provided_contract_names' in res_attr:
            provided = []
            for c in (res_attr.pop('provided_contract_names', []) or []):
                provided.append(self._contract_relation_class(
                    name=c, provides=True))
        if 'consumed_contract_names' in res_attr:
            consumed = []
            for c in (res_attr.pop('consumed_contract_names', []) or []):
                consumed.append(self._contract_relation_class(
                    name=c, provides=False))
        self.contracts = provided + consumed
        # map remaining attributes to model
        super(ContractRelationMixin, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(ContractRelationMixin, self).to_attr(session)
        for c in res_attr.pop('contracts', []):
            attr = ('provided_contract_names' if c.provides
                    else 'consumed_contract_names')
            res_attr.setdefault(attr, []).append(c.name)
        return res_attr


class EndpointGroupStaticPath(model_base.Base):
    """DB model for static-paths configured for an EPG."""

    __tablename__ = 'aim_endpoint_group_static_paths'

    epg_aim_id = sa.Column(sa.Integer,
                           sa.ForeignKey('aim_endpoint_groups.aim_id'),
                           primary_key=True)
    # Use VARCHAR with ASCII encoding to work-around MySQL limitations
    # on the length of primary keys
    path = sa.Column(VARCHAR(512, charset='latin1'), primary_key=True)
    host = sa.Column(sa.String(255), nullable=True, index=True)
    mode = sa.Column(sa.Enum('regular', 'native', 'untagged'))
    encap = sa.Column(sa.String(24))


class EndpointGroupContractMasters(model_base.Base):
    """DB model for contract-masters configured for an EPG."""

    __tablename__ = 'aim_endpoint_group_contract_masters'

    epg_aim_id = sa.Column(sa.Integer,
                           sa.ForeignKey('aim_endpoint_groups.aim_id'),
                           primary_key=True)
    app_profile_name = model_base.name_column(primary_key=True)
    name = model_base.name_column(primary_key=True)


class EndpointGroup(model_base.Base, model_base.HasAimId,
                    model_base.HasName, model_base.HasDisplayName,
                    model_base.HasTenantName,
                    ContractRelationMixin, model_base.IsMonitored,
                    model_base.IsSynced):
    """DB model for EndpointGroup."""

    __tablename__ = 'aim_endpoint_groups'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name',
                               'app_profile_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    app_profile_name = model_base.name_column(nullable=False)

    bd_name = model_base.name_column()
    qos_name = model_base.name_column()
    policy_enforcement_pref = sa.Column(sa.String(16))

    _contract_relation_class = EndpointGroupContract
    contracts = orm.relationship(EndpointGroupContract,
                                 backref='epg',
                                 cascade='all, delete-orphan',
                                 lazy='joined')
    vmm_domains = orm.relationship(EndpointGroupVMMDomain,
                                   backref='epg',
                                   cascade='all, delete-orphan',
                                   lazy='joined')
    physical_domains = orm.relationship(EndpointGroupPhysicalDomain,
                                        backref='epg',
                                        cascade='all, delete-orphan',
                                        lazy='joined')
    static_paths = orm.relationship(EndpointGroupStaticPath,
                                    backref='epg',
                                    cascade='all, delete-orphan',
                                    lazy='joined')
    epg_contract_masters = orm.relationship(EndpointGroupContractMasters,
                                            backref='epg',
                                            cascade='all, delete-orphan',
                                            lazy='joined')

    def from_attr(self, session, res_attr):
        vmm_domains = [] if any(
            x in res_attr for x in [
                'openstack_vmm_domain_names',
                'vmm_domains']) else self.vmm_domains[:]
        physical_domains = [] if any(
            x in res_attr for x in [
                'physical_domain_names',
                'physical_domains']) else self.physical_domains[:]
        vmm_ids = set()
        phys_ids = set()

        for d in (res_attr.pop('vmm_domains', []) or []):
            vmm_name = d['name']
            vmm_type = utils.KNOWN_VMM_TYPES.get(d['type'].lower(), d['type'])
            vmm_domains.append(
                EndpointGroupVMMDomain(vmm_name=vmm_name, vmm_type=vmm_type))
            vmm_ids.add((vmm_type, vmm_name))

        for d in (res_attr.pop('physical_domains', []) or []):
            physical_domains.append(
                EndpointGroupPhysicalDomain(physdom_name=d['name']))
            phys_ids.add(d['name'])

        for d in (res_attr.pop('openstack_vmm_domain_names', []) or []):
            vmm_name = d
            vmm_type = utils.OPENSTACK_VMM_TYPE
            if (vmm_type, vmm_name) not in vmm_ids:
                vmm_domains.append(EndpointGroupVMMDomain(
                    vmm_name=d, vmm_type=utils.OPENSTACK_VMM_TYPE))

        for d in (res_attr.pop('physical_domain_names', []) or []):
            if d not in phys_ids:
                physical_domains.append(EndpointGroupPhysicalDomain(
                    physdom_name=d))

        self.vmm_domains = vmm_domains
        self.physical_domains = physical_domains

        if 'static_paths' in res_attr:
            static_paths = []
            for p in (res_attr.pop('static_paths', []) or []):
                if p.get('path') and p.get('encap'):
                    static_paths.append(EndpointGroupStaticPath(
                        path=p['path'], encap=p['encap'],
                        mode=p.get('mode', 'regular'), host=p.get('host', '')))
            self.static_paths = static_paths

        if 'epg_contract_masters' in res_attr:
            epg_contract_masters = []
            for p in (res_attr.pop('epg_contract_masters', []) or []):
                if p.get('app_profile_name') and p.get('name'):
                    epg_contract_masters.append(EndpointGroupContractMasters(
                        app_profile_name=p['app_profile_name'],
                        name=p['name']))
            self.epg_contract_masters = epg_contract_masters

        # map remaining attributes to model
        super(EndpointGroup, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(EndpointGroup, self).to_attr(session)
        for d in res_attr.pop('vmm_domains', []):
            res_attr.setdefault('vmm_domains', []).append(
                {'type': d.vmm_type, 'name': d.vmm_name})
            # NOTE(ivar): backward compatibility
            if d.vmm_type == utils.OPENSTACK_VMM_TYPE:
                res_attr.setdefault(
                    'openstack_vmm_domain_names', []).append(d.vmm_name)
        for d in res_attr.pop('physical_domains', []):
            res_attr.setdefault('physical_domains', []).append(
                {'name': d.physdom_name})
            # NOTE(ivar): backward compatibility
            res_attr.setdefault('physical_domain_names', []).append(
                d.physdom_name)
        for p in res_attr.pop('static_paths', []):
            static_path = {'path': p.path, 'encap': p.encap}
            if p.host:
                static_path['host'] = p.host
            if p.mode and p.mode != 'regular':
                static_path['mode'] = p.mode
            res_attr.setdefault('static_paths', []).append(static_path)
        for p in res_attr.pop('epg_contract_masters', []):
            res_attr.setdefault('epg_contract_masters', []).append(
                {'app_profile_name': p.app_profile_name, 'name': p.name})
        return res_attr


class Filter(model_base.Base, model_base.HasAimId,
             model_base.HasName, model_base.HasDisplayName,
             model_base.HasTenantName, model_base.AttributeMixin,
             model_base.IsMonitored):
    """DB model for Filter."""

    __tablename__ = 'aim_filters'
    __table_args__ = (model_base.uniq_column(__tablename__, 'tenant_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))


class FilterEntry(model_base.Base, model_base.HasAimId,
                  model_base.HasName, model_base.HasDisplayName,
                  model_base.HasTenantName, model_base.AttributeMixin,
                  model_base.IsMonitored):
    """DB model for Filter Entry."""

    __tablename__ = 'aim_filter_entries'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'filter_name',
                               'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    filter_name = model_base.name_column(nullable=False)

    arp_opcode = sa.Column(sa.String(16))
    ether_type = sa.Column(sa.String(16))
    ip_protocol = sa.Column(sa.String(16))
    icmpv4_type = sa.Column(sa.String(16))
    icmpv6_type = sa.Column(sa.String(16))
    source_from_port = sa.Column(sa.String(16))
    source_to_port = sa.Column(sa.String(16))
    dest_from_port = sa.Column(sa.String(16))
    dest_to_port = sa.Column(sa.String(16))
    tcp_flags = sa.Column(sa.String(16))
    stateful = sa.Column(sa.Boolean)
    fragment_only = sa.Column(sa.Boolean)


class Contract(model_base.Base, model_base.HasAimId,
               model_base.HasName, model_base.HasDisplayName,
               model_base.HasTenantName, model_base.AttributeMixin,
               model_base.IsMonitored):
    """DB model for Contract."""

    __tablename__ = 'aim_contracts'
    __table_args__ = (model_base.uniq_column(__tablename__, 'tenant_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    scope = sa.Column(sa.String(24))


class ContractSubjectFilter(model_base.Base):
    """DB model for filters used by Contract Subject."""
    __tablename__ = 'aim_contract_subject_filters'

    subject_aim_id = sa.Column(sa.Integer,
                               sa.ForeignKey('aim_contract_subjects.aim_id'),
                               primary_key=True)
    name = model_base.name_column(primary_key=True)
    direction = sa.Column(sa.Enum('bi', 'in', 'out'), primary_key=True)


class ContractSubject(model_base.Base, model_base.HasAimId,
                      model_base.HasName, model_base.HasDisplayName,
                      model_base.HasTenantName, model_base.AttributeMixin,
                      model_base.IsMonitored):
    """DB model for Contract Subject."""

    __tablename__ = 'aim_contract_subjects'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'contract_name',
                               'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    contract_name = model_base.name_column(nullable=False)
    service_graph_name = model_base.name_column()
    in_service_graph_name = model_base.name_column()
    out_service_graph_name = model_base.name_column()

    filters = orm.relationship(ContractSubjectFilter,
                               backref='contract',
                               cascade='all, delete-orphan',
                               lazy='joined')

    def from_attr(self, session, res_attr):
        ins = [f for f in self.filters if f.direction == 'in']
        outs = [f for f in self.filters if f.direction == 'out']
        bis = [f for f in self.filters if f.direction == 'bi']

        if 'in_filters' in res_attr:
            ins = []
            for f in (res_attr.pop('in_filters', []) or []):
                ins.append(ContractSubjectFilter(name=f, direction='in'))
        if 'out_filters' in res_attr:
            outs = []
            for f in (res_attr.pop('out_filters', []) or []):
                outs.append(ContractSubjectFilter(name=f, direction='out'))
        if 'bi_filters' in res_attr:
            bis = []
            for f in (res_attr.pop('bi_filters', []) or []):
                bis.append(ContractSubjectFilter(name=f, direction='bi'))
        self.filters = ins + outs + bis
        # map remaining attributes to model
        super(ContractSubject, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(ContractSubject, self).to_attr(session)
        for f in res_attr.pop('filters', []):
            if f.direction == 'in':
                attr = 'in_filters'
            elif f.direction == 'out':
                attr = 'out_filters'
            else:
                attr = 'bi_filters'
            res_attr.setdefault(attr, []).append(f.name)
        return res_attr


class Endpoint(model_base.Base, model_base.HasDisplayName,
               model_base.AttributeMixin):
    """DB model for Endpoint."""

    __tablename__ = 'aim_endpoints'
    __table_args__ = (
        model_base.to_tuple(model_base.Base.__table_args__))

    uuid = sa.Column(sa.String(36), primary_key=True)
    epg_tenant_name = model_base.name_column()
    epg_app_profile_name = model_base.name_column()
    epg_name = model_base.name_column()


class L3Outside(model_base.Base, model_base.HasAimId,
                model_base.HasName, model_base.HasDisplayName,
                model_base.HasTenantName, model_base.AttributeMixin,
                model_base.IsMonitored):
    """DB model for L3Outside."""

    __tablename__ = 'aim_l3outsides'
    __table_args__ = (model_base.uniq_column(__tablename__, 'tenant_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    vrf_name = model_base.name_column()
    l3_domain_dn = sa.Column(sa.String(1024))
    bgp_enable = sa.Column(sa.Boolean, nullable=False)


class L3OutNodeProfile(model_base.Base, model_base.HasAimId,
                       model_base.HasName, model_base.HasDisplayName,
                       model_base.HasTenantName, model_base.AttributeMixin,
                       model_base.IsMonitored):
    """DB model for L3OutNodeProfile."""

    __tablename__ = 'aim_l3out_node_profiles'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'l3out_name',
                               'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    l3out_name = model_base.name_column(nullable=False)


class L3OutNode(model_base.Base, model_base.HasAimId,
                model_base.HasTenantName, model_base.AttributeMixin,
                model_base.IsMonitored):
    """DB model for L3OutNode."""

    __tablename__ = 'aim_l3out_nodes'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'l3out_name',
                               'node_profile_name', 'node_path') +
        model_base.to_tuple(model_base.Base.__table_args__))

    l3out_name = model_base.name_column(nullable=False)
    node_profile_name = model_base.name_column(nullable=False)
    # Use VARCHAR with ASCII encoding to work-around MySQL limitations
    # on the length of primary keys
    node_path = sa.Column(VARCHAR(512, charset='latin1'), nullable=False)
    router_id = sa.Column(sa.String(64), nullable=False)
    router_id_loopback = sa.Column(sa.Boolean, nullable=False)


class L3OutNextHop(model_base.Base):
    """DB model for next hops under a L3OutStaticRoute."""

    __tablename__ = 'aim_l3out_next_hops'

    static_route_aim_id = sa.Column(
        sa.Integer, sa.ForeignKey('aim_l3out_static_routes.aim_id'),
        primary_key=True)
    addr = sa.Column(sa.String(64), primary_key=True)
    preference = sa.Column(sa.String(16), nullable=False)


class L3OutStaticRoute(model_base.Base, model_base.HasAimId,
                       model_base.HasDisplayName,
                       model_base.HasTenantName, model_base.AttributeMixin,
                       model_base.IsMonitored):
    """DB model for L3OutStaticRoute."""

    __tablename__ = 'aim_l3out_static_routes'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'l3out_name',
                               'node_profile_name', 'node_path', 'cidr') +
        model_base.to_tuple(model_base.Base.__table_args__))

    l3out_name = model_base.name_column(nullable=False)
    node_profile_name = model_base.name_column(nullable=False)
    # Use VARCHAR with ASCII encoding to work-around MySQL limitations
    # on the length of primary keys
    node_path = sa.Column(VARCHAR(512, charset='latin1'), nullable=False)
    cidr = sa.Column(sa.String(64), nullable=False)
    preference = sa.Column(sa.String(16), nullable=False)
    next_hop_list = orm.relationship(L3OutNextHop,
                                     backref='static_route',
                                     cascade='all, delete-orphan',
                                     lazy='joined')

    def from_attr(self, session, res_attr):
        if 'next_hop_list' in res_attr:
            next_hop_list = []
            for p in (res_attr.pop('next_hop_list', []) or []):
                if p.get('addr') and p.get('preference'):
                    next_hop_list.append(L3OutNextHop(
                        addr=p['addr'], preference=p['preference']))
            self.next_hop_list = next_hop_list

        # map remaining attributes to model
        super(L3OutStaticRoute, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(L3OutStaticRoute, self).to_attr(session)
        for p in res_attr.pop('next_hop_list', []):
            res_attr.setdefault('next_hop_list', []).append(
                {'addr': p.addr,
                 'preference': p.preference})
        return res_attr


class L3OutInterfaceProfile(model_base.Base, model_base.HasAimId,
                            model_base.HasName, model_base.HasDisplayName,
                            model_base.HasTenantName,
                            model_base.AttributeMixin,
                            model_base.IsMonitored):
    """DB model for L3OutInterfaceProfile."""

    __tablename__ = 'aim_l3out_interface_profiles'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'l3out_name',
                               'node_profile_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    l3out_name = model_base.name_column(nullable=False)
    node_profile_name = model_base.name_column(nullable=False)


class L3OutInterfaceSecondaryIpA(model_base.Base):
    """DB model for secondary IPs under an Interface."""

    __tablename__ = 'aim_l3out_interface_secondary_ip_a'

    interface_aim_id = sa.Column(
        sa.Integer, sa.ForeignKey('aim_l3out_interfaces.aim_id'),
        primary_key=True)
    addr = sa.Column(sa.String(64), primary_key=True)


class L3OutInterfaceSecondaryIpB(model_base.Base):
    """DB model for secondary IPs under an Interface."""

    __tablename__ = 'aim_l3out_interface_secondary_ip_b'

    interface_aim_id = sa.Column(
        sa.Integer, sa.ForeignKey('aim_l3out_interfaces.aim_id'),
        primary_key=True)
    addr = sa.Column(sa.String(64), primary_key=True)


class L3OutInterface(model_base.Base, model_base.HasAimId,
                     model_base.HasTenantName, model_base.AttributeMixin,
                     model_base.IsMonitored):
    """DB model for L3OutInterface."""

    __tablename__ = 'aim_l3out_interfaces'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'l3out_name',
                               'node_profile_name', 'interface_profile_name',
                               'interface_path') +
        model_base.to_tuple(model_base.Base.__table_args__))

    l3out_name = model_base.name_column(nullable=False)
    node_profile_name = model_base.name_column(nullable=False)
    interface_profile_name = model_base.name_column(nullable=False)
    # Use VARCHAR with ASCII encoding to work-around MySQL limitations
    # on the length of primary keys
    interface_path = sa.Column(VARCHAR(512, charset='latin1'), nullable=False)
    encap = sa.Column(sa.String(24), nullable=False)
    mode = sa.Column(sa.Enum('regular', 'native', 'untagged'))
    type = sa.Column(sa.String(16), nullable=False)
    host = sa.Column(sa.String(255), nullable=True, index=True)
    primary_addr_a = sa.Column(sa.String(64), nullable=False)
    primary_addr_b = sa.Column(sa.String(64))
    secondary_addr_a_list = orm.relationship(L3OutInterfaceSecondaryIpA,
                                             backref='interface_a',
                                             cascade='all, delete-orphan',
                                             lazy='joined')
    secondary_addr_b_list = orm.relationship(L3OutInterfaceSecondaryIpB,
                                             backref='interface_b',
                                             cascade='all, delete-orphan',
                                             lazy='joined')

    def from_attr(self, session, res_attr):
        primary_addr_a = res_attr.get('primary_addr_a', '')
        if primary_addr_a and 'secondary_addr_a_list' in res_attr:
            addr_list = []
            for p in (res_attr.pop('secondary_addr_a_list', []) or []):
                if p.get('addr'):
                    addr_list.append(
                        L3OutInterfaceSecondaryIpA(addr=p['addr']))
            self.secondary_addr_a_list = addr_list

        primary_addr_b = res_attr.get('primary_addr_b', '')
        if primary_addr_b and 'secondary_addr_b_list' in res_attr:
            addr_list = []
            for p in (res_attr.pop('secondary_addr_b_list', []) or []):
                if p.get('addr'):
                    addr_list.append(
                        L3OutInterfaceSecondaryIpB(addr=p['addr']))
            self.secondary_addr_b_list = addr_list

        # map remaining attributes to model
        super(L3OutInterface, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(L3OutInterface, self).to_attr(session)
        for p in res_attr.pop('secondary_addr_a_list', []):
            res_attr.setdefault('secondary_addr_a_list', []).append(
                {'addr': p.addr})
        for p in res_attr.pop('secondary_addr_b_list', []):
            res_attr.setdefault('secondary_addr_b_list', []).append(
                {'addr': p.addr})
        return res_attr


class ExternalNetworkContract(model_base.Base):
    """DB model for Contracts used by ExternalNetwork."""
    __tablename__ = 'aim_external_network_contracts'

    ext_net_aim_id = sa.Column(sa.Integer,
                               sa.ForeignKey('aim_external_networks.aim_id'),
                               primary_key=True)
    name = model_base.name_column(primary_key=True)
    provides = sa.Column(sa.Boolean, primary_key=True)


class ExternalNetwork(model_base.Base, model_base.HasAimId,
                      model_base.HasName, model_base.HasDisplayName,
                      model_base.HasTenantName,
                      ContractRelationMixin, model_base.IsMonitored):
    """DB model for ExternalNetwork."""

    __tablename__ = 'aim_external_networks'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'l3out_name',
                               'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    l3out_name = model_base.name_column(nullable=False)

    nat_epg_dn = sa.Column(sa.String(1024))

    _contract_relation_class = ExternalNetworkContract
    contracts = orm.relationship(ExternalNetworkContract,
                                 backref='extnet',
                                 cascade='all, delete-orphan',
                                 lazy='joined')


class ExternalSubnet(model_base.Base, model_base.HasAimId,
                     model_base.HasDisplayName,
                     model_base.HasTenantName, model_base.AttributeMixin,
                     model_base.IsMonitored):
    """DB model for ExternalSubnet."""

    __tablename__ = 'aim_external_subnets'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'l3out_name',
                               'external_network_name', 'cidr') +
        model_base.to_tuple(model_base.Base.__table_args__))

    l3out_name = model_base.name_column(nullable=False)
    external_network_name = model_base.name_column(nullable=False)
    cidr = sa.Column(sa.String(64), nullable=False)
    aggregate = sa.Column(sa.String(64), nullable=False)
    scope = sa.Column(sa.String(64), nullable=False)


class SecurityGroup(model_base.Base, model_base.HasAimId,
                    model_base.HasName, model_base.HasDisplayName,
                    model_base.HasTenantName, model_base.AttributeMixin,
                    model_base.IsMonitored):
    """DB model for SecurityGroup."""

    __tablename__ = 'aim_security_groups'
    __table_args__ = (model_base.uniq_column(__tablename__, 'tenant_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))


class SecurityGroupSubject(model_base.Base, model_base.HasAimId,
                           model_base.HasName, model_base.HasDisplayName,
                           model_base.HasTenantName,
                           model_base.AttributeMixin,
                           model_base.IsMonitored):
    """DB model SecurityGroup Subject."""
    __tablename__ = 'aim_security_group_subjects'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name',
                               'security_group_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    security_group_name = model_base.name_column(nullable=False)


class SecurityGroupRuleRemoteIp(model_base.Base):
    __tablename__ = 'aim_security_group_rule_remote_ips'

    security_group_rule_aim_id = sa.Column(
        sa.Integer, sa.ForeignKey('aim_security_group_rules.aim_id'),
        primary_key=True)
    cidr = sa.Column(sa.String(64), nullable=False, primary_key=True)


class SecurityGroupRule(model_base.Base, model_base.HasAimId,
                        model_base.HasName, model_base.HasDisplayName,
                        model_base.HasTenantName,
                        model_base.AttributeMixin,
                        model_base.IsMonitored):
    """DB model SecurityGroup Subject."""
    __tablename__ = 'aim_security_group_rules'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name',
                               'security_group_name',
                               'security_group_subject_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))
    security_group_name = model_base.name_column(nullable=False)
    security_group_subject_name = model_base.name_column(nullable=False)
    remote_ips = orm.relationship(SecurityGroupRuleRemoteIp,
                                  backref='security_group_rule',
                                  cascade='all, delete-orphan',
                                  lazy='joined')
    direction = sa.Column(sa.String(16))
    ethertype = sa.Column(sa.String(16))
    ip_protocol = sa.Column(sa.String(16))
    from_port = sa.Column(sa.String(16))
    to_port = sa.Column(sa.String(16))
    conn_track = sa.Column(sa.String(25))
    icmp_code = sa.Column(sa.String(16))
    icmp_type = sa.Column(sa.String(16))
    remote_group_id = sa.Column(sa.String(64), nullable=False)

    def from_attr(self, session, res_attr):
        if 'remote_ips' in res_attr:
            # list of IPs has same order as DB objects
            old_ip_list = [x.cidr for x in self.remote_ips]
            # Use sets to calculate additions and deletions
            old_set = set(old_ip_list)
            new_set = set(res_attr['remote_ips'])
            # For deletions, start from the end of the list to preserve order
            deletion_indexes = [old_ip_list.index(ip)
                                for ip in (old_set - new_set)]
            deletion_indexes.sort()
            if deletion_indexes:
                for index in deletion_indexes[::-1]:
                    self.remote_ips.pop(index)
            for ip in (new_set - old_set):
                self.remote_ips.append(
                    SecurityGroupRuleRemoteIp(cidr=ip))
            res_attr.pop('remote_ips')

        # map remaining attributes to model
        super(SecurityGroupRule, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(SecurityGroupRule, self).to_attr(session)
        res_attr['remote_ips'] = [x.cidr for x in res_attr['remote_ips']]
        return res_attr


class Pod(model_base.Base, model_base.HasAimId, model_base.AttributeMixin,
          model_base.IsMonitored, model_base.HasName):
    """DB model for VMM Domain."""
    __tablename__ = 'aim_pods'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))


class Topology(model_base.Base, model_base.AttributeMixin,
               model_base.HasAimId, model_base.HasName):
    __tablename__ = 'aim_topologies'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))


class VMMController(model_base.Base, model_base.HasDisplayName,
                    model_base.HasAimId, model_base.AttributeMixin,
                    model_base.IsMonitored, model_base.HasName):
    """DB model for VMM Controller."""
    __tablename__ = 'aim_vmm_controllers'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'domain_type', 'domain_name',
                               'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    domain_name = model_base.name_column(nullable=False)
    domain_type = model_base.name_column(nullable=False)

    scope = sa.Column(sa.Enum('unmanaged', 'vm', 'iaas', 'network',
                              'MicrosoftSCVMM', 'openstack', 'kubernetes'))
    root_cont_name = sa.Column(sa.String(64))
    host_or_ip = sa.Column(sa.String(128))
    mode = sa.Column(sa.Enum('default', 'n1kv', 'unknown', 'ovs', 'k8s'))


class VmmInjectedNamespace(model_base.Base, model_base.HasAimId,
                           model_base.HasName, model_base.HasDisplayName,
                           model_base.AttributeMixin):
    """DB model VmmInjectedNamespace."""
    __tablename__ = 'aim_vmm_inj_namespaces'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'domain_type', 'domain_name',
                               'controller_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    domain_type = model_base.name_column(nullable=False)
    domain_name = model_base.name_column(nullable=False)
    controller_name = model_base.name_column(nullable=False)


class VmmInjectedDeployment(model_base.Base, model_base.HasAimId,
                            model_base.HasName, model_base.HasDisplayName,
                            model_base.AttributeMixin):
    """DB model VmmInjectedDeployment."""
    __tablename__ = 'aim_vmm_inj_deployments'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'domain_type', 'domain_name',
                               'controller_name', 'namespace_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    domain_type = model_base.name_column(nullable=False)
    domain_name = model_base.name_column(nullable=False)
    controller_name = model_base.name_column(nullable=False)
    namespace_name = model_base.name_column(nullable=False)

    replicas = sa.Column(sa.Integer)


class VmmInjectedReplicaSet(model_base.Base, model_base.HasAimId,
                            model_base.HasName, model_base.HasDisplayName,
                            model_base.AttributeMixin):
    """DB model VmmInjectedReplicaSet."""
    __tablename__ = 'aim_vmm_inj_replica_sets'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'domain_type', 'domain_name',
                               'controller_name', 'namespace_name',
                               'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    domain_type = model_base.name_column(nullable=False)
    domain_name = model_base.name_column(nullable=False)
    controller_name = model_base.name_column(nullable=False)
    namespace_name = model_base.name_column(nullable=False)
    deployment_name = model_base.name_column()


class VmmInjectedServicePort(model_base.Base):
    """DB model service_ports used by VmmInjectedService."""
    __tablename__ = 'aim_vmm_inj_service_ports'

    svc_aim_id = sa.Column(
        sa.Integer, sa.ForeignKey('aim_vmm_inj_services.aim_id'),
        primary_key=True)
    port = sa.Column(sa.String(32), nullable=False, primary_key=True)
    protocol = sa.Column(sa.String(32), nullable=False, primary_key=True)
    target_port = sa.Column(sa.String(32), nullable=False, primary_key=True)
    node_port = sa.Column(sa.String(32))


class VmmInjectedServiceEndpoint(model_base.Base):
    """DB model endpoints used by VmmInjectedService."""
    __tablename__ = 'aim_vmm_inj_service_endpoints'

    svc_aim_id = sa.Column(
        sa.Integer, sa.ForeignKey('aim_vmm_inj_services.aim_id'),
        primary_key=True)
    ip = sa.Column(sa.String(64), primary_key=True)
    pod_name = model_base.name_column(primary_key=True)


class VmmInjectedService(model_base.Base, model_base.HasAimId,
                         model_base.HasName, model_base.HasDisplayName,
                         model_base.AttributeMixin):
    """DB model VmmInjectedService."""
    __tablename__ = 'aim_vmm_inj_services'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'domain_type', 'domain_name',
                               'controller_name', 'namespace_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    domain_type = model_base.name_column(nullable=False)
    domain_name = model_base.name_column(nullable=False)
    controller_name = model_base.name_column(nullable=False)
    namespace_name = model_base.name_column(nullable=False)
    service_type = sa.Column(sa.Enum('clusterIp', 'externalName',
                                     'nodePort', 'loadBalancer'))
    cluster_ip = sa.Column(sa.String(64))
    load_balancer_ip = sa.Column(sa.String(64))

    ports = orm.relationship(VmmInjectedServicePort,
                             backref='service',
                             cascade='all, delete-orphan',
                             lazy='joined')
    eps = orm.relationship(VmmInjectedServiceEndpoint,
                           backref='service',
                           cascade='all, delete-orphan',
                           lazy='joined')

    def from_attr(self, session, res_attr):
        if 'service_ports' in res_attr:
            ports = []
            for p in (res_attr.pop('service_ports', []) or []):
                if not (p.get('port') and p.get('target_port') and
                        p.get('protocol')):
                    continue
                ports.append(VmmInjectedServicePort(**p))
            self.ports = ports
        if 'endpoints' in res_attr:
            eps = []
            for e in (res_attr.pop('endpoints', []) or []):
                if e.get('ip') and e.get('pod_name'):
                    eps.append(VmmInjectedServiceEndpoint(**e))
            self.eps = eps
        # map remaining attributes to model
        super(VmmInjectedService, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(VmmInjectedService, self).to_attr(session)
        for p in res_attr.pop('ports', []):
            port = {'port': p.port, 'protocol': p.protocol,
                    'target_port': p.target_port}
            if p.node_port is not None:
                port['node_port'] = p.node_port
            res_attr.setdefault('service_ports', []).append(port)
        for e in res_attr.pop('eps', []):
            res_attr.setdefault('endpoints',
                                []).append({'ip': e.ip,
                                            'pod_name': e.pod_name})
        return res_attr


class VmmInjectedHost(model_base.Base, model_base.HasAimId,
                      model_base.HasName, model_base.HasDisplayName,
                      model_base.AttributeMixin):
    """DB model VmmInjectedHost."""
    __tablename__ = 'aim_vmm_inj_hosts'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'domain_type', 'domain_name',
                               'controller_name', 'name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    domain_type = model_base.name_column(nullable=False)
    domain_name = model_base.name_column(nullable=False)
    controller_name = model_base.name_column(nullable=False)

    host_name = sa.Column(sa.String(128))
    kernel_version = sa.Column(sa.String(32))
    os = sa.Column(sa.String(64))


class VmmInjectedContGroup(model_base.Base, model_base.HasAimId,
                           model_base.HasName, model_base.HasDisplayName,
                           model_base.AttributeMixin):
    """DB model VmmInjectedContGroup."""
    __tablename__ = 'aim_vmm_inj_cont_groups'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'domain_type', 'domain_name',
                               'controller_name', 'namespace_name') +
        model_base.to_tuple(model_base.Base.__table_args__))

    domain_type = model_base.name_column(nullable=False)
    domain_name = model_base.name_column(nullable=False)
    controller_name = model_base.name_column(nullable=False)
    namespace_name = model_base.name_column(nullable=False)

    host_name = model_base.name_column(nullable=False)
    compute_node_name = model_base.name_column(nullable=False)
    replica_set_name = model_base.name_column(nullable=False)


class L3OutInterfaceBgpPeerP(model_base.Base, model_base.HasAimId,
                             model_base.HasTenantName,
                             model_base.AttributeMixin,
                             model_base.IsMonitored):
    """DB model for BgpPeerConnectivityProfile."""
    __tablename__ = 'aim_l3out_interface_bgp_peer_prefix'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'tenant_name', 'l3out_name',
                               'node_profile_name', 'interface_profile_name',
                               'interface_path', 'addr') +
        model_base.to_tuple(model_base.Base.__table_args__))
    l3out_name = model_base.name_column(nullable=False)
    node_profile_name = model_base.name_column(nullable=False)
    interface_profile_name = model_base.name_column(nullable=False)
    interface_path = sa.Column(VARCHAR(512, charset='latin1'), nullable=False)
    addr = sa.Column(sa.String(64), nullable=False)
    asn = sa.Column(sa.BigInteger)

    def to_attr(self, session):
        res_attr = super(L3OutInterfaceBgpPeerP, self).to_attr(session)
        if 'asn' in res_attr:
            res_attr['asn'] = str(res_attr['asn'])
        return res_attr


class QosRequirement(model_base.Base, model_base.HasAimId,
                     model_base.HasName, model_base.HasDisplayName,
                     model_base.HasTenantName, model_base.AttributeMixin,
                     model_base.IsMonitored):
    """DB model for QosRequirement."""

    __tablename__ = 'aim_qos_requirement'
    __table_args__ = (model_base.uniq_column(__tablename__, 'tenant_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))
    egress_dpp_pol = sa.Column(sa.String(64))
    ingress_dpp_pol = sa.Column(sa.String(64))

    dscp = orm.relationship("QosDscpMarking",
                            backref=orm.backref("qos_requirement"),
                            uselist=False,
                            cascade='all, delete-orphan', lazy='joined')

    def from_attr(self, session, res_attr):
        if 'dscp' in res_attr:
            dscp = res_attr.pop('dscp', None)
            if dscp:
                self.dscp = QosDscpMarking(mark=dscp)
            else:
                self.dscp = None

        # map remaining attributes to model
        super(QosRequirement, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(QosRequirement, self).to_attr(session)

        d = res_attr.pop('dscp', None)
        if d:
            res_attr['dscp'] = d.mark
        else:
            res_attr['dscp'] = None

        return res_attr


class QosDppPol(model_base.Base, model_base.HasAimId,
                model_base.HasName, model_base.HasDisplayName,
                model_base.HasTenantName,
                model_base.AttributeMixin,
                model_base.IsMonitored):
    """DB model Qos Datapath Policing Policy."""
    __tablename__ = 'aim_qos_dpp_pol'
    __table_args__ = (model_base.uniq_column(__tablename__, 'tenant_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    rate = sa.Column(sa.BigInteger)
    pir = sa.Column(sa.BigInteger)
    type = sa.Column(sa.String(16))
    mode = sa.Column(sa.String(16))
    burst = sa.Column(sa.String(16))
    be = sa.Column(sa.String(16))
    rate_unit = sa.Column(sa.String(16))
    burst_unit = sa.Column(sa.String(16))
    pir_unit = sa.Column(sa.String(16))
    be_unit = sa.Column(sa.String(16))
    conform_action = sa.Column(sa.String(16))
    exceed_action = sa.Column(sa.String(16))
    violate_action = sa.Column(sa.String(16))
    conform_mark_dscp = sa.Column(sa.String(16))
    exceed_mark_dscp = sa.Column(sa.String(16))
    violate_mark_dscp = sa.Column(sa.String(16))
    conform_mark_cos = sa.Column(sa.String(16))
    exceed_mark_cos = sa.Column(sa.String(16))
    violate_mark_cos = sa.Column(sa.String(16))
    admin_st = sa.Column(sa.String(16))
    sharing_mode = sa.Column(sa.String(16))


class QosDscpMarking(model_base.Base):
    """DB model Qos Dscp Marking."""
    __tablename__ = 'aim_qos_dscp_marking'

    qos_requirement_aim_id = sa.Column(
        sa.String(255), sa.ForeignKey('aim_qos_requirement.aim_id'),
        primary_key=True)
    mark = sa.Column(sa.SmallInteger)


class SpanVsourceGroup(model_base.Base, model_base.HasDisplayName,
                       model_base.HasAimId, model_base.AttributeMixin,
                       model_base.IsMonitored, model_base.HasName):
    """DB model for ERSPAN VSource Group"""

    __tablename__ = 'aim_span_vsource_grp'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    admin_st = sa.Column(sa.Enum('start', 'stop'))


class SpanSrcPath(model_base.Base):
    """DB model for static-paths configured for an EPG."""

    __tablename__ = 'aim_span_src_paths'

    vsrc_aim_id = sa.Column(sa.String(64),
                            sa.ForeignKey('aim_span_vsource.aim_id'),
                            primary_key=True)

    path = sa.Column(sa.String(255), nullable=False, primary_key=True)


class SpanVsource(model_base.Base, model_base.HasDisplayName,
                  model_base.HasAimId, model_base.AttributeMixin,
                  model_base.IsMonitored, model_base.HasName):
    """DB model for ERSPAN VSource"""

    __tablename__ = 'aim_span_vsource'
    __table_args__ = (model_base.uniq_column(__tablename__, 'vsg_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    vsg_name = model_base.name_column(nullable=False)
    dir = sa.Column(sa.Enum('in', 'out', 'both'))

    paths = orm.relationship(SpanSrcPath,
                             backref='span_vsrc',
                             cascade='all, delete-orphan',
                             lazy='joined')

    def from_attr(self, session, res_attr):
        if 'src_paths' in res_attr:
            src_paths = []
            for l in (res_attr.pop('src_paths', []) or []):
                src_paths.append(SpanSrcPath(path=l))
            self.paths = src_paths

        # map remaining attributes to model
        super(SpanVsource, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(SpanVsource, self).to_attr(session)
        for l in res_attr.pop('paths', []):
            res_attr.setdefault('src_paths', []).append(l.path)
        return res_attr


class SpanVdestGroup(model_base.Base, model_base.HasDisplayName,
                     model_base.HasAimId, model_base.AttributeMixin,
                     model_base.IsMonitored, model_base.HasName):
    """DB model for ERSPAN VDest Group"""

    __tablename__ = 'aim_span_vdest_grp'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))


class SpanVdest(model_base.Base, model_base.HasDisplayName,
                model_base.HasAimId, model_base.AttributeMixin,
                model_base.IsMonitored, model_base.HasName):
    """DB model for ERSPAN VDest"""

    __tablename__ = 'aim_span_vdest'
    __table_args__ = (model_base.uniq_column(__tablename__, 'vdg_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    vdg_name = model_base.name_column(nullable=False)


class SpanVepgSummary(model_base.Base, model_base.HasDisplayName,
                      model_base.HasAimId, model_base.AttributeMixin,
                      model_base.IsMonitored):
    """DB model for ERSPAN Vepg Summary"""

    __tablename__ = 'aim_span_vepg_summary'
    __table_args__ = (model_base.uniq_column(__tablename__, 'vdg_name',
                                             'vd_name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    vdg_name = model_base.name_column(nullable=False)
    vd_name = model_base.name_column(nullable=False)
    dst_ip = sa.Column(sa.String(64), nullable=False)
    flow_id = sa.Column(sa.Integer)
    ttl = sa.Column(sa.Integer)
    mtu = sa.Column(sa.Integer)
    mode = sa.Column(sa.Enum('visible', 'not-visible'))
    src_ip_prefix = sa.Column(sa.String(64))
    dscp = sa.Column(sa.Integer)


class InfraRspanVsrcGroup(model_base.Base):
    """DB model for source relation to all eps using acc bndle groups"""

    __tablename__ = 'aim_infra_rspan_vsrc_grp'

    accgrp_aim_id = sa.Column(sa.String(64),
                              sa.ForeignKey('aim_infra_acc_bundle_grp.aim_id'),
                              primary_key=True)
    name = model_base.name_column(primary_key=True)


class InfraRspanVdestGroup(model_base.Base):
    """DB model for source relation to all eps using acc bndle groups"""

    __tablename__ = 'aim_infra_rspan_vdest_grp'

    accgrp_aim_id = sa.Column(sa.String(64),
                              sa.ForeignKey('aim_infra_acc_bundle_grp.aim_id'),
                              primary_key=True)
    name = model_base.name_column(primary_key=True)


class InfraAccBundleGroup(model_base.Base, model_base.HasDisplayName,
                          model_base.HasAimId, model_base.AttributeMixin,
                          model_base.IsMonitored, model_base.HasName):
    """DB model for bundle interface group"""

    __tablename__ = 'aim_infra_acc_bundle_grp'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    lag_t = sa.Column(sa.Enum('link', 'node'))

    vsource_grps = orm.relationship(InfraRspanVsrcGroup,
                                    backref='acc_bundle',
                                    cascade='all, delete-orphan',
                                    lazy='joined')

    vdest_grps = orm.relationship(InfraRspanVdestGroup,
                                  backref='acc_bundle',
                                  cascade='all, delete-orphan',
                                  lazy='joined')

    def from_attr(self, session, res_attr):
        if 'span_vsource_group_names' in res_attr:
            span_vsource_group_names = []
            for l in (res_attr.pop('span_vsource_group_names', []) or []):
                span_vsource_group_names.append(InfraRspanVsrcGroup(name=l))
            self.vsource_grps = span_vsource_group_names

        if 'span_vdest_group_names' in res_attr:
            span_vdest_group_names = []
            for l in (res_attr.pop('span_vdest_group_names', []) or []):
                span_vdest_group_names.append(InfraRspanVdestGroup(name=l))
            self.vdest_grps = span_vdest_group_names
        # map remaining attributes to model
        super(InfraAccBundleGroup, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(InfraAccBundleGroup, self).to_attr(session)
        for l in res_attr.pop('vsource_grps', []):
            res_attr.setdefault('span_vsource_group_names', []).append(l.name)
        for l in res_attr.pop('vdest_grps', []):
            res_attr.setdefault('span_vdest_group_names', []).append(l.name)
        return res_attr


class InfraRspanVsrcApGroup(model_base.Base):
    """DB model for source relation to all eps using acc ports groups"""

    __tablename__ = 'aim_infra_rspan_vsrc_ap_grp'

    accport_aim_id = sa.Column(sa.String(64),
                               sa.ForeignKey('aim_infra_acc_port_grp.aim_id'),
                               primary_key=True)
    name = model_base.name_column(primary_key=True)


class InfraRspanVdestApGroup(model_base.Base):
    """DB model for source relation to all eps using acc ports groups"""

    __tablename__ = 'aim_infra_rspan_vdest_ap_grp'

    accport_aim_id = sa.Column(sa.String(64),
                               sa.ForeignKey('aim_infra_acc_port_grp.aim_id'),
                               primary_key=True)
    name = model_base.name_column(primary_key=True)


class InfraAccPortGroup(model_base.Base, model_base.HasDisplayName,
                        model_base.HasAimId, model_base.AttributeMixin,
                        model_base.IsMonitored, model_base.HasName):
    """DB model for interface policy group"""

    __tablename__ = 'aim_infra_acc_port_grp'
    __table_args__ = (model_base.uniq_column(__tablename__, 'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    vsource_grps = orm.relationship(InfraRspanVsrcApGroup,
                                    backref='acc_port',
                                    cascade='all, delete-orphan',
                                    lazy='joined')

    vdest_grps = orm.relationship(InfraRspanVdestApGroup,
                                  backref='acc_port',
                                  cascade='all, delete-orphan',
                                  lazy='joined')

    def from_attr(self, session, res_attr):
        if 'span_vsource_group_names' in res_attr:
            span_vsource_group_names = []
            for l in (res_attr.pop('span_vsource_group_names', []) or []):
                span_vsource_group_names.append(InfraRspanVsrcApGroup(name=l))
            self.vsource_grps = span_vsource_group_names
        if 'span_vdest_group_names' in res_attr:
            span_vdest_group_names = []
            for l in (res_attr.pop('span_vdest_group_names', []) or []):
                span_vdest_group_names.append(InfraRspanVdestApGroup(name=l))
            self.vdest_grps = span_vdest_group_names
        # map remaining attributes to model
        super(InfraAccPortGroup, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(InfraAccPortGroup, self).to_attr(session)
        for l in res_attr.pop('vsource_grps', []):
            res_attr.setdefault('span_vsource_group_names', []).append(l.name)
        for l in res_attr.pop('vdest_grps', []):
            res_attr.setdefault('span_vdest_group_names', []).append(l.name)
        return res_attr


class SpanSpanlbl(model_base.Base, model_base.HasDisplayName,
                  model_base.HasAimId, model_base.AttributeMixin,
                  model_base.IsMonitored, model_base.HasName):
    """DB model for ERSPAN VSource"""

    __tablename__ = 'aim_span_spanlbl'
    __table_args__ = (model_base.uniq_column(__tablename__, 'vsg_name',
                                             'name') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    vsg_name = model_base.name_column(nullable=False)
    tag = sa.Column(sa.String(64))
