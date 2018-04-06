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

from aim import config
from aim.db import api

import click
from click import exceptions as exc
import logging

AVAILABLE_FORMATS = ['table', 'json']
DEFAULT_FORMAT = 'tables'

global_opts = [
    config.cfg.StrOpt('apic_system_id',
                      help="Prefix for APIC domain/names/profiles created"),
]
config.CONF.register_opts(global_opts)
curr_format = DEFAULT_FORMAT


@click.group()
@click.option('--config-file', '-c', multiple=True,
              default=['/etc/aim/aim.conf', '/etc/aim/aimctl.conf'],
              help='AIM static configuration file')
@click.option('--fmt', '-f', multiple=False,
              default='tables',
              help='AIM output format. One of: tables, json')
@click.option('--debug', '-d', is_flag=True)
@click.pass_context
def aim(ctx, config_file, fmt, debug):
    """Group for AIM cli."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
    if ctx.obj is None:
        ctx.obj = {}

    args = []
    if config_file:
        for file in config_file:
            args += ['--config-file', file]
        config.CONF(project='aim', args=args)
        if not config.CONF.config_file:
            raise exc.UsageError(
                "Unable to find configuration file via the default "
                "search paths (~/.aim/, ~/, /etc/aim/, /etc/) and "
                "the '--config-file' option %s!" % config_file)
        ctx.obj['conf'] = config.CONF

    ctx.obj['fmt'] = DEFAULT_FORMAT
    if fmt in AVAILABLE_FORMATS:
        ctx.obj['fmt'] = fmt
        curr_format = fmt

    api.get_store()
