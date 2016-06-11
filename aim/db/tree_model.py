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

from aim.agent.aid.universes.aci import converter
from aim.api import resource as api_res
from aim.api import status as aim_status
from aim.common.hashtree import exceptions as exc
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim.db import model_base

from apicapi import apic_client

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
    root_full_hash = sa.Column(sa.String(256), nullable=True)
    operational_root_full_hash = sa.Column(sa.String(256), nullable=True)
    tree = sa.Column(sa.LargeBinary, nullable=True)
    operational_tree = sa.Column(sa.LargeBinary, nullable=True)
    agents = orm.relationship(AgentToHashTreeAssociation,
                              backref='hash_trees',
                              cascade='all, delete-orphan',
                              lazy="joined")


class TenantTreeManager(object):

    trees = {False: 'tree', True: 'operational_tree'}
    hashes = {False: 'root_full_hash', True: 'operational_root_full_hash'}

    def __init__(self, tree_klass, tenant_rn_funct=None,
                 tenant_key_funct=None):
        self.tree_klass = tree_klass
        self.tenant_rn_funct = (tenant_rn_funct or
                                self._default_tenant_rn_funct)
        self.tenant_key_funct = (tenant_key_funct or
                                 self._default_tenant_key_funct)

    @utils.log
    def update_bulk(self, context, hash_trees, operational=False):
        trees = {self.tenant_rn_funct(x): x for x in hash_trees}
        with context.db_session.begin(subtransactions=True):
            db_objs = self._find_query(context,
                                       in_={'tenant_rn': trees.keys()}).all()
            for obj in db_objs:
                hash_tree = trees.pop(obj.tenant_rn)
                setattr(obj, self.hashes[operational],
                        hash_tree.root_full_hash)
                setattr(obj, self.trees[operational], str(hash_tree))
                context.db_session.add(obj)

            for hash_tree in trees.values():
                # Tree creation
                empty_tree = structured_tree.StructuredHashTree()
                key_args = {
                    self.trees[operational]: str(hash_tree),
                    self.hashes[operational]: (hash_tree.root_full_hash or
                                               'none'),
                    self.trees[not operational]: str(empty_tree),
                    self.hashes[not operational]: (empty_tree.root_full_hash or
                                                   'none'),
                    'tenant_rn': self.tenant_rn_funct(hash_tree)}
                obj = TenantTree(**key_args)
                context.db_session.add(obj)

    @utils.log
    def delete_bulk(self, context, hash_trees):
        with context.db_session.begin(subtransactions=True):
            db_objs = self._find_query(
                context, in_={'tenant_rn': [self.tenant_rn_funct(x)
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
    def delete_by_tenant_rn(self, context, tenant_rn):
        with context.db_session.begin(subtransactions=True):
            db_objs = self._find_query(
                context, in_={'tenant_rn': [tenant_rn]}).all()
            for db_obj in db_objs:
                context.db_session.delete(db_obj)

    @utils.log
    def find(self, context, operational=False, **kwargs):
        result = self._find_query(context, in_=kwargs).all()
        return [self.tree_klass.from_string(
            str(getattr(x, self.trees[operational])),
            self.tenant_key_funct(x.tenant_rn)) for x in result]

    @utils.log
    def get(self, context, tenant_rn, operational=False):
        try:
            return self.tree_klass.from_string(str(
                getattr(self._find_query(context, tenant_rn=tenant_rn).one(),
                        self.trees[operational])),
                self.tenant_key_funct(tenant_rn))
        except sql_exc.NoResultFound:
            raise exc.HashTreeNotFound(tenant_rn=tenant_rn)

    @utils.log
    def find_changed(self, context, tenant_map, operational=False):
        if not tenant_map:
            return {}
        full_hash = {False: 'root_full_hash',
                     True: 'operational_root_full_hash'}
        return dict((x.tenant_rn,
                     self.tree_klass.from_string(
                         str(getattr(x, self.trees[operational])),
                         self.tenant_key_funct(x.tenant_rn)))
                    for x in self._find_query(
                        context, in_={'tenant_rn': tenant_map.keys()},
                        notin_={full_hash[operational]:
                                tenant_map.values()}).all())

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

    def _default_tenant_rn_funct(self, tree):
        return tree.root_key[0]

    def _default_tenant_key_funct(self, rn):
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

    # Change this to be by object type if ever needed
    _exclude = ['display_name']

    def __init__(self):
        pass

    @staticmethod
    def _build_hash_tree_key(resource):
        def _key_by_dn(dn=None):
            try:
                return AimHashTreeMaker._dn_to_key(resource._aci_mo_name,
                                                   dn or resource.dn)
            except Exception as e:
                LOG.warning("Failed to get DN for resource %s: %s",
                            resource, e)

        if isinstance(resource, aim_status.AciFault):
            return _key_by_dn(resource.external_identifier)
        elif isinstance(resource, api_res.AciResourceBase):
            return _key_by_dn()
        else:
            return None

    @staticmethod
    def _dn_to_key(mo_type, dn):
        try:
            type_and_dn = apic_client.DNManager().aci_decompose_with_type(
                dn, mo_type)
            return tuple(['|'.join(x) for x in type_and_dn])
        except (apic_client.DNManager.InvalidNameFormat,
                apic_client.cexc.ApicManagedObjectNotSupported):
            LOG.warning("Failed to transform DN %s to key for hash-tree", dn)
            return

    @staticmethod
    def _extract_tenant_name(root_key):
        return root_key[0][root_key[0].find('|') + 1:]

    def update(self, tree, updates):
        """Add/update AIM resource to tree.

        :param tree: ComparableCollection instance
        :param updates: list of resources *of a single tenant* that should be
                        added/updated
        :return: The updated tree (value is also changed)
        """
        aci_objects = converter.AimToAciModelConverter().convert(updates)
        for obj in aci_objects:
            for mo, v in obj.iteritems():
                attr = v.get('attributes', {})
                dn = attr.pop('dn', None)
                key = AimHashTreeMaker._dn_to_key(mo, dn) if dn else None
                if key:
                    tree.add(key, **attr)
        return tree

    def delete(self, tree, deletes):
        """Delete AIM resources from tree.

        :param tree: ComparableCollection instance
        :param deletes: list of resources *of a single tenant* that should be
                        deleted
        :return: The updated tree (value is also changed)
        """
        for resource in deletes:
            key = self._build_hash_tree_key(resource)
            if key:
                tree.pop(key)
        return tree

    def get_tenant_key(self, resource):
        key = self._build_hash_tree_key(resource)
        return self._extract_tenant_name(key) if key else None

    @staticmethod
    def tenant_rn_funct(tree):
        """RN funct for Tree Maker

        Utility function for TreeManager initialization
        :param tree:
        :return:
        """
        return AimHashTreeMaker._extract_tenant_name(tree.root_key)

    @staticmethod
    def tenant_key_funct(key):
        """Key funct for Tree Maker

        Utility function for TreeManager initialization
        :param tree:
        :return:
        """
        return AimHashTreeMaker._build_hash_tree_key(api_res.Tenant(name=key))


class TenantHashTreeManager(TenantTreeManager):
    def __init__(self):
        super(TenantHashTreeManager, self).__init__(
            structured_tree.StructuredHashTree,
            AimHashTreeMaker.tenant_rn_funct,
            AimHashTreeMaker.tenant_key_funct)
