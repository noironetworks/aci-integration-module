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

import os
import tempfile

import eventlet
import greenlet
import mock

from aim.agent.aid import event_handler
from aim.tests import base


class TestEventHandler(base.TestAimDBBase):

    def setUp(self):
        super(TestEventHandler, self).setUp()
        self.sock_dir = tempfile.mkdtemp()
        self.addCleanup(self._rm_socket_dir)
        self.set_override('unix_socket_path',
                          '%s/events/test.sock' % self.sock_dir,
                          group='aim')
        self.set_override('recovery_restart', False, 'aim')
        self.handler = event_handler.EventHandler().initialize(
            self.cfg_manager)
        # Context switch
        eventlet.sleep(0)
        self.addCleanup(self._unlink_socket)

        self.sender = event_handler.EventSender().initialize(self.cfg_manager)
        eventlet.sleep(0)
        # Context switch
        if self.sender:
            self.addCleanup(self.sender.sock.close)

    def _rm_socket_dir(self):
        try:
            os.rmdir('%s/events' % self.sock_dir)
        except OSError:
            pass
        os.rmdir(self.sock_dir)

    def _unlink_socket(self):
        os.unlink(self.handler.us_path)

    def test_open(self):
        self.assertFalse(self.handler.sock._closed)
        self.assertFalse(self.sender.sock._closed)

    def test_receive_event(self):
        self.sender.serve()
        self.assertEqual(event_handler.EVENT_SERVE, self.handler.get_event())

        self.sender.reconcile()
        self.assertEqual(event_handler.EVENT_RECONCILE,
                         self.handler.get_event())

    def test_listener_killed(self):
        self.handler.listener.kill()
        self.assertTrue(self.handler.listener.dead)

        self.handler._recv_loop = mock.Mock(side_effect=Exception)
        self.handler.listener = self.handler._spawn_listener()
        eventlet.sleep(0)
        self.assertFalse(self.handler.listener.dead)
        self.handler.listener.kill()

        del self.handler.sock
        self.handler._connect = mock.Mock(side_effect=greenlet.GreenletExit)
        self.handler.listener = self.handler._spawn_listener()
        eventlet.sleep(0)
        self.assertTrue(self.handler.listener.dead)
