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

from aim.agent.aid import service
from aim.tools.cli.groups import aimcli


@aimcli.aim.command(name='aid')
@click.pass_context
# Debug utility for ACI web socket
def aid(ctx):
    try:
        agent = service.AID(ctx.obj['conf'])
    except (RuntimeError, ValueError) as e:
        click.echo("%s Agent terminated!" % e)
        return
    agent.daemon_loop()
