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

"""Support utf-8 constrained indexed columns

Revision ID: 2b48bf7f19cb
Revises: bcdef2211410
Create Date: 2018-03-12 12:23:39.608507

"""

# revision identifiers, used by Alembic.
revision = '2b48bf7f19cb'
down_revision = 'bcdef2211410'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.sqltypes import VARCHAR


_INSPECTOR = None

TABLES = ('aim_endpoint_group_static_paths',
          'aim_concrete_device_ifs',
          'aim_device_cluster_devices',
          'aim_l3out_interfaces')


def get_inspector():
    """Reuse inspector"""
    global _INSPECTOR

    if _INSPECTOR:
        return _INSPECTOR
    else:
        bind = op.get_bind()
        _INSPECTOR = sa.engine.reflection.Inspector.from_engine(bind)
    return _INSPECTOR


def get_columns(table):
    """Returns list of columns for given table."""
    inspector = get_inspector()
    return inspector.get_columns(table)


def upgrade():
    for table in TABLES:
        columns = get_columns(table)
        for column in columns:
            if isinstance(column['type'], VARCHAR) and (
                    column['name'] == 'host' and
                    column['type'].length == 512):
                with op.batch_alter_table(table) as batch_op:
                    batch_op.alter_column(
                        'host', existing_type=sa.String(length=512),
                        type_=sa.String(255))


def downgrade():
    pass
