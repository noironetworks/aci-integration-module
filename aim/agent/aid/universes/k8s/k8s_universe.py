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

from aim.agent.aid.universes import base_universe as base


LOG = logging.getLogger(__name__)
serving_tenants = {}


class K8sUniverse(base.HashTreeStoredUniverse):
    """HashTree Universe of the ACI state.

    This Hash Tree based observer retrieves and stores state information
    from the Kubernetes REST API.
    """

    def initialize(self, store, conf_mgr):
        super(K8sUniverse, self).initialize(store, conf_mgr)
        return self

    @property
    def name(self):
        return "K8S_Config_Universe"

    @property
    def serving_tenants(self):
        global serving_tenants
        return serving_tenants

    def serve(self, tenants):
        # Verify differences
        global serving_tenants
        pass

    def observe(self):
        pass

    def push_resources(self, resources):
        pass

    def get_resources(self, resource_keys):
        pass

    def get_resources_for_delete(self, resource_keys):
        pass
