# Copyright (c) 2018 Cisco Systems
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
from sqlalchemy.dialects.mysql import VARCHAR

from aim.common import utils

StaticPath = sa.Table(
    'aim_static_path', sa.MetaData(),
    sa.Column('aim_id', sa.String(64), primary_key=True),
    sa.Column('tenant_name', sa.String(128)),
    sa.Column('path', sa.String(255)),
    sa.Column('host', sa.String(128)),
    sa.Column('mode', sa.Enum('regular', 'native', 'untagged')),
    sa.Column('encap', sa.String(64)),
    sa.Column('monitored', sa.Boolean, default=False),
    sa.Column('name', sa.String(64)),
)

EndpointGroupStaticPath = sa.Table(
    'aim_endpoint_group_static_paths', sa.MetaData(),
    sa.Column('epg_aim_id', sa.Integer, primary_key=True),
    sa.Column('path', VARCHAR(512, charset='latin1'), primary_key=True),
    sa.Column('host', sa.String(1024), nullable=True, index=True),
    sa.Column('encap', sa.String(24)),
    sa.Column('mode', sa.Enum('regular', 'native', 'untagged'))
)

EndpointGroup = sa.Table(
    'aim_endpoint_groups', sa.MetaData(),
    sa.Column('aim_id', sa.String(64)),
    sa.Column('tenant_name', sa.String(128)),
    sa.Column('name', sa.String(64)),
)


def migrate(session):
    with session.begin(subtransactions=True):
        static_paths = []
        for ep in session.query(EndpointGroup).all():
            ensp = session.query(EndpointGroupStaticPath).filter(
                EndpointGroupStaticPath.c.epg_aim_id == ep.aim_id).all()
            for sp in ensp:
                static_paths.append({
                    'aim_id': utils.generate_uuid(),
                    'tenant_name': ep.tenant_name,
                    'path': sp.path,
                    'host': sp.host,
                    'mode': sp.mode,
                    'name': ep.name
                })
        for sp in static_paths:
            session.execute(
                StaticPath.insert().values(sp))
