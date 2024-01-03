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
import sqlalchemy as sa

from aim.agent.aid.event_services import rpc
from aim import context
from aim.db import api
from aim.tools.cli.groups import aimcli


@aimcli.aim.group(name='tenant')
@click.pass_context
def tenant(ctx):
    aim_ctx = context.AimContext(store=api.get_store(expire_on_commit=True))
    ctx.obj['aim_ctx'] = aim_ctx


# Add tenant-rebalance command to the tenant group
@tenant.command(name='rebalance',
                help="Vnodes to be modified to rebalance tenants")
@click.option('--vnodes', type=click.IntRange(40, 400),
              help='Modify the partitions between the range of 40 to 400',
              default=40)
@click.pass_context
def rebalance_tenants_across_nodes(ctx, vnodes):
    # Update the DB with the modified number of vnodes
    aim_ctx = ctx.obj['aim_ctx']
    dbsession = aim_ctx.store.db_session
    dbsession.get_bind()
    with dbsession.begin():
        aim_consistent_hashring_params_table = sa.Table(
            'aim_consistent_hashring_params', sa.MetaData(),
            sa.Column('value', sa.Integer, nullable=False),
            sa.Column('name', sa.String(16), nullable=False, primary_key=True))
        stmt = (aim_consistent_hashring_params_table.update().
                where(aim_consistent_hashring_params_table.c.name == 'vnodes').
                values(value=vnodes))
        dbsession.execute(stmt)

    # rebalance tenants across the aim processes by changing vnodes
    rpc.AIDEventRpcApi().serve({})
