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

from aim.db import model_base


class Tenant(model_base.Base, model_base.HasName,
             model_base.HasDisplayName, model_base.AttributeMixin):
    """DB model for Tenant."""

    __tablename__ = 'aim_tenants'


class BridgeDomain(model_base.Base, model_base.HasName,
                   model_base.HasDisplayName, model_base.HasTenantNameKey,
                   model_base.AttributeMixin):
    """DB model for BridgeDomain."""

    __tablename__ = 'aim_bridge_domains'

    vrf_name = model_base.name_column()
    enable_arp_flood = sa.Column(sa.Boolean)
    enable_routing = sa.Column(sa.Boolean)
    limit_ip_learn_to_subnets = sa.Column(sa.Boolean)
    l2_unknown_unicast_mode = sa.Column(sa.String(16))
    ep_move_detect_mode = sa.Column(sa.String(16))


class Subnet(model_base.Base, model_base.HasTenantNameKey,
             model_base.AttributeMixin):
    """DB model for Subnet."""

    __tablename__ = 'aim_subnets'
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ['tenant_name', 'bd_name'],
            ['aim_bridge_domains.tenant_name', 'aim_bridge_domains.name'],
            name='fk_bd'),
        model_base.Base.__table_args__)

    bd_name = model_base.name_column(primary_key=True)
    gw_ip_mask = sa.Column(sa.String(64), primary_key=True)
    display_name = sa.Column(sa.String(256))
    scope = sa.Column(sa.String(16))


class VRF(model_base.Base, model_base.HasName,
          model_base.HasDisplayName, model_base.HasTenantNameKey,
          model_base.AttributeMixin):
    """DB model for BridgeDomain."""

    __tablename__ = 'aim_vrfs'

    policy_enforcement_pref = sa.Column(sa.Integer)


class ApplicationProfile(model_base.Base, model_base.HasName,
                         model_base.HasDisplayName,
                         model_base.HasTenantNameKey,
                         model_base.AttributeMixin):
    """DB model for ApplicationProfile."""

    __tablename__ = 'aim_app_profiles'


class EndpointGroup(model_base.Base, model_base.HasName,
                    model_base.HasDisplayName, model_base.HasTenantNameKey,
                    model_base.AttributeMixin):
    """DB model for EndpointGroup."""

    __tablename__ = 'aim_endpoint_groups'
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ['tenant_name', 'app_profile_name'],
            ['aim_app_profiles.tenant_name', 'aim_app_profiles.name'],
            name='fk_app_profile'),
        model_base.Base.__table_args__)

    app_profile_name = model_base.name_column(primary_key=True)
    bd_name = model_base.name_column()
    bd_tenant_name = model_base.name_column()
    # TODO(amitbose) Map contract names
