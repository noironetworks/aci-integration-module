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

"""Modify concrete interface column size

Revision ID: de3ed29972f1
Revises: 0836fabb11ff
Create Date: 2017-07-18 15:30:10.357536

"""

# revision identifiers, used by Alembic.
revision = 'de3ed29972f1'
down_revision = '0836fabb11ff'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


def upgrade():
    with op.batch_alter_table(
            'aim_device_cluster_if_concrete_ifs') as batch_op:
        batch_op.alter_column(
            'interface',
            existing_type=sa.String(length=64),
            type_=mysql.VARCHAR(512, charset='latin1'),
            existing_nullable=False,
            existing_server_default="")


def downgrade():
    pass
