# Copyright (c) 2018 Cisco Systems
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
"""bgp peer prefix

Revision ID: f18e545de625
Revises: 310941aa5ee1
Create Date: 2018-01-21 22:19:15.594994

"""
# revision identifiers, used by Alembic.
revision = 'f18e545de625'
down_revision = '310941aa5ee1'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import VARCHAR


def upgrade():
    op.add_column('aim_l3outsides', sa.Column('bgp_enable', sa.Boolean(),
                                              server_default=sa.false(),
                                              nullable=False))
    op.add_column('aim_external_subnets',
                  sa.Column('aggregate', sa.String(64), server_default="",
                            nullable=False))
    op.add_column('aim_external_subnets',
                  sa.Column('scope', sa.String(64),
                            server_default="import-security", nullable=False))
    op.create_table(
        'aim_l3out_interface_bgp_peer_prefix',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('node_profile_name', sa.String(64), nullable=False),
        sa.Column('interface_profile_name', sa.String(64), nullable=False),
        sa.Column('interface_path', VARCHAR(512, charset='latin1'),
                  nullable=False),
        sa.Column('addr', sa.String(64), nullable=False),
        sa.Column('asn', sa.Integer),
        sa.Column('local_asn', sa.Integer),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'l3out_name', 'node_profile_name',
                            'interface_profile_name', 'interface_path',
                            'addr',
                            name='uniq_aim_l3out_interface_bgp_peer_pfx_id'),
        sa.Index('uniq_aim_l3out_interface_bgp_peer_pfx_idx', 'tenant_name',
                 'l3out_name', 'node_profile_name',
                 'interface_profile_name', 'interface_path', 'addr'))


def downgrade():
    pass
