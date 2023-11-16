# Copyright (c) 2020 Cisco Systems
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

"""Tables for remote ip container under security groups
Revision ID: a94984a4452b
Revises: 5e285945cf4d
Create date: 2023-09-12 10:19:03.236000000
"""

# revision identifiers, used by Alembic.

from alembic import op
import sqlalchemy as sa

revision = 'a94984a4452b'
down_revision = '5e285945cf4d'
branch_labels = None
depends_on = None


def upgrade():
    # Create the new tables
    op.create_table(
        'aim_sg_remoteip_containers',
        sa.Column('aim_id', sa.String(255), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('security_group_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('name', sa.String(64), default=''),
        sa.PrimaryKeyConstraint('tenant_name', 'security_group_name'))

    op.create_table(
        'aim_sg_container_remote_ips',
        sa.Column('aim_id', sa.String(255), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('security_group_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('addr', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('tenant_name', 'security_group_name', 'addr'))

    op.create_table(
        'aim_sg_remoteipcont_references',
        sa.Column('security_group_rule_aim_id',
                  sa.String(255), nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('tDn', sa.String(256), nullable=False),
        sa.PrimaryKeyConstraint('security_group_rule_aim_id', 'tDn'))

    op.create_table(
        'aim_aci_supported_mos',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('supports', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('name'))

    aim_aci_supported_mos_table = sa.Table(
        'aim_aci_supported_mos', sa.MetaData(),
        sa.Column('supports', sa.Boolean, nullable=False),
        sa.Column('name', sa.String(64), nullable=False, primary_key=True))
    stmt = sa.insert(aim_aci_supported_mos_table).values(name="remoteipcont",
                                                         supports=False)
    dbsession = sa.orm.Session(bind=op.get_bind())
    dbsession.execute(stmt)
    dbsession.commit()


def downgrade():
    pass
