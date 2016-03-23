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


class BridgeDomain(model_base.Base, model_base.HasRn,
                   model_base.AttributeMixin):
    """DB model for BridgeDomain."""

    __tablename__ = 'aim_bridge_domains'

    tenant_rn = sa.Column(sa.String(64), primary_key=True)
    vrf_rn = sa.Column(sa.String(64))
    enable_arp_flood = sa.Column(sa.Boolean)
    enable_routing = sa.Column(sa.Boolean)
    limit_ip_learn_to_subnets = sa.Column(sa.Boolean)
    l2_unknown_unicast_mode = sa.Column(sa.String(16))
    ep_move_detect_mode = sa.Column(sa.String(16))
