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

"""Create tables for VMM and Physical Domains.

Revision ID: 1249face3348
Revises: ab9b4e196100
Create Date: 2016-08-11 17:59:18.910872

"""

# revision identifiers, used by Alembic.
revision = '1249face3348'
down_revision = 'ab9b4e196100'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        'aim_vmm_domains',
        sa.Column('type', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('type', 'name'))

    op.create_table(
        'aim_physical_domains',
        sa.Column('name', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('name'))

    op.create_table(
        'aim_endpoint_group_vmm_domains',
        sa.Column('epg_aim_id', sa.Integer, nullable=False),
        sa.Column('vmm_type', sa.String(64), nullable=False),
        sa.Column('vmm_name', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('epg_aim_id', 'vmm_type', 'vmm_name'),
        sa.ForeignKeyConstraint(
            ['epg_aim_id'], ['aim_endpoint_groups.aim_id']))

    op.create_table(
        'aim_endpoint_group_physical_domains',
        sa.Column('epg_aim_id', sa.Integer, nullable=False),
        sa.Column('physdom_name', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('epg_aim_id', 'physdom_name'),
        sa.ForeignKeyConstraint(
            ['epg_aim_id'], ['aim_endpoint_groups.aim_id']))


def downgrade():
    pass
