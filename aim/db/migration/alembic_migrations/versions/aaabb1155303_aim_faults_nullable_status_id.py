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

"""Drop FK constraint in aim faults table

Revision ID: aaabb1155303
Revises:

"""

# revision identifiers, used by Alembic.
revision = 'aaabb1155303'
down_revision = '5d975a5c2d60'
branch_labels = None
depends_on = None

from alembic import op
from sqlalchemy.engine import reflection


def upgrade():
    try:
        inspector = reflection.Inspector.from_engine(op.get_bind())
        fk_name = [fk['name'] for fk in
                   inspector.get_foreign_keys('aim_faults')
                   if 'status_id' in fk['constrained_columns']]
        op.drop_constraint(fk_name[0], 'aim_faults', 'foreignkey')
    except NotImplementedError:
        pass


def downgrade():
    pass
