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

Revision ID: 4caed435b0cd
Revises: f0c056954eee
Create date: 2020-07-06 16:32:03.236000000

"""

# revision identifiers, used by Alembic.
revision = '4caed435b0cd'
down_revision = 'f0c056954eee'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_netflow_exporter_pol',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('dst_addr', sa.String(64)),
        sa.Column('dst_port', sa.String(16)),
        sa.Column('src_addr', sa.String(64)),
        sa.Column('ver', sa.String(16)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('name',
                            name='uniq_aim_netflow_exporter_pol_identity'),
        sa.Index('idx_aim_netflow_exporter_pol_identity', 'name'))

    op.create_table(
        'aim_infra',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.UniqueConstraint('name', name='uniq_aim_infra_identity'),
        sa.PrimaryKeyConstraint('aim_id'))


def downgrade():
    pass
