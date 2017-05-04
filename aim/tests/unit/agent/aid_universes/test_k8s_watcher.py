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

import copy
import mock
from mock import patch
import time

from aim.agent.aid.universes.k8s import k8s_watcher
from aim import aim_manager
from aim.api import resource
from aim.api import status
from aim.k8s import api_v1
from aim.tests import base


class TestK8SWatcher(base.TestAimDBBase):

    def setUp(self):
        super(TestK8SWatcher, self).setUp()
        self.mgr = aim_manager.AimManager()

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
        stream_mock = mock.Mock()

        with patch.object(watcher.klient.watch, 'stream', new=stream_mock):
            stream_mock.return_value = [copy.copy(ev)]
            watcher._observe_objects(api_v1.Pod, 1)
            self.assertEqual(ev_exp, watcher.q.get_nowait())

            ev['object']['spec']['hostNetwork'] = False
            stream_mock.return_value = [copy.copy(ev)]
            watcher._observe_objects(api_v1.Pod, 1)
            self.assertEqual(ev, watcher.q.get_nowait())

            ev['object']['spec'].pop('hostNetwork', None)
            stream_mock.return_value = [copy.copy(ev)]
            watcher._observe_objects(api_v1.Pod, 1)
            self.assertEqual(ev, watcher.q.get_nowait())

            ev['type'] = 'MODIFIED'
            ev['object']['spec']['hostNetwork'] = True
            stream_mock.return_value = [copy.copy(ev)]
            watcher._observe_objects(api_v1.Pod, 1)
            self.assertEqual(ev_exp, watcher.q.get_nowait())

    @base.requires(['k8s'])
    def test_delete_status(self):
        tn = self.mgr.create(self.ctx, resource.Tenant(
            name='test_delete_status'))
        st = self.mgr.get_status(self.ctx, tn)
        self.assertIsNotNone(self.mgr.get(self.ctx, st))
        db_obj = self.mgr._query_db_obj(self.ctx.store, tn)
        self.ctx.store.delete(db_obj)
        self.assertIsNone(self.mgr.get(self.ctx, st))

    @base.requires(['k8s'])
    def test_no_tree_update_on_event(self):
        bd = resource.BridgeDomain(tenant_name='t1', name='bd1')
        bd_db_obj = self.ctx.store.make_db_obj(bd)
        bd_db_obj.update({'kind': bd_db_obj.kind,
                          'apiVersion': bd_db_obj.api_version})

        ev = {'type': 'ADDED', 'object': bd_db_obj}

        watcher = k8s_watcher.K8sWatcher()
        self.assertEqual(set(['tn-t1']), watcher._process_event(ev))

        # no-change event
        self.assertEqual(set(), watcher._process_event(ev))

        # no real change
        ev['type'] = 'MODIFIED'
        self.assertEqual(set(), watcher._process_event(ev))

        # change to irrelevant attribute
        ev['object']['spec']['someAttr'] = 'someValue'
        self.assertEqual(set(), watcher._process_event(ev))

        # delete
        ev['type'] = 'DELETED'
        self.assertEqual(set(['tn-t1']), watcher._process_event(ev))

    @base.requires(['k8s'])
    def test_endpoints_event(self):
        watcher = k8s_watcher.K8sWatcher()
        store = self.ctx.store

        ns = resource.VmmInjectedNamespace(
            domain_type='Kubernetes',
            domain_name='kubernetes',
            controller_name='kube-cluster',
            name='ns-%s' % self.test_id)
        svc = resource.VmmInjectedService(
            domain_type=ns.domain_type,
            domain_name=ns.domain_name,
            controller_name=ns.controller_name,
            namespace_name=ns.name,
            name='svc1',
            service_ports=[{'port': '23', 'protocol': 'tcp',
                            'target_port': '45'}],
            endpoints=[{'ip': '1.2.3.4', 'pod_name': 'foo'},
                       {'ip': '2.1.3.4', 'pod_name': 'bar'}])

        svc_db_obj = store.make_db_obj(svc)
        ep_db_obj = svc_db_obj.endpoints
        ep_db_obj['subsets'][0]['ports'] = [{'port': 80}]

        ev_obj = {'kind': ep_db_obj.kind,
                  'apiVersion': ep_db_obj.api_version}
        ev_obj.update(ep_db_obj)
        ev = {'type': 'ADDED', 'object': ev_obj}

        # event with no Service object
        self.assertIsNone(watcher._parse_event(ev))

        def _verify_event_processing(exp_svc):
            res = watcher._parse_event(ev)
            self.assertEqual('modified', res['event_type'])
            self.assertEqual(resource.VmmInjectedService,
                             type(res['resource']))
            for attr in ['name', 'namespace_name', 'endpoints']:
                self.assertEqual(getattr(exp_svc, attr),
                                 getattr(res['resource'], attr))

            aff_ten = watcher._process_event(ev)
            self.assertEqual(set(['vmmp-Kubernetes']), aff_ten)
            cfg_tree = watcher.trees['config']['vmmp-Kubernetes']
            ht_key = (watcher.tt_builder.tt_maker
                      ._build_hash_tree_key(exp_svc))
            ht_children = [x.key
                           for x in cfg_tree.find(ht_key).get_children()
                           if 'vmmInjectedSvcEp|' in x.key[-1]]
            self.assertEqual(len(exp_svc.endpoints), len(ht_children))
            for e in exp_svc.endpoints:
                child_key = ht_key + ('vmmInjectedSvcEp|%s' % e['pod_name'],)
                self.assertTrue(child_key in ht_children,
                                child_key)

        # create Service and Endpoints, send event
        self.mgr.create(self.ctx, ns)
        self.mgr.create(self.ctx, svc)
        store.klient.create(type(ep_db_obj),
                            ep_db_obj['metadata']['namespace'],
                            ep_db_obj)
        _verify_event_processing(svc)

        # update Endpoints, send event
        ep_db_obj['subsets'][0]['addresses'] = (
            ep_db_obj['subsets'][0]['addresses'][:-1])
        store.klient.replace(type(ep_db_obj),
                             ep_db_obj['metadata']['name'],
                             ep_db_obj['metadata']['namespace'],
                             ep_db_obj)
        svc.endpoints = svc.endpoints[:-1]
        ev['type'] = 'MODIFIED'
        _verify_event_processing(svc)

        # delete Endpoints, send event
        store.klient.delete(type(ep_db_obj),
                            ep_db_obj['metadata']['name'],
                            ep_db_obj['metadata']['namespace'],
                            {})
        ev['type'] = 'DELETED'
        svc.endpoints = []
        _verify_event_processing(svc)

    @base.requires(['k8s'])
    def test_endpoints_event_filter(self):
        watcher = k8s_watcher.K8sWatcher()
        watcher._renew_klient_watch()

        thd = 1
        watcher._observe_thread_state[thd] = {'watch_stop': False}

        self.assertTrue(watcher.q.empty())
        ev = {'type': 'MODIFIED',
              'object': {'kind': 'Endpoints',
                         'metadata': {}}}
        stream_mock = mock.Mock(return_value=[ev])

        with patch.object(watcher.klient.watch, 'stream', new=stream_mock):
            for n in ['kube-controller-manager', 'kube-scheduler']:
                ev['object']['metadata']['name'] = n
                watcher._observe_objects(api_v1.Endpoints, 1)
                self.assertTrue(watcher.q.empty())

    @base.requires(['k8s'])
    def test_process_pod_status_event(self):
        watcher = k8s_watcher.K8sWatcher()
        store = self.ctx.store

        ns = resource.VmmInjectedNamespace(
            domain_type='Kubernetes',
            domain_name='kubernetes',
            controller_name='kube-cluster',
            name='ns-%s' % self.test_id)
        pod = resource.VmmInjectedContGroup(
            domain_type=ns.domain_type,
            domain_name=ns.domain_name,
            controller_name=ns.controller_name,
            namespace_name=ns.name,
            name='pod1')
        pod_ht_key = watcher.tt_builder.tt_maker._build_hash_tree_key(pod)

        self.mgr.create(self.ctx, ns)

        pod_db_obj = store.make_db_obj(pod)
        store.add(pod_db_obj)
        pod_db_obj = store.query(api_v1.Pod, resource.VmmInjectedContGroup,
                                 namespace_name=ns.name, name=pod.name)[0]

        pod.name = 'hidden-pod1'
        hidden_pod_ht_key = (
            watcher.tt_builder.tt_maker._build_hash_tree_key(pod))
        hidden_pod_db_obj = store.make_db_obj(pod)
        hidden_pod_db_obj['spec']['hostNetwork'] = True
        store.add(hidden_pod_db_obj)
        hidden_pod_db_obj = store.query(api_v1.Pod,
                                        resource.VmmInjectedContGroup,
                                        namespace_name=ns.name,
                                        name=pod.name)[0]

        # test pod that is not hidden
        stat = status.AciStatus(resource_type='VmmInjectedContGroup',
                                resource_id=pod_db_obj.aim_id,
                                resource_root=pod.root)
        for t in ['ADDED', 'MODIFIED', 'DELETED']:
            ev = {'event_type': t, 'resource': stat}
            exp_ev = copy.copy(ev)

            watcher._process_pod_status_event(ev)
            self.assertEqual(exp_ev, ev)

        # seed the hash-tree with the non-hidden pod
        ev = {'type': 'ADDED', 'object': pod_db_obj}
        watcher._process_event(ev)
        cfg_tree = watcher.trees['config'][pod.root]
        self.assertIsNotNone(cfg_tree.find(pod_ht_key))

        # test pod that is hidden
        stat.resource_id = hidden_pod_db_obj.aim_id
        for t in ['ADDED', 'MODIFIED', 'DELETED']:
            ev = {'event_type': t, 'resource': stat}
            exp_ev = copy.copy(ev)
            exp_ev['event_type'] = 'DELETED'
            watcher._process_pod_status_event(ev)
            self.assertEqual(exp_ev, ev)

            ev2 = {'type': t, 'object': store.make_db_obj(stat)}
            watcher._process_event(ev2)
            self.assertIsNone(cfg_tree.find(hidden_pod_ht_key))
