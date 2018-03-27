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

"""Migrate HostDomainMapping to HostDomainMappingV2
Revision ID: 5e29ae4f45e6
Revises: 593d228d2fb4
Create Date: 2017-10-25 16:39:33.713695
"""

# revision identifiers, used by Alembic.
revision = '5e29ae4f45e6'
down_revision = '593d228d2fb4'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

from aim.db.migration.data_migration import host_domain_mapping_v2


def upgrade():
    # A model of the new domains table
    op.create_table(
        'aim_host_domain_mapping_v2',
        sa.Column('host_name', sa.String(128)),
        sa.Column('domain_name', sa.String(64)),
        sa.Column('domain_type', sa.Enum('PhysDom',
                                         'OpenStack',
                                         'Kubernetes',
                                         'VMware')),
        sa.PrimaryKeyConstraint('host_name', 'domain_name', 'domain_type')
    )
    session = sa.orm.Session(bind=op.get_bind(), autocommit=True)
    host_domain_mapping_v2.migrate(session)


def downgrade():
    pass
