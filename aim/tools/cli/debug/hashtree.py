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

from aim import aim_manager
from aim.api import resource
from aim.common.hashtree import exceptions as h_exc
from aim import context
from aim.db import api
from aim.db import hashtree_db_listener
from aim.db import tree_model
from aim.tools.cli.groups import aimcli


@aimcli.aim.group(name='hashtree')
@click.pass_context
def hashtree(ctx):
    session = api.get_session(expire_on_commit=True)
    aim_ctx = context.AimContext(db_session=session)
    tenant_tree_mgr = tree_model.TenantHashTreeManager()
    manager = aim_manager.AimManager()
    ctx.obj['manager'] = manager
    ctx.obj['tenant_tree_mgr'] = tenant_tree_mgr
    ctx.obj['aim_ctx'] = aim_ctx


@hashtree.command(name='dump')
@click.option('--tenant', '-t')
@click.option('--flavor', '-f')
@click.pass_context
def dump(ctx, tenant, flavor):
    trees = {'configuration': tree_model.CONFIG_TREE,
             'operational': tree_model.OPERATIONAL_TREE,
             'monitored': tree_model.MONITORED_TREE}
    flavor = flavor or 'configuration'
    search = tree_model.CONFIG_TREE
    for type, tree in trees.iteritems():
        if type.startswith(flavor):
            search = tree
            break
    tenant_tree_mgr = ctx.obj['tenant_tree_mgr']
    aim_ctx = ctx.obj['aim_ctx']
    tenants = [tenant] if tenant else tenant_tree_mgr.get_tenants(aim_ctx)
    for t in tenants:
        try:
            tree = tenant_tree_mgr.get(aim_ctx, t, tree=search)
            if tree and tree.root:
                click.echo('%s for tenant %s:' % (search.__name__, t))
                click.echo(json.dumps(tree.root.to_dict(), indent=2))
            else:
                click.echo('%s not found for tenant %s' % (search.__name__, t))
        except h_exc.HashTreeNotFound:
            click.echo('%s not found for tenant %s' % (search.__name__, t))


@hashtree.command(name='reset')
@click.option('--tenant', '-t')
@click.pass_context
def reset(ctx, tenant):
    _reset(ctx, tenant)


def _reset(ctx, tenant):
    mgr = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']
    listener = hashtree_db_listener.HashTreeDbListener(mgr, aim_ctx.store)
    session = aim_ctx.db_session
    with session.begin(subtransactions=True):
        created = []
        # Delete existing trees
        filters = {}
        if tenant:
            filters['name'] = tenant
        tenants = mgr.find(aim_ctx, resource.Tenant, **filters)
        for t in tenants:
            listener.tt_mgr.delete_by_tenant_rn(aim_ctx, t.name)
        # Retrieve objects
        for klass in aim_manager.AimManager._db_model_map:
            if issubclass(klass, resource.AciResourceBase):
                filters = {}
                if tenant:
                    filters[klass.tenant_ref_attribute] = tenant
                # Get all objects of that type
                for obj in mgr.find(aim_ctx, klass, **filters):
                    # Need all the faults and statuses as well
                    stat = mgr.get_status(aim_ctx, obj)
                    if stat:
                        created.append(stat)
                        created.extend(stat.faults)
                        del stat.faults
                    created.append(obj)
        # Reset the trees
        listener.on_commit(session, created, [], [])
