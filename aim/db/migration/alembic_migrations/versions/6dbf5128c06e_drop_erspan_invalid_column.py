# Copyright (c) 2020 Cisco Systems
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

"""Drop erspan invalid column
Revision ID: 6dbf5128c06e
Revises: fccf2c4f6282
Create Date: 2020-10-05 11:13:39.608507
"""

# revision identifiers, used by Alembic.
revision = '6dbf5128c06e'
down_revision = 'fccf2c4f6282'
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    with op.batch_alter_table('aim_span_vepg_summary') as batch_op:
        batch_op.drop_column('invalid')
        batch_op.drop_column('ver_enforced')
        batch_op.drop_column('route_ip')
        batch_op.drop_column('scope')
        batch_op.drop_column('ver')

    with op.batch_alter_table('aim_span_spanlbl') as batch_op:
        batch_op.drop_column('vsg_aim_id')


def downgrade():
    pass
