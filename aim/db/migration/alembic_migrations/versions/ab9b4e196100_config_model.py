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

"""Create Status and Fault model

Revision ID: accfe645090a
Revises:
Create Date: 2016-03-15 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = 'ab9b4e196100'
down_revision = '3ef7607a41b0'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        'aim_config',
        sa.Column('key', sa.String(32), nullable=False),
        sa.Column('host', sa.String(32), nullable=False, default=''),
        sa.Column('group', sa.String(32), nullable=False, default=''),
        sa.Column('value', sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint('key', 'host', 'group'))


def downgrade():
    pass
