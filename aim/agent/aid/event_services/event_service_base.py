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

import abc
import signal
import six
import sys

from oslo_log import log as logging

from aim.agent.aid import event_handler
from aim import config as aim_cfg
from aim import context
from aim.db import api


LOG = logging.getLogger(__name__)
logging.register_options(aim_cfg.CONF)


@six.add_metaclass(abc.ABCMeta)
class EventServiceBase(object):

    def __init__(self, conf):
        self.host = aim_cfg.CONF.aim.aim_service_identifier
        self.session = api.get_session()
        self.context = context.AimContext(self.session)
        self.conf_manager = aim_cfg.ConfigManager(self.context, self.host)
        # TODO(ivar): heartbeat for these services?
        self.sender = event_handler.EventSender().initialize(self.conf_manager)
        self.run_daemon_loop = True

    @abc.abstractmethod
    def run(self):
        pass

    def _handle_sigterm(self, signum, frame):
        LOG.debug("Agent caught SIGTERM, quitting daemon loop.")
        self.run_daemon_loop = False


def main(klass):
    aim_cfg.init(sys.argv[1:])
    aim_cfg.setup_logging()
    try:
        agent = klass(aim_cfg.CONF)
    except (RuntimeError, ValueError) as e:
        LOG.error("%s Agent terminated!" % e)
        sys.exit(1)

    signal.signal(signal.SIGTERM, agent._handle_sigterm)
    agent.run()
