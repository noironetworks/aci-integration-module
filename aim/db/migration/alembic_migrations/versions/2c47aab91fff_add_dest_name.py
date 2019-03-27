# Copyright (c) 2018 Cisco Systems
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

"""Add name column to service redirect destinations

Revision ID: 2c47aab91fff
Revises: 7ba6b6346710
Create Date: 2018-03-12 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = '2c47aab91fff'
down_revision = '7ba6b6346710'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        'aim_service_redirect_policy_destinations',
        sa.Column('name', sa.String(64), nullable=True)
    )


def downgrade():
    pass
