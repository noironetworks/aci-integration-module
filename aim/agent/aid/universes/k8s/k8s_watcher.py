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

import Queue as queue
import threading
import time
import traceback

from oslo_log import log as logging

from aim.agent.aid import event_handler
from aim import aim_manager
from aim.api import tree as aim_tree
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim import context
from aim.db import api
from aim.k8s import api_v1
from aim import tree_manager


LOG = logging.getLogger(__name__)
serving_tenants = {}
name_to_res = {utils.camel_to_snake(x.__name__): x for x in
               aim_manager.AimManager.aim_resources}
OBSERVER_LOOP_MAX_WAIT = 10
OBSERVER_LOOP_MAX_RETRIES = 5
BUILDER_LOOP_MAX_WAIT = 10
BUILDER_LOOP_MAX_RETRIES = 5
MONITOR_LOOP_MAX_WAIT = 5
MONITOR_LOOP_MAX_RETRIES = 5

COLD_BUILD_TIME = 10
WARM_BUILD_TIME = 0.2

ACTION_CREATED = 'added'
ACTION_MODIFIED = 'modified'
ACTION_DELETED = 'deleted'
ACTION_ERROR = 'error'


class K8SObserverStopped(Exception):
    message = "Kubernetes observer connection is closed."


class K8sWatcher(object):
    """HashTree Universe of the ACI state.

    This Hash Tree based observer retrieves and stores state information
    from the Kubernetes REST API.
    """

    def __init__(self, *args, **kwargs):
        self.ctx = context.AimContext(store=api.get_store())
        if 'streaming' not in self.ctx.store.features:
            # TODO(ivar) raise something meaningful
            raise Exception
        self.mgr = aim_manager.AimManager()
        self.tt_mgr = tree_manager.HashTreeManager()
        self.tt_maker = tree_manager.AimHashTreeMaker()
        self.tt_builder = tree_manager.HashTreeBuilder(self.mgr)
        self.klient = self.ctx.store.klient
        self.namespace = self.ctx.store.namespace
        self.trees = {}
        self.warmup_time = COLD_BUILD_TIME
        self.q = queue.Queue()
        self.event_handler = event_handler.EventHandler
        self._stop = False
        self._http_resp = None
        # Tenants whose trees need to be saved in AIM
        self.affected_tenants = set()

    def run(self):
        threads = {'observer': self.observer_thread,
                   'persister': self.persistence_thread,
                   'monitor': self.monitor_thread}
        for attr, thd in threads.iteritems():
            setattr(self, attr, threading.Thread(target=thd))
            getattr(self, attr).daemon = True
            getattr(self, attr).start()

    def stop_threads(self):
        self._stop = True
        if self._http_resp:
            LOG.info('Stopping watcher HTTP response.')
            self._http_resp.close()
        self.klient.stop_watch()

    def _thread(self, func, name):
        LOG.info("Starting main loop of %s", name)
        try:
            while True:
                func()
        except utils.ThreadExit:
            return
        except Exception as e:
            LOG.error(traceback.format_exc())
            utils.perform_harakiri(LOG, "%s thread stopped "
                                        "unexpectedly: %s" % (name, e.message))

    def _parse_event(self, event):
        event_type = event['type']
        event_object = event['object']
        res_klass = name_to_res.get(event_object['spec']['type'])
        if res_klass:
            db_obj = api_v1.AciContainersObject()
            db_obj.update(event_object)
            return {
                'event_type': event_type,
                'resource': self.ctx.store.make_resource(res_klass, db_obj)
            }

    def _get_event(self, timeout=None):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            # Timeout expired
            return None

    def _renew_klient_watch(self):
        self.klient.get_new_watch()

    def observer_thread(self):
        self._thread(self.observer_loop, "K8S Observer")

    def persistence_thread(self):
        self._thread(self.persistence_loop, "K8S Tree Builder")

    def monitor_thread(self):
        self._thread(self.monitor_loop, "K8S Connection Monitor")

    @utils.retry_loop(MONITOR_LOOP_MAX_WAIT, MONITOR_LOOP_MAX_RETRIES,
                      'K8S monitor thread')
    def monitor_loop(self):
        self._monitor_loop()

    def _monitor_loop(self):
        utils.sleep(MONITOR_LOOP_MAX_WAIT)
        if self._http_resp and self._http_resp.closed:
            raise K8SObserverStopped()

    @utils.retry_loop(OBSERVER_LOOP_MAX_WAIT, OBSERVER_LOOP_MAX_RETRIES,
                      'K8S observer thread')
    def observer_loop(self):
        self._observer_loop()

    def wrap_list_namespaced_aci(self, *args, **kwargs):
        resp = self.klient.list_namespaced_aci(*args, **kwargs)
        if hasattr(resp, 'close') and callable(resp.close):
            self._http_resp = resp
        return resp

    def _observer_loop(self):
        # Reset all trees and events
        LOG.info("Resetting observer loop.")
        if self._stop:
            LOG.info("Quitting k8s observer loop")
            raise utils.ThreadExit()
        self._reset_trees()
        self._renew_klient_watch()
        for event in self.klient.watch.stream(self.wrap_list_namespaced_aci,
                                              namespace=self.namespace):
            event = self._parse_event(event)
            LOG.debug("Kubernetes event received: %s", event)
            if event:
                self.affected_tenants |= set(self._process_event(event))
            self.q.put(object())

    def _reset_trees(self):
        self.trees = None
        self.affected_tenants = set()
        try:
            while self.q.get_nowait():
                pass
        except queue.Empty:
            pass
        self.tt_mgr.delete_all(self.ctx)
        self.warmup_time = COLD_BUILD_TIME
        self.trees = {}

    @utils.retry_loop(BUILDER_LOOP_MAX_WAIT, BUILDER_LOOP_MAX_RETRIES,
                      'K8S observer thread')
    def persistence_loop(self):
        self._persistence_loop()

    def _persistence_loop(self):
        if self._stop:
            LOG.info("Quitting k8s builder loop")
            raise utils.ThreadExit()
        first_event_time = None
        warmup_wait = COLD_BUILD_TIME
        while warmup_wait > 0:
            event = self._get_event(warmup_wait)
            if not first_event_time:
                first_event_time = time.time()
            warmup_wait = (first_event_time + self.warmup_time -
                           time.time())
            if event:
                LOG.debug('Got save event from queue')

        if self.trees:
            affected_tenants = self.affected_tenants
            self.affected_tenants = set()
            try:
                # Save procedure can be context switched at this point
                self._save_trees(affected_tenants)
                self.warmup_time = WARM_BUILD_TIME
            except Exception:
                LOG.error(traceback.format_exc())
                # Put the affected tenants back to the list since we couldn't
                # persist their trees.
                self.affected_tenants |= affected_tenants

    def _process_event(self, event):
        # push event into tree
        affected_tenants = set()
        aim_res = event['resource']
        action = event['event_type']
        changes = {'added': [], 'deleted': []}
        if action.lower() in [ACTION_CREATED, ACTION_MODIFIED]:
            changes['added'].append(aim_res)
        elif action.lower() in [ACTION_DELETED]:
            changes['deleted'].append(aim_res)
        key = self.tt_maker.get_root_key(aim_res)

        # Initialize tree if needed
        if key and self.trees is not None:
            cfg = self.trees.setdefault(self.tt_builder.CONFIG, {}).setdefault(
                key, structured_tree.StructuredHashTree())
            mo = self.trees.setdefault(self.tt_builder.MONITOR, {}).setdefault(
                key, structured_tree.StructuredHashTree())
            oper = self.trees.setdefault(self.tt_builder.OPER, {}).setdefault(
                key, structured_tree.StructuredHashTree())
            affected_tenants.add(key)

            self.tt_builder.build(changes['added'], [], changes['deleted'],
                                  {self.tt_builder.CONFIG: {key: cfg},
                                   self.tt_builder.MONITOR: {key: mo},
                                   self.tt_builder.OPER: {key: oper}},
                                  aim_ctx=self.ctx)
        return affected_tenants

    def _save_trees(self, affected_tenants):
        cfg_trees = []
        oper_trees = []
        mon_trees = []
        for tenant in affected_tenants:
            tree = self.trees.get(self.tt_builder.CONFIG).get(tenant)
            if tree and tree.root_key:
                cfg_trees.append(tree)
            tree = self.trees.get(self.tt_builder.MONITOR).get(tenant)
            if tree and tree.root_key:
                mon_trees.append(tree)
            tree = self.trees.get(self.tt_builder.OPER).get(tenant)
            if tree and tree.root_key:
                oper_trees.append(tree)

        if cfg_trees:
            self.tt_mgr.update_bulk(self.ctx, cfg_trees)
        if oper_trees:
            self.tt_mgr.update_bulk(self.ctx, oper_trees,
                                    tree=aim_tree.OperationalTree)
        if mon_trees:
            self.tt_mgr.update_bulk(self.ctx, mon_trees,
                                    tree=aim_tree.MonitoredTree)

        if cfg_trees or oper_trees or mon_trees:
            self.event_handler.serve()
