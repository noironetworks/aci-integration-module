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

"""Add pod_id and from_config column to HostLink model

Revision ID: 593d228d2fb4
Revises: 0e6172dd5b09
Create Date: 2017-10-25 16:39:33.713695

"""

# revision identifiers, used by Alembic.
revision = '593d228d2fb4'
down_revision = '0e6172dd5b09'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('aim_host_links',
                  sa.Column('pod_id', sa.String(128), server_default='1'))
    op.add_column('aim_host_links',
                  sa.Column('from_config', sa.Boolean,
                            server_default=sa.literal(False)))


def downgrade():
    pass
