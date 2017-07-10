# Copyright (c) 2017 Cisco Systems
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

"""Add description to Tenant

Revision ID: 0836fabb11ff
Revises: accaff4a0907

"""

# revision identifiers, used by Alembic.
revision = '0836fabb11ff'
down_revision = 'accaff4a0907'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.add_column(
        'aim_tenants',
        sa.Column('descr', sa.String(128), default='')
    )


def downgrade():
    pass
