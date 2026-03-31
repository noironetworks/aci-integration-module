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
from sqlalchemy.sql import text

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


def _is_mysql():
    return op.get_bind().dialect.name == 'mysql'


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


def _get_column_metadata(table_name, column_name):
    query = text(
        'SELECT character_set_name, collation_name '
        'FROM information_schema.columns '
        'WHERE table_schema = DATABASE() '
        'AND table_name = :table_name AND column_name = :column_name')
    return op.get_bind().execute(
        query, table_name=table_name, column_name=column_name).first()


def _pending_name_columns(case_sensitive):
    result = OrderedDict()
    for table_name, columns in _case_sensitive_name_columns().items():
        pending_columns = []
        for column in columns:
            metadata = _get_column_metadata(table_name, column.name)
            if not metadata:
                continue
            if case_sensitive:
                if metadata[0] != 'latin1' or metadata[1] != 'latin1_bin':
                    pending_columns.append(column)
            elif metadata[1] == 'latin1_bin':
                pending_columns.append(column)
        if pending_columns:
            result[table_name] = pending_columns
    return result


def _alter_name_columns(columns_by_table, new_type):
    bind = op.get_bind()
    compiled_type = new_type.compile(dialect=bind.dialect)
    for table_name, columns in columns_by_table.items():
        print('Applying case-sensitivity change to table %s' % table_name)
        clauses = [
            'MODIFY `%s` %s %s' % (
                column.name, compiled_type,
                'NULL' if column.nullable else 'NOT NULL')
            for column in columns]
        op.execute('ALTER TABLE `%s` %s' % (table_name, ', '.join(clauses)))


def _set_foreign_key_checks(enabled):
    op.execute('SET FOREIGN_KEY_CHECKS=%d' % (1 if enabled else 0))


def _set_lock_wait_timeout(timeout):
    op.execute('SET SESSION lock_wait_timeout=%d' % timeout)


def _get_lock_wait_timeout():
    return op.get_bind().execute(
        text('SELECT @@SESSION.lock_wait_timeout')).scalar()


def _restore_migration_session(fk_checks, lock_wait_timeout):
    bind = op.get_bind()
    if bind is None or bind.closed:
        return
    try:
        _set_foreign_key_checks(fk_checks)
        _set_lock_wait_timeout(lock_wait_timeout)
    except Exception:
        # A KeyboardInterrupt while MySQL is executing DDL can invalidate the
        # session. The session-scoped settings are dropped with that connection.
        pass


def _get_table_foreign_keys(table_name):
    return sa.inspect(op.get_bind()).get_foreign_keys(table_name)


def _find_matching_fk(table_name, local, remote):
    remote_table = remote[0].split('.')[0]
    remote_columns = [column.split('.')[-1] for column in remote]
    for fk in _get_table_foreign_keys(table_name):
        if (fk.get('referred_table') == remote_table and
                fk.get('constrained_columns') == list(local) and
                fk.get('referred_columns') == remote_columns):
            return fk


def _drop_case_sensitive_fks():
    for table_name, _fk_name, local, remote, _ondelete in (
            FKS_ON_CASE_SENSITIVE_COLUMNS):
        fk = _find_matching_fk(table_name, local, remote)
        if not fk or not fk.get('name'):
            continue
        op.execute(
            'ALTER TABLE `%s` DROP FOREIGN KEY `%s`' %
            (table_name, fk['name']))


def _create_case_sensitive_fks():
    for table_name, fk_name, local, remote, ondelete in (
            FKS_ON_CASE_SENSITIVE_COLUMNS):
        if _find_matching_fk(table_name, local, remote):
            continue
        query = (
            'ALTER TABLE `%s` ADD CONSTRAINT `%s` FOREIGN KEY (%s) '
            'REFERENCES `%s` (%s)' % (
                table_name, fk_name,
                ', '.join('`%s`' % column for column in local),
                remote[0].split('.')[0],
                ', '.join('`%s`' % column.split('.')[-1]
                          for column in remote)))
        if ondelete:
            query += ' ON DELETE %s' % ondelete
        op.execute(query)


def _needs_case_sensitive_fk_refresh(columns_by_table):
    return ('aim_lib_clone_l3out' in columns_by_table or
            'aim_l3outsides' in columns_by_table)


def upgrade():
    if not _is_mysql():
        return
    pending_columns = _pending_name_columns(case_sensitive=True)
    if not pending_columns:
        return
    old_lock_wait_timeout = _get_lock_wait_timeout()
    try:
        _set_lock_wait_timeout(30)
        if _needs_case_sensitive_fk_refresh(pending_columns):
            print('Refreshing case-sensitive foreign keys')
            _drop_case_sensitive_fks()
        _set_foreign_key_checks(False)
        _alter_name_columns(pending_columns, CASE_SENSITIVE_NAME)
        if _needs_case_sensitive_fk_refresh(pending_columns):
            _create_case_sensitive_fks()
    finally:
        _restore_migration_session(True, old_lock_wait_timeout)


def downgrade():
    if not _is_mysql():
        return
    pending_columns = _pending_name_columns(case_sensitive=False)
    if not pending_columns:
        return
    old_lock_wait_timeout = _get_lock_wait_timeout()
    try:
        _set_lock_wait_timeout(30)
        if _needs_case_sensitive_fk_refresh(pending_columns):
            print('Refreshing case-sensitive foreign keys')
            _drop_case_sensitive_fks()
        _set_foreign_key_checks(False)
        _alter_name_columns(pending_columns, DEFAULT_NAME)
        if _needs_case_sensitive_fk_refresh(pending_columns):
            _create_case_sensitive_fks()
    finally:
        _restore_migration_session(True, old_lock_wait_timeout)
