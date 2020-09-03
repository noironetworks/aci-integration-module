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

"""Tables for erspan
Revision ID: fccf2c4f6282
Revises: 794ad00f3080
Create date: 2020-08-17 13:05:03.236000000
"""

# revision identifiers, used by Alembic.
revision = 'fccf2c4f6282'
down_revision = '794ad00f3080'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_span_vsource_grp',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('admin_st', sa.Enum('start', 'stop')),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('name',
                            name='uniq_aim_span_vsource_grp_identity'),
        sa.Index('idx_aim_span_vsource_grp_identity', 'name'))

    op.create_table(
        'aim_span_vsource',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('vsg_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('dir', sa.Enum('in', 'out', 'both')),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('vsg_name', 'name',
                            name='uniq_aim_span_vsource_identity'),
        sa.Index('idx_aim_span_vsource_identity', 'vsg_name', 'name'))

    op.create_table(
        'aim_span_src_paths',
        sa.Column('vsrc_aim_id', sa.String(64), nullable=False),
        sa.Column('path', sa.String(255), nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('vsrc_aim_id', 'path'),
        sa.ForeignKeyConstraint(
            ['vsrc_aim_id'], ['aim_span_vsource.aim_id']))

    op.create_table(
        'aim_span_vdest_grp',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('name',
                            name='uniq_aim_span_vdest_grp_identity'),
        sa.Index('idx_aim_span_vdest_grp_identity', 'name'))

    op.create_table(
        'aim_span_vdest',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('vdg_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('vdg_name', 'name',
                            name='uniq_aim_span_vdest_identity'),
        sa.Index('idx_aim_span_vdest_identity', 'vdg_name', 'name'))

    op.create_table(
        'aim_span_vepg_summary',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('vdg_name', sa.String(64), nullable=False),
        sa.Column('vd_name', sa.String(64), nullable=False),
        sa.Column('dst_ip', sa.String(64), nullable=False),
        sa.Column('flow_id', sa.Integer),
        sa.Column('ttl', sa.Integer),
        sa.Column('mtu', sa.Integer),
        sa.Column('invalid', sa.Boolean),
        sa.Column('mode', sa.Enum('visible', 'not-visible')),
        sa.Column('route_ip', sa.String(64)),
        sa.Column('scope', sa.Enum('public', 'private', 'shared')),
        sa.Column('src_ip_prefix', sa.String(64)),
        sa.Column('ver', sa.Enum('ver1', 'ver2')),
        sa.Column('ver_enforced', sa.Boolean),
        sa.Column('dscp', sa.Integer),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('vdg_name', 'vd_name',
                            name='uniq_aim_span_vepg_summary_identity'),
        sa.Index('idx_aim_span_vepg_summary_identity', 'vdg_name',
                 'vd_name'))

    op.create_table(
        'aim_infra_acc_bundle_grp',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('lag_t', sa.Enum('link', 'node')),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('name',
                            name='uniq_aim_infra_acc_bundle_grp_identity'),
        sa.Index('idx_aim_infra_acc_bundle_grp_identity', 'name'))

    op.create_table(
        'aim_infra_acc_port_grp',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('name',
                            name='uniq_aim_infra_acc_port_grp_identity'),
        sa.Index('idx_aim_infra_acc_port_grp_identity', 'name'))

    op.create_table(
        'aim_infra_rspan_vsrc_grp',
        sa.Column('accgrp_aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('accgrp_aim_id', 'name'),
        sa.ForeignKeyConstraint(
            ['accgrp_aim_id'], ['aim_infra_acc_bundle_grp.aim_id']))

    op.create_table(
        'aim_infra_rspan_vsrc_ap_grp',
        sa.Column('accport_aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('accport_aim_id', 'name'),
        sa.ForeignKeyConstraint(
            ['accport_aim_id'], ['aim_infra_acc_port_grp.aim_id']))

    op.create_table(
        'aim_span_spanlbl',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('vsg_aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('vsg_name', sa.String(64), nullable=False),
        sa.Column('tag', sa.String(64)),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('vsg_name', 'name',
                            name='uniq_aim_span_spanlbl_identity'),
        sa.Index('idx_aim_span_spanlbl_identity', 'vsg_name', 'name'))

    op.create_table(
        'aim_infra_rspan_vdest_grp',
        sa.Column('accgrp_aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('accgrp_aim_id', 'name'),
        sa.ForeignKeyConstraint(
            ['accgrp_aim_id'], ['aim_infra_acc_bundle_grp.aim_id']))

    op.create_table(
        'aim_infra_rspan_vdest_ap_grp',
        sa.Column('accport_aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('accport_aim_id', 'name'),
        sa.ForeignKeyConstraint(
            ['accport_aim_id'], ['aim_infra_acc_port_grp.aim_id']))


def downgrade():
    pass
