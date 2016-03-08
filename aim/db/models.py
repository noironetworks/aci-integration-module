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

import sqlalchemy as sa

from aim.db import model_base


class AttributeMixin(object):
    """Mixin class for translating between resource and model."""

    def from_attr(self, resource_attr):
        """Populate model from resource attribute dictionary.

        Child classes should override this method to specify a custom
        mapping of resource attributes to model properties.
        """
        for k, v in resource_attr.iteritems():
            setattr(self, k, v)

    def to_attr(self):
        """Get resource attribute dictionary for a model object.

        Child classes should override this method to specify a custom
        mapping of model properties to resource attributes.
        """
        return {k: getattr(self, k) for k in self.__dict__.keys()}


class BridgeDomain(model_base.Base,
                   AttributeMixin):
    """DB model for BridgeDomain."""

    __tablename__ = 'aim_bridge_domain'

    tenant_rn = sa.Column(sa.String(64), primary_key=True)
    vrf_tenant_rn = sa.Column(sa.String(64))
    vrf_rn = sa.Column(sa.String(64))
    enable_arp_flood = sa.Column(sa.Boolean)
    enable_routing = sa.Column(sa.Boolean)
    limit_ip_learn_to_subnet = sa.Column(sa.Boolean)
    l2_unknown_unicast_mode = sa.Column(sa.String(16))
    ep_move_detect_mode = sa.Column(sa.String(16))
