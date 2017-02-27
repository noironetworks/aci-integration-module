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

"""Create Agent table

Revision ID: accfe645090a
Revises:
Create Date: 2016-03-15 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = 'accfe645090a'
down_revision = '72fa5bce100b'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.expression import func


def upgrade():

    op.create_table(
        'aim_agents',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('agent_type', sa.String(255), nullable=False),
        sa.Column('host', sa.String(255), nullable=False),
        sa.Column('binary_file', sa.String(255), nullable=False),
        sa.Column('admin_state_up', sa.Boolean, default=True, nullable=False),
        sa.Column('heartbeat_timestamp', sa.TIMESTAMP,
                  server_default=func.now(), onupdate=func.now()),
        sa.Column('beat_count', sa.Integer, default=0),
        sa.Column('description', sa.String(255)),
        sa.Column('version', sa.String(10)),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_type', 'host',
                            name='uniq_agents0agent_type0host'))

    op.create_table(
        'aim_agent_to_tree_associations',
        sa.Column('agent_id', sa.String(length=255), nullable=True),
        sa.Column('tree_tenant_rn', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['tree_tenant_rn'],
                                ['aim_tenant_trees.tenant_rn'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_id'], ['aim_agents.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('agent_id', 'tree_tenant_rn'))


def downgrade():
    pass
