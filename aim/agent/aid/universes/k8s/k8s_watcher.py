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

import eventlet
from eventlet import queue
import time
import traceback

from oslo_log import log as logging

from aim.agent.aid import event_handler
from aim import aim_manager
from aim.api import resource
from aim.api import status
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
        self._observe_thread_state = {}

        self._k8s_types_to_observe = set([])
        self._k8s_aim_type_map = {}
        self._k8s_kinds = set([])

        for aim_res in aim_manager.AimManager.aim_resources:
            if issubclass(aim_res, resource.AciResourceBase):
                k8s_type = self.ctx.store.resource_to_db_type(aim_res)
                self._k8s_types_to_observe.add(k8s_type)
                self._k8s_kinds.add(k8s_type.kind)
                if k8s_type != api_v1.AciContainersObject:
                    self._k8s_aim_type_map[k8s_type.kind] = (aim_res, k8s_type)

        self._event_filters = {api_v1.Pod: self._pod_event_filter}

    def run(self):
        threads = {'observer': self.observer_thread,
                   'persister': self.persistence_thread}
        for attr, thd in threads.iteritems():
            setattr(self, attr, eventlet.spawn(thd))

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

    def _pod_event_filter(self, event):
        spec = event.get('object', {}).get('spec', {})
        if (spec.get('hostNetwork') and
                event['type'].lower() != ACTION_DELETED):
            # Mark hostNetwork objects as deleted to clean them and any
            # related objects (e.g. Status) from the tree/backend.
            event['type'] = ACTION_DELETED.upper()
        return True

    def _get_event(self, timeout=None):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            # Timeout expired
            return None

    def _renew_klient_watch(self):
        self.klient.get_new_watch()

    def observer_thread(self):
        self._thread(self.observe_and_monitor_loop, "K8S Observer")

    def persistence_thread(self):
        self._thread(self.persistence_loop, "K8S Tree Builder")

    @utils.retry_loop(OBSERVER_LOOP_MAX_WAIT, OBSERVER_LOOP_MAX_RETRIES,
                      'K8S observer thread')
    def observe_and_monitor_loop(self):
        LOG.info("Starting observe and monitor loop.")

        if self._stop:
            LOG.info("Quitting k8s observe and monitor loop")
            raise utils.ThreadExit()

        self._start_observers(self._k8s_types_to_observe)

        while not self._stop:
            exc = self._check_observers()
            if exc:
                break
            utils.sleep(MONITOR_LOOP_MAX_WAIT)
        for ts in self._observe_thread_state.values():
            ts['watch_stop'] = True
            ts['thread'].kill()
        if self.klient.watch:
            self.klient.stop_watch()
        if exc:
            raise exc

    def _start_observers(self, types_to_observe):
        self._reset_trees()
        self._renew_klient_watch()

        self._observe_thread_state = {}
        for id, typ in enumerate(list(types_to_observe)):
            self._observe_thread_state[id] = dict(watch_stop=False)
            thd = eventlet.spawn(self._observe_objects, typ, id)
            self._observe_thread_state[id]['thread'] = thd

    def _check_observers(self):
        exc = None
        for t in self._observe_thread_state:
            tstate = self._observe_thread_state[t]
            thd = tstate['thread']
            if tstate.get('watch_exception'):
                exc = tstate.get('watch_exception')
                LOG.info('Thread %s raised exception %s', thd, exc)
                break
            if tstate.get('http_resp') and tstate['http_resp'].closed:
                LOG.info('HTTP response closed for thread %s', thd)
                exc = K8SObserverStopped()
                break
            if thd.dead:
                LOG.info('Thread %s is not alive', thd)
                exc = K8SObserverStopped()
                break
        return exc

    def wrap_list_call(self, *args, **kwargs):
        tstate = kwargs.pop('_thread_state')
        resp = self.klient.list(*args, **kwargs)
        if hasattr(resp, 'close') and callable(resp.close):
            tstate['http_resp'] = resp
        return resp

    def _observe_objects(self, k8s_type, id):
        my_state = self._observe_thread_state.get(id, {})
        LOG.debug('Start observing %s objects', k8s_type.kind)
        ev_filt = self._event_filters.get(k8s_type, lambda x: True)
        if not my_state['watch_stop']:
            try:
                ns = (self.namespace
                      if k8s_type == api_v1.AciContainersObject else None)
                for event in self.klient.watch.stream(
                        self.wrap_list_call, k8s_type,
                        _thread_state=my_state,
                        namespace=ns):
                    if my_state['watch_stop']:
                        LOG.debug('Stopping %s objects thread', k8s_type.kind)
                        break
                    ev_name = event.get('object',
                                        {}).get('metadata',
                                                {}).get('name')
                    if ev_filt(event):
                        LOG.debug("Received Kubernetes event for %s %s",
                                  k8s_type.kind, ev_name or event)
                        self.q.put(event)
                    else:
                        LOG.debug("Ignoring Kubernetes event for %s %s",
                                  k8s_type.kind, ev_name or event)
            except Exception as e:
                LOG.debug('Observe %s objects caught exception: %s',
                          k8s_type.kind, e)
                LOG.debug(traceback.format_exc())
                my_state['watch_exception'] = e
        LOG.debug('End observing %s objects', k8s_type.kind)

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
        affected_tenants = set(self.affected_tenants)
        while warmup_wait > 0:
            event = self._get_event(warmup_wait)
            if not first_event_time:
                first_event_time = time.time()
            warmup_wait = (first_event_time + self.warmup_time -
                           time.time())
            if event:
                LOG.debug('Got save event from queue')
                affected_tenants |= self._process_event(event)

        if affected_tenants:
            LOG.info('Saving trees for tenants: %s', affected_tenants)
            try:
                # Save procedure can be context switched at this point
                self._save_trees(affected_tenants)
                self.warmup_time = WARM_BUILD_TIME
                self.affected_tenants = set()
            except Exception:
                LOG.error(traceback.format_exc())
                # Put the affected tenants back to the list since we couldn't
                # persist their trees.
                self.affected_tenants |= affected_tenants

    def _parse_event(self, event):
        event_type = event['type']
        event_object = event['object']
        kind = event_object.get('kind')
        if kind not in self._k8s_kinds:
            return

        if kind == api_v1.AciContainersObject.kind:
            aim_klass = name_to_res.get(event_object['spec']['type'])
            k8s_type = api_v1.AciContainersObject
        else:
            aim_klass, k8s_type = self._k8s_aim_type_map[kind]

        if aim_klass and k8s_type:
            db_obj = k8s_type()
            db_obj.update(event_object)
            aim_res = self.ctx.store.make_resource(aim_klass, db_obj)
            try:
                aim_res.aim_id = db_obj.aim_id
            except (AttributeError, KeyError):
                pass
            return {'event_type': event_type,
                    'resource': aim_res}

    def _process_event(self, event):
        event = self._parse_event(event)
        affected_tenants = set()
        if not event:
            return affected_tenants

        aim_res = event['resource']
        if (not isinstance(aim_res, resource.AciResourceBase) and
                not isinstance(aim_res, status.OperationalResource)):
            return affected_tenants

        # push event into tree
        action = event['event_type']
        changes = {'added': [], 'deleted': []}
        if action.lower() in [ACTION_CREATED, ACTION_MODIFIED]:
            changes['added'].append(aim_res)
        elif action.lower() in [ACTION_DELETED]:
            self._cleanup_status(aim_res)
            changes['deleted'].append(aim_res)
        key = self.tt_maker.get_root_key(aim_res)

        LOG.info('K8s event: %s %s', action, aim_res)

        # Initialize tree if needed
        if key and self.trees is not None:
            cfg = self.trees.setdefault(self.tt_builder.CONFIG, {}).setdefault(
                key, structured_tree.StructuredHashTree())
            mo = self.trees.setdefault(self.tt_builder.MONITOR, {}).setdefault(
                key, structured_tree.StructuredHashTree())
            oper = self.trees.setdefault(self.tt_builder.OPER, {}).setdefault(
                key, structured_tree.StructuredHashTree())
            old_hash = (cfg.root_full_hash, mo.root_full_hash,
                        oper.root_full_hash)

            self.tt_builder.build(changes['added'], [], changes['deleted'],
                                  {self.tt_builder.CONFIG: {key: cfg},
                                   self.tt_builder.MONITOR: {key: mo},
                                   self.tt_builder.OPER: {key: oper}},
                                  aim_ctx=self.ctx)
            new_hash = (cfg.root_full_hash, mo.root_full_hash,
                        oper.root_full_hash)
            if old_hash != new_hash:
                affected_tenants.add(key)
        return affected_tenants

    def _cleanup_status(self, aim_res):
        if isinstance(aim_res, resource.AciResourceBase):
            LOG.debug("Cleanup status for AIM resource: %s" % aim_res)
            status = self.mgr.get_status(self.ctx, aim_res)
            if status:
                self.mgr.delete(self.ctx, status)

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
