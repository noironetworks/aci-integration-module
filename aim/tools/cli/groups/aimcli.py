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
from click import exceptions as exc
from oslo_config import cfg

_db_opts = [
    cfg.StrOpt('connection',
               deprecated_name='sql_connection',
               default='',
               secret=True,
               help='URL to database'),
    cfg.StrOpt('engine',
               default='',
               help='Database engine for which script will be generated '
                    'when using offline migration.'),
]


@click.group()
@click.option('--config-file', '-c', multiple=True,
              help='AIM static configuration file')
@click.pass_context
def aim(ctx, config_file):
    """Group for AIM cli."""
    if ctx.obj is None:
        ctx.obj = {}
    args = []
    for file in config_file or []:
        args += ['--config-file', file]
    cfg.CONF(project='aim', args=args)
    if not cfg.CONF.config_file:
        raise exc.UsageError(
            "Unable to find configuration file via the default "
            "search paths (~/.aim/, ~/, /etc/aim/, /etc/) and "
            "the '--config-file' option %s!" % config_file)
    cfg.CONF.register_opts(_db_opts, 'database')
    ctx.obj['conf'] = cfg.CONF
