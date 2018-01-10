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

"""Modify external id column size

Revision ID: 1e3fda0945f2
Revises: 6d55c6f80f40
Create Date: 2018-01-09 15:30:10.357536

"""

# revision identifiers, used by Alembic.
revision = '1e3fda0945f2'
down_revision = '6d55c6f80f40'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


def upgrade():
    with op.batch_alter_table('aim_faults') as batch_op:
        batch_op.alter_column(
            'external_identifier',
            existing_type=sa.String(length=255),
            type_=mysql.VARCHAR(512, charset='latin1'),
            existing_nullable=False,
            existing_server_default="")


def downgrade():
    pass
