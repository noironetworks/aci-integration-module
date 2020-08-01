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

"""Create tables for Qos policies

Revision ID: 794ad00f3080
Revises: 4caed435b0cd
Create Date: 2020-07-22 15:29:38.013141

"""

# revision identifiers, used by Alembic.
revision = '794ad00f3080'
down_revision = '4caed435b0cd'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        'aim_qos_requirement',
        sa.Column('aim_id', sa.String(255)),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('egress_dpp_pol', sa.String(64)),
        sa.Column('ingress_dpp_pol', sa.String(64)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_qos_req_identity'),
        sa.Index('idx_aim_qos_req_identity', 'tenant_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name'], ['aim_tenants.name'], name='fk_qos_req_tn'))

    op.create_table(
        'aim_qos_dpp_pol',
        sa.Column('aim_id', sa.String(255)),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('rate', sa.BigInteger),
        sa.Column('pir', sa.BigInteger),
        sa.Column('type', sa.String(16)),
        sa.Column('mode', sa.String(16)),
        sa.Column('burst', sa.String(16)),
        sa.Column('be', sa.String(16)),
        sa.Column('rate_unit', sa.String(16)),
        sa.Column('burst_unit', sa.String(16)),
        sa.Column('pir_unit', sa.String(16)),
        sa.Column('be_unit', sa.String(16)),
        sa.Column('conform_action', sa.String(16)),
        sa.Column('exceed_action', sa.String(16)),
        sa.Column('violate_action', sa.String(16)),
        sa.Column('conform_mark_dscp', sa.String(16)),
        sa.Column('exceed_mark_dscp', sa.String(16)),
        sa.Column('violate_mark_dscp', sa.String(16)),
        sa.Column('conform_mark_cos', sa.String(16)),
        sa.Column('exceed_mark_cos', sa.String(16)),
        sa.Column('violate_mark_cos', sa.String(16)),
        sa.Column('admin_st', sa.String(16)),
        sa.Column('sharing_mode', sa.String(16)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_qos_bw_lt_identity'),
        sa.ForeignKeyConstraint(
            ['tenant_name'], ['aim_tenants.name'], name='fk_qos_bw_lt_tn'))

    op.create_table(
        'aim_qos_dscp_marking',
        sa.Column('qos_requirement_aim_id', sa.String(255)),
        sa.Column('mark', sa.SmallInteger),
        sa.PrimaryKeyConstraint('qos_requirement_aim_id'),
        sa.ForeignKeyConstraint(
            ['qos_requirement_aim_id'],
            ['aim_qos_requirement.aim_id'],
            name='fk_qos_dscp_req'))

    op.add_column(
        'aim_endpoint_groups',
        sa.Column('qos_name', sa.String(64), default=''))


def downgrade():
    pass
