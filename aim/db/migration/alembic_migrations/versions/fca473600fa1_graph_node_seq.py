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

"""Add Service Graph Node Sequence Number

Revision ID: fca473600fa1
Revises: f18e545de625
Create Date: 2018-01-29 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = 'fca473600fa1'
down_revision = 'f18e545de625'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.add_column(
        'aim_service_graph_nodes',
        sa.Column('sequence_number', sa.Integer))
    with op.batch_alter_table('aim_service_graph_nodes') as batch_op:
        batch_op.create_unique_constraint(
            "uniq_aim_service_graph_node_seq",
            ["tenant_name", "service_graph_name", "sequence_number"])


def downgrade():
    pass
