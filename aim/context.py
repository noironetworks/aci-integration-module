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

from aim import aim_store


class AimContext(object):
    """Holds contextual information needed for AimManager calls."""

    def __init__(self, db_session=None, store=None):
        if db_session:
            self.store = aim_store.SqlAlchemyStore(db_session)
        else:
            self.store = store

    # For backwards compatibility
    @property
    def db_session(self):
        try:
            return self.store.db_session
        except AttributeError:
            return None
