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

"""Tables for SVI

Revision ID: 6d55c6f80f40
Revises: dd2f91cf1b1e
Create Date: 2017-12-18 14:36:19.451172

"""

# revision identifiers, used by Alembic.
revision = '6d55c6f80f40'
down_revision = 'dd2f91cf1b1e'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import VARCHAR


def upgrade():
    op.create_table(
        'aim_l3out_node_profiles',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'l3out_name', 'name',
                            name='uniq_aim_l3out_node_profile_identity'),
        sa.Index('idx_aim_l3out_node_profile_identity',
                 'tenant_name', 'l3out_name', 'name'))

    op.create_table(
        'aim_l3out_nodes',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('node_profile_name', sa.String(64), nullable=False),
        sa.Column('node_path', VARCHAR(512, charset='latin1'), nullable=False),
        sa.Column('router_id', sa.String(64), nullable=False),
        sa.Column('router_id_loopback', sa.Boolean, nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'l3out_name', 'node_profile_name',
                            'node_path',
                            name='uniq_aim_l3out_node_identity'),
        sa.Index('idx_aim_l3out_node_identity',
                 'tenant_name', 'l3out_name', 'node_profile_name',
                 'node_path'))

    op.create_table(
        'aim_l3out_static_routes',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('node_profile_name', sa.String(64), nullable=False),
        sa.Column('node_path', VARCHAR(512, charset='latin1'), nullable=False),
        sa.Column('cidr', sa.String(64), nullable=False),
        sa.Column('preference', sa.String(16), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'l3out_name', 'node_profile_name',
                            'node_path', 'cidr',
                            name='uniq_aim_l3out_static_route_identity'),
        sa.Index('idx_aim_l3out_static_route_identity',
                 'tenant_name', 'l3out_name', 'node_profile_name',
                 'node_path', 'cidr'))

    op.create_table(
        'aim_l3out_next_hops',
        sa.Column('static_route_aim_id', sa.Integer, nullable=False),
        sa.Column('addr', sa.String(64), nullable=False),
        sa.Column('preference', sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint('static_route_aim_id', 'addr'),
        sa.ForeignKeyConstraint(
            ['static_route_aim_id'], ['aim_l3out_static_routes.aim_id']))

    op.create_table(
        'aim_l3out_interface_profiles',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('node_profile_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'l3out_name', 'node_profile_name',
                            'name',
                            name='uniq_aim_l3out_if_profile_identity'),
        sa.Index('idx_aim_l3out_if_profile_identity',
                 'tenant_name', 'l3out_name', 'node_profile_name',
                 'name'))

    op.create_table(
        'aim_l3out_interfaces',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('node_profile_name', sa.String(64), nullable=False),
        sa.Column('interface_profile_name', sa.String(64), nullable=False),
        sa.Column('interface_path', VARCHAR(512, charset='latin1'),
                  nullable=False),
        sa.Column('encap', sa.String(24), nullable=False),
        sa.Column('type', sa.String(16), nullable=False),
        sa.Column('primary_addr_a', sa.String(64), nullable=False),
        sa.Column('primary_addr_b', sa.String(64)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'l3out_name', 'node_profile_name',
                            'interface_profile_name', 'interface_path',
                            name='uniq_aim_l3out_if_identity'),
        sa.Index('idx_aim_l3out_if_identity',
                 'tenant_name', 'l3out_name', 'node_profile_name',
                 'interface_profile_name', 'interface_path'))

    op.create_table(
        'aim_l3out_interface_secondary_ip_a',
        sa.Column('interface_aim_id', sa.Integer, nullable=False),
        sa.Column('addr', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('interface_aim_id', 'addr'),
        sa.ForeignKeyConstraint(
            ['interface_aim_id'], ['aim_l3out_interfaces.aim_id']))

    op.create_table(
        'aim_l3out_interface_secondary_ip_b',
        sa.Column('interface_aim_id', sa.Integer, nullable=False),
        sa.Column('addr', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('interface_aim_id', 'addr'),
        sa.ForeignKeyConstraint(
            ['interface_aim_id'], ['aim_l3out_interfaces.aim_id']))


def downgrade():
    pass
