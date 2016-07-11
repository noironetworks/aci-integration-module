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
import json

from aim.common.hashtree import exceptions as h_exc
from aim import context
from aim.db import api
from aim.db import tree_model
from aim.tools.cli.groups import aimcli


@aimcli.aim.group(name='hashtree')
@click.pass_context
def hashtree(ctx):
    session = api.get_session(expire_on_commit=True)
    aim_ctx = context.AimContext(db_session=session)
    tenant_tree_mgr = tree_model.TenantHashTreeManager()
    ctx.obj['tenant_tree_mgr'] = tenant_tree_mgr
    ctx.obj['aim_ctx'] = aim_ctx


@hashtree.command(name='dump')
@click.option('--tenant', '-t')
@click.pass_context
def dump(ctx, tenant):
    tenant_tree_mgr = ctx.obj['tenant_tree_mgr']
    aim_ctx = ctx.obj['aim_ctx']
    tenants = [tenant] if tenant else tenant_tree_mgr.get_tenants(aim_ctx)
    for t in tenants:
        try:
            tree = tenant_tree_mgr.get(aim_ctx, t)
            click.echo('Tenant: %s' % t)
            click.echo(json.dumps(tree.root.to_dict(), indent=2))
        except h_exc.HashTreeNotFound:
            click.echo('Tree not found for tenant %s' % t)
