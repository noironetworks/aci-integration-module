# Copyright (c) 2021 Cisco Systems
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

"""Table for adding EPG Subnet
Revision ID: 60399662af3c
Revises: 7b8a71bee019
Create date: 2022-10-12 14:22:40.236000000
"""

# revision identifiers, used by Alembic.
revision = '60399662af3c'
down_revision = '7b8a71bee019'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_epg_subnets',
        sa.Column('aim_id', sa.String(255), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('app_profile_name', sa.String(64), nullable=False),
        sa.Column('epg_name', sa.String(64), nullable=False),
        sa.Column('gw_ip_mask', sa.String(64), nullable=False),
        sa.Column('scope', sa.String(16)),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'app_profile_name',
                            'epg_name', 'gw_ip_mask',
                            name='uniq_aim_epg_subnets_identity'),
        sa.Index('idx_aim_epg_subnets_identity',
                 'tenant_name', 'app_profile_name', 'epg_name', 'gw_ip_mask'),
    )


def downgrade():
    pass
