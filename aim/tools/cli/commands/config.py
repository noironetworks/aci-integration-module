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

import click

from aim import config as aim_cfg
from aim import context
from aim.db import api
from aim.tools.cli.groups import aimcli


@aimcli.aim.group(name='config')
@click.pass_context
def config(ctx):
    session = api.get_session(expire_on_commit=True)
    aim_ctx = context.AimContext(db_session=session)
    ctx.obj['manager'] = aim_cfg.ConfigManager()
    ctx.obj['aim_ctx'] = aim_ctx


@config.command(name='update')
@click.argument('host', required=False)
@click.pass_context
def update(ctx, host):
    """Current database version."""
    host = host or ''
    ctx.obj['manager'].to_db(ctx.obj['aim_ctx'], ctx.obj['conf'],
                             host=host)


@config.command(name='replace')
@click.argument('host', required=False)
@click.pass_context
def replace(ctx, host):
    """Used for upgrading database."""
    host = host or ''
    ctx.obj['manager'].replace_all(ctx.obj['aim_ctx'], ctx.obj['conf'],
                                   host=host)
