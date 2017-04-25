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

"""Table for OpflexDevice

Revision ID: 7838968744ce
Revises: babbefa38870
Create Date: 2017-04-06 12:31:28.953422

"""

# revision identifiers, used by Alembic.
revision = '7838968744ce'
down_revision = 'dc598e78e318'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_opflex_devices',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('pod_id', sa.String(36), nullable=False),
        sa.Column('node_id', sa.String(36), nullable=False),
        sa.Column('bridge_interface', sa.String(36), nullable=False),
        sa.Column('dev_id', sa.String(36), nullable=False),
        sa.Column('host_name', sa.String(128)),
        sa.Column('ip', sa.String(64)),
        sa.Column('fabric_path_dn', sa.String(512)),
        sa.Column('domain_name', sa.String(64)),
        sa.Column('controller_name', sa.String(64)),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('pod_id', 'node_id', 'bridge_interface', 'dev_id',
                            name='uniq_aim_odev_identity'),
        sa.Index('idx_aim_odev_identity', 'pod_id', 'node_id',
                 'bridge_interface', 'dev_id'))


def downgrade():
    pass
