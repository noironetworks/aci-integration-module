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

"""Create tables for security groups

Revision ID: abf7bb5a4100
Revises: d38c07b36c11
Create Date: 2016-07-07 15:29:38.013141

"""

# revision identifiers, used by Alembic.
revision = 'abf7bb5a4100'
down_revision = 'd38c07b36c11'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        'aim_security_groups',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_sg_identity'),
        sa.Index('idx_aim_sg_identity', 'tenant_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name'], ['aim_tenants.name'], name='fk_sg_tn'))

    op.create_table(
        'aim_security_group_subjects',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('security_group_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'security_group_name', 'name',
                            name='uniq_aim_sg_subjects_identity'),
        sa.Index('idx_aim_sg_subjects_identity',
                 'tenant_name', 'security_group_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'security_group_name'],
            ['aim_security_groups.tenant_name', 'aim_security_groups.name'],
            name='fk_sg_subject'))

    op.create_table(
        'aim_security_group_rules',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('security_group_name', sa.String(64), nullable=False),
        sa.Column('security_group_subject_name', sa.String(64),
                  nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('ethertype', sa.String(16)),
        sa.Column('direction', sa.String(16)),
        sa.Column('ip_protocol', sa.String(16)),
        sa.Column('from_port', sa.String(16)),
        sa.Column('to_port', sa.String(16)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'security_group_name',
                            'security_group_subject_name', 'name',
                            name='uniq_aim_sg_rules_identity'),
        sa.Index('idx_aim_sg_rules_identity',
                 'tenant_name', 'security_group_name',
                 'security_group_subject_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'security_group_name',
             'security_group_subject_name'],
            ['aim_security_group_subjects.tenant_name',
             'aim_security_group_subjects.security_group_name',
             'aim_security_group_subjects.name'],
            name='fk_sg_rule'))

    op.create_table(
        'aim_security_group_rule_remote_ips',
        sa.Column('security_group_rule_aim_id', sa.Integer, nullable=False),
        sa.Column('cidr', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('security_group_rule_aim_id', 'cidr'),
        sa.ForeignKeyConstraint(
            ['security_group_rule_aim_id'],
            ['aim_security_group_rules.aim_id']))


def downgrade():
    pass
