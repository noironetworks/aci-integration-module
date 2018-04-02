# Copyright (c) 2018 Cisco Systems
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

"""Tables for IP SLA

Revision ID: 7ba6b6346710
Revises: 32e5974ada25
Create Date: 2018-03-29 14:36:19.451172

"""

# revision identifiers, used by Alembic.
revision = '7ba6b6346710'
down_revision = '32e5974ada25'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_service_redirect_health_group',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_service_redirect_'
                                 'health_group_identity'),
        sa.Index('idx_aim_service_redirect_health_group_identity',
                 'tenant_name', 'name'))

    op.create_table(
        'aim_service_redirect_monitoring_policy',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('type', sa.String(32), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('tcp_port', sa.String(32), nullable=False),
        sa.Column('frequency', sa.Integer, nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_service_redirect_'
                                 'monitoring_policy_identity'),
        sa.Index('idx_aim_service_redirect_monitoring_policy_identity',
                 'tenant_name', 'name'))

    op.add_column(
        'aim_service_redirect_policy_destinations',
        sa.Column('redirect_health_group_dn', sa.String(1024), nullable=True))

    op.add_column(
        'aim_service_redirect_policies',
        sa.Column('monitoring_policy_tenant_name', sa.String(64),
                  nullable=True))
    op.add_column(
        'aim_service_redirect_policies',
        sa.Column('monitoring_policy_name', sa.String(64), nullable=True))


def downgrade():
    pass
