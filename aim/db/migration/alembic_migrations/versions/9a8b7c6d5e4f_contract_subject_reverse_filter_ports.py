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
"""Add reverse filter ports to contract subjects

Revision ID: 9a8b7c6d5e4f
Revises: e322787e56fd
Create Date: 2026-07-06 11:50:00.000000

"""

# revision identifiers, used by Alembic.
revision = '9a8b7c6d5e4f'
down_revision = 'e322787e56fd'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        'aim_contract_subjects',
        sa.Column('reverse_filter_ports', sa.Boolean(),
                  nullable=False, server_default=sa.true()))


def downgrade():
    pass
