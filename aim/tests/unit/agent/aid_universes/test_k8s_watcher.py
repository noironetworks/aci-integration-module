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


import eventlet
# https://github.com/eventlet/eventlet/issues/401
eventlet.sleep()
eventlet.monkey_patch()

import copy
import mock
from mock import patch
import time

from aim.agent.aid.universes.k8s import k8s_watcher
from aim.k8s import api_v1
from aim.tests import base


class TestK8SWatcher(base.TestAimDBBase):

    def setUp(self):
        super(TestK8SWatcher, self).setUp()

    @base.requires(['k8s'])
    def test_connection_monitor(self):
        watcher = k8s_watcher.K8sWatcher()

        resp = mock.Mock(closed=False)
        thd = 1
        watcher._observe_thread_state[thd] = {
            'http_resp': resp,
            'thread': mock.Mock(dead=False)}

        self.assertIsNone(watcher._check_observers())

        resp.closed = True
        self.assertEqual(k8s_watcher.K8SObserverStopped,
                         type(watcher._check_observers()))

        resp.closed = False
        watcher._observe_thread_state[thd]['watch_exception'] = Exception()
        self.assertEqual(Exception, type(watcher._check_observers()))

    @base.requires(['k8s'])
    def test_observe_state(self):
        watcher = k8s_watcher.K8sWatcher()
        watcher._renew_klient_watch()

        thd = 1
        watcher._observe_thread_state[thd] = {'watch_stop': False}

        resp = mock.Mock(closed=False)
        list_mock = mock.Mock(return_value=resp)
        with patch.object(watcher.klient, 'list', new=list_mock):
            watcher._observe_objects(api_v1.AciContainersObject, 1)

            self.assertEqual(resp,
                             watcher._observe_thread_state[thd]['http_resp'])

            resp.closed = True
            watcher._observe_objects(api_v1.AciContainersObject, 1)
            ts = watcher._observe_thread_state[thd]['http_resp']
            self.assertEqual(True, ts.closed)

        stream_mock = mock.Mock(side_effect=Exception('FAKE ERROR'))
        with patch.object(watcher.klient.watch, 'stream', new=stream_mock):
            watcher._observe_objects(api_v1.AciContainersObject, 1)
            exc = watcher._observe_thread_state[thd]['watch_exception']
            self.assertEqual(Exception, type(exc))

    @base.requires(['k8s'])
    def test_observe_thread_dead(self):
        watcher = k8s_watcher.K8sWatcher()

        with patch.object(watcher, '_observe_objects'):
            watcher._start_observers(['a'])
            time.sleep(1)  # yield
            self.assertEqual(k8s_watcher.K8SObserverStopped,
                             type(watcher._check_observers()))

    @base.requires(['k8s'])
    def test_pod_event_filter(self):
        watcher = k8s_watcher.K8sWatcher()
        watcher._renew_klient_watch()

        thd = 1
        watcher._observe_thread_state[thd] = {'watch_stop': False}

        self.assertTrue(watcher.q.empty())
        ev = {'type': 'ADDED',
              'object': {'kind': 'Pod',
                         'spec': {'hostNetwork': True}}}
        ev_exp = copy.copy(ev)
        ev_exp['type'] = 'DELETED'
        stream_mock = mock.Mock(return_value=[ev])

        with patch.object(watcher.klient.watch, 'stream', new=stream_mock):
            watcher._observe_objects(api_v1.Pod, 1)
            self.assertEqual(ev_exp, watcher.q.get_nowait())

            ev['object']['spec']['hostNetwork'] = False
            watcher._observe_objects(api_v1.Pod, 1)
            self.assertEqual(ev_exp, watcher.q.get_nowait())

            ev['object']['spec'].pop('hostNetwork', None)
            watcher._observe_objects(api_v1.Pod, 1)
            self.assertEqual(ev_exp, watcher.q.get_nowait())

            ev['type'] = 'MODIFIED'
            ev['object']['spec']['hostNetwork'] = True
            watcher._observe_objects(api_v1.Pod, 1)
            self.assertEqual(ev_exp, watcher.q.get_nowait())
