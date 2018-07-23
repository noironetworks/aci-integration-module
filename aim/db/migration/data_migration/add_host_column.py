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
from sqlalchemy import update


HostLink = sa.Table(
    'aim_host_links', sa.MetaData(),
    sa.Column('host_name', sa.String(128), primary_key=True),
    sa.Column('interface_name', sa.String(32), primary_key=True),
    sa.Column('interface_mac', sa.String(24)),
    sa.Column('switch_id', sa.String(128)),
    sa.Column('module', sa.String(128)),
    sa.Column('port', sa.String(128)),
    sa.Column('path', VARCHAR(512, charset='latin1')),
    sa.Column('pod_id', sa.String(128)),
    sa.Column('from_config', sa.Boolean, default=False)
)


EndpointGroupStaticPath = sa.Table(
    'aim_endpoint_group_static_paths', sa.MetaData(),
    sa.Column('path', VARCHAR(512, charset='latin1'), primary_key=True),
    sa.Column('host', sa.String(1024), nullable=True, index=True),
    sa.Column('encap', sa.String(24))
)


ConcreteDeviceInterface = sa.Table(
    'aim_concrete_device_ifs', sa.MetaData(),
    sa.Column('path', sa.String(512)),
    sa.Column('host', sa.String(1024), nullable=True, index=True),
    sa.Column('device_cluster_name', sa.String(64), nullable=False),
    sa.Column('device_name', sa.String(64), nullable=False),
    sa.Column('name', sa.String(64), nullable=False),
    sa.Column('tenant_name', sa.String(64), nullable=False),
    sa.Column('display_name', sa.String(64), nullable=False),
    sa.Column('aim_id', sa.Integer, primary_key=True, autoincrement=True),
    sa.Column('monitored', sa.Boolean, default=False)
)

DeviceClusterDevice = sa.Table(
    'aim_device_cluster_devices', sa.MetaData(),
    sa.Column('name', sa.String(64), nullable=False),
    sa.Column('path', VARCHAR(512, charset='latin1'), primary_key=True),
    sa.Column('host', sa.String(1024), nullable=True, index=True),
)

L3OutInterface = sa.Table(
    'aim_l3out_interfaces', sa.MetaData(),
    sa.Column('interface_path', VARCHAR(512, charset='latin1'),
              nullable=False),
    sa.Column('host', sa.String(1024), nullable=True, index=True),
    sa.Column('l3out_name', sa.String(64), nullable=False),
    sa.Column('node_profile_name', sa.String(64), nullable=False),
    sa.Column('interface_profile_name', sa.String(64), nullable=False),
    sa.Column('tenant_name', sa.String(64), nullable=False),
    sa.Column('primary_addr_a', sa.String(64), nullable=False),
    sa.Column('primary_addr_b', sa.String(64), nullable=False),
    sa.Column('aim_id', sa.Integer, primary_key=True, autoincrement=True),
    sa.Column('monitored', sa.Boolean, default=False)
)


Status = sa.Table(
    'aim_statuses', sa.MetaData(),
    sa.Column('resource_type', sa.String(255), nullable=False),
    sa.Column('resource_id', sa.Integer, nullable=False),
    sa.Column('resource_root', sa.String(255), nullable=False),
    sa.Column('sync_status', sa.String(50), nullable=True),
    sa.Column('sync_message', sa.TEXT, default=''),
    sa.Column('health_score', sa.Integer, nullable=False),
    sa.Column('id', sa.String(255), primary_key=True),

)


def migrate(session):
    with session.begin(subtransactions=True):
        host_links = session.query(HostLink).all()
        for hlink in host_links:
            session.execute(update(EndpointGroupStaticPath).where(
                EndpointGroupStaticPath.c.path == hlink.path).values(
                host=hlink.host_name))
            session.execute(update(ConcreteDeviceInterface).where(
                ConcreteDeviceInterface.c.path == hlink.path).values(
                host=hlink.host_name))
            session.execute(update(DeviceClusterDevice).where(
                DeviceClusterDevice.c.path == hlink.path).values(
                host=hlink.host_name))
            session.execute(update(L3OutInterface).where(
                L3OutInterface.c.interface_path == hlink.path).values(
                host=hlink.host_name))
