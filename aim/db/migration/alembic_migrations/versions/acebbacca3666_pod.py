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

"""Create Pod Table.

Revision ID: acebbacca3666
Revises: aceb1ac13668

Create Date: 2016-08-11 17:59:18.910872

"""

# revision identifiers, used by Alembic.
revision = 'acebbacca3666'
down_revision = 'aceb1ac13668'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        'aim_pods',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.UniqueConstraint('name', name='uniq_aim_pod_identity'),
        sa.PrimaryKeyConstraint('aim_id'))


def downgrade():
    pass
