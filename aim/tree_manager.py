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

from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.api import status as aim_status
from aim.api import tree as tree_res
from aim.common.hashtree import exceptions as exc
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim.db import tree_model

from apicapi import apic_client

LOG = logging.getLogger(__name__)


ROOT_TREE = tree_res.Tree
CONFIG_TREE = tree_res.ConfigTree
OPERATIONAL_TREE = tree_res.OperationalTree
MONITORED_TREE = tree_res.MonitoredTree
SUPPORTED_TREES = [CONFIG_TREE, OPERATIONAL_TREE, MONITORED_TREE]


class TreeManager(object):

    def __init__(self, tree_klass, root_rn_funct=None,
                 root_key_funct=None):
        self.tree_klass = tree_klass
        self.root_rn_funct = root_rn_funct or self._default_root_rn_funct
        self.root_key_funct = root_key_funct or self._default_root_key_funct

    @utils.log
    def update_bulk(self, context, hash_trees, tree=CONFIG_TREE):
        trees = {self.root_rn_funct(x): x for x in hash_trees}
        with context.store.begin(subtransactions=True):
            db_objs = self._find_query(context, tree, lock_update=True,
                                       in_={'root_rn': list(trees.keys())})
            for obj in db_objs:
                hash_tree = trees.pop(obj.root_rn)
                obj.root_full_hash = hash_tree.root_full_hash
                obj.tree = str(hash_tree).encode('utf-8')
                context.store.add(obj)

            for hash_tree in trees.values():
                # Tree creation
                empty_tree = structured_tree.StructuredHashTree()
                # Create base tree
                root_rn = self.root_rn_funct(hash_tree)
                self._create_if_not_exist(context, ROOT_TREE, root_rn)
                for tree_klass in SUPPORTED_TREES:
                    if tree_klass == tree:
                        # Then put the updated tree in it
                        self._create_if_not_exist(
                            context, tree_klass, root_rn,
                            tree=str(hash_tree).encode('utf-8'),
                            root_full_hash=hash_tree.root_full_hash or 'none')
                    else:
                        # Attempt to create an empty tree:
                        self._create_if_not_exist(
                            context, tree_klass, root_rn,
                            tree=str(empty_tree).encode('utf-8'),
                            root_full_hash=empty_tree.root_full_hash or 'none')

    def get_base_tree(self, context, root_rn, lock_update=False):
        db_objs = self._find_query(context, ROOT_TREE, lock_update=lock_update,
                                   in_={'root_rn': [root_rn]})
        return db_objs[0] if db_objs else None

    @utils.log
    def delete_bulk(self, context, hash_trees):
        with context.store.begin(subtransactions=True):
            root_rns = [self.root_rn_funct(x) for x in hash_trees]
            for type in SUPPORTED_TREES + [ROOT_TREE]:
                db_objs = self._find_query(context, type, lock_update=True,
                                           in_={'root_rn': root_rns})
                for db_obj in db_objs:
                    context.store.delete(db_obj)

    @utils.log
    def delete_all(self, context):
        with context.store.begin(subtransactions=True):
            for type in SUPPORTED_TREES + [ROOT_TREE]:
                db_objs = self._find_query(context, type, lock_update=True)
                for db_obj in db_objs:
                    context.store.delete(db_obj)

    def update(self, context, hash_tree, tree=CONFIG_TREE):
        return self.update_bulk(context, [hash_tree], tree=tree)

    def delete(self, context, hash_tree):
        return self.delete_bulk(context, [hash_tree])

    @utils.log
    def delete_by_root_rn(self, context, root_rn, if_empty=False):
        try:
            with context.store.begin(subtransactions=True):
                self._delete_if_exist(context, ROOT_TREE, root_rn)
                for type in SUPPORTED_TREES:
                    self._delete_if_exist(context, type, root_rn,
                                          if_empty=if_empty)
        except exc.HashTreeNotEmpty:
            LOG.warning("Hashtree not empty for root %s, rolling "
                        "back deletion." % root_rn)

    @utils.log
    def clean_by_root_rn(self, context, root_rn):
        empty_tree = structured_tree.StructuredHashTree()
        with context.store.begin(subtransactions=True):
            for tree_type in SUPPORTED_TREES:
                obj = self._find_query(context, tree_type, root_rn=root_rn,
                                       lock_update=True)
                if obj:
                    obj[0].tree = str(empty_tree).encode('utf-8')
                    context.store.add(obj[0])
            obj = self._find_query(context, ROOT_TREE, root_rn=root_rn,
                                   lock_update=True)
            if obj:
                obj[0].needs_reset = False
                context.store.add(obj[0])

    @utils.log
    def clean_all(self, context):
        empty_tree = structured_tree.StructuredHashTree()
        with context.store.begin(subtransactions=True):
            for tree_type in SUPPORTED_TREES:
                db_objs = self._find_query(context, tree_type,
                                           lock_update=True)
                for db_obj in db_objs:
                    db_obj.tree = str(empty_tree).encode('utf-8')
                    context.store.add(db_obj)
            db_objs = self._find_query(context, ROOT_TREE, lock_update=True)
            for db_obj in db_objs:
                db_obj.needs_reset = False
                context.store.add(db_obj)

    @utils.log
    def find(self, context, tree=CONFIG_TREE, **kwargs):
        result = self._find_query(context, tree, in_=kwargs)
        return [self.tree_klass.from_string(
            str(x.tree.decode('utf-8')),
            self.root_key_funct(x.root_rn)) for x in result]

    @utils.log
    def get(self, context, root_rn, lock_update=False, tree=CONFIG_TREE):
        try:
            return self.tree_klass.from_string(str(
                self._find_query(context, tree, lock_update=lock_update,
                                 root_rn=root_rn)[0].tree.decode('utf-8')),
                self.root_key_funct(root_rn))
        except IndexError:
            raise exc.HashTreeNotFound(root_rn=root_rn)

    @utils.log
    def find_changed(self, context, root_map, tree=CONFIG_TREE):
        if not root_map:
            return {}
        return dict((
            x.root_rn,
            self.tree_klass.from_string(
                str(x.tree.decode('utf-8')), self.root_key_funct(x.root_rn)))
            for x in self._find_query(
                context, tree, in_={'root_rn': list(root_map.keys())},
                notin_={'root_full_hash': list(root_map.values())}))

    @utils.log
    def get_roots(self, context):
        return [x.root_rn for x in self._find_query(context, ROOT_TREE)]

    @utils.log
    def set_needs_reset_by_root_rn(self, context, root_rn, needs_reset=True):
        db_obj = self._find_query(context, ROOT_TREE, lock_update=True,
                                  root_rn=root_rn)
        if db_obj:
            db_obj[0].needs_reset = needs_reset
            context.store.add(db_obj[0])

    def retrieve_uninitialized_roots(self, context):
        # Only works with sql store
        if 'sql' in context.store.features:
            db_session = context.store.db_session
            sq = db_session.query(
                tree_model.Tree.root_rn).distinct().subquery()
            all = db_session.query(tree_model.ActionLog.root_rn).filter(
                tree_model.ActionLog.root_rn.notin_(sq)).distinct().all()
            return [x.root_rn for x in all]
        else:
            return []

    def _delete_if_exist(self, context, tree_type, root_rn, if_empty=False):
        with context.store.begin(subtransactions=True):
            obj = self._find_query(context, tree_type, root_rn=root_rn,
                                   lock_update=True)
            if obj:
                if if_empty:
                    tree = self.tree_klass.from_string(
                        str(obj[0].tree.decode('utf-8')),
                        self.root_key_funct(root_rn))
                    if tree.root:
                        # Raise a error to rollback any ongoing transaction
                        raise exc.HashTreeNotEmpty(root_rn=root_rn)
                context.store.delete(obj[0])

    def _create_if_not_exist(self, context, tree_type, root_rn, **kwargs):
        with context.store.begin(subtransactions=True):
            obj = self._find_query(context, tree_type, root_rn=root_rn)
            if not obj:
                resource = tree_type(root_rn=root_rn, **kwargs)
                db_obj = context.store.make_db_obj(resource)
                context.store.add(db_obj)

    def _find_query(self, context, tree_type, in_=None, notin_=None,
                    lock_update=False, **kwargs):
        db_type = context.store.resource_to_db_type(tree_type)
        return context.store.query(db_type, tree_type, in_=in_, notin_=notin_,
                                   lock_update=lock_update, **kwargs)

    def _default_root_rn_funct(self, tree):
        return tree.root_key[0]

    def _default_root_key_funct(self, rn):
        return rn,


class AimHashTreeMaker(object):
    """Hash Tree Maker

    Utility class that updates a given Hash Tree with AIM resources following
    a specific convention. This can be used to maintain consistent
    representation across different parts of the system

    In our current convention, each node of a given AIM resource is added to
    the tree with a key represented as follows:

    list('apicType|res-name', 'apicChildType|res-name')
    """

    def __init__(self):
        pass

    @staticmethod
    def _extract_dn(res):
        try:
            if not isinstance(res, aim_status.AciStatus):
                return res.dn
        except Exception as e:
            LOG.warning("Failed to extract DN for resource %s: %s",
                        res, e)

    @staticmethod
    def _build_hash_tree_key(resource):
        dn = AimHashTreeMaker._extract_dn(resource)
        return AimHashTreeMaker._build_hash_tree_key_from_dn(
            dn, getattr(resource, '_aci_mo_name', None))

    @staticmethod
    def _build_hash_tree_key_from_dn(dn, mo_name):
        if dn:
            try:
                return AimHashTreeMaker._dn_to_key(mo_name, dn)
            except Exception as e:
                LOG.warning("Failed to get Key from dn %s: %s", dn, e)

    @staticmethod
    def _dn_to_key(mo_type, dn):
        type_and_dn = utils.decompose_dn(mo_type, dn)
        return tuple([str('|'.join(x))
                      for x in type_and_dn]) if type_and_dn else None

    @staticmethod
    def _extract_root_rn(root_key):
        root_split = root_key[0].split('|')
        return apic_client.DNManager().build([root_split]).split('/')[-1]

    @staticmethod
    def _extract_root_from_dn(dn):
        return dn.split('/')[-1]

    def _clean_related(self, tree, node):
        for child in (node.get_children() if node else []):
            if child.metadata.get('related'):
                tree.clear(child.key)
                self._clean_related(tree, child)

    def _prepare_aim_resource(self, tree, aim_res):
        result = {}
        aim_res_dn = AimHashTreeMaker._extract_dn(aim_res)
        if not aim_res_dn:
            return result

        # Remove "related" child-nodes
        aim_res_key = AimHashTreeMaker._build_hash_tree_key(aim_res)
        node = tree.find(aim_res_key) if aim_res_key else None
        self._clean_related(tree, node)
        return self.aim_res_to_nodes(aim_res)

    @staticmethod
    def aim_res_to_nodes(aim_res):
        result = {}
        aim_res_dn = AimHashTreeMaker._extract_dn(aim_res)
        is_error = getattr(aim_res, '_error', False)
        is_monitored = (getattr(aim_res, 'monitored', False) or
                        getattr(aim_res, 'pre_existing', False))
        pending = getattr(aim_res, '_pending', None)
        to_aci = converter.AimToAciModelConverter()
        for obj in to_aci.convert([aim_res]):
            for mo, v in obj.items():
                attr = v.get('attributes', {})
                dn = attr.pop('dn', None)
                key = AimHashTreeMaker._build_hash_tree_key_from_dn(dn, mo)
                if key:
                    attr['_metadata'] = {'monitored': is_monitored,
                                         'attributes': copy.copy(attr)}
                    if dn != aim_res_dn:
                        attr['_metadata']['related'] = True
                    if pending is not None:
                        attr['_metadata']['pending'] = pending
                    attr['_error'] = is_error
                    result[key] = attr
        return result

    def update(self, tree, updates):
        """Add/update AIM resource to tree.

        :param tree: ComparableCollection instance
        :param updates: list of resources *of a single root* that should be
                        added/updated
        :return: The updated tree (value is also changed)
        """
        to_update = {}
        for aim_res in updates:
            to_update.update(self._prepare_aim_resource(tree, aim_res))
        for k, v in to_update.items():
            tree.add(k, **v)
        return tree

    def delete(self, tree, deletes):
        """Delete AIM resources from tree.

        :param tree: ComparableCollection instance
        :param deletes: list of resources *of a single root* that should be
                        deleted
        :return: The updated tree (value is also changed)
        """
        for resource in deletes:
            key = self._build_hash_tree_key(resource)
            if key:
                tree.clear(key)
                node = tree.find(key)
                self._clean_related(tree, node)
        return tree

    def clear(self, tree, resources):
        """Set AIM resources to dummy in tree

        :param tree:
        :param items:
        :return:
        """
        to_aci = converter.AimToAciModelConverter()
        for obj in to_aci.convert(resources):
            for mo, v in obj.items():
                attr = v.get('attributes', {})
                dn = attr.pop('dn', None)
                key = AimHashTreeMaker._build_hash_tree_key_from_dn(dn, mo)
                if key:
                    tree.clear(key)
        return tree

    def get_root_key(self, resource):
        try:
            return resource.root
        except (AttributeError, KeyError):
            return None

    @staticmethod
    def root_rn_funct(tree):
        """RN funct for Tree Maker

        Utility function for TreeManager initialization
        :param tree:
        :return:
        """
        return AimHashTreeMaker._extract_root_rn(tree.root_key)

    @staticmethod
    def root_key_funct(key):
        """Key funct for Tree Maker

        Utility function for TreeManager initialization
        :param tree:
        :return:
        """
        splits = key.split('-', 1)
        mo = apic_client.ManagedObjectClass.prefix_to_mos[splits[0]]
        dn = apic_client.DNManager().build([[mo, splits[-1]]])
        return AimHashTreeMaker._build_hash_tree_key_from_dn(dn, mo)


class HashTreeManager(TreeManager):
    def __init__(self):
        super(HashTreeManager, self).__init__(
            structured_tree.StructuredHashTree,
            AimHashTreeMaker.root_rn_funct,
            AimHashTreeMaker.root_key_funct)


class HashTreeBuilder(object):
    CONFIG = 'config'
    OPER = 'oper'
    MONITOR = 'monitor'

    def __init__(self, aim_manager):
        self.aim_manager = aim_manager
        self.tt_maker = AimHashTreeMaker()

    def build(self, added, updated, deleted, tree_map, aim_ctx=None):
        """Build hash tree

        :param updated: list of AIM objects
        :param deleted: list of AIM objects
        :param tree_map: map of trees by type and root
        eg: {'config': {'tn1': <root hashtree>}}
        :return: tree updates
        """
        LOG.debug('Builder called with %s %s %s' % (added, updated, deleted))
        # Segregate updates by root
        updates_by_root = {}
        all_updates = [added, updated, deleted]
        conf = CONFIG_TREE
        monitor = MONITORED_TREE
        oper = OPERATIONAL_TREE
        for idx in range(len(all_updates)):
            # tree_index == 0 -> ADD
            # tree_inder == 1 -> DELETE
            tree_index = 0 if idx < 2 else 1
            for res in all_updates[idx]:
                if isinstance(res, aim_status.AciStatus) and aim_ctx:
                    parent = self.aim_manager.get_by_id(
                        aim_ctx, res.parent_class, res.resource_id)
                    # Remove main object from config tree if in sync error
                    # during an update
                    if parent and parent.root == res.resource_root:
                        if getattr(parent, 'sync', True):
                            if tree_index == 0:
                                if res.sync_status == res.SYNC_FAILED:
                                    # Put the object in error state
                                    parent._error = True
                                    parent._pending = False
                                elif res.sync_status == res.SYNC_PENDING:
                                    parent._pending = True
                                elif res.sync_status == res.SYNCED:
                                    parent._pending = False
                                all_updates[1].append(parent)
                            else:
                                # Delete parent on operational tree
                                parent_key = self.tt_maker.get_root_key(parent)
                                updates_by_root.setdefault(
                                    parent_key, {conf: ([], []),
                                                 monitor: ([], []),
                                                 oper: ([], [])})
                                updates_by_root[
                                    parent_key][oper][tree_index].append(
                                    parent)
                    elif tree_index == 0:
                        # Parent doesn't exist for some reason, delete the
                        # status object
                        try:
                            LOG.info("Deleting parentless status object "
                                     "%s" % res)
                            self.aim_manager.delete(aim_ctx, res)
                        except Exception as e:
                            LOG.warning("An exception has occurred while "
                                        "trying to delete status object "
                                        "%s: %s" % (res, str(e)))
                        continue
                key = self.tt_maker.get_root_key(res)
                if not key:
                    continue
                updates_by_root.setdefault(
                    key, {conf: ([], []), monitor: ([], []), oper: ([], [])})
                if isinstance(res, aim_status.AciFault):
                    # Operational Tree
                    updates_by_root[key][oper][tree_index].append(res)
                else:
                    if getattr(res, 'monitored', None):
                        # Monitored Tree
                        res_copy = copy.deepcopy(res)
                        updates_by_root[key][monitor][tree_index].append(
                            res_copy)
                        # Don't modify the original resource in a visible
                        # way
                        res = copy.deepcopy(res)
                        # Fake this as pre-existing
                        res.pre_existing = True
                        res.monitored = False
                    # Configuration Tree
                    updates_by_root[key][conf][tree_index].append(res)

        upd_trees, udp_op_trees, udp_mon_trees = [], [], []
        for root, upd in updates_by_root.items():
            try:
                ttree = tree_map[self.CONFIG][root]
                ttree_operational = tree_map[self.OPER][root]
                ttree_monitor = tree_map[self.MONITOR][root]
            except KeyError:
                # Some objects do not belong to the specified roots
                continue
            # Update Configuration Tree
            self.tt_maker.update(ttree, upd[conf][0])
            self.tt_maker.delete(ttree, upd[conf][1])
            # Clear new monitored objects
            self.tt_maker.clear(ttree, upd[monitor][0])

            # Update Operational Tree
            self.tt_maker.update(ttree_operational, upd[oper][0])
            self.tt_maker.delete(ttree_operational, upd[oper][1])
            # Delete operational resources as well
            self.tt_maker.delete(ttree_operational, upd[conf][1])
            self.tt_maker.delete(ttree_operational, upd[monitor][1])

            # Update Monitored Tree
            self.tt_maker.update(ttree_monitor, upd[monitor][0])
            self.tt_maker.delete(ttree_monitor, upd[monitor][1])
            # Clear new owned objects
            self.tt_maker.clear(ttree_monitor, upd[conf][0])

            if ttree.root_key:
                upd_trees.append(ttree)
            if ttree_operational.root_key:
                udp_op_trees.append(ttree_operational)
            if ttree_monitor.root_key:
                udp_mon_trees.append(ttree_monitor)
        return upd_trees, udp_op_trees, udp_mon_trees
