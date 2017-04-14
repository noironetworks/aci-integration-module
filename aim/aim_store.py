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

from aim import aim_manager
from aim.api import infra as api_infra
from aim.api import resource as api_res
from aim.api import service_graph as api_service_graph
from aim.api import status as api_status
from aim.api import tree as api_tree
from aim.common import utils
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
              lock_update=False, **filters):
        # Return list of objects that match specified criteria
        pass

    def add_commit_hook(self):
        pass

    def from_attr(self, db_obj, resource_klass, attribute_dict):
        # Update DB object from attribute dictionary
        pass

    def to_attr(self, resource_klass, db_obj):
        # Construct attribute dictionary from DB object
        pass

    def make_resource(self, cls, db_obj):
        attr_val = {k: v for k, v in self.to_attr(cls, db_obj).iteritems()
                    if k in cls.attributes()}
        return cls(**attr_val)

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

    _features = ['foreign_keys', 'timestamp', 'hooks']

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
                    api_res.Pod: models.Pod}

    resource_map = {}
    for k, v in db_model_map.iteritems():
        resource_map[v] = k

    def __init__(self, db_session, initialize_hooks=True):
        super(SqlAlchemyStore, self).__init__()
        self.db_session = db_session
        if initialize_hooks:
            self._hashtree_db_listener = ht_db_l.HashTreeDbListener(
                aim_manager.AimManager())
            self.register_update_listener(
                'hashtree_db_listener_on_commit',
                self._hashtree_db_listener.on_commit)

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

    def query(self, db_obj_type, resource_klass, in_=None, notin_=None,
              lock_update=False, **filters):
        query = self.db_session.query(db_obj_type)
        for k, v in (in_ or {}).iteritems():
            query = query.filter(getattr(db_obj_type, k).in_(v))
        for k, v in (notin_ or {}).iteritems() or {}:
            query = query.filter(getattr(db_obj_type, k).notin_(
                [(x or '') for x in v]))
        if filters:
            query = query.filter_by(**filters)
        if lock_update:
            query = query.with_lockmode('update')
        return query.all()

    def add_commit_hook(self):
        if not sa_event.contains(self.db_session, 'before_flush',
                                 self._before_session_commit):
            sa_event.listen(self.db_session, 'before_flush',
                            self._before_session_commit, self)

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


class K8sStore(AimStore):

    def __init__(self, namespace=None, config_file=None):
        super(K8sStore, self).__init__()
        self.klient = api_v1.AciContainersV1(config_file=config_file)
        self.namespace = namespace or api_v1.K8S_DEFAULT_NAMESPACE
        self.db_session = None

    _features = ['k8s', 'streaming']

    @property
    def name(self):
        return 'Kubernetes'

    @property
    def supports_hooks(self):
        return False

    def resource_to_db_type(self, resource_klass):
        return api_v1.AciContainersObject

    def from_attr(self, db_obj, resource_klass, attribute_dict):
        name = utils.camel_to_snake(resource_klass.__name__)
        db_obj.setdefault('spec', {'type': name, name: {}})
        db_obj.setdefault('metadata', {'labels': {'aim_type': name}})
        labels = db_obj['metadata']['labels']
        attrs = db_obj['spec'][name]
        for k, v in attribute_dict.iteritems():
            if k in resource_klass.identity_attributes:
                labels[k] = utils.sanitize_name(v)
            attrs[k] = v
        if 'name' not in db_obj['metadata']:
            db_obj['metadata']['name'] = self._build_name(name, resource_klass,
                                                          db_obj)

    def to_attr(self, resource_klass, db_obj):
        result = {}
        for k in resource_klass.attributes():
            try:
                result[k] = getattr(db_obj, k)
            except AttributeError:
                pass
        return result

    def add(self, db_obj):
        created = None
        try:
            curr = self.klient.read_namespaced_aci(db_obj['metadata']['name'],
                                                   self.namespace)
            if curr:
                # Replace this version object
                curr['spec'] = db_obj['spec']
                self.klient.replace_namespaced_aci(db_obj['metadata']['name'],
                                                   self.namespace, curr)
                created = curr
        except api_v1.klient.ApiException as e:
            if str(e.status) == '404':
                # Object doesn't exist, create it.
                db_obj.pop('resourceVersion', None)
                self.klient.create_namespaced_aci(self.namespace, db_obj)
                created = db_obj
            else:
                raise
        self._post_create(created)

    def delete(self, db_obj):
        deleted = db_obj
        try:
            self.klient.delete_collection_namespaced_aci(
                self.namespace,
                label_selector=','.join(
                    ['%s=%s' % (k, v) for k, v in
                     db_obj['metadata']['labels'].iteritems()]))
        except api_v1.klient.ApiException as e:
            if str(e.status) == '404':
                LOG.info("Resource %s not found in K8S during deletion",
                         db_obj['metadata']['name'])
            else:
                raise
        self._post_delete(deleted)

    def query(self, db_obj_type, resource_klass, in_=None, notin_=None,
              lock_update=False, **filters):
        name = utils.camel_to_snake(resource_klass.__name__)
        if 'aim_id' in filters:
            try:
                item = self.klient.read_namespaced_aci(filters.pop('aim_id'),
                                                       self.namespace)
                items = [item]
            except api_v1.klient.ApiException as e:
                if str(e.status) == '404':
                    items = []
                else:
                    raise e
        else:
            label_selector = self._build_label_selector(resource_klass,
                                                        filters)
            items = self.klient.list_namespaced_aci(
                self.namespace, label_selector=label_selector)
            items = items['items']
        result = []
        for item in items:
            if filters or in_ or notin_:
                for k, v in filters.iteritems():
                    if item['spec'][name].get(k) != v:
                        break
                else:
                    for k, v in (in_ or {}).iteritems():
                        if item['spec'][name].get(k) not in v:
                            break
                    else:
                        for k, v in (notin_ or {}).iteritems():
                            if item['spec'][name].get(k) in v:
                                break
                        else:
                            db_obj = api_v1.AciContainersObject()
                            db_obj.update(item)
                            result.append(db_obj)
            else:
                db_obj = api_v1.AciContainersObject()
                db_obj.update(item)
                result.append(db_obj)
        return result

    def _build_label_selector(self, resource_klass, filters):
        result = 'aim_type=%s' % utils.camel_to_snake(resource_klass.__name__)
        for filter in filters:
            if filter in resource_klass.identity_attributes:
                result += ',%s=%s' % (
                    filter, utils.sanitize_name(filters[filter]))
        return result

    def _build_name(self, type, resource_klass, db_obj):
        components = []
        for attr in sorted(resource_klass.identity_attributes):
            components.append(db_obj['spec'][type][attr])
        return utils.sanitize_name(type, *components)

    def _post_create(self, created):
        # Can be patched in UTs to simulate Hashtree postcommit
        pass

    def _post_delete(self, deleted):
        # Can be patched in UTs to simulate Hashtree postcommit
        pass


class KeyValueStore(AimStore):

    def __init__(self, **kwargs):
        pass
