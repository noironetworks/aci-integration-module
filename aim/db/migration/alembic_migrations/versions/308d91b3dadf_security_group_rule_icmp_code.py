# Copyright 2017 Cisco, Inc.
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

"""Add icmp_type amd icmp_code column

Revision ID: 308d91b3dadf
Revises: 2b48bf7f19cb
Create Date: 2019-03-12 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = '308d91b3dadf'
down_revision = '2b48bf7f19cb'


from aim.api import types as t
from alembic import op
import sqlalchemy as sa


def upgrade():

    op.add_column(
        'aim_security_group_rules',
        sa.Column('icmp_type', sa.String(16), nullable=False,
                  server_default=t.UNSPECIFIED)
    )
    op.add_column(
        'aim_security_group_rules',
        sa.Column('icmp_code', sa.String(16), nullable=False,
                  server_default=t.UNSPECIFIED)
    )


def downgrade():
    pass
