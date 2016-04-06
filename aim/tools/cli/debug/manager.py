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
from oslo_utils import importutils

from aim import aim_manager
from aim.api import resource
from aim import context
from aim.db import api
from aim.tools.cli.groups import aimcli


@aimcli.aim.group(name='manager')
@click.pass_context
# Debug utility for ACI web socket
def manager(ctx):
    session = api.get_session(expire_on_commit=True)
    aim_ctx = context.AimContext(db_session=session)
    manager = aim_manager.AimManager()
    ctx.obj['manager'] = manager
    ctx.obj['aim_ctx'] = aim_ctx


@manager.command(name='create')
@click.argument('type', required=True)
@click.option('--attribute', '-a', multiple=True)
@click.pass_context
def create(ctx, type, attribute):
    manager = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']
    klass = importutils.import_class(resource.__name__ + '.%s' % type)
    attribute = {x.split('=')[0]: x.split('=')[1] for x in attribute}
    res = klass(**attribute)
    manager.create(aim_ctx, res)


@manager.command(name='delete')
@click.argument('type', required=True)
@click.option('--attribute', '-a', multiple=True)
@click.pass_context
def delete(ctx, type, attribute):
    manager = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']
    klass = importutils.import_class(resource.__name__ + '.%s' % type)
    attribute = {x.split('=')[0]: x.split('=')[1] for x in attribute}
    res = klass(**attribute)
    manager.delete(aim_ctx, res)


@manager.command(name='update')
@click.argument('type', required=True)
@click.option('--attribute', '-a', multiple=True)
@click.option('--modify', '-m', multiple=True)
@click.pass_context
def update(ctx, type, attribute, modify):
    manager = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']
    klass = importutils.import_class(resource.__name__ + '.%s' % type)
    attribute = {x.split('=')[0]: x.split('=')[1] for x in attribute}
    modify = {x.split('=')[0]: x.split('=')[1] for x in modify}
    res = klass(**attribute)
    manager.update(aim_ctx, res, **modify)
