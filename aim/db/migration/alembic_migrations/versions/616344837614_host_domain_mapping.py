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

"""Table for HostDomainMapping

Revision ID: 616344837614
Revises: babbefa38870
Create Date: 2017-04-13 16:39:33.713695

"""

# revision identifiers, used by Alembic.
revision = '616344837614'
down_revision = 'babbefa38870'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_host_domain_mapping',
        sa.Column('host_name', sa.String(128), nullable=False),
        sa.Column('vmm_domain_name', sa.String(64)),
        sa.Column('physical_domain_name', sa.String(64)),
        sa.PrimaryKeyConstraint('host_name'))


def downgrade():
    pass
