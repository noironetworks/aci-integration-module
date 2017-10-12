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

"""Table for HostLinkNetworkLabel

Revision ID: 0e6172dd5b09
Revises: dabed1dabeda
Create Date: 2017-10-12 16:39:33.713695

"""

# revision identifiers, used by Alembic.
revision = '0e6172dd5b09'
down_revision = 'dabed1dabeda'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_host_link_network_label',
        sa.Column('host_name', sa.String(128), nullable=False),
        sa.Column('network_label', sa.String(64), nullable=False),
        sa.Column('interface_name', sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint('host_name', 'network_label',
                                'interface_name'))


def downgrade():
    pass
