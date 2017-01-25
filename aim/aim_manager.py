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
from sqlalchemy import event as sa_event

from aim.api import infra as api_infra
from aim.api import resource as api_res
from aim.api import status as api_status
from aim.db import agent_model
from aim.db import hashtree_db_listener as ht_db_l
from aim.db import infra_model
from aim.db import models
from aim.db import status_model
from aim import exceptions as exc


LOG = logging.getLogger(__name__)


class AimManager(object):
    """Main object for performing operations on AIM.

    To manipulate AIM database objects, invoke the appropriate
    operation specifying an AimContext and the resource to operate on. The
    resource should be an object of type that inherits from
    aim.api.ResourceBase.
    The AimContext must have property 'db_session' set to sqlalchemy
    ORM session object; the database operation is performed in the
    context of that session.
    Example: Create a BridgeDomain object and then retrieve it

        db = ...
        a_ctx = AimContext(db_session=db)
        mgr = AimManager(...)

        bd = aim.api.resource.BridgeDomain(...)
        mgr.create(a_ctx, bd)

        retrieved_bd = mgr.get(a_ctx, bd)
    """

    _db_model_map = {api_res.BridgeDomain: models.BridgeDomain,
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
                     api_infra.HostLink: infra_model.HostLink}

    # Build adjacency graph (Key: <ACI Resource> Value: <Key's children>)
    _model_tree = {}
    _res_by_aci_type = {}
    for klass in _db_model_map:
        try:
            _model_tree.setdefault(klass._tree_parent, []).append(klass)
            _res_by_aci_type[klass._aci_mo_name] = klass
        except AttributeError:
            pass

    def __init__(self):
        # TODO(amitbose): initialize anything we need, for example DB stuff
        self._resource_map = {}
        for k, v in self._db_model_map.iteritems():
            self._resource_map[v] = k
        self._update_listeners = []
        self._hashtree_db_listener = ht_db_l.HashTreeDbListener(self)

    def create(self, context, resource, overwrite=False, fix_ownership=False):
        """Persist AIM resource to the database.

        If 'overwrite' is True, and an object exists in the database
        with the same identity attribute values, then that object will
        be over-written with the specified resource. Otherwise an
        integrity constraint violation is raised.
        """
        self._validate_resource_class(resource)
        with context.db_session.begin(subtransactions=True):
            old_db_obj = None
            old_monitored = None
            new_monitored = None
            if overwrite:
                old_db_obj = self._query_db_obj(context.db_session, resource)
                if old_db_obj:
                    old_monitored = getattr(old_db_obj, 'monitored', None)
                    new_monitored = getattr(resource, 'monitored', None)
                    if fix_ownership and old_monitored != new_monitored:
                        raise exc.InvalidMonitoredStateUpdate(object=resource)
                    attr_val = self._extract_attributes(resource, "other")
                    old_db_obj.from_attr(context.db_session, attr_val)
            db_obj = old_db_obj or self._make_db_obj(context.db_session,
                                                     resource)
            self._add_commit_hook(context.db_session)
            context.db_session.add(db_obj)
            # Propagate sync status to neighbor objects
            # TODO(ivar): workaround for newly created monitored Tenant that
            # will always stay in pending state.
            if not old_db_obj and isinstance(
                    resource, api_res.Tenant) and getattr(
                    resource, 'monitored', None):
                self.set_resource_sync_synced(context, resource)
            elif isinstance(resource, api_res.AciResourceBase):
                # Monitored objects that are not changing the monitored status
                # should not go in pending.
                if self._should_set_pending(old_db_obj, old_monitored,
                                            new_monitored):
                    self.set_resource_sync_pending(context, resource)
            return self.get(context, resource)

    def update(self, context, resource, fix_ownership=False,
               **update_attr_val):
        """Persist updates to AIM resource to the database.

        Values of identity attributes of parameter 'resource' are used
        to determine the database object to update; no other attributes
        from 'resource' are used during the update. Param 'update_attr_val'
        specifies the values of the attributes to update.
        If the object does not exist in the database, no changes are
        made to the database.
        """
        self._validate_resource_class(resource)
        with context.db_session.begin(subtransactions=True):
            db_obj = self._query_db_obj(context.db_session, resource)
            if db_obj:
                old_monitored = getattr(db_obj, 'monitored', None)
                new_monitored = update_attr_val.get('monitored')
                if fix_ownership and old_monitored != new_monitored:
                    raise exc.InvalidMonitoredStateUpdate(object=resource)
                attr_val = {k: v for k, v in update_attr_val.iteritems()
                            if k in resource.other_attributes}
                db_obj.from_attr(context.db_session, attr_val)
                context.db_session.add(db_obj)
                self._add_commit_hook(context.db_session)
                if isinstance(resource, api_res.AciResourceBase):
                    # Monitored objects that are not changing the monitored
                    # status should not go in pending.
                    if self._should_set_pending(db_obj, old_monitored,
                                                new_monitored):
                        self.set_resource_sync_pending(context, resource)
                return self.get(context, resource)

    def _should_set_pending(self, old_obj, old_monitored, new_monitored):
        return (not old_obj or not old_monitored or
                new_monitored is not None and old_monitored != new_monitored)

    def delete(self, context, resource):
        """Delete AIM resource from the database.

        Only values of identity attributes of parameter 'resource' are
        used; other attributes may be left unspecified.
        If the object does not exist in the database, no error is reported.
        """
        self._validate_resource_class(resource)
        with context.db_session.begin(subtransactions=True):
            db_obj = self._query_db_obj(context.db_session, resource)
            if db_obj:
                if isinstance(resource, api_res.AciResourceBase):
                    status = self.get_status(context, resource)
                    if status and getattr(db_obj, 'monitored', None):
                        if status.sync_status == status.SYNC_PENDING:
                            # Cannot delete monitored objects if sync status
                            # is pending, or ownership flip might fail
                            raise exc.InvalidMonitoredObjectDelete(
                                object=resource)
                    # Recursively delete monitored children
                    for child_res in self._iter_children(context, resource,
                                                         monitored=True):
                        self.delete(context, child_res)
                    if status:
                        for fault in status.faults:
                            self.clear_fault(context, fault)
                        self.delete(context, status)
                context.db_session.delete(db_obj)
                self._add_commit_hook(context.db_session)

    def get(self, context, resource):
        """Get AIM resource from the database.

        Values of identity attributes of parameter 'resource' are used
        to determine the database object to fetch; other attributes may
        be left unspecified.
        Returns a resource with all the attributes populated with contents
        of the object in the database if the object is found, None
        otherwise.
        """
        self._validate_resource_class(resource)
        db_obj = self._query_db_obj(context.db_session, resource)
        return self._make_resource(
            context.db_session, type(resource), db_obj) if db_obj else None

    def get_by_id(self, context, resource_class, aim_id):
        self._validate_resource_class(resource_class)
        db_obj = self._query_db(context.db_session,
                                resource_class, aim_id=aim_id).one()
        return self._make_resource(
            context.db_session, resource_class, db_obj) if db_obj else None

    def find(self, context, resource_class, **kwargs):
        """Find AIM resources from the database that match specified criteria.

        Parameter 'resource_class' indicates the type of resource to
        look for. Matching criteria are specified as keyword-arguments.
        Only equality matches are supported.
        Returns a list of resources that match.
        """
        self._validate_resource_class(resource_class)
        attr_val = {k: v for k, v in kwargs.iteritems()
                    if k in (resource_class.other_attributes +
                             resource_class.identity_attributes +
                             resource_class.db_attributes)}
        result = []
        for obj in self._query_db(context.db_session,
                                  resource_class, **attr_val).all():
            result.append(
                self._make_resource(context.db_session, resource_class, obj))
        return result

    def get_status(self, context, resource):
        """Get status of an AIM resource, if any.

        Values of identity attributes of parameter 'resource' are used
        to determine the object to get status for; other attributes may
        be left unspecified.
        """

        with context.db_session.begin(subtransactions=True):
            if isinstance(resource, api_res.AciResourceBase):
                res_type, res_id = self._get_status_params(context, resource)
                if res_type and res_id is not None:
                    status = self.get(context, api_status.AciStatus(
                        resource_type=res_type, resource_id=res_id))
                    if not status:
                        # Create one with default values
                        return self.update_status(context, resource,
                                                  api_status.AciStatus())
                    status.faults = self.find(context, api_status.AciFault,
                                              status_id=status.id)
                    return status
        return None

    def update_status(self, context, resource, status):
        """Update the status of an AIM resource.

        Values of identity attributes of parameter 'resource' are used
        to determine the object whose status will be updated; other
        attributes may be left unspecified.
        """
        with context.db_session.begin(subtransactions=True):
            if isinstance(resource, api_res.AciResourceBase):
                res_type, res_id = self._get_status_params(context, resource)
                if res_type and res_id:
                    status.resource_type = res_type
                    status.resource_id = res_id
                    return self.create(context, status, overwrite=True)

    def _set_resource_sync(self, context, resource, sync_status, message='',
                           exclude=None):
        if isinstance(resource, api_status.AciStatus):
            return False
        with context.db_session.begin(subtransactions=True):
            self._validate_resource_class(resource)
            status = self.get_status(context, resource)
            exclude = exclude or []
            if status and status.sync_status not in exclude:
                self.update(context, status, sync_status=sync_status,
                            sync_message=message)
                return True
            return False

    def set_resource_sync_synced(self, context, resource):
        self._set_resource_sync(context, resource, api_status.AciStatus.SYNCED)

    def set_resource_sync_pending(self, context, resource, top=True):
        # When a resource goes in pending state, propagate to both parent
        # and subtree
        with context.db_session.begin(subtransactions=True):
            # If resource is already in pending or synced state stop
            # propagation
            if self._set_resource_sync(
                    context, resource, api_status.AciStatus.SYNC_PENDING,
                    exclude=[api_status.AciStatus.SYNCED,
                             api_status.AciStatus.SYNC_PENDING]
                    if not top else []):
                # Change parent first
                parent_klass = resource._tree_parent
                if parent_klass:
                    identity = {v: resource.identity[i]
                                for i, v in enumerate(
                        parent_klass.identity_attributes)}
                    self.set_resource_sync_pending(context,
                                                   parent_klass(**identity),
                                                   top=False)
                for child_res in self._iter_children(context, resource):
                    self.set_resource_sync_pending(context, child_res,
                                                   top=False)

    def set_resource_sync_error(self, context, resource, message=''):
        with context.db_session.begin(subtransactions=True):
            # No need to set sync_error for resources already in that state
            if self._set_resource_sync(
                    context, resource, api_status.AciStatus.SYNC_FAILED,
                    message=message,
                    exclude=[api_status.AciStatus.SYNC_FAILED]):
                # Set sync_error for the whole subtree
                for child_res in self._iter_children(context, resource):
                    self.set_resource_sync_error(
                        context, child_res,
                        message="Parent resource %s is "
                                "in error state" % str(resource))

    def set_fault(self, context, resource, fault):
        with context.db_session.begin(subtransactions=True):
            status = self.get_status(context, resource)
            if status:
                fault.status_id = status.id
                self.create(context, fault, overwrite=True)

    def clear_fault(self, context, fault, **kwargs):
        with context.db_session.begin(subtransactions=True):
            db_fault = self._query_db(
                context.db_session, api_status.AciFault,
                external_identifier=fault.external_identifier).first()
            if db_fault:
                context.db_session.delete(db_fault)
                self._add_commit_hook(context.db_session)

    def register_update_listener(self, func):
        """Register callback for update to AIM objects.

        Parameter 'func' should be a function that accepts 4 parameters.
        The first parameter is SQLAlchemy ORM session in which AIM objects
        are being updated. Rest of the parameters are lists of AIM resources
        that were added, updated and deleted respectively.
        The callback will be invoked before the database transaction
        that updated the AIM object commits.

        Example:

        def my_listener(session, added, updated, deleted):
            "Iterate over 'added', 'updated', 'deleted'

        a_mgr = AimManager()
        a_mgr.register_update_listener(my_listener)

        """
        self._update_listeners.append(func)

    def unregister_update_listener(self, func):
        """Remove callback for update to AIM objects."""
        self._update_listeners.remove(func)

    def _validate_resource_class(self, resource_or_class):
        res_cls = (resource_or_class if isinstance(resource_or_class, type)
                   else type(resource_or_class))
        db_cls = self._db_model_map.get(res_cls)
        if not db_cls:
            raise exc.UnknownResourceType(type=res_cls)
        return db_cls

    def _query_db(self, db_session, resource_class, **kwargs):
        db_cls = self._db_model_map[resource_class]
        return db_session.query(db_cls).filter_by(**kwargs)

    def _query_db_obj(self, db_session, resource):
        id_attr = self._extract_attributes(resource, "id")
        cls = type(resource)
        return self._query_db(db_session, cls, **id_attr).first()

    def _extract_attributes(self, resource, attr_type=None):
        val = {}
        if not attr_type or attr_type == "id":
            val.update({k: getattr(resource, k)
                        for k in resource.identity_attributes})
        if not attr_type or attr_type == "other":
            val.update({k: getattr(resource, k, None)
                        for k in resource.other_attributes})
        if not attr_type or attr_type == "db":
            val.update({k: getattr(resource, k, None)
                        for k in resource.db_attributes})
        return val

    def _make_db_obj(self, session, resource):
        cls = self._db_model_map.get(type(resource))
        obj = cls()
        obj.from_attr(session, self._extract_attributes(resource))
        return obj

    def _make_resource(self, session, cls, db_obj):
        attr_val = {k: v for k, v in db_obj.to_attr(session).iteritems()
                    if k in (cls.other_attributes + cls.identity_attributes +
                             cls.db_attributes)}
        return cls(**attr_val)

    def _add_commit_hook(self, session):
        if not sa_event.contains(session, 'before_flush',
                                 self._before_session_commit):
            sa_event.listen(session, 'before_flush',
                            self._before_session_commit)

    def _before_session_commit(self, session, flush_context, instances):
        added = []
        updated = []
        deleted = []
        modified = [(session.new, added),
                    (session.dirty, updated),
                    (session.deleted, deleted)]
        for mod_set, res_list in modified:
            for db_obj in mod_set:
                res_cls = self._resource_map.get(type(db_obj))
                if res_cls:
                    res = self._make_resource(session, res_cls, db_obj)
                    res_list.append(res)
        for func in self._update_listeners[:]:
            LOG.debug("Invoking pre-commit hook %s with %d add(s), "
                      "%d update(s), %d delete(s)",
                      func.__name__, len(added), len(updated), len(deleted))
            func(session, added, updated, deleted)

    def _get_status_params(self, context, resource):
        res_type = type(resource).__name__
        db_obj = self._query_db_obj(context.db_session, resource)
        if db_obj is None:
            # TODO(ivar): should we raise a proper exception?
            return None, None
        try:
            res_id = db_obj.aim_id
        except AttributeError:
            LOG.warn("Resource with type %s doesn't support status" %
                     res_type)
            return None, None
        return res_type, res_id

    def _iter_children(self, context, resource, **kwargs):
        for child_klass in self._model_tree.get(
                type(resource), []):
            identity = {child_klass.identity_attributes[i]: v
                        for i, v in enumerate(resource.identity)}
            # Extra search attributes
            identity.update(kwargs)
            for child_res in self.find(context, child_klass,
                                       **identity):
                yield child_res
