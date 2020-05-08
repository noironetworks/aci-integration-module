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

from apicapi import apic_manager
from apicapi import config as cfg
from oslo_log import log as logging

from aim import aim_manager
from aim import config
from aim import context
from aim.db import api
from aim.db import infra_model
from aim.tools.cli.groups import aimcli


def get_apic_manager():
    apic_config = config.CONF.apic
    network_config = {
        'vlan_ranges': apic_config.vlan_ranges,
        'switch_dict': cfg.create_switch_dictionary(),
        'vpc_dict': cfg.create_vpc_dictionary(apic_config),
        'external_network_dict': cfg.create_external_network_dictionary(),
    }
    aim_ctx = context.AimContext(store=api.get_store())
    manager = aim_manager.AimManager()
    db = infra_model.HostLinkManager(aim_ctx, manager)
    apic_system_id = config.CONF.apic_system_id
    return apic_manager.APICManager(db, logging, network_config, apic_config,
                                    None, None, apic_system_id)


@aimcli.aim.group(name='infra')
@click.pass_context
def infra(ctx):
    cfg.ConfigValidator.validators.pop('apic_model', None)
    ctx.obj['apic_manager'] = get_apic_manager()


@infra.command(name='create')
@click.pass_context
def create(ctx):
    ctx.obj['apic_manager'].ensure_infra_created_on_apic()
    ctx.obj['apic_manager'].ensure_bgp_pod_policy_created_on_apic()
    ctx.obj['apic_manager'].ensure_opflex_client_cert_validation_disabled()


@infra.command(name='tag-list')
@click.option('--tag-name', '-t', help='Tag name')
@click.pass_context
def tag_list(ctx, tag_name):
    """APIC command for listing tagged resources.

    Lists all the resources in ACI with a tagInst.
    """
    with ctx.obj['apic_manager'].apic.transaction():
        # Find all the MOs with the system ID
        for mo in ctx.obj['apic_manager'].apic.list_mo(
                ctx.obj['apic_manager'].apic.tagInst.mo, name=tag_name):
            click.echo("%s" % mo['tagInst']['attributes']['dn'])


@infra.command(name='tag-delete')
@click.option('--dn', help='Distinguished Name (DN) for Managed Oobject (MO)')
@click.pass_context
def tag_delete(ctx, dn, **kwargs):
    """APIC command for deleting tagged resources.

    Deletes the tagged resources in ACI with a tagInst.
    """
    if 'tag-' not in dn.split('/')[-1]:
        click.echo("%s object isn't a tag -- ignoring" % dn)
        return
    with ctx.obj['apic_manager'].apic.transaction():
        ctx.obj['apic_manager'].apic.DELETE('/mo/%s.json' % dn)
        click.echo("%s deleted" % dn)
