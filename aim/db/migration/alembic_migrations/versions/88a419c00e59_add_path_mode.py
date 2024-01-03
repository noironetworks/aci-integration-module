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

"""Add mode to EPG static path

Revision ID: 88a419c00e59
Revises: 287c1e5b30c1
Create Date: 2019-10-21 14:58:47.408348

"""

# revision identifiers, used by Alembic.
revision = '88a419c00e59'
down_revision = '287c1e5b30c1'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

from aim.db import api


def upgrade():

    session = api.get_session(expire_on_commit=True)
    with session.begin():
        op.add_column(
            'aim_endpoint_group_static_paths',
            sa.Column('mode', sa.Enum('regular', 'native', 'untagged'),
                      nullable=False, server_default='regular'))


def downgrade():
    pass
