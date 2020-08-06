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

Revision ID: 26630ed17b50
Revises: 4caed435b0cd
Create date: 2020-07-28 13:05:03.236000000

"""

# revision identifiers, used by Alembic.
revision = '26630ed17b50'
down_revision = '4caed435b0cd'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import VARCHAR


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
        sa.Index('idx_aim_span_vsource_identity', 'vsg_name', 'name'),
        sa.ForeignKeyConstraint(
            ['vsg_name'], ['aim_span_vsource_grp.name'], name='fk_vsg'))

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
        sa.Index('idx_aim_span_vdest_identity', 'vdg_name', 'name'),
        sa.ForeignKeyConstraint(
            ['vdg_name'], ['aim_span_vdest_grp.name'], name='fk_vdg'))

    op.create_table(
        'aim_span_vepg_summary',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('vdg_name', sa.String(64), nullable=False),
        sa.Column('vd_name', sa.String(64), nullable=False),
        sa.Column('dst_ip', sa.String(64), nullable=False),
        sa.Column('flow_id', sa.Integer),
        sa.Column('ttl', sa.Integer),
        sa.Column('mtu', sa.Integer),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('vdg_name', 'vd_name',
                            name='uniq_aim_span_vepg_summary_identity'),
        sa.Index('idx_aim_span_vepg_summary_identity', 'vdg_name',
                 'vd_name'),
        sa.ForeignKeyConstraint(
            ['vdg_name', 'vd_name'],
            ['aim_span_vdest.vdg_name', 'aim_span_vdest.name'],
            name='fk_vepg_sum'))

    op.create_table(
        'aim_span_src_vport',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('vsg_name', sa.String(64), nullable=False),
        sa.Column('vs_name', sa.String(64), nullable=False),
        sa.Column('src_path', VARCHAR(512, charset='latin1'), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('vsg_name', 'vs_name', 'src_path',
                            name='uniq_aim_span_src_vport_identity'),
        sa.Index('idx_aim_span_src_vport_identity', 'vsg_name',
                 'vs_name', 'src_path'),
        sa.ForeignKeyConstraint(
            ['vsg_name', 'vs_name'],
            ['aim_span_vsource.vsg_name', 'aim_span_vsource.name'],
            name='fk_vport_sum'))

    op.create_table(
        'aim_infra_acc_bundle_grp',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
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
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('acc_bndle_grp_name', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('acc_bndle_grp_name', 'name',
                            name='uniq_aim_infra_rspan_vsrc_grp_identity'),
        sa.Index('idx_aim_infra_rspan_vsrc_grp_identity',
                 'acc_bndle_grp_name', 'name'),
        sa.ForeignKeyConstraint(
            ['acc_bndle_grp_name'], ['aim_infra_acc_bundle_grp.name'],
            name='fk_rspan'))

    op.create_table(
        'aim_infra_rspan_vsrc_ap_grp',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('acc_port_grp_name', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('acc_port_grp_name', 'name',
                            name='uniq_aim_infra_rspan_vsrc_ap_grp_identity'),
        sa.Index('idx_aim_infra_rspan_vsrc_ap_grp_identity',
                 'acc_port_grp_name', 'name'),
        sa.ForeignKeyConstraint(
            ['acc_port_grp_name'], ['aim_infra_acc_port_grp.name'],
            name='fk_rspan_ap'))

    op.create_table(
        'aim_span_spanlbl',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('vsg_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('vsg_name', 'name',
                            name='uniq_aim_span_spanlbl_identity'),
        sa.Index('idx_aim_span_spanlbl_identity', 'vsg_name', 'name'),
        sa.ForeignKeyConstraint(
            ['vsg_name'], ['aim_span_vsource_grp.name'], name='fk_slbl'))

    op.create_table(
        'aim_infra_rspan_vdest_grp',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('acc_bndle_grp_name', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('acc_bndle_grp_name', 'name',
                            name='uniq_aim_infra_rspan_vdest_grp_identity'),
        sa.Index('idx_aim_infra_rspan_vdest_grp_identity',
                 'acc_bndle_grp_name', 'name'),
        sa.ForeignKeyConstraint(
            ['acc_bndle_grp_name'], ['aim_infra_acc_bundle_grp.name'],
            name='fk_rdest'))

    op.create_table(
        'aim_infra_rspan_vdest_ap_grp',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('acc_port_grp_name', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('acc_port_grp_name', 'name',
                            name='uniq_aim_infra_rspan_vdest_ap_grp_identity'),
        sa.Index('idx_aim_infra_rspan_vdest_ap_grp_identity',
                 'acc_port_grp_name', 'name'),
        sa.ForeignKeyConstraint(
            ['acc_port_grp_name'], ['aim_infra_acc_port_grp.name'],
            name='fk_rdest_ap'))


def downgrade():
    pass
