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


StaticPathsV2 = sa.Table(
    'aim_endpoint_group_static_paths_v2', sa.MetaData(),
    sa.Column('aim_id', sa.String(255)),
    sa.Column('tenant_name', sa.String(64)),
    sa.Column('app_profile_name', sa.String(64)),
    sa.Column('epg_name', sa.String(64)),
    sa.Column('path', VARCHAR(512, charset='latin1')),
    sa.Column('host', sa.String(255)),
    sa.Column('mode', sa.Enum('regular', 'native', 'untagged')),
    sa.Column('encap', sa.String(24)),
    sa.Column('monitored', sa.Boolean, default=False)
)

StaticPaths = sa.Table(
    'aim_endpoint_group_static_paths', sa.MetaData(),
    sa.Column('epg_aim_id', sa.String(255)),
    sa.Column('path', VARCHAR(512, charset='latin1')),
    sa.Column('host', sa.String(255)),
    sa.Column('mode', sa.Enum('regular', 'native', 'untagged')),
    sa.Column('encap', sa.String(24))
)

EndPointGroup = sa.Table(
    'aim_endpoint_groups', sa.MetaData(),
    sa.Column('aim_id', sa.String(255)),
    sa.Column('name', sa.String(64)),
    sa.Column('app_profile_name', sa.String(64)),
    sa.Column('tenant_name', sa.String(64)),
    sa.Column('bd_name', sa.String(64)),
    sa.Column('policy_enforcement_pref', sa.String(16)),
    sa.Column('qos_name', sa.String(64)),
    sa.Column('monitored', sa.Boolean)
)


def migrate(session):
    with session.begin(subtransactions=True):
        migrations = []
        for static_path in session.query(StaticPaths).all():
            epg = session.query(EndPointGroup).filter(
                EndPointGroup.c.aim_id == static_path.epg_aim_id).one()
            migrations.append({'aim_id': utils.generate_uuid(),
                               'tenant_name': epg.tenant_name,
                               'app_profile_name': epg.app_profile_name,
                               'epg_name': epg.name,
                               'path': static_path.path,
                               'host': static_path.host,
                               'mode': static_path.mode,
                               'encap': static_path.encap,
                               'monitored': epg.monitored})
        session.execute(StaticPaths.delete())
        if migrations:
            for migration in migrations:
                session.execute(StaticPathsV2.insert().values(migration))
