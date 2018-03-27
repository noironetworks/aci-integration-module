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

"""Add root column to status model

Revision ID: accfe645090a
Revises: abf7bb5a4100
Create Date: 2016-03-15 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = 'aabce110030f'
down_revision = '616344837614'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

from aim.db.migration.data_migration import status_add_tenant


def upgrade():

    op.add_column(
        'aim_statuses',
        sa.Column('resource_root', sa.String(64), nullable=False,
                  server_default='|unknown|'))
    session = sa.orm.Session(bind=op.get_bind(), autocommit=True)
    status_add_tenant.migrate(session)


def downgrade():
    pass
