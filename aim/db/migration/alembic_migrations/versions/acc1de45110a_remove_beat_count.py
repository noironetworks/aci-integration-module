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

"""Remove beat count

Revision ID: acc1de45110a
Revises: f1ca776aafab
Create Date: 2016-03-15 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = 'accfe645090a'
down_revision = 'f1ca776aafab'
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    with op.batch_alter_table('aim_agents') as batch_op:
        batch_op.drop_column('beat_count')


def downgrade():
    pass
