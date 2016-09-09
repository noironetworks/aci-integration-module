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

"""Tables for L3out

Revision ID: 8e313fbeb93b
Revises: 74f15b6aee51
Create Date: 2016-08-08 16:23:26.119724

"""

# revision identifiers, used by Alembic.
revision = '8e313fbeb93b'
down_revision = '1249face3348'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        'aim_bridge_domain_l3outs',
        sa.Column('bd_aim_id', sa.Integer, nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('bd_aim_id', 'name'),
        sa.ForeignKeyConstraint(
            ['bd_aim_id'], ['aim_bridge_domains.aim_id']))

    op.create_table(
        'aim_l3outsides',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('vrf_name', sa.String(64)),
        sa.Column('l3_domain_dn', sa.String(1024)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_l3outsides_identity'),
        sa.Index('idx_aim_l3outsides_identity', 'tenant_name', 'name'))

    op.create_table(
        'aim_external_networks',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('nat_epg_dn', sa.String(1024)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'l3out_name', 'name',
                            name='uniq_aim_external_networks_identity'),
        sa.Index('idx_aim_external_networks_identity',
                 'tenant_name', 'l3out_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'l3out_name'],
            ['aim_l3outsides.tenant_name', 'aim_l3outsides.name'],
            name='fk_l3out'))

    op.create_table(
        'aim_external_network_contracts',
        sa.Column('ext_net_aim_id', sa.Integer, nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('provides', sa.Boolean, nullable=False),
        sa.PrimaryKeyConstraint('ext_net_aim_id', 'name', 'provides'),
        sa.ForeignKeyConstraint(
            ['ext_net_aim_id'], ['aim_external_networks.aim_id']))

    op.create_table(
        'aim_external_subnets',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('cidr', sa.String(64), nullable=False),
        sa.Column('external_network_name', sa.String(64), nullable=False),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'l3out_name',
                            'external_network_name', 'cidr',
                            name='uniq_aim_external_subnets_identity'),
        sa.Index('idx_aim_external_subnets_identity',
                 'tenant_name', 'l3out_name', 'external_network_name',
                 'cidr'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'l3out_name', 'external_network_name'],
            ['aim_external_networks.tenant_name',
             'aim_external_networks.l3out_name',
             'aim_external_networks.name'],
            name='fk_ext_net'))


def downgrade():
    pass
