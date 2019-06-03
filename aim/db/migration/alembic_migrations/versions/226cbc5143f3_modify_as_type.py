# Copyright (c) 2019 Cisco Systems
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

"""Modify external id column size

Revision ID: 226cbc5143f3
Revises: 308d91b3dadf
Create Date: 2019-06-01 15:30:10.357536

"""

# revision identifiers, used by Alembic.
revision = '226cbc5143f3'
down_revision = '308d91b3dadf'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table('aim_l3out_interface_bgp_peer_prefix') as b_op:
        b_op.alter_column('asn', existing_type=sa.Integer,
                          type_=sa.BigInteger, existing_nullable=False)


def downgrade():
    pass
