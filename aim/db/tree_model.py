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
    agents = orm.relationship(AgentToHashTreeAssociation,
                              backref='hash_trees',
                              cascade='all, delete-orphan',
                              lazy="joined")


class TypeTreeBase(object):
    # TODO(ivar): Make tenant_rn a FK with cascade delete.
    #
    tenant_rn = sa.Column(sa.String(64), primary_key=True)
    root_full_hash = sa.Column(sa.String(256), nullable=True)
    tree = sa.Column(sa.LargeBinary, nullable=True)


class ConfigTenantTree(model_base.Base, TypeTreeBase):
    __tablename__ = 'aim_config_tenant_trees'


class OperationalTenantTree(model_base.Base, TypeTreeBase):
    __tablename__ = 'aim_operational_tenant_trees'


CONFIG_TREE = ConfigTenantTree
OPERATIONAL_TREE = OperationalTenantTree
SUPPORTED_TREES = [CONFIG_TREE, OPERATIONAL_TREE]


class TenantTreeManager(object):

    def __init__(self, tree_klass, tenant_rn_funct=None,
                 tenant_key_funct=None):
        self.tree_klass = tree_klass
        self.tenant_rn_funct = (tenant_rn_funct or
                                self._default_tenant_rn_funct)
        self.tenant_key_funct = (tenant_key_funct or
                                 self._default_tenant_key_funct)

    @utils.log
    def update_bulk(self, context, hash_trees, tree=CONFIG_TREE):
        trees = {self.tenant_rn_funct(x): x for x in hash_trees}
        with context.db_session.begin(subtransactions=True):
            db_objs = self._find_query(context, tree,
                                       in_={'tenant_rn': trees.keys()}).all()
            for obj in db_objs:
                hash_tree = trees.pop(obj.tenant_rn)
                obj.root_full_hash = hash_tree.root_full_hash
                obj.tree = str(hash_tree)
                context.db_session.add(obj)

            for hash_tree in trees.values():
                # Tree creation
                empty_tree = structured_tree.StructuredHashTree()
                # Create base tree
                tenant_rn = self.tenant_rn_funct(hash_tree)
                self._create_if_not_exist(context, TenantTree, tenant_rn)
                for tree_klass in SUPPORTED_TREES:
                    if tree_klass == tree:
                        # Then put the updated tree in it
                        self._create_if_not_exist(
                            context, tree_klass, tenant_rn,
                            tree=str(hash_tree),
                            root_full_hash=hash_tree.root_full_hash or 'none')
                    else:
                        # Attempt to create an empty tree:
                        self._create_if_not_exist(
                            context, tree_klass, tenant_rn,
                            tree=str(empty_tree),
                            root_full_hash=empty_tree.root_full_hash or 'none')

    @utils.log
    def delete_bulk(self, context, hash_trees):
        with context.db_session.begin(subtransactions=True):
            tenant_rns = [self.tenant_rn_funct(x) for x in hash_trees]
            for type in SUPPORTED_TREES + [TenantTree]:
                db_objs = self._find_query(
                    context, type, in_={'tenant_rn': tenant_rns}).all()
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
            self._delete_if_exist(context, TenantTree, tenant_rn)
            for type in SUPPORTED_TREES:
                self._delete_if_exist(context, type, tenant_rn)

    @utils.log
    def find(self, context, tree=CONFIG_TREE, **kwargs):
        result = self._find_query(context, tree, in_=kwargs).all()
        return [self.tree_klass.from_string(
            str(x.tree), self.tenant_key_funct(x.tenant_rn)) for x in result]

    @utils.log
    def get(self, context, tenant_rn, tree=CONFIG_TREE):
        try:
            return self.tree_klass.from_string(str(
                self._find_query(context, tree,
                                 tenant_rn=tenant_rn).one().tree),
                self.tenant_key_funct(tenant_rn))
        except sql_exc.NoResultFound:
            raise exc.HashTreeNotFound(tenant_rn=tenant_rn)

    @utils.log
    def find_changed(self, context, tenant_map, tree=CONFIG_TREE):
        if not tenant_map:
            return {}
        return dict((x.tenant_rn,
                     self.tree_klass.from_string(
                         str(x.tree), self.tenant_key_funct(x.tenant_rn)))
                    for x in self._find_query(
                        context, tree, in_={'tenant_rn': tenant_map.keys()},
                        notin_={'root_full_hash': tenant_map.values()}).all())

    @utils.log
    def get_tenants(self, context):
        return [x[0] for x in
                context.db_session.query(TenantTree.tenant_rn).all()]

    def _delete_if_exist(self, context, tree_type, tenant_rn):
        with context.db_session.begin(subtransactions=True):
            obj = self._find_query(context, tree_type,
                                   tenant_rn=tenant_rn).first()
            if obj:
                context.db_session.delete(obj)
            return obj

    def _create_if_not_exist(self, context, tree_type, tenant_rn, **kwargs):
        with context.db_session.begin(subtransactions=True):
            obj = self._find_query(context, tree_type,
                                   tenant_rn=tenant_rn).first()
            if not obj:
                obj = tree_type(tenant_rn=tenant_rn, **kwargs)
                context.db_session.add(obj)
            return obj

    def _find_query(self, context, tree_type, in_=None, notin_=None, **kwargs):
        query = context.db_session.query(tree_type)
        for k, v in (in_ or {}).iteritems():
            query = query.filter(getattr(tree_type, k).in_(v))
        for k, v in (notin_ or {}).iteritems() or {}:
            query = query.filter(getattr(tree_type, k).notin_(
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
    def _extract_dn(res):
        try:
            if isinstance(res, aim_status.AciFault):
                return res.external_identifier
            elif isinstance(res, api_res.AciResourceBase):
                return res.dn
        except Exception as e:
            LOG.warning("Failed to extract DN for resource %s: %s",
                        res, e)

    @staticmethod
    def _build_hash_tree_key(resource):
        dn = AimHashTreeMaker._extract_dn(resource)
        if dn:
            try:
                return AimHashTreeMaker._dn_to_key(resource._aci_mo_name, dn)
            except Exception as e:
                LOG.warning("Failed to get DN for resource %s: %s",
                            resource, e)

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
        to_update = {}
        to_aci = converter.AimToAciModelConverter()
        for aim_res in updates:
            aim_res_dn = AimHashTreeMaker._extract_dn(aim_res)
            if not aim_res_dn:
                continue

            # Remove "related" child-nodes
            aim_res_key = AimHashTreeMaker._build_hash_tree_key(aim_res)
            node = tree.find(aim_res_key) if aim_res_key else None
            for child in (node.get_children() if node else []):
                if child.metadata.get('related'):
                    tree.pop(child.key)

            for obj in to_aci.convert([aim_res]):
                for mo, v in obj.iteritems():
                    attr = v.get('attributes', {})
                    dn = attr.pop('dn', None)
                    key = AimHashTreeMaker._dn_to_key(mo, dn) if dn else None
                    if key:
                        if dn != aim_res_dn:
                            attr['_metadata'] = {'related': True}
                        to_update[key] = attr
        for k, v in to_update.iteritems():
            tree.add(k, **v)
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
