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

"""Create table for tenant, subnet, vrf, app-profile and EPG.

Revision ID: 7349fa0a2ad8
Revises: accfe645090a
Create Date: 2016-04-05 17:59:18.910872

"""

# revision identifiers, used by Alembic.
revision = '7349fa0a2ad8'
down_revision = 'accfe645090a'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_tenants',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.PrimaryKeyConstraint('name'))

    op.create_table(
        'aim_subnets',
        sa.Column('bd_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('gw_ip_mask', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('scope', sa.String(16)),
        sa.PrimaryKeyConstraint('gw_ip_mask', 'bd_name', 'tenant_name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'bd_name'],
            ['aim_bridge_domains.tenant_name', 'aim_bridge_domains.name'],
            name='fk_bd'))

    op.create_table(
        'aim_vrfs',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('policy_enforcement_pref', sa.Integer),
        sa.PrimaryKeyConstraint('name', 'tenant_name'))

    op.create_table(
        'aim_app_profiles',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.PrimaryKeyConstraint('tenant_name', 'name'))

    op.create_table(
        'aim_endpoint_groups',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('app_profile_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('bd_name', sa.String(64)),
        sa.Column('bd_tenant_name', sa.String(64)),
        sa.PrimaryKeyConstraint('name', 'app_profile_name', 'tenant_name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'app_profile_name'],
            ['aim_app_profiles.tenant_name', 'aim_app_profiles.name'],
            name='fk_app_profile'))


def downgrade():
    pass
