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

from aim.agent.aid.universes import base_universe as base


class AimDbUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the AIM DB state.

    This Hash Tree bases observer retrieves and stores state information
    from the AIM database.
    """

    def serve(self, tenants):
        pass

    def get_aim_resources(self, resource_keys):
        pass

    def push_aim_resources(self, resources):
        pass

    def push_aim_resource(self, resource):
        pass

    def get_aim_resource(self, resource_key):
        pass

    def state(self):
        pass

    def observe(self):
        pass

    def initialize(self, db_handler):
        pass
