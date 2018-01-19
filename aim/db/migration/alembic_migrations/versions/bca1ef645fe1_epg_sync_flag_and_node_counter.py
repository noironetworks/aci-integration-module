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

"""Add sync flag to EndpointGroup and SG node counter

Revision ID: bca1ef645fe1
Revises: 1e3fda0945f2
Create Date: 2018-01-10 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = 'bca1ef645fe1'
down_revision = '1e3fda0945f2'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.add_column(
        'aim_endpoint_groups',
        sa.Column('sync', sa.Boolean, server_default=sa.literal(True))
    )
    op.add_column(
        'aim_service_graph_linear_chain_nodes',
        sa.Column('sequence_number', sa.Integer))
    with op.batch_alter_table(
            'aim_service_graph_linear_chain_nodes') as batch_op:
        batch_op.create_unique_constraint(
            "uniq_aim_service_graph_node_identity",
            ["sg_aim_id", "name", "sequence_number"])


def downgrade():
    pass
