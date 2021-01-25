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

"""Use strings for QoS resources
Revision ID: 2f05b6baf008
Revises: ffbe2f21aa75
Create date: 2021-01-25 13:56:03.236000000
"""

# revision identifiers, used by Alembic.
revision = '2f05b6baf008'
down_revision = 'ffbe2f21aa75'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table('aim_qos_dpp_pol') as batch_op:
        batch_op.alter_column(
            "rate", existing_type=sa.BigInteger,
            type_=sa.String(32),
            existing_nullable=False,
            nullable=False)
        batch_op.alter_column(
            "pir", existing_type=sa.BigInteger,
            type_=sa.String(32),
            existing_nullable=False,
            nullable=False)
    with op.batch_alter_table('aim_qos_dscp_marking') as batch_op:
        batch_op.alter_column(
            "mark", existing_type=sa.SmallInteger,
            type_=sa.String(16),
            existing_nullable=False,
            nullable=False)


def downgrade():
    pass
