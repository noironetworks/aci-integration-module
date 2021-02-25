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


"""

Revision ID: 185efc4806b2
Revises: 2f05b6baf008
Create Date: 2021-02-23 12:04:35.098964

"""

# revision identifiers, used by Alembic.
revision = '185efc4806b2'
down_revision = '2f05b6baf008'
branch_labels = None
depends_on = None

from aim.common import utils
from aim.db.migration.data_migration import contract_subject_filter
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_contract_subject_filter_relation',
        sa.Column('aim_id', sa.String(255), default=utils.generate_uuid),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('filter_name', sa.String(64), nullable=False),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('contract_subject_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('action', sa.Enum('permit', 'deny'), default='permit'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name',
                            'contract_subject_name',
                            'filter_name',
                            name='uniq_aim_contract_subject_filter_identity'),
        sa.Index('idx_aim_contract_subject_filter_identity',
                 'tenant_name', 'contract_name', 'contract_subject_name',
                 'filter_name'))
    op.create_table(
        'aim_contract_subject_in_filter_relation',
        sa.Column('aim_id', sa.String(255), default=utils.generate_uuid),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('filter_name', sa.String(64), nullable=False),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('contract_subject_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('action', sa.Enum('permit', 'deny'), default='permit'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name',
                            'contract_subject_name',
                            'filter_name',
                            name='uniq_aim_contract_subject'
                            '_in_filter_identity'),
        sa.Index('idx_aim_contract_subject_in_filter_identity',
                 'tenant_name', 'contract_name', 'contract_subject_name',
                 'filter_name'))
    op.create_table(
        'aim_contract_subject_out_filter_relation',
        sa.Column('aim_id', sa.String(255), default=utils.generate_uuid),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('filter_name', sa.String(64), nullable=False),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('contract_subject_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('action', sa.Enum('permit', 'deny'), default='permit'),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name',
                            'contract_subject_name',
                            'filter_name',
                            name='uniq_aim_contract_subject'
                            '_out_filter_identity'),
        sa.Index('idx_aim_contract_subject_out_filter_identity',
                 'tenant_name', 'contract_name', 'contract_subject_name',
                 'filter_name'))
    op.create_table(
        'aim_contract_subject_graph_relation',
        sa.Column('aim_id', sa.String(255), default=utils.generate_uuid),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('graph_name', sa.String(64)),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('contract_subject_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name',
                            'contract_subject_name',
                            name='uniq_aim_contract_subject'
                            '_graph_identity'),
        sa.Index('idx_aim_contract_subject_graph_identity',
                 'tenant_name', 'contract_name', 'contract_subject_name'))
    op.create_table(
        'aim_contract_subject_in_graph_relation',
        sa.Column('aim_id', sa.String(255), default=utils.generate_uuid),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('graph_name', sa.String(64)),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('contract_subject_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name',
                            'contract_subject_name',
                            name='uniq_aim_contract_subject'
                            '_in_graph_identity'),
        sa.Index('idx_aim_contract_subject_in_graph_identity',
                 'tenant_name', 'contract_name', 'contract_subject_name'))
    op.create_table(
        'aim_contract_subject_out_graph_relation',
        sa.Column('aim_id', sa.String(255), default=utils.generate_uuid),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.Column('graph_name', sa.String(64)),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('contract_subject_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name',
                            'contract_subject_name',
                            name='uniq_aim_contract_subject'
                            '_out_graph_identity'),
        sa.Index('idx_aim_contract_subject_out_graph_identity',
                 'tenant_name', 'contract_name', 'contract_subject_name'))
    session = sa.orm.Session(bind=op.get_bind(), autocommit=True)
    contract_subject_filter.migrate(session)


def downgrade():
    pass
