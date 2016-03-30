# Copyright (c) 2013 OpenStack Foundation.
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

from apicapi import config as apic_config  # noqa
from oslo_config import cfg

agent_opts = [
    cfg.IntOpt('agent_down_time', default=75,
               help=("Seconds to regard the agent is down; should be at "
                     "least twice report_interval.")),
    ]

cfg.CONF.register_opts(agent_opts, 'aim')


db_opts = [
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

cfg.CONF.register_opts(db_opts, 'database')


CONF = cfg.CONF
