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

"""Create TenantTree table

Revision ID: 72fa5bce100b
Revises:
Create Date: 2016-03-15 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = '72fa5bce100b'
down_revision = '40855b7eb958'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_tenant_trees',
        sa.Column('tenant_rn', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('tenant_rn'))

    op.create_table(
        'aim_config_tenant_trees',
        sa.Column('tenant_rn', sa.String(64), nullable=False),
        sa.Column('root_full_hash', sa.String(64), nullable=True),
        sa.Column('tree', sa.LargeBinary, nullable=True),
        sa.PrimaryKeyConstraint('tenant_rn'))

    op.create_table(
        'aim_operational_tenant_trees',
        sa.Column('tenant_rn', sa.String(64), nullable=False),
        sa.Column('root_full_hash', sa.String(64), nullable=True),
        sa.Column('tree', sa.LargeBinary, nullable=True),
        sa.PrimaryKeyConstraint('tenant_rn'))

    op.create_table(
        'aim_monitored_tenant_trees',
        sa.Column('tenant_rn', sa.String(64), nullable=False),
        sa.Column('root_full_hash', sa.String(64), nullable=True),
        sa.Column('tree', sa.LargeBinary, nullable=True),
        sa.PrimaryKeyConstraint('tenant_rn'))


def downgrade():
    pass
