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

"""Add host column to EPG and concrete devices

Revision ID: 1b58ffa871bb
Revises: f1ca776aafab
Create Date: 2018-03-12 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = '1b58ffa871bb'
down_revision = 'f1ca776aafab'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

from aim.db.migration.data_migration import add_host_column


def upgrade():
    op.add_column(
        'aim_endpoint_group_static_paths',
        sa.Column('host', sa.String(1024), nullable=True, index=True)
    )
    op.add_column(
        'aim_concrete_device_ifs',
        sa.Column('host', sa.String(1024), nullable=True, index=True)
    )
    op.add_column(
        'aim_device_cluster_devices',
        sa.Column('host', sa.String(1024), nullable=True, index=True)
    )
    session = sa.orm.Session(bind=op.get_bind(), autocommit=True)
    add_host_column.migrate(session)


def downgrade():
    pass
