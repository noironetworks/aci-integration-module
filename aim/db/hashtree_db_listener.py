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

import copy
import traceback

from oslo_log import log as logging
from oslo_utils import importutils

from aim.api import resource
from aim.api import status as api_status
from aim.api import tree as aim_tree
from aim.common.hashtree import exceptions as hexc
from aim.common.hashtree import structured_tree as htree
from aim.common import utils
from aim import config as aim_cfg
from aim import tree_manager

MAX_EVENTS_PER_ROOT = 10000
LOG = logging.getLogger(__name__)
# Not really rootless, they just miss the root reference attributes
ROOTLESS_TYPES = ['fabricTopology']


class HashTreeDbListener(object):
    """Updates persistent hash-tree in response to DB updates."""

    def __init__(self, aim_manager):
        self.aim_manager = aim_manager
        self.tt_mgr = tree_manager.HashTreeManager()
        self.tt_maker = tree_manager.AimHashTreeMaker()
        self.tt_builder = tree_manager.HashTreeBuilder(self.aim_manager)

    def on_commit(self, store, added, updated, deleted):
        # Query hash-tree for each tenant and modify the tree based on DB
        # updates
        # TODO(ivar): Use proper store context once dependency issue is fixed
        ctx = utils.FakeContext(store=store)
        resetting_roots = set()
        with ctx.store.begin(subtransactions=True):
            for i, resources in enumerate((added + updated, deleted)):
                for res in resources:
                    try:
                        root = res.root
                    except AttributeError:
                        continue
                    if i == 0 and getattr(res, 'sync', True):
                        action = aim_tree.ActionLog.CREATE
                    else:
                        action = aim_tree.ActionLog.DELETE
                    # TODO(ivar): root should never be None for any object!
                    # We have some conversions broken
                    if self._get_reset_count(ctx, root) > 0:
                        resetting_roots.add(root)
                    if not root or root in resetting_roots:
                        continue
                    if self._get_log_count(ctx, root) >= MAX_EVENTS_PER_ROOT:
                        LOG.warn('Max events per root %s reached, '
                                 'requesting a reset' % root)
                        action = aim_tree.ActionLog.RESET
                    log = aim_tree.ActionLog(
                        root_rn=root, action=action,
                        object_dict=utils.json_dumps(res.__dict__),
                        object_type=type(res).__name__)
                    self.aim_manager.create(ctx, log)

    def _get_log_count(self, ctx, root):
        return self.aim_manager.count(ctx, aim_tree.ActionLog, root_rn=root)

    def _get_reset_count(self, ctx, root):
        return self.aim_manager.count(ctx, aim_tree.ActionLog, root_rn=root,
                                      action=aim_tree.ActionLog.RESET)

    def _delete_trees(self, aim_ctx, root=None):
        with aim_ctx.store.begin(subtransactions=True):
            # Delete existing trees
            if root:
                self.tt_mgr.clean_by_root_rn(aim_ctx, root)
            else:
                self.tt_mgr.clean_all(aim_ctx)

    def _recreate_trees(self, aim_ctx, root=None):
        with aim_ctx.store.begin(subtransactions=True):
            cache = {}
            log_by_root = {}
            # Delete existing trees
            if root:
                type, name = self.tt_mgr.root_key_funct(root)[0].split('|')
            # Retrieve objects
            for klass in self.aim_manager.aim_resources:
                if issubclass(klass, resource.AciResourceBase):
                    filters = {}
                    if root:
                        if self._retrieve_class_root_type(
                                klass, cache=cache) != type:
                            # Not the right subtree
                            continue
                        if type not in ROOTLESS_TYPES:
                            filters[klass.root_ref_attribute()] = name
                    # Get all objects of that type
                    for obj in self.aim_manager.find(aim_ctx, klass,
                                                     **filters):
                        # Need all the faults and statuses as well
                        stat = self.aim_manager.get_status(
                            aim_ctx, obj, create_if_absent=False)
                        if getattr(obj, 'sync', True):
                            if stat:
                                log_by_root.setdefault(obj.root, []).append(
                                    (aim_tree.ActionLog.CREATE, stat, None))
                                for f in stat.faults:
                                    log_by_root.setdefault(
                                        obj.root, []).append(
                                        (aim_tree.ActionLog.CREATE, f, None))
                                del stat.faults
                            log_by_root.setdefault(obj.root, []).append(
                                (aim_tree.ActionLog.CREATE, obj, None))
            # Reset the trees
            self._push_changes_to_trees(aim_ctx, log_by_root,
                                        delete_logs=False, check_reset=False)

    def cleanup_zombie_status_objects(self, aim_ctx, roots=None):
        with aim_ctx.store.begin(subtransactions=True):
            # Retrieve objects
            klass = api_status.AciStatus
            filters = {}
            if roots is not None:
                filters['in_'] = {'resource_root': roots}
            to_delete = []
            for stat in self.aim_manager.find(aim_ctx, klass, **filters):
                parent = self.aim_manager.get_by_id(
                    aim_ctx, stat.parent_class, stat.resource_id)
                if not parent or parent.root != stat.resource_root:
                    to_delete.append(stat.id)
            if to_delete:
                LOG.info("Deleting parentless status objects "
                         "%s" % to_delete)
                self.aim_manager.delete_all(
                    aim_ctx, klass, in_={'id': to_delete})

    def reset(self, store, root=None):
        aim_ctx = utils.FakeContext(store=store)
        with aim_ctx.store.begin(subtransactions=True):
            self.cleanup_zombie_status_objects(aim_ctx, roots=[root])
            self._delete_trees(aim_ctx, root=root)
            self._recreate_trees(aim_ctx, root=root)

    def _retrieve_class_root_type(self, klass, cache=None):
        cache = cache if cache is not None else {}
        if klass in cache:
            return cache[klass]
        stack = [klass]
        while klass._tree_parent:
            klass = klass._tree_parent
            stack.append(klass)
        for k in stack:
            cache[k] = klass._aci_mo_name
        return cache[klass]

    def catch_up_with_action_log(self, store, served_tenants=None):
        ctx = utils.FakeContext(store=store)
        with ctx.store.begin(subtransactions=True):
            served_tenants = served_tenants or set()
            to_init = set(self.tt_mgr.retrieve_uninitialized_roots(ctx))
            served_tenants |= to_init
            # Nothing will happen if there's no action log
            kwargs = {'order_by': ['root_rn', 'id']}
            if served_tenants:
                kwargs['in_'] = {'root_rn': served_tenants}
            logs = self.aim_manager.find(ctx, aim_tree.ActionLog, **kwargs)
            LOG.debug('Processing action logs: %s' % logs)
            log_by_root, resetting_roots = self._preprocess_logs(ctx, logs)
            self._cleanup_resetting_roots(ctx, log_by_root, resetting_roots)
            self._push_changes_to_trees(ctx, log_by_root)
            # REVISIT: This is temporary code for verifying solutions
            # to concurrency issues. Remove when no longer needed.
            if aim_cfg.CONF.aim.validate_config_trees:
                self._validate_config_trees(ctx, log_by_root.keys())

    def _preprocess_logs(self, ctx, logs):
        resetting_roots = set()
        log_by_root = {}
        resource_paths = ('resource', 'service_graph', 'infra', 'tree',
                          'status')
        for log in logs:
            if log.action == aim_tree.ActionLog.RESET:
                resetting_roots.add(log.root_rn)
            action = log.action
            aim_res = None
            for path in resource_paths:
                try:
                    klass = importutils.import_class(
                        'aim.api.' + path + '.%s' % log.object_type)
                    aim_res = klass(**utils.json_loads(log.object_dict))
                except ImportError:
                    pass
            if not aim_res:
                LOG.warn('Aim resource for event %s not found' % log)
                continue
            # REVISIT: We currently only query the DB for
            # SecurityGroupRule resources, but should treat all
            # resource types uniformly, and therefore should do this
            # for all resource types. This will also allow elimination
            # of the epoch bumping when modifying list attributes of
            # other resource types. But we probably will want to
            # optimize this quering to avoid a roundtrip to the DB
            # server for each action log item, by making one find()
            # call for each resource type, filtering with the
            # identities from all the action log items being
            # processed.
            if isinstance(aim_res, resource.SecurityGroupRule):
                if aim_cfg.CONF.aim.fetch_sgr_from_db:
                    db_aim_res = self.aim_manager.get(ctx, aim_res)
                    if db_aim_res:
                        if action == aim_tree.ActionLog.DELETE:
                            LOG.warn("AIM resource %s exists in DB for delete "
                                     "action" % db_aim_res)
                        else:
                            # Use current resource from DB so that list
                            # attributes do no need to be protected from
                            # concurrent updates by bumping the resource's
                            # epoch.
                            aim_res = db_aim_res
                    else:
                        if action != aim_tree.ActionLog.DELETE:
                            LOG.warn("AIM resource %s does not exist in DB "
                                     "for create/update action" % aim_res)
            log_by_root.setdefault(log.root_rn, []).append(
                (action, aim_res, log))
        return log_by_root, resetting_roots

    def _cleanup_resetting_roots(self, ctx, log_by_root, resetting_roots):
        for root in resetting_roots:
            with ctx.store.begin(subtransactions=True):
                self._delete_logs(ctx, log_by_root[root])
                self.tt_mgr.set_needs_reset_by_root_rn(ctx, root)
                log_by_root[root] = []

    def _delete_logs(self, ctx, logs):
        self.aim_manager.delete_all(ctx, aim_tree.ActionLog,
                                    in_={'uuid': [x[2].uuid for x in logs]})

    def _push_changes_to_trees(self, ctx, log_by_root, delete_logs=True,
                               check_reset=True):
        conf = tree_manager.CONFIG_TREE
        monitor = tree_manager.MONITORED_TREE
        oper = tree_manager.OPERATIONAL_TREE
        for root_rn in log_by_root:
            try:
                tree_map = {}
                with ctx.store.begin(subtransactions=True):
                    try:
                        ttree = self.tt_mgr.get_base_tree(ctx, root_rn,
                                                          lock_update=True)
                        if check_reset and ttree and ttree.needs_reset:
                            LOG.warn('RESET action received for root %s, '
                                     'resetting trees' % root_rn)
                            self.reset(ctx.store, root_rn)
                            continue
                        ttree_conf = self.tt_mgr.get(
                            ctx, root_rn, lock_update=True, tree=conf)
                        ttree_operational = self.tt_mgr.get(
                            ctx, root_rn, lock_update=True, tree=oper)
                        ttree_monitor = self.tt_mgr.get(
                            ctx, root_rn, lock_update=True, tree=monitor)
                    except hexc.HashTreeNotFound:
                        ttree_conf = htree.StructuredHashTree()
                        ttree_operational = htree.StructuredHashTree()
                        ttree_monitor = htree.StructuredHashTree()
                    tree_map.setdefault(
                        self.tt_builder.CONFIG, {})[root_rn] = ttree_conf
                    tree_map.setdefault(
                        self.tt_builder.OPER, {})[root_rn] = ttree_operational
                    tree_map.setdefault(
                        self.tt_builder.MONITOR, {})[root_rn] = ttree_monitor
                    for action, aim_res, _ in log_by_root[root_rn]:
                        added = deleted = []
                        if action == aim_tree.ActionLog.CREATE:
                            added = [aim_res]
                        else:
                            deleted = [aim_res]
                        self.tt_builder.build(added, [], deleted, tree_map,
                                              aim_ctx=ctx)
                    if ttree_conf.root_key:
                        self.tt_mgr.update(ctx, ttree_conf)
                    if ttree_operational.root_key:
                        self.tt_mgr.update(ctx, ttree_operational, tree=oper)
                    if ttree_monitor.root_key:
                        self.tt_mgr.update(ctx, ttree_monitor, tree=monitor)
                    if delete_logs:
                        self._delete_logs(ctx, log_by_root[root_rn])
            except Exception as e:
                LOG.error('Failed to update root %s '
                          'tree for: %s' % (root_rn, str(e)))
                LOG.debug(traceback.format_exc())

    def _validate_config_trees(self, ctx, roots):
        LOG.info("validating config trees for roots: %s" % roots)
        for root in roots:
            LOG.info("validating config tree for root: %s" % root)
            with ctx.store.begin(subtransactions=True):
                before = copy.deepcopy(
                    self.tt_mgr.get(
                        ctx, root, tree=tree_manager.CONFIG_TREE))
                self.cleanup_zombie_status_objects(ctx, roots=[root])
                self._delete_trees(ctx, root=root)
                self._recreate_trees(ctx, root=root)
                after = self.tt_mgr.get(
                    ctx, root, tree=tree_manager.CONFIG_TREE)
                if before.root_full_hash != after.root_full_hash:
                    LOG.warning("invalid config tree for root: %s" % root)
                    LOG.warning(" before recreating: %s" % before)
                    LOG.warning(" after recreating: %s" % after)
