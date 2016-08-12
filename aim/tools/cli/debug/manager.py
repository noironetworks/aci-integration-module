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

from apicapi import config
import click
from oslo_utils import importutils
from tabulate import tabulate

from aim import aim_manager
from aim.api import resource
from aim.common import utils
from aim import context
from aim.db import api
from aim.tools.cli.groups import aimcli


def print_resource(res):
    if res:
        rows = [[a, getattr(res, a, None)] for a in res.attributes()]
        if isinstance(res, resource.AciResourceBase):
            rows.append(['dn', res.dn])
        click.echo(tabulate(rows, headers=['Property', 'Value'],
                            tablefmt='psql'))


def print_resources(res_list, attrs=None):
    if not res_list:
        return
    if attrs:
        header = ['Identity'] + attrs
        rows = [([','.join(res.identity)] +
                 [getattr(res, a, None) for a in attrs])
                for res in res_list]
    else:
        header = res_list[0].identity_attributes
        rows = [res.identity for res in res_list]
    click.echo(tabulate(rows, headers=header, tablefmt='psql'))


@aimcli.aim.group(name='manager')
@click.pass_context
# Debug utility for ACI web socket
def manager(ctx):
    session = api.get_session(expire_on_commit=True)
    aim_ctx = context.AimContext(db_session=session)
    manager = aim_manager.AimManager()
    ctx.obj['manager'] = manager
    ctx.obj['aim_ctx'] = aim_ctx


def validate_attributes(klass, attributes, param_name, dn_is_valid=False):
    valid_attr = klass.attributes()
    if dn_is_valid and issubclass(klass, resource.AciResourceBase):
        valid_attr.append('dn')
    bad_attr = [a for a in attributes if a not in valid_attr]
    if bad_attr:
        raise click.BadParameter(
            'Invalid attribute(s): %s' % ', '.join(bad_attr),
            param_hint=param_name)


@manager.command(name='create')
@click.argument('type', required=True)
@click.option('--attribute', '-a', multiple=True)
@click.pass_context
def create(ctx, type, attribute):
    manager = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']
    klass = importutils.import_class(resource.__name__ + '.%s' % type)
    attribute = {x.split('=')[0]: x.split('=')[1] for x in attribute}
    validate_attributes(klass, attribute.keys(), '--attribute/-a')
    res = klass(**attribute)
    print_resource(manager.create(aim_ctx, res))


@manager.command(name='delete')
@click.argument('type', required=True)
@click.option('--attribute', '-a', multiple=True)
@click.pass_context
def delete(ctx, type, attribute):
    manager = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']
    klass = importutils.import_class(resource.__name__ + '.%s' % type)
    attribute = {x.split('=')[0]: x.split('=')[1] for x in attribute}
    validate_attributes(klass, attribute.keys(), '--attribute/-a')
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
    validate_attributes(klass, attribute.keys(), '--attribute/-a')
    modify = {x.split('=')[0]: x.split('=')[1] for x in modify}
    validate_attributes(klass, modify.keys(), '--modify/-m')
    res = klass(**attribute)
    print_resource(manager.update(aim_ctx, res, **modify))


@manager.command(name='find')
@click.argument('type', required=True)
@click.option('--attribute', '-a', multiple=True)
@click.option('--column', '-c', multiple=True)
@click.pass_context
def find(ctx, type, attribute, column):
    manager = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']
    klass = importutils.import_class(resource.__name__ + '.%s' % type)
    column = list(column) if column else []
    validate_attributes(klass, column, '--column/-c', dn_is_valid=True)
    attribute = {x.split('=')[0]: x.split('=')[1] for x in attribute}
    validate_attributes(klass, attribute.keys(), '--attribute/-a')
    results = manager.find(aim_ctx, klass, **attribute)
    print_resources(results, attrs=column)


@manager.command(name='get')
@click.argument('type', required=True)
@click.option('--attribute', '-a', multiple=True)
@click.pass_context
def get(ctx, type, attribute):
    manager = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']
    klass = importutils.import_class(resource.__name__ + '.%s' % type)
    attribute = {x.split('=')[0]: x.split('=')[1] for x in attribute}
    validate_attributes(klass, attribute.keys(), '--attribute/-a')
    res = klass(**attribute)
    res = manager.get(aim_ctx, res)
    print_resource(res)


@manager.command(name='describe')
@click.argument('type', required=True)
@click.pass_context
def describe(ctx, type):
    klass = importutils.import_class(resource.__name__ + '.%s' % type)
    rows = [[set_type, ', '.join(getattr(klass, set_type))]
            for set_type in [
                'identity_attributes', 'other_attributes', 'db_attributes']]
    click.echo(tabulate(rows, tablefmt='psql'))


@manager.command(name='load-domains')
@click.option('--replace/--no-replace', default=False)
@click.option('--enforce/--no-enforce', default=False)
@click.pass_context
def load_domains(ctx, replace, enforce):
    manager = ctx.obj['manager']
    aim_ctx = ctx.obj['aim_ctx']

    with aim_ctx.db_session.begin(subtransactions=True):
        if replace:
            curr_vmms = manager.find(aim_ctx, resource.VMMDomain)
            curr_physds = manager.find(aim_ctx, resource.PhysicalDomain)

            for dom in curr_physds + curr_vmms:
                click.echo("Deleting %s: %s" % (type(dom), dom.__dict__))
                manager.delete(aim_ctx, dom)

        vmms = config.create_vmdom_dictionary()
        physdoms = config.create_physdom_dictionary()
        for vmm in vmms:
            res = resource.VMMDomain(type='OpenStack', name=vmm)
            print_resource(manager.create(aim_ctx, res, overwrite=True))
        for phys in physdoms:
            res = resource.PhysicalDomain(name=phys)
            print_resource(manager.create(aim_ctx, res, overwrite=True))

        if enforce:
            # Update the existing EPGs with the new domain configuration
            all_vmms = manager.find(aim_ctx, resource.VMMDomain)
            all_physds = manager.find(aim_ctx, resource.PhysicalDomain)
            os_vmm_names = [vmm.name for vmm in all_vmms
                            if vmm.type == utils.OPENSTACK_VMM_TYPE]
            phys_names = [phys.name for phys in all_physds]
            all_epgs = manager.find(aim_ctx, resource.EndpointGroup)
            for epg in all_epgs:
                print_resource(
                    manager.update(aim_ctx, epg,
                                   openstack_vmm_domain_names=os_vmm_names,
                                   physical_domain_names=phys_names))
