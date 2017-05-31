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
import traceback

from oslo_log import log as logging

from aim.agent.aid.event_services import event_service_base
from aim.common import utils
from aim import config as aim_cfg


LOG = logging.getLogger(__name__)
logging.register_options(aim_cfg.CONF)


class Poller(event_service_base.EventServiceBase):

    def __init__(self, conf):
        super(Poller, self).__init__(conf)
        self.loop_count = float('inf')
        # TODO(ivar): per service config
        self.polling_interval = self.conf_manager.get_option_and_subscribe(
            self._change_polling_interval, 'service_polling_interval',
            group='aim_event_service_polling')
        self.recovery_retries = None

    def run(self):
        utils.spawn_thread(self._poll)
        try:
            while self.run_daemon_loop:
                time.sleep(1)
        finally:
            LOG.info("Killing poller thread")

    def _poll(self):
        # Loop count is the equivalent of a True in normal usage, but it's
        # useful for testing.
        while self.loop_count > 0:
            try:
                start_time = time.time()
                self._daemon_loop()
                utils.wait_for_next_cycle(
                    start_time, self.polling_interval,
                    LOG, readable_caller='Event Service Poller',
                    notify_exceeding_timeout=False)
                self.loop_count -= 1
                self.recovery_retries = None
            except Exception:
                LOG.error('A error occurred in polling agent.')
                LOG.error(traceback.format_exc())
                self.recovery_retries = utils.exponential_backoff(
                    10, tentative=self.recovery_retries)

    def _daemon_loop(self):
        self.sender.serve()

    def _change_polling_interval(self, new_conf):
        # TODO(ivar): interrupt current sleep and restart with new value
        self.polling_interval = new_conf['value']


def main():
    event_service_base.main(Poller)


if __name__ == '__main__':
    main()
