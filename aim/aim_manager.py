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

from aim.api import resource as api_res
from aim.api import status as api_status
from aim.db import agent_model
from aim.db import hashtree_db_listener as ht_db_l
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
                     api_res.ExternalSubnet: models.ExternalSubnet, }

    def __init__(self):
        # TODO(amitbose): initialize anything we need, for example DB stuff
        self._resource_map = {}
        for k, v in self._db_model_map.iteritems():
            self._resource_map[v] = k
        self._update_listeners = []
        self._hashtree_db_listener = ht_db_l.HashTreeDbListener(self)

    def create(self, context, resource, overwrite=False):
        """Persist AIM resource to the database.

        If 'overwrite' is True, and an object exists in the database
        with the same identity attribute values, then that object will
        be over-written with the specified resource. Otherwise an
        integrity constraint violation is raised.
        """
        self._validate_resource_class(resource)
        with context.db_session.begin(subtransactions=True):
            db_obj = None
            if overwrite:
                db_obj = self._query_db_obj(context.db_session, resource)
                if db_obj:
                    if (getattr(db_obj, 'monitored', None) !=
                            getattr(resource, 'monitored', None)):
                        raise exc.InvalidMonitoredStateUpdate(
                            object=resource)
                    attr_val = self._extract_attributes(resource, "other")
                    db_obj.from_attr(context.db_session, attr_val)
            db_obj = db_obj or self._make_db_obj(context.db_session, resource)
            context.db_session.add(db_obj)
            self._add_commit_hook(context.db_session)
            return self.get(context, resource)

    def update(self, context, resource, **update_attr_val):
        """Persist updates to AIM resource to the database.

        Values of identity attributes of parameter 'resource' are used
        to determine the database object to update; no other attributes
        from 'resource' are used during the update. Param 'update_attr_val'
        specifies the values of the attributes to update.
        If the object does not exist in the database, no changes are
        made to the database.
        """
        self._validate_resource_class(resource)
        if not update_attr_val:
            return self.get(context, resource)
        with context.db_session.begin(subtransactions=True):
            db_obj = self._query_db_obj(context.db_session, resource)
            if db_obj:
                if 'monitored' in update_attr_val:
                    # TODO(ivar) Accept monitored state change.
                    # To implement this, we need to realize what changed
                    # in the before_flush hooks.
                    raise exc.InvalidMonitoredStateUpdate(object=resource)
                attr_val = {k: v for k, v in update_attr_val.iteritems()
                            if k in resource.other_attributes}
                db_obj.from_attr(context.db_session, attr_val)
                context.db_session.add(db_obj)
                self._add_commit_hook(context.db_session)
                return self.get(context, resource)

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
                if res_type and res_id:
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
