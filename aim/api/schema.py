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

import collections

from aim import aim_manager
from aim.common import utils

writable_classes = aim_manager.AimManager._db_model_map.keys()
schema_spec = "http://json-schema.org/draft-04/schema#"


def generate_schema():
    definitions = collections.OrderedDict()
    type_enum = []
    top_properties = {"type": {"type": "string", "enum": type_enum}}
    base = collections.OrderedDict(
        [("$schema", schema_spec),
         ("type", "object"),
         ("title", "AciObjectSpec"),
         ("properties", top_properties),
         ("definitions", definitions)])
    for klass in writable_classes:
        required = klass.identity_attributes.keys()
        properties = {}
        for attr in [klass.identity_attributes, klass.other_attributes,
                     klass.db_attributes]:
            for k, v in attr.iteritems():
                properties[k] = v
        title = klass.__name__
        name = utils.camel_to_snake(title)
        definitions[utils.camel_to_snake(title)] = collections.OrderedDict(
            [("type", "object"),
             ("title", title),
             ("properties", properties),
             ("required", required)])
        type_enum.append(name)
        top_properties[name] = {"$ref": "#/definitions/%s" % name}
    return base
