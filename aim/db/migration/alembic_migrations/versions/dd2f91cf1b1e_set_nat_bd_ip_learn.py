# Copyright (c) 2017 Cisco Systems
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

"""Fix default value for BD's Limit IP Learning to subnets

Revision ID: dd2f91cf1b1e
Revises: 5e29ae4f45e6
Create Date: 2017-11-06 16:39:33.713695

"""

# revision identifiers, used by Alembic.
revision = 'dd2f91cf1b1e'
down_revision = '5e29ae4f45e6'
branch_labels = None
depends_on = None
testing = True

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.expression import update

AIM_BRIDGE_DOMAINS = 'aim_bridge_domains'
AIM_BRIDGE_DOMAINS_L3OUTS = 'aim_bridge_domain_l3outs'

# A model of the BridgeDomainL3Out table with the fields we're interested
bd_l3outs = sa.Table(AIM_BRIDGE_DOMAINS_L3OUTS, sa.MetaData(),
                     sa.Column('bd_aim_id',
                               sa.Integer,
                               sa.ForeignKey('aim_bridge_domains.aim_id'),
                               primary_key=True),
                     sa.Column('name', sa.String(64)))

# A model of the BridgeDomain table with the fields we're interested
bridge_domains = sa.Table(AIM_BRIDGE_DOMAINS, sa.MetaData(),
                          sa.Column('name', sa.String(64)),
                          sa.Column('tenant_name', sa.String(64)),
                          sa.Column('display_name', sa.String(64)),
                          sa.Column('monitored', sa.Boolean,
                                    nullable=False, default=False),
                          sa.Column('aim_id',
                                    sa.Integer,
                                    primary_key=True, autoincrement=True),
                          sa.Column('limit_ip_learn_to_subnets',
                                    sa.Boolean))


def upgrade():
    session = sa.orm.Session(bind=op.get_bind())
    my_bd_l3outs = get_bd_l3out_values(session)
    for bd_l3out in my_bd_l3outs:
        bd_update = update(bridge_domains).values(
            {'limit_ip_learn_to_subnets': True}).where(
                bridge_domains.c.aim_id == bd_l3out['bd_aim_id'])
        session.execute(bd_update)


def get_bd_l3out_values(session):
    values = []
    for row in session.query(bd_l3outs).all():
        bd_id, name = row
        values.append({'bd_aim_id': bd_id})
    # this commit appears to be necessary to allow further operations
    session.commit()
    return values


def downgrade():
    pass
