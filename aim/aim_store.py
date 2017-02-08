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
from sqlalchemy import event as sa_event


class AimStore(object):
    """Interface to backend persistence for AIM resources."""

    def begin(self, **kwargs):
        # Begin transaction of updates, if applicable.
        # Should return a contextmanager object

        # default returns a no-op contextmanager
        return contextmanager(lambda: (yield))

    def resource_to_db_type(self, resource_type):
        # Returns the DB object type for an AIM resource type
        return resource_type

    def add(self, db_obj):
        # Save (create/update) object to backend
        pass

    def delete(self, db_obj):
        # Delete object from backend if it exists
        pass

    def query(self, db_obj_type, **filters):
        # Return list of objects that match specified criteria
        pass

    def add_commit_hook(self, callback_func):
        pass

    def from_attr(self, db_obj, resource_type, attribute_dict):
        # Update DB object from attribute dictionary
        pass

    def to_attr(self, resource_type, db_obj):
        # Construct attribute dictionary from DB object
        pass


class SqlAlchemyStore(AimStore):

    # Dict mapping AIM resources to DB model objects
    db_model_map = {}

    def __init__(self, db_session):
        self.db_session = db_session

    def begin(self, **kwargs):
        return self.db_session.begin(subtransactions=True)

    def resource_to_db_type(self, resource_type):
        return self.db_model_map.get(resource_type)

    def add(self, db_obj):
        self.db_session.add(db_obj)

    def delete(self, db_obj):
        self.db_session.delete(db_obj)

    def query(self, db_obj_type, **filters):
        return self.db_session.query(db_obj_type).filter_by(**filters).all()

    def add_commit_hook(self, callback_func):
        if not sa_event.contains(self.db_session, 'before_flush',
                                 callback_func):
            sa_event.listen(self.db_session, 'before_flush', callback_func)

    def from_attr(self, db_obj, resource_type, attribute_dict):
        db_obj.from_attr(self.db_session, attribute_dict)

    def to_attr(self, resource_type, db_obj):
        return db_obj.to_attr(self.db_session)


class KeyValueStore(AimStore):

    def __init__(self, **kwargs):
        pass
