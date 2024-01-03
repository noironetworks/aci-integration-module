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

"""Tables for external network contracts
Revision ID: 7b8a71bee019
Revises: 5b00b6d805e9
Create date: 2022-04-12 13:05:03.236000000
"""

# revision identifiers, used by Alembic.
revision = '7b8a71bee019'
down_revision = '5b00b6d805e9'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

from aim.db.migration.data_migration import contracts_to_resources


def upgrade():
    # Create the two new tables
    op.create_table(
        'aim_external_network_provided_contracts',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('ext_net_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.UniqueConstraint('tenant_name', 'l3out_name', 'ext_net_name',
                            'name', name='uniq_aim_ext_net_pcon_identity'),
        sa.Index('idx_aim_ext_net_pcon_identity',
                 'tenant_name', 'l3out_name', 'ext_net_name', 'name'),
        sa.PrimaryKeyConstraint('aim_id'))

    op.create_table(
        'aim_external_network_consumed_contracts',
        sa.Column('aim_id', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('l3out_name', sa.String(64), nullable=False),
        sa.Column('ext_net_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('epoch', sa.BigInteger(), nullable=False,
                  server_default='0'),
        sa.UniqueConstraint('tenant_name', 'l3out_name', 'ext_net_name',
                            'name', name='uniq_aim_ext_net_ccon_identity'),
        sa.Index('idx_aim_ext_net_ccon_identity',
                 'tenant_name', 'l3out_name', 'ext_net_name', 'name'),
        sa.PrimaryKeyConstraint('aim_id'))

    # Migrate the data to the new tables
    session = sa.orm.Session(bind=op.get_bind())

    contracts_to_resources.migrate(session)

    # REmove the old table
    op.drop_table('aim_external_network_contracts')


def downgrade():
    pass
