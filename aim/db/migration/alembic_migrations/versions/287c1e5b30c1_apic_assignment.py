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

"""Table for ApicAssignment

Revision ID: 287c1e5b30c1
Revises: 226cbc5143f3
Create Date: 2019-10-02 15:30:10.357536

"""

# revision identifiers, used by Alembic.
revision = '287c1e5b30c1'
down_revision = '226cbc5143f3'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.expression import func


def upgrade():
    op.create_table(
        'aim_apic_assignment',
        sa.Column('apic_host', sa.String(128), nullable=False),
        sa.Column('aim_aid_id', sa.String(64), nullable=False),
        sa.Column('last_update_timestamp', sa.TIMESTAMP,
                  server_default=func.now(), onupdate=func.now()),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('apic_host'))


def downgrade():
    pass
