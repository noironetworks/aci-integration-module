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

import mock

from aim.tests import base


class TestEventServiceBase(base.TestAimDBBase):

    def setUp(self):
        super(TestEventServiceBase, self).setUp()
        self.send_serve = mock.patch(
            'aim.agent.aid.event_handler.EventSender.serve')
        self.send_serve.start()
        self.send_reconcile = mock.patch(
            'aim.agent.aid.event_handler.EventSender.reconcile')
        self.send_reconcile.start()
        self.initialize = mock.patch(
            'aim.agent.aid.event_handler.EventSender.initialize')
        self.initialize.start()

        self.addCleanup(self.send_serve.stop)
        self.addCleanup(self.send_reconcile.stop)
        self.addCleanup(self.initialize.stop)
