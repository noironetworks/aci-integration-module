# Copyright (c) 2024 Cisco Systems
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

"""Fix Table for remote ip container under security groups
Revision ID: 79deb77b4719
Revises: a94984a4452b
Create date: 2024-02-22 10:19:03.236000000
"""

# revision identifiers, used by Alembic.

from alembic import op
import sqlalchemy as sa

revision = '79deb77b4719'
down_revision = 'a94984a4452b'
branch_labels = None
depends_on = None


def upgrade():
    # Re-create table with supported column length
    with op.batch_alter_table('aim_sg_remoteipcont_references') as batch_op:
        batch_op.alter_column(
            "tDn", existing_type=sa.String(256),
            type_=sa.String(255),
            existing_nullable=False,
            nullable=False)


def downgrade():
    pass
