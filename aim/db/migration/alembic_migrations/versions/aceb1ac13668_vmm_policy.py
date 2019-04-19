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

"""Create tables for VMM Policies.

Revision ID: aceb1ac13668
Revises: 7838968744ce

Create Date: 2016-08-11 17:59:18.910872

"""

# revision identifiers, used by Alembic.
revision = 'aceb1ac13668'
down_revision = '7838968744ce'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

from aim import aim_manager
from aim.api import resource
from aim import context
from aim.db import api


def upgrade():

    op.create_table(
        'aim_vmm_policies',
        sa.Column('type', sa.String(64), nullable=False),
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'))

    session = api.get_session(expire_on_commit=True)
    old_vmm_table = sa.Table('aim_vmm_domains', sa.MetaData(),
                             sa.Column('type', sa.String(64), nullable=False),
                             sa.Column('name', sa.String(64), nullable=False))
    old_phys_table = sa.Table('aim_physical_domains', sa.MetaData(),
                              sa.Column('name', sa.String(64), nullable=False))

    mgr = aim_manager.AimManager()
    ctx = context.AimContext(db_session=session)
    new_vmms = []
    new_phys = []
    with session.begin(subtransactions=True):
        for vmm in session.query(old_vmm_table).all():
            new_vmms.append(resource.VMMDomain(type=vmm.type, name=vmm.name,
                                               monitored=True))
        for phys in session.query(old_phys_table).all():
            new_phys.append(resource.PhysicalDomain(name=phys.name,
                                                    monitored=True))

    op.drop_table('aim_vmm_domains')
    op.drop_table('aim_physical_domains')

    op.create_table(
        'aim_vmm_domains',
        sa.Column('type', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('enforcement_pref', sa.Enum('sw', 'hw', 'unknown')),
        sa.Column('mode', sa.Enum('default', 'n1kv', 'unknown', 'ovs',
                                  'k8s')),
        sa.Column('mcast_address', sa.String(64)),
        sa.Column('encap_mode', sa.Enum('unknown', 'vlan', 'vxlan')),
        sa.Column('pref_encap_mode', sa.Enum('unspecified', 'vlan',
                                             'vxlan')),
        sa.Column('vlan_pool_name', sa.String(64)),
        sa.Column('vlan_pool_type', sa.Enum('static', 'dynamic')),
        sa.Column('mcast_addr_pool_name', sa.String(64)),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('type', 'name',
                            name='uniq_aim_vmm_domains_identity'),
        sa.Index('idx_aim_vmm_domains_identity', 'type', 'name'))

    op.create_table(
        'aim_physical_domains',
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'))

    with session.begin(subtransactions=True):
        for obj in new_vmms + new_phys:
            mgr.create(ctx, obj)


def downgrade():
    pass
