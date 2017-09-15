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

"""Create table for HostLinks and EPG static-paths.

Revision ID: dabed1dabeda
Revises: baccabeffa81
Create Date: 2017-09-15 19:02:47.560600

"""

# revision identifiers, used by Alembic.
revision = 'dabed1dabeda'
down_revision = 'baccabeffa81'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_endpoint_group_contract_masters',
        sa.Column('epg_aim_id', sa.Integer, nullable=False),
        sa.Column('app_profile_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('epg_aim_id', 'app_profile_name', 'name'),
        sa.ForeignKeyConstraint(
            ['epg_aim_id'], ['aim_endpoint_groups.aim_id']))


def downgrade():
    pass
