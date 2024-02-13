#    Copyright 2016 Huawei Technologies India Pvt Limited.
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

"""add static path

Revision ID: c0975c8bd940
Revises: f399fa0f5f25
Create Date: 2024-02-02 03:56:09.327448

"""

# revision identifiers, used by Alembic.
revision = 'c0975c8bd940'
down_revision = 'a94984a4452b'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

from aim.db.migration.data_migration import add_static_path


def upgrade():
    op.create_table(
        'aim_static_path',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(128), nullable=False),
        sa.Column('path', sa.String(255), nullable=False),
        sa.Column('host', sa.String(128), nullable=False),
        sa.Column('mode', sa.Enum('regular', 'native', 'untagged'),
                  nullable=False),
        sa.Column('encap', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, default=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'))

    session = sa.orm.Session(bind=op.get_bind(), autocommit=True)
    add_static_path.migrate(session)


def downgrade():
    pass
