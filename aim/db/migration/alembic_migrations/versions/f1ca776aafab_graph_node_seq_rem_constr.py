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

"""Remove Service Graph Node Sequence Number Constraint

Revision ID: f1ca776aafab
Revises: 8764ba5df8d0
Create Date: 2018-01-29 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = 'f1ca776aafab'
down_revision = '8764ba5df8d0'
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    with op.batch_alter_table('aim_service_graph_nodes') as batch_op:
        batch_op.drop_constraint("uniq_aim_service_graph_node_seq",
                                 type_='unique')


def downgrade():
    pass
