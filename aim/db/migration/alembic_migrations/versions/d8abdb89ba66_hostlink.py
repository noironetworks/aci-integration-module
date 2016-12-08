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

"""Create table for HostLinks and EPG static-paths.

Revision ID: d8abdb89ba66
Revises: 07113feba145
Create Date: 2016-11-30 19:02:47.560600

"""

# revision identifiers, used by Alembic.
revision = 'd8abdb89ba66'
down_revision = '07113feba145'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_endpoint_group_static_paths',
        sa.Column('epg_aim_id', sa.Integer, nullable=False),
        sa.Column('path', sa.String(1024), nullable=False),
        sa.Column('encap', sa.String(24)),
        sa.PrimaryKeyConstraint('epg_aim_id', 'path'),
        sa.ForeignKeyConstraint(
            ['epg_aim_id'], ['aim_endpoint_groups.aim_id']))

    op.create_table(
        'aim_host_links',
        sa.Column('host_name', sa.String(256), nullable=False),
        sa.Column('interface_name', sa.String(64), nullable=False),
        sa.Column('interface_mac', sa.String(24)),
        sa.Column('switch_id', sa.String(128)),
        sa.Column('module', sa.String(128)),
        sa.Column('port', sa.String(128)),
        sa.Column('path', sa.String(1024)),
        sa.PrimaryKeyConstraint('host_name', 'interface_name'))


def downgrade():
    pass
