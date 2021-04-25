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

"""Tables for adding Out of Band BRC

Revision ID: 61db5ac02ffa
Revises: 2f05b6baf008
Create date: 2021-02-09  23:18:34.236000000

"""

# revision identifiers, used by Alembic.
from alembic import op
import sqlalchemy as sa
revision = '61db5ac02ffa'
down_revision = '2f05b6baf008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'aim_oob_contracts',
        sa.Column('aim_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('scope', sa.String(24)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(),
                  nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_oob_contracts_identity'),
        sa.Index('idx_aim_oob_contracts_identity', 'tenant_name', 'name'))

    op.create_table(
        'aim_oob_contract_subjects',
        sa.Column('aim_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('service_graph_name', sa.String(64), server_default=''),
        sa.Column('in_service_graph_name', sa.String(64), server_default=''),
        sa.Column('out_service_graph_name', sa.String(64), server_default=''),
        sa.Column('epoch', sa.BigInteger(),
                  nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name', 'name',
                            name='uniq_aim_oob_contract_subjects_identity'),
        sa.Index('idx_aim_oob_contract_subjects_identity',
                 'tenant_name', 'contract_name', 'name'))

    op.create_table(
        'aim_oob_contract_subject_filters',
        sa.Column('subject_aim_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('direction', sa.Enum('bi', 'in', 'out'), nullable=False),
        sa.PrimaryKeyConstraint('subject_aim_id', 'name', 'direction'))


def downgrade():
    pass
