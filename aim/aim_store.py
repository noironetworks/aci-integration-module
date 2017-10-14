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

from contextlib import contextmanager
import copy
from oslo_log import log as logging
from sqlalchemy import event as sa_event
from sqlalchemy.sql.expression import func

from aim.agent.aid.event_services import rpc
from aim import aim_manager
from aim.api import infra as api_infra
from aim.api import resource as api_res
from aim.api import service_graph as api_service_graph
from aim.api import status as api_status
from aim.api import tree as api_tree
from aim.db import agent_model
from aim.db import config_model
from aim.db import hashtree_db_listener as ht_db_l
from aim.db import infra_model
from aim.db import models
from aim.db import service_graph_model
from aim.db import status_model
from aim.db import tree_model
from aim.k8s import api_v1


LOG = logging.getLogger(__name__)


@contextmanager
def _begin(**kwargs):
    yield


class AimStore(object):
    """Interface to backend persistence for AIM resources."""

    _features = []
    _update_listeners = {}
    _postcommit_listeners = {}

    def __init__(self):
        pass

    def __getattr__(self, item):
        if item.startswith('supports_'):
            return item.replace('supports_', '') in self.features
        else:
            raise AttributeError(item)

    @property
    def features(self):
        return self._features

    @property
    def current_timestamp(self):
        return None

    def begin(self, **kwargs):
        # Begin transaction of updates, if applicable.
        # Should return a contextmanager object

        # default returns a no-op contextmanager
        return _begin(**kwargs)

    def expunge_all(self):
        # Expunge transaction artifacts if supported
        pass

    def resource_to_db_type(self, resource_klass):
        # Returns the DB object type for an AIM resource type
        return resource_klass

    def add(self, db_obj):
        # Save (create/update) object to backend
        pass

    def delete(self, db_obj):
        # Delete object from backend if it exists
        pass

    def query(self, db_obj_type, resource_klass, in_=None, notin_=None,
              order_by=None, lock_update=False, **filters):
        # Return list of objects that match specified criteria
        pass

    def count(self, db_obj_type, resource_klass, in_=None, notin_=None,
              **filters):
        # Return count of objects that match specified criteria
        pass

    def delete_all(self, db_obj_type, resource_klass, in_=None, notin_=None,
                   **filters):
        # Delete all objects that match specified criteria
        pass

    def add_commit_hook(self):
        pass

    def from_attr(self, db_obj, resource_klass, attribute_dict):
        # Update DB object from attribute dictionary
        pass

    def to_attr(self, resource_klass, db_obj):
        # Construct attribute dictionary from DB object
        pass

    def make_resource(self, cls, db_obj, include_aim_id=False):
        attr_val = {k: v for k, v in self.to_attr(cls, db_obj).iteritems()
                    if k in cls.attributes()}
        res = cls(**attr_val)
        if include_aim_id and hasattr(db_obj, 'aim_id'):
            res._aim_id = db_obj.aim_id
        return res

    def register_update_listener(self, name, func):
        """Register callback for update to AIM objects.

        Parameter 'func' should be a function that accepts 4 parameters.
        The first parameter is AimStore using which AIM objects
        are being updated. Rest of the parameters are lists of AIM resources
        that were added, updated and deleted respectively.
        If the store supports transaction, the callback will be invoked
        before the transaction that updated the AIM object commits.

        Example:

        def my_listener(store, added, updated, deleted):
            # Iterate over 'added', 'updated', 'deleted'
            ...

        a_store = AimStore(...)    # Typically a sub-class of AimStore
        a_store.register_update_listener(my_listener)

        """
        if name not in self._update_listeners:
            self._update_listeners[name] = func

    def unregister_update_listener(self, name):
        """Remove callback for update to AIM objects."""
        self._update_listeners.pop(name, None)

    def register_postcommit_listener(self, name, func):
        if name not in self._postcommit_listeners:
            self._postcommit_listeners[name] = func

    def unregister_postcommit_listener(self, name):
        """Remove callback for update to AIM objects."""
        self._postcommit_listeners.pop(name, None)

    def extract_attributes(self, resource, attr_type=None):
        val = {}
        if not attr_type or attr_type == "id":
            val.update({k: getattr(resource, k)
                        for k in resource.identity_attributes})
        if not attr_type or attr_type == "other":
            val.update({k: getattr(resource, k, None)
                        for k in resource.other_attributes})
        if not attr_type or attr_type == "db":
            val.update({k: getattr(resource, k)
                        for k in resource.db_attributes
                        if hasattr(resource, k)})
        return val

    def make_db_obj(self, resource):
        cls = self.resource_to_db_type(type(resource))
        obj = cls()
        self.from_attr(obj, type(resource),
                       self.extract_attributes(resource))
        return obj


class SqlAlchemyStore(AimStore):

    _features = ['foreign_keys', 'timestamp', 'hooks', 'sql']

    # Dict mapping AIM resources to DB model objects
    db_model_map = {api_res.BridgeDomain: models.BridgeDomain,
                    api_res.Agent: agent_model.Agent,
                    api_res.Tenant: models.Tenant,
                    api_res.Subnet: models.Subnet,
                    api_res.VRF: models.VRF,
                    api_res.ApplicationProfile: models.ApplicationProfile,
                    api_res.EndpointGroup: models.EndpointGroup,
                    api_res.Filter: models.Filter,
                    api_res.FilterEntry: models.FilterEntry,
                    api_res.Contract: models.Contract,
                    api_res.ContractSubject: models.ContractSubject,
                    api_status.AciStatus: status_model.Status,
                    api_status.AciFault: status_model.Fault,
                    api_res.Endpoint: models.Endpoint,
                    api_res.VMMDomain: models.VMMDomain,
                    api_res.PhysicalDomain: models.PhysicalDomain,
                    api_res.L3Outside: models.L3Outside,
                    api_res.ExternalNetwork: models.ExternalNetwork,
                    api_res.ExternalSubnet: models.ExternalSubnet,
                    api_infra.HostLink: infra_model.HostLink,
                    api_infra.HostDomainMapping: (
                        infra_model.HostDomainMapping),
                    api_infra.HostLinkNetworkLabel: (
                        infra_model.HostLinkNetworkLabel),
                    api_res.SecurityGroup: models.SecurityGroup,
                    api_res.SecurityGroupSubject: models.SecurityGroupSubject,
                    api_res.SecurityGroupRule: models.SecurityGroupRule,
                    api_res.Configuration: config_model.Configuration,
                    api_tree.Tree: tree_model.Tree,
                    api_tree.ConfigTree: tree_model.ConfigTree,
                    api_tree.MonitoredTree: tree_model.MonitoredTree,
                    api_tree.OperationalTree: tree_model.OperationalTree,
                    api_service_graph.DeviceCluster: (
                        service_graph_model.DeviceCluster),
                    api_service_graph.DeviceClusterInterface: (
                        service_graph_model.DeviceClusterInterface),
                    api_service_graph.ConcreteDevice: (
                        service_graph_model.ConcreteDevice),
                    api_service_graph.ConcreteDeviceInterface: (
                        service_graph_model.ConcreteDeviceInterface),
                    api_service_graph.ServiceGraph: (
                        service_graph_model.ServiceGraph),
                    api_service_graph.ServiceGraphConnection: (
                        service_graph_model.ServiceGraphConnection),
                    api_service_graph.ServiceGraphNode: (
                        service_graph_model.ServiceGraphNode),
                    api_service_graph.ServiceRedirectPolicy: (
                        service_graph_model.ServiceRedirectPolicy),
                    api_service_graph.DeviceClusterContext: (
                        service_graph_model.DeviceClusterContext),
                    api_service_graph.DeviceClusterInterfaceContext: (
                        service_graph_model.DeviceClusterInterfaceContext),
                    api_infra.OpflexDevice: infra_model.OpflexDevice,
                    api_res.VMMPolicy: models.VMMPolicy,
                    api_res.Pod: models.Pod,
                    api_res.Topology: models.Topology,
                    api_res.VMMController: models.VMMController,
                    api_res.VmmInjectedNamespace: models.VmmInjectedNamespace,
                    api_res.VmmInjectedDeployment: (
                        models.VmmInjectedDeployment),
                    api_res.VmmInjectedReplicaSet: (
                        models.VmmInjectedReplicaSet),
                    api_res.VmmInjectedService: models.VmmInjectedService,
                    api_res.VmmInjectedHost: models.VmmInjectedHost,
                    api_res.VmmInjectedContGroup: models.VmmInjectedContGroup,
                    api_tree.ActionLog: tree_model.ActionLog}

    resource_map = {}
    for k, v in db_model_map.iteritems():
        resource_map[v] = k

    def __init__(self, db_session, initialize_hooks=True):
        super(SqlAlchemyStore, self).__init__()
        self.db_session = db_session
        self.initialize_hooks = initialize_hooks
        if initialize_hooks:
            self._initialize_hooks()

    def _initialize_hooks(self):
        self._hashtree_db_listener = ht_db_l.HashTreeDbListener(
            aim_manager.AimManager())
        self.register_update_listener('hashtree_db_listener_on_commit',
                                      self._hashtree_db_listener.on_commit)
        self.register_postcommit_listener(
            'tree_creation_postcommit',
            rpc.AIDEventRpcApi().tree_creation_postcommit)

    @property
    def name(self):
        return 'SQLAlchemy'

    @property
    def current_timestamp(self):
        return self.db_session.query(func.now()).scalar()

    @property
    def supports_foreign_keys(self):
        return True

    def begin(self, **kwargs):
        return self.db_session.begin(subtransactions=True)

    def expunge_all(self):
        self.db_session.expunge_all()

    def resource_to_db_type(self, resource_klass):
        return self.db_model_map.get(resource_klass)

    def add(self, db_obj):
        self.db_session.add(db_obj)

    def delete(self, db_obj):
        self.db_session.delete(db_obj)

    def _query(self, db_obj_type, resource_klass, in_=None, notin_=None,
               order_by=None, lock_update=False, **filters):
        query = self.db_session.query(db_obj_type)
        for k, v in (in_ or {}).iteritems():
            query = query.filter(getattr(db_obj_type, k).in_(v))
        for k, v in (notin_ or {}).iteritems() or {}:
            query = query.filter(getattr(db_obj_type, k).notin_(
                [(x or '') for x in v]))
        if filters:
            query = query.filter_by(**filters)
        if order_by:
            if isinstance(order_by, list):
                args = [getattr(db_obj_type, x) for x in order_by]
            else:
                args = [getattr(db_obj_type, order_by)]
            query = query.order_by(*args)
        if lock_update:
            query = query.with_lockmode('update')
        return query

    def query(self, db_obj_type, resource_klass, in_=None, notin_=None,
              order_by=None, lock_update=False, **filters):

        return self._query(db_obj_type, resource_klass, in_=in_, notin_=notin_,
                           order_by=order_by, lock_update=lock_update,
                           **filters).all()

    def count(self, db_obj_type, resource_klass, in_=None, notin_=None,
              **filters):

        return self._query(db_obj_type, resource_klass, in_=in_, notin_=notin_,
                           **filters).count()

    def delete_all(self, db_obj_type, resource_klass, in_=None, notin_=None,
                   **filters):
        return self._query(db_obj_type, resource_klass, in_=in_, notin_=notin_,
                           **filters).delete(synchronize_session='fetch')

    def add_commit_hook(self):
        if not sa_event.contains(self.db_session, 'before_flush',
                                 self._before_session_commit):
            sa_event.listen(self.db_session, 'before_flush',
                            self._before_session_commit, self)
        if not sa_event.contains(
                self.db_session, 'after_transaction_end',
                self._after_transaction_end):
            sa_event.listen(self.db_session, 'after_transaction_end',
                            self._after_transaction_end)
        if not sa_event.contains(self.db_session, 'after_flush',
                                 self._after_session_flush):
            sa_event.listen(self.db_session, 'after_flush',
                            self._after_session_flush)

    def from_attr(self, db_obj, resource_klass, attribute_dict):
        db_obj.from_attr(self.db_session, attribute_dict)

    def to_attr(self, resource_klass, db_obj):
        return db_obj.to_attr(self.db_session)

    @staticmethod
    def _before_session_commit(session, flush_context, instances):
        store = SqlAlchemyStore(session, initialize_hooks=False)
        added = []
        updated = []
        deleted = []
        modified = [(session.new, added),
                    (session.dirty, updated),
                    (session.deleted, deleted)]
        for mod_set, res_list in modified:
            for db_obj in mod_set:
                res_cls = store.resource_map.get(type(db_obj))
                if res_cls:
                    res = store.make_resource(res_cls, db_obj)
                    res_list.append(res)
        for f in copy.copy(SqlAlchemyStore._update_listeners).values():
            LOG.debug("Invoking pre-commit hook %s with %d add(s), "
                      "%d update(s), %d delete(s)",
                      f.__name__, len(added), len(updated), len(deleted))
            f(store, added, updated, deleted)

    def _after_session_flush(self, session, _):
        # Stash log changes
        added = set([x.root_rn for x in session.new
                     if isinstance(x, tree_model.ActionLog)])
        updated = set([x.root_rn for x in session.dirty
                       if isinstance(x, tree_model.ActionLog)])
        try:
            session._aim_stash
        except AttributeError:
            session._aim_stash = {'added': set(), 'updated': set(),
                                  'deleted': set()}
        session._aim_stash['added'] |= added
        session._aim_stash['updated'] |= updated

    @staticmethod
    def _after_transaction_end(session, transaction):
        # Check if outermost transaction
        try:
            if transaction.parent is not None:
                return
        except AttributeError:
            # sqlalchemy 1.0.11 and below
            if transaction._parent is not None:
                return
        try:
            added = session._aim_stash['added']
            updated = session._aim_stash['updated']
        except AttributeError:
            return
        for f in copy.copy(SqlAlchemyStore._postcommit_listeners).values():
            LOG.debug("Invoking after transaction commit hook %s with "
                      "%d add(s), %d update(s))",
                      f.__name__, len(added), len(updated))
            try:
                f(session, [], updated | added, [])
            except Exception as ex:
                LOG.error("An error occurred during aim manager postcommit "
                          "execution: %s" % ex.message)
        del session._aim_stash


class K8sStore(AimStore):

    db_model_map = {api_res.VmmInjectedNamespace: api_v1.Namespace,
                    api_res.VmmInjectedDeployment: api_v1.Deployment,
                    api_res.VmmInjectedReplicaSet: api_v1.ReplicaSet,
                    api_res.VmmInjectedService: api_v1.Service,
                    api_res.VmmInjectedHost: api_v1.Node,
                    api_res.VmmInjectedContGroup: api_v1.Pod}

    def __init__(self, namespace=None, config_file=None,
                 vmm_domain=None, vmm_controller=None):
        super(K8sStore, self).__init__()
        self.klient = api_v1.AciContainersV1(config_file=config_file)
        self.namespace = namespace or api_v1.K8S_DEFAULT_NAMESPACE
        self.attribute_defaults = {'domain_type': 'Kubernetes',
                                   'domain_name': vmm_domain or 'kubernetes',
                                   'controller_name':
                                   vmm_controller or 'kube-cluster'}
        self.db_session = None

    _features = ['k8s', 'streaming', 'object_uid']

    @property
    def name(self):
        return 'Kubernetes'

    @property
    def supports_hooks(self):
        return False

    def resource_to_db_type(self, resource_klass):
        return self.db_model_map.get(resource_klass,
                                     api_v1.AciContainersObject)

    def from_attr(self, db_obj, resource_klass, attribute_dict):
        db_obj.from_attr(resource_klass, attribute_dict)

    def to_attr(self, resource_klass, db_obj):
        return db_obj.to_attr(resource_klass, defaults=self.attribute_defaults)

    def add(self, db_obj):
        # TODO(amitbose) Handle aux_objects
        created = None
        k8s_klass = type(db_obj)
        obj_ns = (self.namespace
                  if k8s_klass == api_v1.AciContainersObject
                  else db_obj['metadata'].get('namespace', self.namespace))
        retries = 3  # this is arbitrary
        while retries:
            retries -= 1
            try:
                curr = self.klient.read(k8s_klass, db_obj['metadata']['name'],
                                        obj_ns)
                if curr:
                    curr['spec'].update(db_obj.get('spec', {}))
                    curr['metadata'].setdefault('annotations', {}).update(
                        db_obj.get('metadata', {}).get('annotations', {}))
                    curr['metadata'].setdefault('labels', {}).update(
                        db_obj.get('metadata', {}).get('labels', {}))
                    curr.pop('status', None)
                    self.klient.replace(k8s_klass, db_obj['metadata']['name'],
                                        obj_ns, curr)
                    created = curr
                break
            except api_v1.klient.ApiException as e:
                if str(e.status) == '404':
                    # Object doesn't exist, create it.
                    db_obj.get('metadata', {}).pop('resourceVersion', None)
                    self.klient.create(k8s_klass, obj_ns, db_obj)
                    created = db_obj
                    break
                elif str(e.status) == '409' and retries:
                    LOG.info('Concurrent modification on %s %s, retrying '
                             'replace operation',
                             k8s_klass.kind, db_obj['metadata']['name'])
                else:
                    raise
        self._post_create(created)

    def delete(self, db_obj):
        # TODO(amitbose) Handle aux_objects
        deleted = db_obj
        obj_ns = db_obj['metadata'].get('namespace', self.namespace)
        try:
            if isinstance(db_obj, api_v1.AciContainersObject):
                # Can't delete third-party objects using their name
                self.klient.delete_collection(
                    api_v1.AciContainersObject, self.namespace,
                    label_selector=','.join(
                        ['%s=%s' % (k, v) for k, v in
                         db_obj['metadata']['labels'].iteritems()]))
            else:
                self.klient.delete(type(db_obj), db_obj['metadata']['name'],
                                   obj_ns, {})
        except api_v1.klient.ApiException as e:
            if str(e.status) == '404':
                LOG.info("Resource %s not found in K8S during deletion",
                         db_obj['metadata']['name'])
            else:
                raise
        self._post_delete(deleted)

    def query(self, db_obj_type, resource_klass, in_=None, notin_=None,
              order_by=None, lock_update=False, **filters):
        def_ns = (self.namespace
                  if db_obj_type == api_v1.AciContainersObject else None)

        selectors = db_obj_type().build_selectors(resource_klass, filters)
        obj_name = selectors.pop('name', None)
        obj_ns = selectors.pop('namespace', None) or def_ns

        if obj_name and obj_ns:
            try:
                item = self.klient.read(db_obj_type, obj_name, obj_ns)
                items = [item]
            except api_v1.klient.ApiException as e:
                if str(e.status) == '404':
                    items = []
                else:
                    raise e
        else:
            field_selectors = selectors.pop('field_selector', [])
            if obj_name:
                field_selectors.append('metadata.name=%s' % obj_name)
            if field_selectors:
                selectors['field_selector'] = '&'.join(field_selectors)
            try:
                items = self.klient.list(db_obj_type, obj_ns, **selectors)
                items = items['items']
            except api_v1.klient.ApiException as e:
                if str(e.status) == '400':
                    # Some K8S objects may not support fieldSelector
                    LOG.info('Query for %s, namespace %s, selectors %s '
                             'treated as Bad Request: %s',
                             db_obj_type.kind, obj_ns, selectors, e)
                    items = []
                else:
                    raise e

        result = []
        aim_id_val = filters.pop('aim_id', None)
        for item in (items or []):
            if item['metadata'].get('deletionTimestamp'):
                continue
            db_obj = db_obj_type()
            db_obj.update(item)
            if aim_id_val is not None and db_obj.aim_id != aim_id_val:
                continue
            for aux_a, aux_kls in db_obj_type.aux_objects.iteritems():
                try:
                    aux_item_raw = self.klient.read(
                        aux_kls,
                        db_obj['metadata']['name'],
                        db_obj['metadata'].get('namespace'))
                    aux_item = aux_kls()
                    aux_item.update(aux_item_raw)
                    setattr(db_obj, aux_a, aux_item)
                except api_v1.klient.ApiException as e:
                    if str(e.status) != '404':
                        raise e
            item_attr = db_obj.to_attr(resource_klass,
                                       defaults=self.attribute_defaults)
            if filters or in_ or notin_:
                for k, v in filters.iteritems():
                    if item_attr.get(k) != v:
                        break
                else:
                    for k, v in (in_ or {}).iteritems():
                        if item_attr.get(k) not in v:
                            break
                    else:
                        for k, v in (notin_ or {}).iteritems():
                            if item_attr.get(k) in v:
                                break
                        else:
                            result.append(db_obj)
            else:
                result.append(db_obj)
        if order_by:
            if isinstance(order_by, basestring):
                order_by = [order_by]
            result = sorted(result,
                            key=lambda x: tuple([x[k] for k in order_by]))
        return result

    def count(self, db_obj_type, resource_klass, in_=None, notin_=None,
              **filters):
        return len(
            self.query(db_obj_type, resource_klass, in_=in_, notin_=notin_,
                       **filters))

    def delete_all(self, db_obj_type, resource_klass, in_=None, notin_=None,
                   **filters):
        for obj in self.query(db_obj_type, resource_klass, in_=in_,
                              notin_=notin_, **filters):
            self.delete(obj)

    def _post_create(self, created):
        # Can be patched in UTs to simulate Hashtree postcommit
        pass

    def _post_delete(self, deleted):
        # Can be patched in UTs to simulate Hashtree postcommit
        pass


class KeyValueStore(AimStore):

    def __init__(self, **kwargs):
        pass
