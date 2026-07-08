# Copyright (c) 2026 Cisco Systems
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
"""Add resilient hash to service redirect policy

Revision ID: 4f91c2a7b8d3
Revises: 9a8b7c6d5e4f
Create Date: 2026-07-08 12:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = '4f91c2a7b8d3'
down_revision = '9a8b7c6d5e4f'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        'aim_service_redirect_policies',
        sa.Column('resilient_hash_enabled', sa.Boolean(),
                  nullable=False, server_default=sa.false()))


def downgrade():
    pass
