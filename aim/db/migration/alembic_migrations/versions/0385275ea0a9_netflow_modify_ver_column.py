# Copyright (c) 2020 Cisco Systems
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

"""Tables for add netflow

Revision ID: 0385275ea0a9
Revises: 6dbf5128c06e
Create date: 2020-10-21 13:56:03.236000000

"""

# revision identifiers, used by Alembic.
revision = '0385275ea0a9'
down_revision = '6dbf5128c06e'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table('aim_netflow_exporter_pol') as batch_op:
        batch_op.alter_column(
            "ver", existing_type=sa.String(16),
            type_=sa.Enum('v5', 'v9', 'cisco-v1'))


def downgrade():
    pass
