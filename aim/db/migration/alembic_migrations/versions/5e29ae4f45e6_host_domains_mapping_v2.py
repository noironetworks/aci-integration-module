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

from aim import aim_manager
from aim.api import infra
from aim import context
from aim.db import api


AIM_HOST_DOMAIN_MAPPING_V2 = 'aim_host_domain_mapping_v2'


def upgrade():
    # A model of the new domains table
    domainsv2 = op.create_table(
        AIM_HOST_DOMAIN_MAPPING_V2,
        sa.Column('host_name', sa.String(128)),
        sa.Column('domain_name', sa.String(64)),
        sa.Column('domain_type', sa.Enum('PhysDom',
                                         'OpenStack',
                                         'Kubernetes',
                                         'VMware')),
        sa.PrimaryKeyConstraint('host_name', 'domain_name', 'domain_type')
    )

    mgr = aim_manager.AimManager()
    ctx = context.AimContext(db_session=api.get_session(expire_on_commit=True))
    with ctx.db_session.begin(subtransactions=True):
        migrations = []
        for mapping in mgr.find(ctx, infra.HostDomainMapping):
            if mapping.vmm_domain_name:
                migrations.append({'host_name': mapping.host_name,
                                   'domain_name': mapping.vmm_domain_name,
                                   'domain_type': 'OpenStack'})
            if mapping.physical_domain_name:
                migrations.append({'host_name': mapping.host_name,
                                   'domain_name': mapping.physical_domain_name,
                                   'domain_type': 'PhysDom'})
        op.bulk_insert(domainsv2, migrations)
        # we can clear out the old table
        mgr.delete_all(ctx, infra.HostDomainMapping)


def downgrade():
    pass
