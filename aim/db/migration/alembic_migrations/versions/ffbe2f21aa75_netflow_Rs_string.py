# Copyright (c) 2021 Cisco Systems
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

"""Use strings for ERSPAN summary resource
Revision ID: ffbe2f21aa75
Revises: 105b5f35b8fd
Create date: 2021-01-24 16:56:03.236000000
"""

# revision identifiers, used by Alembic.
revision = 'ffbe2f21aa75'
down_revision = '105b5f35b8fd'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table('aim_vmm_reln_exporter_pol') as batch_op:
        batch_op.alter_column(
            "active_flow_time_out", existing_type=sa.Integer,
            type_=sa.String(16),
            existing_nullable=False,
            nullable=False)
        batch_op.alter_column(
            "idle_flow_time_out", existing_type=sa.Integer,
            type_=sa.String(16),
            existing_nullable=False,
            nullable=False)
        batch_op.alter_column(
            "sampling_rate", existing_type=sa.Integer,
            type_=sa.String(16),
            existing_nullable=False,
            nullable=False)


def downgrade():
    pass
