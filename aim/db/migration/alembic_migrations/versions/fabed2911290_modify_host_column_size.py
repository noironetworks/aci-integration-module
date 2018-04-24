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

"""Modify host column size

Revision ID: fabed2911290
Revises: 2c47aab91fff
Create Date: 2018-04-23 15:30:10.357536

"""

# revision identifiers, used by Alembic.
revision = 'fabed2911290'
down_revision = '2c47aab91fff'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


TABLES = ('aim_endpoint_group_static_paths',
          'aim_concrete_device_ifs',
          'aim_device_cluster_devices',
          'aim_l3out_interfaces')


def upgrade():
    for table in TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                'host', existing_type=sa.String(length=1024),
                type_=sa.String(512))


def downgrade():
    pass
