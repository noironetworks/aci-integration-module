# Copyright (c) 2017 Cisco Systems
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

import mock

from aim.agent.aid.universes.k8s import k8s_watcher
from aim.tests import base


class TestK8SWatcher(base.TestAimDBBase):

    def setUp(self):
        super(TestK8SWatcher, self).setUp()

    @base.requires(['k8s'])
    def test_connection_monitor(self):
        k8s_watcher.MONITOR_LOOP_MAX_WAIT = 0
        watcher = k8s_watcher.K8sWatcher()
        # Watcher's _http_resp is None
        watcher._monitor_loop()

        watcher._http_resp = mock.Mock(closed=False)
        watcher._monitor_loop()

        watcher._http_resp.closed = True
        self.assertRaises(k8s_watcher.K8SObserverStopped,
                          watcher._monitor_loop)
