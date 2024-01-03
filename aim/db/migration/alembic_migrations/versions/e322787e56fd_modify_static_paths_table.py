# Copyright (c) 2021 Cisco Systems
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

"""Modify Static Paths Table
Revision ID: e322787e56fd
Revises: cf83ad8832f0
Create date: 2024-02-02 14:22:40.236000000
"""

# revision identifiers, used by Alembic.
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import VARCHAR

from aim.db.migration.data_migration import static_paths_v2

revision = 'e322787e56fd'
down_revision = 'cf83ad8832f0'
branch_labels = None
depends_on = None


def upgrade():
    session = sa.orm.Session(bind=op.get_bind())
    with session.begin():
        op.create_table(
            'aim_endpoint_group_static_paths_v2',
            sa.Column('aim_id', sa.String(255), nullable=False),
            sa.Column('tenant_name', sa.String(64), nullable=False),
            sa.Column('app_profile_name', sa.String(64), nullable=False),
            sa.Column('epg_name', sa.String(64), nullable=False),
            sa.Column('path', VARCHAR(512, charset='latin1'), nullable=False),
            sa.Column('host', sa.String(255), nullable=True, index=True),
            sa.Column('mode', sa.Enum('regular', 'native', 'untagged'),
                      nullable=False, server_default='regular'),
            sa.Column('encap', sa.String(24)),
            sa.Column('monitored', sa.Boolean, nullable=False, default=False),
            sa.Column('epoch', sa.BigInteger(), nullable=False,
                      server_default='0'),
            sa.PrimaryKeyConstraint('aim_id'),
            sa.UniqueConstraint('tenant_name', 'app_profile_name',
                                'epg_name', 'path',
                                name='uniq_aim_epg_static_paths_v2_identity'),
            sa.Index('idx_aim_endpoint_group_static_paths_v2_identity',
                     'tenant_name', 'app_profile_name', 'epg_name', 'path'))

        # Migrate the data to the new tables
        static_paths_v2.migrate(session)

        # Remove the old table
        op.drop_table('aim_endpoint_group_static_paths')

        # Rename new table
        op.rename_table("aim_endpoint_group_static_paths_v2",
                        "aim_endpoint_group_static_paths")


def downgrade():
    pass
