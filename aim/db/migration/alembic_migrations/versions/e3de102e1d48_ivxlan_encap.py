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

Revision ID: e3de102e1d48
Revises: 226cbc5143f3
Create Date: 2018-01-10 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = 'e3de102e1d48'
down_revision = '226cbc5143f3'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table('aim_vmm_domains') as batch_op:
        batch_op.alter_column(
            "encap_mode", existing_type=sa.Enum('unknown', 'vlan', 'vxlan',
                                                'ivxlan'),
            type_=sa.String(64))


def downgrade():
    pass
