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

"""Create tables for system security groups
Revision ID: 47f3082b9b0a
Revises: 61db5ac02ffa
Create Date: 2016-07-07 15:29:38.013141
"""

# revision identifiers, used by Alembic.
revision = '47f3082b9b0a'
down_revision = '61db5ac02ffa'
branch_labels = None
depends_on = None

from aim.api import types as t
from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        'aim_system_security_groups',
        sa.Column('aim_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_sys_sg_identity'),
        sa.Index('idx_aim_sys_sg_identity', 'tenant_name', 'name'))

    op.create_table(
        'aim_system_security_group_subjects',
        sa.Column('aim_id', sa.String(255), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('security_group_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'security_group_name', 'name',
                            name='uniq_aim_sys_sg_subjects_identity'),
        sa.Index('idx_aim_sys_sg_subjects_identity',
                 'tenant_name', 'security_group_name', 'name'))

    op.create_table(
        'aim_system_security_group_rules',
        sa.Column('aim_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('security_group_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('security_group_subject_name', sa.String(64),
                  nullable=False),
        sa.Column('ethertype', sa.String(16)),
        sa.Column('direction', sa.String(16)),
        sa.Column('ip_protocol', sa.String(16)),
        sa.Column('from_port', sa.String(16)),
        sa.Column('to_port', sa.String(16)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('conn_track', sa.String(25), nullable=False,
                  server_default='reflexive'),
        sa.Column('remote_group_id', sa.String(64),
                  server_default='', nullable=False),
        sa.Column('icmp_type', sa.String(16), nullable=False,
                  server_default=t.UNSPECIFIED),
        sa.Column('icmp_code', sa.String(16), nullable=False,
                  server_default=t.UNSPECIFIED),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'security_group_name',
                            'name',
                            name='uniq_aim_sys_sg_rules_identity'),
        sa.Index('idx_aim_sys_sg_rules_identity',
                 'tenant_name', 'security_group_name',
                 'security_group_subject_name', 'name'))

    op.create_table(
        'aim_system_security_group_rule_remote_ips',
        sa.Column('security_group_rule_aim_id', sa.String(255),
                  nullable=False),
        sa.Column('cidr', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('security_group_rule_aim_id', 'cidr'),
        sa.ForeignKeyConstraint(
            ['security_group_rule_aim_id'],
            ['aim_system_security_group_rules.aim_id']))


def downgrade():
    pass
