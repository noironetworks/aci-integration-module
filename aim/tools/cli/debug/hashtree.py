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
from aim.common.hashtree import exceptions as h_exc
from aim import context
from aim.db import api
from aim.db import hashtree_db_listener
from aim.tools.cli.groups import aimcli
from aim import tree_manager


@aimcli.aim.group(name='hashtree')
@click.pass_context
def hashtree(ctx):
    aim_ctx = context.AimContext(store=api.get_store(expire_on_commit=True))
    tree_mgr = tree_manager.HashTreeManager()
    manager = aim_manager.AimManager()
    ctx.obj['manager'] = manager
    ctx.obj['tree_mgr'] = tree_mgr
    ctx.obj['aim_ctx'] = aim_ctx


@hashtree.command(name='dump')
@click.option('--tenant', '-t')
@click.option('--flavor', '-f')
@click.pass_context
def dump(ctx, tenant, flavor):
    trees = {'configuration': tree_manager.CONFIG_TREE,
             'operational': tree_manager.OPERATIONAL_TREE,
             'monitored': tree_manager.MONITORED_TREE}
    flavor = flavor or 'configuration'
    search = tree_manager.CONFIG_TREE
    for type, tree in list(trees.items()):
        if type.startswith(flavor):
            search = tree
            break
    tree_mgr = ctx.obj['tree_mgr']
    aim_ctx = ctx.obj['aim_ctx']
    tenants = [tenant] if tenant else tree_mgr.get_roots(aim_ctx)
    for t in tenants:
        try:
            tree = tree_mgr.get(aim_ctx, t, tree=search)
            if tree and tree.root:
                click.echo('%s for tenant %s:' % (search.__name__, t))
                click.echo(json.dumps(tree.root.to_dict(), indent=2))
            else:
                click.echo('%s not found for tenant %s' % (search.__name__, t))
        except h_exc.HashTreeNotFound:
            click.echo('%s not found for tenant %s' % (search.__name__, t))


@hashtree.command(name='count-tree-nodes')
@click.option('--tenant', '-t')
@click.option('--flavor', '-f')
@click.pass_context
def count_tree_nodes(ctx, tenant, flavor):
    trees = {'configuration': tree_manager.CONFIG_TREE,
             'operational': tree_manager.OPERATIONAL_TREE,
             'monitored': tree_manager.MONITORED_TREE}
    flavor = flavor or 'configuration'
    search = tree_manager.CONFIG_TREE
    for type, tree in list(trees.items()):
        if type.startswith(flavor):
            search = tree
            break
    tree_mgr = ctx.obj['tree_mgr']
    aim_ctx = ctx.obj['aim_ctx']
    tenants = [tenant] if tenant else tree_mgr.get_roots(aim_ctx)
    node_count = 0
    for t in tenants:
        try:
            tree = tree_mgr.get(aim_ctx, t, tree=search)
            if tree and tree.root:
                node_count += _count_nodes_rec(tree.root.to_dict())
        except h_exc.HashTreeNotFound:
            pass
    click.echo('Got a node count of %s for %s tenant(s).' %
               (str(node_count), str(len(tenants))))


@hashtree.command(name='reset')
@click.option('--tenant', '-t')
@click.pass_context
def reset(ctx, tenant):
    _reset(ctx, tenant)


def _reset(ctx, tenant):
    mgr = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']
    listener = hashtree_db_listener.HashTreeDbListener(mgr)
    listener.reset(aim_ctx.store, tenant)


def _count_nodes_rec(node):
    counter = 1
    for x in node["_children"]:
        counter += _count_nodes_rec(x)
    return counter
