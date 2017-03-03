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
from aim.api import status
from aim.api import tree as aim_tree
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim import context
from aim.db import api
from aim.k8s import api_v1

LOG = logging.getLogger(__name__)
serving_tenants = {}
name_to_res = {utils.camel_to_snake(x.__name__): x for x in
               aim_manager.AimManager.aim_resources}
OBSERVER_LOOP_MAX_WAIT = 10
OBSERVER_LOOP_MAX_RETRIES = 5
BUILDER_LOOP_MAX_WAIT = 10
BUILDER_LOOP_MAX_RETRIES = 5

COLD_BUILD_TIME = 10
WARM_BUILD_TIME = 0.2

ACTION_CREATED = 'added'
ACTION_MODIFIED = 'modified'
ACTION_DELETED = 'deleted'
ACTION_ERROR = 'error'


class K8sWatcher(object):
    """HashTree Universe of the ACI state.

    This Hash Tree based observer retrieves and stores state information
    from the Kubernetes REST API.
    """

    def __init__(self, *args, **kwargs):
        self.ctx = context.AimContext(store=api.get_store())
        if 'streaming' not in self.ctx.store.features:
            # TODO(ivar) raise something meaningful
            raise
        self.mgr = aim_manager.AimManager()
        self.tt_mgr = self.ctx.store._hashtree_db_listener.tt_mgr
        self.tt_maker = self.ctx.store._hashtree_db_listener.tt_maker
        self.tt_builder = self.ctx.store._hashtree_db_listener.tt_builder
        self.klient = self.ctx.store.klient
        self.namespace = self.ctx.store.namespace
        self.trees = {}
        self.warmup_time = COLD_BUILD_TIME
        self.q = queue.Queue()
        self.event_handler = event_handler.EventHandler
        self._stop = False
        self._http_resp = None

    def run(self):
        self.observer = threading.Thread(target=self.observer_thread)
        self.observer.daemon = True
        self.observer.start()
        self.builder = threading.Thread(target=self.builder_thread)
        self.builder.daemon = True
        self.builder.start()

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
            LOG.debug(traceback.format_exc())
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

    def builder_thread(self):
        self._thread(self.builder_loop, "K8S Tree Builder")

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
            LOG.debug("Kubernetes event received: %s", event)
            event = self._parse_event(event)
            self.q.put(event)

    def _reset_trees(self):
        self.trees = None
        try:
            while self.q.get_nowait():
                pass
        except queue.Empty:
            pass
        self.warmup_time = COLD_BUILD_TIME
        self.trees = {}

    @utils.retry_loop(BUILDER_LOOP_MAX_WAIT, BUILDER_LOOP_MAX_RETRIES,
                      'K8S observer thread')
    def builder_loop(self):
        self._builder_loop()

    def _builder_loop(self):
        if self._stop:
            LOG.info("Quitting k8s builder loop")
            raise utils.ThreadExit()
        first_event_time = None
        affected_tenants = set()
        warmup_wait = COLD_BUILD_TIME
        while warmup_wait > 0:
            event = self._get_event(warmup_wait)
            if not first_event_time:
                first_event_time = time.time()
            warmup_wait = (first_event_time + self.warmup_time -
                           time.time())
            if event:
                LOG.debug('Got event from queue: %s: %s' %
                          (event['event_type'], event['resource']))
                affected_tenants |= set(self._process_event(event))

        if self.trees:
            self._save_trees(affected_tenants)
            # Builder is warm
            self.warmup_time = WARM_BUILD_TIME

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
        key = self._get_aim_resource_tenant(aim_res)

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

    def _get_aim_resource_tenant(self, aim_resource):
        # TODO(ivar): This can potentially cause a context switch, which may
        # bring to a concurrency conflict on the shared tree map resource. We
        # should find a way to retrieve the tenant RN from status objects
        # without retrieving the parent
        if isinstance(aim_resource, status.AciStatus):
            aim_resource = self.mgr.get_by_id(self.ctx,
                                              aim_resource.parent_class,
                                              aim_resource.resource_id)
        return self.tt_maker.get_tenant_key(aim_resource)

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
                                    tree=aim_tree.OperationalTenantTree)
        if mon_trees:
            self.tt_mgr.update_bulk(self.ctx, mon_trees,
                                    tree=aim_tree.MonitoredTenantTree)

        if cfg_trees or oper_trees or mon_trees:
            self.event_handler.serve()
