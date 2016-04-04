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

import click
from click import exceptions as exc


db_opts = [
    config.cfg.StrOpt('connection',
                      deprecated_name='sql_connection',
                      default='',
                      secret=True,
                      help='URL to database'),
    config.cfg.StrOpt('engine', default='',
                      help='Database engine for which script will be '
                           'generated when using offline migration.'),
]


@click.group()
@click.option('--config-file', '-c', multiple=True,
              help='AIM static configuration file')
@click.pass_context
def aim(ctx, config_file):
    """Group for AIM cli."""
    try:
        config.CONF.register_opts(db_opts, 'database')
    except Exception:
        pass
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
