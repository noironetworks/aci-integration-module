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

from aim.agent.aid.event_services import polling
from aim.tools.cli.groups import aimcli


@aimcli.aim.command(name='event-service-polling')
@click.pass_context
def event_service_polling(ctx):
    try:
        agent = polling.Poller(ctx.obj['conf'])
    except (RuntimeError, ValueError) as e:
        click.echo("%s Agent terminated!" % e)
        return
    agent.run()
