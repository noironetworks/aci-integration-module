# Copyright (c) 2026 Cisco Systems
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

"""Make AIM identity/name columns case-sensitive

Revision ID: 7c8f1d602c3a
Revises: e322787e56fd
Create Date: 2026-03-30 20:35:00.000000
"""

from collections import OrderedDict

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from aim.aim_lib.db import model as aim_lib_model  # noqa
from aim.db import agent_model  # noqa
from aim.db import config_model  # noqa
from aim.db import infra_model  # noqa
from aim.db import model_base
from aim.db import models  # noqa
from aim.db import service_graph_model  # noqa
from aim.db import status_model  # noqa
from aim.db import tree_model  # noqa


# revision identifiers, used by Alembic.
revision = '7c8f1d602c3a'
down_revision = 'e322787e56fd'
branch_labels = None
depends_on = None


CASE_SENSITIVE_NAME = mysql.VARCHAR(
    64, charset='latin1', collation='latin1_bin')
DEFAULT_NAME = sa.String(length=64)
FKS_ON_CASE_SENSITIVE_COLUMNS = (
    ('aim_lib_clone_l3out', 'fk_clone_l3out_l3out',
     ['tenant_name', 'name'], ['aim_l3outsides.tenant_name',
                               'aim_l3outsides.name'], 'CASCADE'),
    ('aim_lib_clone_l3out', 'fk_clone_src_l3out_l3out',
     ['source_tenant_name', 'source_name'], ['aim_l3outsides.tenant_name',
                                             'aim_l3outsides.name'], None),
)


def _case_sensitive_name_columns():
    result = OrderedDict()
    for table_name, table in sorted(model_base.Base.metadata.tables.items()):
        columns = []
        for column in table.columns:
            if (getattr(column.type, 'length', None) == 64 and
                    getattr(column.type, 'charset', None) == 'latin1' and
                    getattr(column.type, 'collation', None) == 'latin1_bin'):
                columns.append(column)
        if columns:
            result[table_name] = columns
    return result


def _alter_name_columns(new_type, existing_type):
    for table_name, columns in _case_sensitive_name_columns().items():
        with op.batch_alter_table(table_name) as batch_op:
            for column in columns:
                batch_op.alter_column(
                    column.name, existing_type=existing_type,
                    type_=new_type, existing_nullable=column.nullable)


def _drop_case_sensitive_fks():
    for table_name, fk_name, _local, _remote, _ondelete in (
            FKS_ON_CASE_SENSITIVE_COLUMNS):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(fk_name, type_='foreignkey')


def _create_case_sensitive_fks():
    for table_name, fk_name, local, remote, ondelete in (
            FKS_ON_CASE_SENSITIVE_COLUMNS):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(
                fk_name, '.'.join(remote[0].split('.')[:-1]),
                local, [column.split('.')[-1] for column in remote],
                ondelete=ondelete)


def upgrade():
    _drop_case_sensitive_fks()
    try:
        op.execute('SET FOREIGN_KEY_CHECKS=0')
        _alter_name_columns(CASE_SENSITIVE_NAME, DEFAULT_NAME)
    finally:
        op.execute('SET FOREIGN_KEY_CHECKS=1')
    _create_case_sensitive_fks()


def downgrade():
    _drop_case_sensitive_fks()
    try:
        op.execute('SET FOREIGN_KEY_CHECKS=0')
        _alter_name_columns(DEFAULT_NAME, CASE_SENSITIVE_NAME)
    finally:
        op.execute('SET FOREIGN_KEY_CHECKS=1')
    _create_case_sensitive_fks()
