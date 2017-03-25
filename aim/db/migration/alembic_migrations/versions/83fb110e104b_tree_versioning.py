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

"""Add version to tree column

Revision ID: 83fb110e104b
Revises:
Create Date: 2016-03-15 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = '83fb110e104b'
down_revision = '5d975a5c2d60'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.add_column(
        'aim_config_tenant_trees',
        sa.Column('resource_version', sa.Integer, nullable=False,
                  server_default='1'))

    op.add_column(
        'aim_operational_tenant_trees',
        sa.Column('resource_version', sa.Integer, nullable=False,
                  server_default='1'))

    op.add_column(
        'aim_monitored_tenant_trees',
        sa.Column('resource_version', sa.Integer, nullable=False,
                  server_default='1'))


def downgrade():
    pass
