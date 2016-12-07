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

import re

from apicapi import config
import click
from tabulate import tabulate

from aim import aim_manager
from aim.api import resource
from aim.common import utils
from aim import context
from aim.db import api
from aim.tools.cli.groups import aimcli


ATTR_UNSPECIFIED = object()


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


def filter_kwargs(klass, kwargs):
    res = {}
    dummy = klass(**{k: kwargs[k] for k in klass.identity_attributes})
    for k, v in kwargs.iteritems():
        if v is not ATTR_UNSPECIFIED:
            if isinstance(getattr(dummy, k), list):
                res[k] = v.split(',')
            else:
                res[k] = v
    return res


def validate_attributes(klass, attributes, param_name, dn_is_valid=False):
    valid_attr = klass.attributes()
    if dn_is_valid and issubclass(klass, resource.AciResourceBase):
        valid_attr.append('dn')
    bad_attr = [a for a in attributes if a not in valid_attr]
    if bad_attr:
        raise click.BadParameter(
            'Invalid attribute(s): %s' % ', '.join(bad_attr),
            param_hint=param_name)


def create(klass):
    def _create(ctx, **kwargs):
        kwargs = filter_kwargs(klass, kwargs)
        manager = ctx.obj['manager']
        aim_ctx = ctx.obj['aim_ctx']
        res = klass(**kwargs)
        print_resource(manager.create(aim_ctx, res))
    return _create


def delete(klass):
    def _delete(ctx, **kwargs):
        kwargs = filter_kwargs(klass, kwargs)
        manager = ctx.obj['manager']
        aim_ctx = ctx.obj['aim_ctx']
        res = klass(**kwargs)
        manager.delete(aim_ctx, res)
    return _delete


def update(klass):
    def _update(ctx, **kwargs):
        kwargs = filter_kwargs(klass, kwargs)
        manager = ctx.obj['manager']
        aim_ctx = ctx.obj['aim_ctx']
        id = {}
        mod = {}
        for k, v in kwargs.iteritems():
            if k in klass.identity_attributes:
                id[k] = v
            else:
                mod[k] = v
        res = klass(**id)
        print_resource(manager.update(aim_ctx, res, **mod))
    return _update


def find(klass):
    def _find(ctx, **kwargs):
        column = kwargs.pop('column')
        kwargs = filter_kwargs(klass, kwargs)
        manager = ctx.obj['manager']
        aim_ctx = ctx.obj['aim_ctx']
        column = list(column) if column else []
        validate_attributes(klass, column, '--column/-c', dn_is_valid=True)
        results = manager.find(aim_ctx, klass, **kwargs)
        print_resources(results, attrs=column)
    return _find


def get(klass):
    def _get(ctx, **kwargs):
        kwargs = filter_kwargs(klass, kwargs)
        manager = ctx.obj['manager']
        aim_ctx = ctx.obj['aim_ctx']
        res = klass(**kwargs)
        res = manager.get(aim_ctx, res)
        if res:
            stat = manager.get_status(aim_ctx, res)
            print_resource(res)
            print_resource(stat)
            for f in stat.faults:
                print_resource(f)
    return _get


def describe(klass):
    def _describe(ctx):
        rows = [[set_type, ', '.join(getattr(klass, set_type))]
                for set_type in [
                    'identity_attributes', 'other_attributes',
                    'db_attributes']]
        click.echo(tabulate(rows, tablefmt='psql'))
    return _describe


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


def convert(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1-\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1-\2', s1).lower()

for res in aim_manager.AimManager._db_model_map:
    # runtime create commands
    def specify_other_attrs(f):
        for opt in reversed(res.other_attributes):
            f = click.option('--%s' % opt, default=ATTR_UNSPECIFIED)(f)
        return f

    def specify_id_attrs(f):
        for id in reversed(res.identity_attributes):
            f = click.argument(id, required=True)(f)
        return f

    def specify_all_attrs(f):
        f = specify_other_attrs(f)
        f = specify_id_attrs(f)
        return f

    def specify_id_attrs_as_options(f):
        for opt in reversed(res.identity_attributes):
            f = click.option('--%s' % opt, default=ATTR_UNSPECIFIED)(f)
        return f

    # runtime create commands
    name = convert(res.__name__)
    f = click.pass_context(create(res))
    f = specify_all_attrs(f)
    manager.command(name=name + '-create')(f)

    # runtime delete commands
    f = click.pass_context(delete(res))
    f = specify_id_attrs(f)
    manager.command(name=name + '-delete')(f)

    # runtime update commands
    f = click.pass_context(update(res))
    f = specify_all_attrs(f)
    manager.command(name=name + '-update')(f)

    # runtime find commands
    f = click.pass_context(find(res))
    f = click.option('--column', '-c', multiple=True)(f)
    f = specify_other_attrs(f)
    f = specify_id_attrs_as_options(f)
    manager.command(name=name + '-find')(f)

    # runtime get commands
    f = click.pass_context(get(res))
    f = specify_id_attrs(f)
    manager.command(name=name + '-get')(f)

    # runtime describe commands
    f = click.pass_context(describe(res))
    manager.command(name=name + '-describe')(f)
