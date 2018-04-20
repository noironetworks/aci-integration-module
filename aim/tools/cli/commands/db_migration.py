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
import sqlalchemy as sa

from aim.agent.aid.universes.aci import aci_universe
from aim import aim_manager
from aim.api import resource
from aim.common import utils
from aim import config
from aim import context
from aim.db import api
from aim.db import hashtree_db_listener
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
    config.setup_logging()


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
    aim_ctx = context.AimContext(store=api.get_store(expire_on_commit=True))
    aim_mgr = aim_manager.AimManager()
    common_tenant = resource.Tenant(name='common', monitored=True)
    if not aim_mgr.get(aim_ctx, common_tenant):
        aim_mgr.create(aim_ctx, common_tenant)

    fix_no_nat_l3out_ownership(aim_ctx)

    click.echo('Rebuilding hash-trees')
    _reset(aim_mgr)


@utils.retry_loop(60, 10, 'reset hashtree', return_=True)
def _reset(aim_mgr):
    aim_ctx = context.AimContext(store=api.get_store(expire_on_commit=True))
    # reset hash-trees to account for schema/converter changes
    listener = hashtree_db_listener.HashTreeDbListener(aim_mgr)
    aim_ctx.store.db_session.expunge_all()
    listener.reset(aim_ctx.store)


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


def fix_no_nat_l3out_ownership(aim_ctx):
    """Relinquish ownership of no-NAT L3Outs in AIM and APIC."""
    saved_l3out_table = sa.Table(
        'aim_lib_save_l3out',
        sa.MetaData(),
        sa.Column('tenant_name', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), primary_key=True),
        sa.Column('monitored', nullable=True),
        sa.Column('vrf_name', nullable=True))
    session = aim_ctx.store.db_session
    bind = session.get_bind()
    with session.begin(subtransactions=True):
        if not saved_l3out_table.exists(bind=bind):
            return
        results = session.execute(
            saved_l3out_table.select(saved_l3out_table.c.monitored.is_(True)))
        click.echo("Fixing ownership of no-NAT L3Outs")
        rows = results.fetchall()
        if rows:
            cfg_mgr = config.ConfigManager(aim_ctx)
            system_id = cfg_mgr.get_option('aim_system_id', 'aim')
            aim_mgr = aim_manager.AimManager()
            apic = aci_universe.AciUniverse.establish_aci_session(cfg_mgr)
            for row in rows:
                l3out = resource.L3Outside(tenant_name=row['tenant_name'],
                                           name=row['name'])
                aim_mgr.update(aim_ctx, l3out, monitored=True)
                tag_dn = "/mo/" + l3out.dn + "/tag-" + system_id
                click.echo('Deleting AIM tag %s' % tag_dn)
                apic.DELETE(tag_dn + ".json")
    # drop the table after the transaction completes because databases
    # like MySQL hold locks on the table
    saved_l3out_table.drop(bind=bind)
