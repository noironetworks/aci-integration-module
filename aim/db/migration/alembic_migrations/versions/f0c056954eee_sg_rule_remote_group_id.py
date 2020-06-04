# Copyright 2020 Cisco, Inc.
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
#

"""Add remote_group_id column

Revision ID: f0c056954eee
Revises: 3880e0a62e1f
Create Date: 2020-05-05 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = 'f0c056954eee'
down_revision = '3880e0a62e1f'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.add_column(
        'aim_security_group_rules',
        sa.Column('remote_group_id', sa.String(64),
                  server_default='', nullable=False)
    )


def downgrade():
    pass
