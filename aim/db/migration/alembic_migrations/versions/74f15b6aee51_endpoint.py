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

"""Create endpoint table

Revision ID: 74f15b6aee51
Revises: 3ef7607a41b0
Create Date: 2016-07-22 17:05:31.709885

"""

# revision identifiers, used by Alembic.
revision = '74f15b6aee51'
down_revision = '3ef7607a41b0'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_endpoints',
        sa.Column('uuid', sa.String(36), primary_key=True),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('epg_tenant_name', sa.String(64)),
        sa.Column('epg_app_profile_name', sa.String(64)),
        sa.Column('epg_name', sa.String(64)),
        sa.PrimaryKeyConstraint('uuid'),
        sa.ForeignKeyConstraint(
            ['epg_tenant_name', 'epg_app_profile_name', 'epg_name'],
            ['aim_endpoint_groups.tenant_name',
             'aim_endpoint_groups.app_profile_name',
             'aim_endpoint_groups.name'],
            name='fk_epg'))


def downgrade():
    pass
