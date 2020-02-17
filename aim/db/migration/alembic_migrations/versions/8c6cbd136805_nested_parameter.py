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

"""Create table for NestedParameter and VlanRange.

Revision ID: 8c6cbd136805
Revises: 3880e0a62e1f
Create Date: 2020-02-21 19:02:47.560600

"""

# revision identifiers, used by Alembic.
revision = '8c6cbd136805'
down_revision = '3880e0a62e1f'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_nested_parameter',
        sa.Column('aim_id', sa.String(255), nullable=False),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('cluster_name', sa.String(64), nullable=False),
        sa.Column('domain_name', sa.String(64)),
        sa.Column('domain_type', sa.String(32), nullable=False),
        sa.Column('domain_infra_vlan', sa.Integer, nullable=False),
        sa.Column('domain_service_vlan', sa.Integer, nullable=False),
        sa.Column('domain_node_vlan', sa.Integer, nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('project_id', 'cluster_name',
                            name='uniq_aim_nested_parameter_identity'),
        sa.Index('idx_aim_nested_parameter_identity',
                 'project_id', 'cluster_name'))

    op.create_table(
        'aim_vlan_ranges',
        sa.Column('nested_parameter_aim_id', sa.String(255),
                  nullable=False),
        sa.Column('start', sa.Integer, nullable=False),
        sa.Column('end', sa.Integer),
        sa.PrimaryKeyConstraint('nested_parameter_aim_id', 'start'),
        sa.ForeignKeyConstraint(['nested_parameter_aim_id'],
                                ['aim_nested_parameter.aim_id']))


def downgrade():
    pass
