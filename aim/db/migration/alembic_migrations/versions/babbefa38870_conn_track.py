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

"""Add conntrack column

Revision ID: babbefa38870
Revises: abf7bb5a4100

"""

# revision identifiers, used by Alembic.
revision = 'babbefa38870'
down_revision = 'abf7bb5a4100'


from alembic import op
import sqlalchemy as sa


def upgrade():

    op.add_column(
        'aim_security_group_rules',
        sa.Column('conn_track', sa.String(25), nullable=False,
                  server_default='reflexive')
    )


def downgrade():
    pass
