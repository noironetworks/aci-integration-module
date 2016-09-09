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
from sqlalchemy import orm

from aim.common import utils
from aim.db import model_base


def to_tuple(obj):
    return obj if isinstance(obj, tuple) else (obj,)


def uniq_column(table, *args, **kwargs):
    name = kwargs.pop('name', None)
    return (sa.UniqueConstraint(
        *args, name=('uniq_' + (name or ('%s_identity' % table)))),
        sa.Index('idx_' + (name or ('%s_identity' % table)), *args))


class Tenant(model_base.Base, model_base.HasDisplayName,
             model_base.AttributeMixin, model_base.IsMonitored):
    """DB model for Tenant."""

    __tablename__ = 'aim_tenants'

    name = model_base.name_column(primary_key=True)


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
    __table_args__ = (uniq_column(__tablename__, 'tenant_name', 'name') +
                      to_tuple(model_base.Base.__table_args__))

    vrf_name = model_base.name_column()
    enable_arp_flood = sa.Column(sa.Boolean)
    enable_routing = sa.Column(sa.Boolean)
    limit_ip_learn_to_subnets = sa.Column(sa.Boolean)
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


class Subnet(model_base.Base, model_base.HasAimId,
             model_base.HasDisplayName,
             model_base.HasTenantName,
             model_base.AttributeMixin, model_base.IsMonitored):
    """DB model for Subnet."""

    __tablename__ = 'aim_subnets'
    __table_args__ = (
        uniq_column(__tablename__, 'tenant_name', 'bd_name', 'gw_ip_mask') +
        (sa.ForeignKeyConstraint(
            ['tenant_name', 'bd_name'],
            ['aim_bridge_domains.tenant_name', 'aim_bridge_domains.name'],
            name='fk_bd'),) +
        to_tuple(model_base.Base.__table_args__))

    bd_name = model_base.name_column(nullable=False)
    gw_ip_mask = sa.Column(sa.String(64), nullable=False)

    scope = sa.Column(sa.String(16))


class VRF(model_base.Base, model_base.HasAimId,
          model_base.HasName, model_base.HasDisplayName,
          model_base.HasTenantName,
          model_base.AttributeMixin, model_base.IsMonitored):
    """DB model for BridgeDomain."""

    __tablename__ = 'aim_vrfs'
    __table_args__ = (uniq_column(__tablename__, 'tenant_name', 'name') +
                      to_tuple(model_base.Base.__table_args__))

    policy_enforcement_pref = sa.Column(sa.String(16))


class ApplicationProfile(model_base.Base, model_base.HasAimId,
                         model_base.HasName, model_base.HasDisplayName,
                         model_base.HasTenantName,
                         model_base.AttributeMixin,
                         model_base.IsMonitored):
    """DB model for ApplicationProfile."""

    __tablename__ = 'aim_app_profiles'
    __table_args__ = (uniq_column(__tablename__, 'tenant_name', 'name') +
                      to_tuple(model_base.Base.__table_args__))


class EndpointGroupContract(model_base.Base):
    """DB model for Contracts used by EndpointGroup."""
    __tablename__ = 'aim_endpoint_group_contracts'

    epg_aim_id = sa.Column(sa.Integer,
                           sa.ForeignKey('aim_endpoint_groups.aim_id'),
                           primary_key=True)
    name = model_base.name_column(primary_key=True)
    provides = sa.Column(sa.Boolean, primary_key=True)


class VMMDomain(model_base.Base, model_base.AttributeMixin):
    """DB model for VMM Domain."""
    __tablename__ = 'aim_vmm_domains'

    type = sa.Column(sa.String(64), primary_key=True)
    name = model_base.name_column(primary_key=True)


class PhysicalDomain(model_base.Base, model_base.AttributeMixin):
    """DB model for VMM Domain."""
    __tablename__ = 'aim_physical_domains'

    name = model_base.name_column(primary_key=True)


class EndpointGroupVMMDomain(model_base.Base):
    """DB model for Contracts used by EndpointGroup."""
    __tablename__ = 'aim_endpoint_group_vmm_domains'
    __table_args__ = (
        (sa.ForeignKeyConstraint(
            ['vmm_type', 'vmm_name'],
            ['aim_vmm_domains.type', 'aim_vmm_domains.name'],
            name='fk_epg'),) +
        to_tuple(model_base.Base.__table_args__))

    epg_aim_id = sa.Column(sa.Integer,
                           sa.ForeignKey('aim_endpoint_groups.aim_id'),
                           primary_key=True)
    vmm_type = sa.Column(sa.String(64), primary_key=True)
    vmm_name = model_base.name_column(primary_key=True)


class EndpointGroupPhysicalDomain(model_base.Base):
    """DB model for Contracts used by EndpointGroup."""
    __tablename__ = 'aim_endpoint_group_physical_domains'
    __table_args__ = (
        (sa.ForeignKeyConstraint(
            ['physdom_name'], ['aim_physical_domains.name'],
            name='fk_epg'),) +
        to_tuple(model_base.Base.__table_args__))

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


class EndpointGroup(model_base.Base, model_base.HasAimId,
                    model_base.HasName, model_base.HasDisplayName,
                    model_base.HasTenantName,
                    ContractRelationMixin, model_base.IsMonitored):
    """DB model for EndpointGroup."""

    __tablename__ = 'aim_endpoint_groups'
    __table_args__ = (
        uniq_column(__tablename__, 'tenant_name', 'app_profile_name', 'name') +
        (sa.ForeignKeyConstraint(
            ['tenant_name', 'app_profile_name'],
            ['aim_app_profiles.tenant_name', 'aim_app_profiles.name'],
            name='fk_app_profile'),) +
        to_tuple(model_base.Base.__table_args__))

    app_profile_name = model_base.name_column(nullable=False)

    bd_name = model_base.name_column()

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

    def from_attr(self, session, res_attr):
        vmm_domains = self.vmm_domains[:]
        physical_domains = self.physical_domains[:]

        if 'openstack_vmm_domain_names' in res_attr:
            vmm_domains = []
            for d in (res_attr.pop('openstack_vmm_domain_names', []) or []):
                vmm_domains.append(EndpointGroupVMMDomain(
                    vmm_name=d, vmm_type=utils.OPENSTACK_VMM_TYPE))
        if 'physical_domain_names' in res_attr:
            physical_domains = []
            for d in (res_attr.pop('physical_domain_names', []) or []):
                physical_domains.append(EndpointGroupPhysicalDomain(
                    physdom_name=d))

        self.vmm_domains = vmm_domains
        self.physical_domains = physical_domains

        # map remaining attributes to model
        super(EndpointGroup, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(EndpointGroup, self).to_attr(session)
        for d in res_attr.pop('vmm_domains', []):
            res_attr.setdefault(
                'openstack_vmm_domain_names', []).append(d.vmm_name)
        for d in res_attr.pop('physical_domains', []):
            res_attr.setdefault('physical_domain_names', []).append(
                d.physdom_name)
        return res_attr


class Filter(model_base.Base, model_base.HasAimId,
             model_base.HasName, model_base.HasDisplayName,
             model_base.HasTenantName, model_base.AttributeMixin,
             model_base.IsMonitored):
    """DB model for Filter."""

    __tablename__ = 'aim_filters'
    __table_args__ = (uniq_column(__tablename__, 'tenant_name', 'name') +
                      to_tuple(model_base.Base.__table_args__))


class FilterEntry(model_base.Base, model_base.HasAimId,
                  model_base.HasName, model_base.HasDisplayName,
                  model_base.HasTenantName, model_base.AttributeMixin,
                  model_base.IsMonitored):
    """DB model for Filter Entry."""

    __tablename__ = 'aim_filter_entries'
    __table_args__ = (
        uniq_column(__tablename__, 'tenant_name', 'filter_name', 'name') +
        (sa.ForeignKeyConstraint(
            ['tenant_name', 'filter_name'],
            ['aim_filters.tenant_name', 'aim_filters.name'],
            name='fk_filter'),) +
        to_tuple(model_base.Base.__table_args__))

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
    __table_args__ = (uniq_column(__tablename__, 'tenant_name', 'name') +
                      to_tuple(model_base.Base.__table_args__))

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
        uniq_column(__tablename__, 'tenant_name', 'contract_name', 'name') +
        (sa.ForeignKeyConstraint(
            ['tenant_name', 'contract_name'],
            ['aim_contracts.tenant_name', 'aim_contracts.name'],
            name='fk_contract'),) +
        to_tuple(model_base.Base.__table_args__))

    contract_name = model_base.name_column(nullable=False)

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
        (sa.ForeignKeyConstraint(
            ['epg_tenant_name', 'epg_app_profile_name', 'epg_name'],
            ['aim_endpoint_groups.tenant_name',
             'aim_endpoint_groups.app_profile_name',
             'aim_endpoint_groups.name'],
            name='fk_epg'),) +
        to_tuple(model_base.Base.__table_args__))

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
    __table_args__ = (uniq_column(__tablename__, 'tenant_name', 'name') +
                      to_tuple(model_base.Base.__table_args__))

    vrf_name = model_base.name_column()
    l3_domain_dn = sa.Column(sa.String(1024))


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
        uniq_column(__tablename__, 'tenant_name', 'l3out_name', 'name') +
        (sa.ForeignKeyConstraint(
            ['tenant_name', 'l3out_name'],
            ['aim_l3outsides.tenant_name', 'aim_l3outsides.name'],
            name='fk_l3out'),) +
        to_tuple(model_base.Base.__table_args__))

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
        uniq_column(__tablename__, 'tenant_name', 'l3out_name',
                    'external_network_name', 'cidr') +
        (sa.ForeignKeyConstraint(
            ['tenant_name', 'l3out_name', 'external_network_name'],
            ['aim_external_networks.tenant_name',
             'aim_external_networks.l3out_name',
             'aim_external_networks.name'],
            name='fk_ext_net'),) +
        to_tuple(model_base.Base.__table_args__))

    l3out_name = model_base.name_column(nullable=False)
    external_network_name = model_base.name_column(nullable=False)
    cidr = sa.Column(sa.String(64), nullable=False)
