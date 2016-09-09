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

"""Create tables for contracts and filters

Revision ID: 3ef7607a41b0
Revises: faade1155a0a
Create Date: 2016-07-07 15:29:38.013141

"""

# revision identifiers, used by Alembic.
revision = '3ef7607a41b0'
down_revision = 'faade1155a0a'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_filters',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_filters_identity'),
        sa.Index('idx_aim_filters_identity', 'tenant_name', 'name'))

    op.create_table(
        'aim_filter_entries',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('filter_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('arp_opcode', sa.String(16)),
        sa.Column('ether_type', sa.String(16)),
        sa.Column('ip_protocol', sa.String(16)),
        sa.Column('icmpv4_type', sa.String(16)),
        sa.Column('icmpv6_type', sa.String(16)),
        sa.Column('source_from_port', sa.String(16)),
        sa.Column('source_to_port', sa.String(16)),
        sa.Column('dest_from_port', sa.String(16)),
        sa.Column('dest_to_port', sa.String(16)),
        sa.Column('tcp_flags', sa.String(16)),
        sa.Column('stateful', sa.Boolean),
        sa.Column('fragment_only', sa.Boolean),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'filter_name', 'name',
                            name='uniq_aim_filter_entries_identity'),
        sa.Index('idx_aim_filter_entries_identity',
                 'tenant_name', 'filter_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'filter_name'],
            ['aim_filters.tenant_name', 'aim_filters.name'],
            name='fk_filter'))

    op.create_table(
        'aim_contracts',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('scope', sa.String(24)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_contracts_identity'),
        sa.Index('idx_aim_contracts_identity', 'tenant_name', 'name'))

    op.create_table(
        'aim_contract_subjects',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name', 'name',
                            name='uniq_aim_contract_subjects_identity'),
        sa.Index('idx_aim_contract_subjects_identity',
                 'tenant_name', 'contract_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'contract_name'],
            ['aim_contracts.tenant_name', 'aim_contracts.name'],
            name='fk_contract'))

    op.create_table(
        'aim_contract_subject_filters',
        sa.Column('subject_aim_id', sa.Integer, nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('direction', sa.Enum('bi', 'in', 'out'), nullable=False),
        sa.PrimaryKeyConstraint('subject_aim_id', 'name', 'direction'),
        sa.ForeignKeyConstraint(
            ['subject_aim_id'], ['aim_contract_subjects.aim_id']))


def downgrade():
    pass
