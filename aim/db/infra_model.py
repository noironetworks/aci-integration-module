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


class HostLink(model_base.Base, model_base.AttributeMixin):
    __tablename__ = 'aim_host_links'

    host_name = sa.Column(sa.String(256), primary_key=True)
    interface_name = sa.Column(sa.String(64), primary_key=True)
    interface_mac = sa.Column(sa.String(24))

    switch_id = sa.Column(sa.String(128))
    module = sa.Column(sa.String(128))
    port = sa.Column(sa.String(128))
    path = sa.Column(sa.String(1024))
