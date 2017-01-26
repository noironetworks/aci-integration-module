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

"""Table for saved L3Out in AIM lib

Revision ID: d38c07b36c11
Revises: d8abdb89ba66
Create Date: 2017-01-26 14:39:19.956708

"""

# revision identifiers, used by Alembic.
revision = 'd38c07b36c11'
down_revision = 'd8abdb89ba66'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        'aim_lib_save_l3out',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=True),
        sa.Column('vrf_name', sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint('name', 'tenant_name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'name'],
            ['aim_l3outsides.tenant_name', 'aim_l3outsides.name'],
            name='fk_save_l3out_l3out', ondelete='CASCADE'))


def downgrade():
    pass
