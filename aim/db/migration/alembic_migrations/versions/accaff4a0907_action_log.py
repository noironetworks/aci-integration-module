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

"""Create Action Log Table

Revision ID: accaff4a0907
Revises: aaabb1155303

"""

# revision identifiers, used by Alembic.
revision = 'accaff4a0907'
down_revision = 'aaabb1155303'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.expression import func


def upgrade():

    op.create_table(
        'aim_action_logs',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
                  autoincrement=True),
        sa.Column('uuid', sa.String(64)),
        sa.Column('root_rn', sa.String(64), nullable=False),
        sa.Column('action', sa.String(25), nullable=False),
        sa.Column('object_type', sa.String(50), nullable=False),
        sa.Column('object_dict', sa.LargeBinary(length=2 ** 24),
                  nullable=True),
        sa.Column('timestamp', sa.TIMESTAMP, server_default=func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid', name='uniq_aim_alogs_uuid'),
        sa.Index('idx_aim_action_logs_rn', 'root_rn'),
        sa.Index('idx_aim_action_logs_uuid', 'uuid'))

    op.add_column('aim_tenant_trees',
                  sa.Column('needs_reset', sa.Boolean,
                            server_default=sa.literal(False)))


def downgrade():
    pass
