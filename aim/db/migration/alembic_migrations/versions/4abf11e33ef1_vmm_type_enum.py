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

"""Change VMM type in devide cluster

Revision ID: 4abf11e33ef1
Revises: fca473600fa1
Create Date: 2018-01-10 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = '4abf11e33ef1'
down_revision = 'fca473600fa1'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table('aim_device_clusters') as batch_op:
        batch_op.alter_column(
            "vmm_domain_type", existing_type=sa.Enum('OpenStack', 'Kubernetes',
                                                     'VMware', ''),
            type_=sa.String(64))


def downgrade():
    pass
