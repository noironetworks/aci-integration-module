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

from aim.tools.cli.groups import aimcli

# This file starts with an underscore, therefore will not be included in the
# final list of CLI commands


# Add hello-aim-cli to the AIM group
@aimcli.aim.command(name='hello-aim-cli')
# Add an option with help string and default value
@click.option('--greeting', help='Very helpful and descriptive',
              default='Boring default greeting')
# The option is passed down as a function argument
def hello_aim_cli(greeting):
    # click.echo will print in the standard output
    click.echo("%s" % greeting)
