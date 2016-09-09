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

"""Create BridgeDomain table

Revision ID: 40855b7eb958
Revises:
Create Date: 2016-03-07 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = '40855b7eb958'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_bridge_domains',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256)),
        sa.Column('vrf_name', sa.String(64)),
        sa.Column('enable_arp_flood', sa.Boolean),
        sa.Column('enable_routing', sa.Boolean),
        sa.Column('limit_ip_learn_to_subnets', sa.Boolean),
        sa.Column('l2_unknown_unicast_mode', sa.String(16)),
        sa.Column('ep_move_detect_mode', sa.String(16)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_aim_bridge_domains_identity'),
        sa.Index('idx_aim_bridge_domains_identity', 'tenant_name', 'name'))


def downgrade():
    pass
