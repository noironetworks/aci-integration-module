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

"""Tables for L3out clones in AIM LIB

Revision ID: 8e313fbeb93b
Revises: 74f15b6aee51
Create Date: 2016-08-08 16:23:26.119724

"""

# revision identifiers, used by Alembic.
revision = '07113feba145'
down_revision = '8e313fbeb93b'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():

    op.create_table(
        'aim_lib_clone_l3out',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('source_name', sa.String(64), nullable=False),
        sa.Column('source_tenant_name', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('name', 'tenant_name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'name'],
            ['aim_l3outsides.tenant_name', 'aim_l3outsides.name'],
            name='fk_clone_l3out_l3out', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['source_tenant_name', 'source_name'],
            ['aim_l3outsides.tenant_name', 'aim_l3outsides.name'],
            name='fk_clone_src_l3out_l3out'))


def downgrade():
    pass
