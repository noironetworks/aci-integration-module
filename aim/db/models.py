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

from aim.db import model_base


def to_tuple(obj):
    return obj if isinstance(obj, tuple) else (obj,)


def uniq_column(table, *args):
    return (sa.UniqueConstraint(*args, name=('uniq_%s_identity' % table)),
            sa.Index('idx_%s_identity' % table, *args))


class Tenant(model_base.Base, model_base.HasDisplayName,
             model_base.AttributeMixin):
    """DB model for Tenant."""

    __tablename__ = 'aim_tenants'

    name = model_base.name_column(primary_key=True)


class BridgeDomain(model_base.Base, model_base.HasAimId,
                   model_base.HasName, model_base.HasDisplayName,
                   model_base.HasTenantName,
                   model_base.AttributeMixin):
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


class Subnet(model_base.Base, model_base.HasAimId,
             model_base.HasDisplayName,
             model_base.HasTenantName,
             model_base.AttributeMixin):
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
          model_base.AttributeMixin):
    """DB model for BridgeDomain."""

    __tablename__ = 'aim_vrfs'
    __table_args__ = (uniq_column(__tablename__, 'tenant_name', 'name') +
                      to_tuple(model_base.Base.__table_args__))

    policy_enforcement_pref = sa.Column(sa.Integer)


class ApplicationProfile(model_base.Base, model_base.HasAimId,
                         model_base.HasName, model_base.HasDisplayName,
                         model_base.HasTenantName,
                         model_base.AttributeMixin):
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


class EndpointGroup(model_base.Base, model_base.HasAimId,
                    model_base.HasName, model_base.HasDisplayName,
                    model_base.HasTenantName,
                    model_base.AttributeMixin):
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
    bd_tenant_name = model_base.name_column()

    contracts = orm.relationship(EndpointGroupContract,
                                 backref='epg',
                                 cascade='all, delete-orphan',
                                 lazy='joined')

    def from_attr(self, session, res_attr):
        self.contracts = []
        for c in (res_attr.pop('provided_contract_names', []) or []):
            self.contracts.append(EndpointGroupContract(name=c,
                                                        provides=True))
        for c in (res_attr.pop('consumed_contract_names', []) or []):
            self.contracts.append(EndpointGroupContract(name=c,
                                                        provides=False))
        # map remaining attributes to model
        super(EndpointGroup, self).from_attr(session, res_attr)

    def to_attr(self, session):
        res_attr = super(EndpointGroup, self).to_attr(session)
        for c in res_attr.pop('contracts', []):
            attr = ('provided_contract_names' if c.provides
                    else 'consumed_contract_names')
            res_attr.setdefault(attr, []).append(c.name)
        return res_attr
