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

from oslo_config import cfg

import sqlalchemy as sa
from sqlalchemy import update

BridgeDomain = sa.Table(
    'aim_bridge_domains', sa.MetaData(),
    sa.Column('aim_id', primary_key=True),
    sa.Column('ep_move_detect_mode', sa.String(16)),
    sa.Column('monitored', sa.Boolean, nullable=False, default=False)
)


def migrate(session):
    with session.begin():
        gen1_hw = cfg.CONF.aim.support_gen1_hw_gratarps
        ep_move = 'garp' if gen1_hw is True else ''
        bds = session.query(BridgeDomain).all()
        for bd in bds:
            if bd.monitored is False and bd.ep_move_detect_mode != ep_move:
                session.execute(update(BridgeDomain).where(
                    BridgeDomain.c.aim_id == bd.aim_id).values(
                    ep_move_detect_mode=ep_move))
