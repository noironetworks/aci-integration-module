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

"""Add dn column to status model

Revision ID: bcdef2211410
Revises: fabed2911290
Create Date: 2016-03-15 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = 'bcdef2211410'
down_revision = 'fabed2911290'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import VARCHAR

from aim.db import api
from aim.db.migration.data_migration import status_add_dn


def upgrade():

    session = api.get_session(expire_on_commit=True)
    with session.begin(subtransactions=True):
        op.add_column(
            'aim_statuses',
            sa.Column('resource_dn', VARCHAR(512, charset='latin1'),
                      nullable=False, server_default=''))
        status_add_dn.migrate(session)


def downgrade():
    pass
