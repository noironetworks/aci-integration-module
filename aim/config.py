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
from oslo_log import log as logging

default_opts = [
    cfg.StrOpt('host', help=("Host where this agent/controller is running"))
]

cfg.CONF.register_opts(default_opts)

agent_opts = [
    cfg.IntOpt('agent_down_time', default=75,
               help=("Seconds to regard the agent is down; should be at "
                     "least twice agent_report_interval.")),
    cfg.IntOpt('agent_polling_interval', default=5,
               help=("Seconds that need to pass before the agent starts each "
                     "new cycle.")),
    cfg.IntOpt('agent_report_interval', default=30,
               help=("Number of seconds after which an agent reports his "
                     "state"))
    ]

cfg.CONF.register_opts(agent_opts, 'aim')

logging.register_options(cfg.CONF)

CONF = cfg.CONF


def init(args, **kwargs):
    CONF(args=args, project='aim')
