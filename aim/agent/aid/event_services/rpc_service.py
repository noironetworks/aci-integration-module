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

import time

from oslo_log import log as logging

from aim.agent.aid.event_services import event_service_base
from aim.agent.aid.event_services import rpc
from aim import config as aim_cfg


LOG = logging.getLogger(__name__)
logging.register_options(aim_cfg.CONF)


class RpcEventService(event_service_base.EventServiceBase):

    def run(self):
        self.endpoints = [rpc.AIDEventServerRpcCallback(self.sender)]
        self.topic = rpc.TOPIC_AID_EVENT
        self.conn = rpc.Connection()
        self.conn.create_consumer(self.topic, self.endpoints)
        self.conn.consume_in_threads()
        LOG.info("RPC Event Service initialized!")
        try:
            while self.run_daemon_loop:
                time.sleep(1)
        finally:
            LOG.info("Closing RPC connection.")
            self.conn.close()


def main():
    event_service_base.main(RpcEventService)


if __name__ == '__main__':
    main()
