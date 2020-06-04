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

from aim.api import resource as api_res
from aim.api import types as t
from aim.common import utils


class Tree(api_res.ResourceBase):
    identity_attributes = t.identity(
        ('root_rn', t.string(64))
    )
    other_attributes = t.other(
        ('needs_reset', t.bool)
    )
    db_attributes = t.db()

    def __init__(self, **kwargs):
        super(Tree, self).__init__({}, **kwargs)


class TypeTreeBase(object):
    identity_attributes = t.identity(
        ('root_rn', t.string(64))
    )
    other_attributes = t.other(
        ('root_full_hash', t.string(256)),
        ('tree', t.string())
    )
    db_attributes = t.db()

    def __init__(self, **kwargs):
        super(TypeTreeBase, self).__init__({}, **kwargs)


class ConfigTree(TypeTreeBase, api_res.ResourceBase):
    pass


class OperationalTree(TypeTreeBase, api_res.ResourceBase):
    pass


class MonitoredTree(TypeTreeBase, api_res.ResourceBase):
    pass


class ActionLog(api_res.ResourceBase):
    CREATE = 'create'
    DELETE = 'delete'
    RESET = 'reset'
    SKIP = 'skip'

    identity_attributes = t.identity(
        ('uuid', t.string(64))
    )
    other_attributes = t.other(
        ('action', t.enum(CREATE, DELETE, RESET)),
        ('object_type', t.string(50)),
        ('object_dict', t.string()),
        ('root_rn', t.string(64)),
    )
    db_attributes = t.db(
        ('timestamp', t.string()),
        ('id', t.integer)
    )

    def __init__(self, **kwargs):
        super(ActionLog, self).__init__({'uuid': utils.generate_uuid()},
                                        **kwargs)
