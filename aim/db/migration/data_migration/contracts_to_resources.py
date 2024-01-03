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

from aim.common import utils

ExternalNetworkProvidedContracts = sa.Table(
    'aim_external_network_provided_contracts', sa.MetaData(),
    sa.Column('aim_id', sa.String(64)),
    sa.Column('tenant_name', sa.String(128)),
    sa.Column('l3out_name', sa.String(64)),
    sa.Column('ext_net_name', sa.String(64)),
    sa.Column('monitored', sa.Boolean, default=False),
    sa.Column('name', sa.String(64))
)

ExternalNetworkConsumedContracts = sa.Table(
    'aim_external_network_consumed_contracts', sa.MetaData(),
    sa.Column('aim_id', sa.String(64)),
    sa.Column('tenant_name', sa.String(128)),
    sa.Column('l3out_name', sa.String(64)),
    sa.Column('ext_net_name', sa.String(64)),
    sa.Column('monitored', sa.Boolean, default=False),
    sa.Column('name', sa.String(64))
)

ExternalNetworkContracts = sa.Table(
    'aim_external_network_contracts', sa.MetaData(),
    sa.Column('ext_net_aim_id', sa.Integer()),
    sa.Column('name', sa.String(128)),
    sa.Column('provides', sa.Boolean())
)

ExternalNetwork = sa.Table(
    'aim_external_networks', sa.MetaData(),
    sa.Column('aim_id', sa.String(255), default=utils.generate_uuid),
    sa.Column('tenant_name', sa.String(128)),
    sa.Column('l3out_name', sa.String(64)),
    sa.Column('name', sa.String(64)),
)


def migrate(session):
    provides = []
    consumes = []
    ext_net_dict = {}
    for enc in session.query(ExternalNetworkContracts).all():
        if not ext_net_dict.get(enc.ext_net_aim_id):
            en = session.query(ExternalNetwork).filter(
                ExternalNetwork.c.aim_id == enc.ext_net_aim_id).one()
            ext_net_dict[enc.ext_net_aim_id] = en
        else:
            en = ext_net_dict[enc.ext_net_aim_id]
        if enc.provides:
            provides.append({'aim_id': utils.generate_uuid(),
                             'tenant_name': en.tenant_name,
                             'l3out_name': en.l3out_name,
                             'ext_net_name': en.name,
                             'name': enc.name})
        else:
            consumes.append({'aim_id': utils.generate_uuid(),
                             'tenant_name': en.tenant_name,
                             'l3out_name': en.l3out_name,
                             'ext_net_name': en.name,
                             'name': enc.name})
    session.execute(ExternalNetworkContracts.delete())
    if provides:
        for provided in provides:
            session.execute(
                ExternalNetworkProvidedContracts.insert().values(provided))
    if consumes:
        for consumed in consumes:
            session.execute(
                ExternalNetworkConsumedContracts.insert().values(consumed))
