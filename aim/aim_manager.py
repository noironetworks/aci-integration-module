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

from aim.api import resource as api_res
from aim.db import models
from aim import exceptions as exc


class AimContext(object):
    """Holds contextual information needed for AimManager calls."""

    def __init__(self, db_session=None):
        self.db_session = db_session


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

    _db_model_map = {api_res.BridgeDomain: models.BridgeDomain}

    def __init__(self):
        # TODO(amitbose): initialize anything we need, for example DB stuff
        pass

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
                    attr_val = self._extract_attributes(resource, "other")
                    db_obj.from_attr(attr_val)
            db_obj = db_obj or self._make_db_obj(resource)
            context.db_session.add(db_obj)

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
            return
        with context.db_session.begin(subtransactions=True):
            db_obj = self._query_db_obj(context.db_session, resource)
            if db_obj:
                attr_val = {k: v for k, v in update_attr_val.iteritems()
                            if k in resource.other_attributes}
                db_obj.from_attr(attr_val)
                context.db_session.add(db_obj)

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
                context.db_session.delete(db_obj)

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
        return db_obj and self._make_resource(type(resource), db_obj) or None

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
                             resource_class.identity_attributes)}
        result = []
        for obj in self._query_db(context.db_session,
                                  resource_class, **attr_val).all():
            result.append(self._make_resource(resource_class, obj))
        return result

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
        return val

    def _make_db_obj(self, resource):
        cls = self._db_model_map.get(type(resource))
        obj = cls()
        obj.from_attr(self._extract_attributes(resource))
        return obj

    def _make_resource(self, cls, db_obj):
        attr_val = {k: v for k, v in db_obj.to_attr().iteritems()
                    if k in (cls.other_attributes + cls.identity_attributes)}
        return cls(**attr_val)
