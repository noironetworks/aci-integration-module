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

import os

import click
from oslo_db.sqlalchemy.migration_cli import manager

from aim import aim_manager
from aim.api import resource
from aim import context
from aim.db import api
from aim.db import migration
from aim.db.migration import alembic_migrations
from aim.tools.cli.groups import aimcli


@aimcli.aim.group(name='db-migration')
@click.pass_context
def db_migration(ctx):
    alembic_path = os.path.abspath(
        os.path.join(os.path.dirname(migration.__file__),
                     'alembic.ini'))
    migrate_path = os.path.abspath(os.path.dirname(
        alembic_migrations.__file__))
    migration_config = {'alembic_ini_path': alembic_path,
                        'alembic_repo_path': migrate_path}
    ctx.obj['manager'] = manager.MigrationManager(migration_config,
                                                  engine=api.get_engine())


@db_migration.command(name='version')
@click.pass_context
def version(ctx):
    """Current database version."""
    ctx.obj['manager'].version()


@db_migration.command(name='upgrade')
@click.argument('version', required=False)
@click.pass_context
def upgrade(ctx, version):
    """Used for upgrading database."""
    version = version or 'head'
    ctx.obj['manager'].upgrade(version)

    # create common tenant
    session = api.get_session(expire_on_commit=True)
    aim_ctx = context.AimContext(db_session=session)
    aim_mgr = aim_manager.AimManager()
    common_tenant = resource.Tenant(name='common', monitored=True)
    if not aim_mgr.get(aim_ctx, common_tenant):
        aim_mgr.create(aim_ctx, common_tenant)


@db_migration.command(name='stamp')
@click.argument('revision', required=True)
@click.pass_context
def stamp(ctx, revision):
    """Stamps database with provided revision."""
    ctx.obj['manager'].stamp(revision)


@db_migration.command(name='revision')
@click.option('--message', default='')
@click.option('--autogenerate/--no-autogenerate', default=False)
@click.pass_context
def revision(ctx, message, autogenerate):
    """Creates template for migration."""
    ctx.obj['manager'].revision(message=message, autogenerate=autogenerate)
