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

"""Add VMM to devide cluster

Revision ID: 310941aa5ee1
Revises: bca1ef645fe1
Create Date: 2018-01-10 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = '310941aa5ee1'
down_revision = 'bca1ef645fe1'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.add_column(
        'aim_device_clusters',
        sa.Column('vmm_domain_name', sa.String(64)))
    op.add_column(
        'aim_device_clusters',
        sa.Column('vmm_domain_type', sa.Enum('OpenStack', 'Kubernetes',
                                             'VMware', '')))


def downgrade():
    pass
