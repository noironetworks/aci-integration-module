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

from oslo_log import log as logging
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import exc as sql_exc

from aim.api import resource as api_res
from aim.common.hashtree import exceptions as exc
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim.db import model_base


LOG = logging.getLogger(__name__)


class AgentToHashTreeAssociation(model_base.Base):
    """Many to many relation between Agents and the trees they serve."""
    __tablename__ = 'aim_agent_to_tree_associations'
    agent_id = sa.Column(
        sa.String(36), sa.ForeignKey('aim_agents.id', ondelete='CASCADE'),
        primary_key=True,)
    tree_tenant_rn = sa.Column(
        sa.String(64), sa.ForeignKey('aim_tenant_trees.tenant_rn',
                                     ondelete='CASCADE'),
        primary_key=True)


class TenantTree(model_base.Base):
    """DB model for TenantTree."""

    __tablename__ = 'aim_tenant_trees'

    tenant_rn = sa.Column(sa.String(64), primary_key=True)
    root_full_hash = sa.Column(sa.String(256), nullable=False)
    tree = sa.Column(sa.LargeBinary, nullable=False)
    agents = orm.relationship(AgentToHashTreeAssociation,
                              backref='hash_trees',
                              cascade='all, delete-orphan',
                              lazy="joined")


class TenantTreeManager(object):

    def __init__(self, tree_klass):
        self.tree_klass = tree_klass

    @utils.log
    def update_bulk(self, context, hash_trees):
        # TODO(ivar): When AIM tenant creation is defined, tenant_rn might not
        # correspond to x.root.key[0] anymore.
        trees = {x.root.key[0]: x for x in hash_trees}
        with context.db_session.begin(subtransactions=True):
            db_objs = self._find_query(context,
                                       in_={'tenant_rn': trees.keys()}).all()
            for obj in db_objs:
                hash_tree = trees.pop(obj.tenant_rn)
                obj.root_full_hash = hash_tree.root.full_hash
                obj.tree = str(hash_tree)
                context.db_session.add(obj)

            for hash_tree in trees.values():
                obj = TenantTree(tenant_rn=hash_tree.root.key[0],
                                 root_full_hash=hash_tree.root.full_hash,
                                 tree=str(hash_tree))
                context.db_session.add(obj)

    @utils.log
    def delete_bulk(self, context, hash_trees):
        with context.db_session.begin(subtransactions=True):
            db_objs = self._find_query(
                context, in_={'tenant_rn': [x.root.key[0]
                                            for x in hash_trees]}).all()
            for db_obj in db_objs:
                context.db_session.delete(db_obj)

    @utils.log
    def update(self, context, hash_tree):
        return self.update_bulk(context, [hash_tree])

    @utils.log
    def delete(self, context, hash_tree):
        return self.delete_bulk(context, [hash_tree])

    @utils.log
    def find(self, context, **kwargs):
        result = self._find_query(context, in_=kwargs).all()
        return [self.tree_klass.from_string(str(x.tree)) for x in result]

    @utils.log
    def get(self, context, tenant_rn):
        try:
            return self.tree_klass.from_string(str(
                self._find_query(context, tenant_rn=tenant_rn).one().tree))
        except sql_exc.NoResultFound:
            raise exc.HashTreeNotFound(tenant_rn=tenant_rn)

    @utils.log
    def find_changed(self, context, tenant_map):
        return dict((x.tenant_rn, self.tree_klass.from_string(str(x.tree)))
                    for x in self._find_query(
                        context, in_={'tenant_rn': tenant_map.keys()},
                        notin_={'root_full_hash': tenant_map.values()}).all())

    @utils.log
    def get_tenants(self, context):
        return [x[0] for x in
                context.db_session.query(TenantTree.tenant_rn).all()]

    def _find_query(self, context, in_=None, notin_=None, **kwargs):
        query = context.db_session.query(TenantTree)
        for k, v in (in_ or {}).iteritems():
            query = query.filter(getattr(TenantTree, k).in_(v))
        for k, v in (notin_ or {}).iteritems() or {}:
            query = query.filter(getattr(TenantTree, k).notin_(
                [(x or '') for x in v]))
        if kwargs:
            query = query.filter_by(**kwargs)
        return query


class TenantHashTreeManager(TenantTreeManager):
    def __init__(self):
        super(TenantHashTreeManager, self).__init__(
            structured_tree.StructuredHashTree)


class AimHashTreeMaker(object):
    """Hash Tree Maker

    Utility class that updates a given Hash Tree with AIM resources following
    a specific convention. This can be used to maintain consistent
    representation across different parts of the system

    In our current convention, each node of a given AIM resource is added to
    the tree with a key represented as follows:

    list('path.to.parent.Class|res-name', 'path.to.child.Class|res-name')
    """

    def __init__(self):
        pass

    def _build_hash_tree_key(self, resource):
        if not isinstance(resource, api_res.AciResourceBase):
            return None

        cls_list = []
        klass = type(resource)
        while klass and hasattr(klass, '_tree_parent'):
            cls_list.append(klass)
            klass = klass._tree_parent
        cls_list.reverse()

        if cls_list[0] != api_res.Tenant:
            return None

        id_values = resource.identity
        if len(id_values) != len(cls_list):
            LOG.warning("Mismatch between number of identity values (%d) and "
                        "parent classes (%d) for %s",
                        len(id_values), len(cls_list), resource)
            return None

        cls_list = ['%s.%s' % (c.__module__, c.__name__) for c in cls_list]
        key = tuple(['|'.join(x) for x in zip(cls_list, id_values)])
        return key

    def update_tree(self, tree, update):
        """Update tree with AIM resources.

        :param tree: ComparableCollection instance
        :param update: dictionary containing resources *of a single tenant*
        represented as follows:
        {"create": [list-of-resources], "delete": [list-of-resources]}
        :return: The updated tree (value is also changed)
        """
        for resource in update.get('delete', []):
            key = self._build_hash_tree_key(resource)
            tree.pop(key)

        for resource in update.get('create', []):
            key = self._build_hash_tree_key(resource)
            tree.add(key, **{x: getattr(resource, x, None)
                             for x in resource.other_attributes})
        return tree

    def get_tenant_key(self, resource):
        key = self._build_hash_tree_key(resource)
        return key[0] if key else None


# TODO(amitbose) Do we need this global?
TREE_MANAGER = TenantHashTreeManager()
