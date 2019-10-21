# Copyright (c) 2019 Cisco Systems
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

"""Add mode column to L3 out interfaces

Revision ID: 3880e0a62e1f
Revises: 88a419c00e59
Create Date: 2019-12-03 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = '3880e0a62e1f'
down_revision = '88a419c00e59'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        'aim_l3out_interfaces',
        sa.Column('mode', sa.Enum('regular', 'native', 'untagged'))
    )


def downgrade():
    pass
