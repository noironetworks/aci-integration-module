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

"""Convert vmm_domain_name to primary key in HostDomainMapping

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

AIM_HOST_DOMAIN_MAPPING = 'aim_host_domain_mapping'

# A model of the networks table with the fields present before
# the migration.
domains = sa.Table(AIM_HOST_DOMAIN_MAPPING, sa.MetaData(),
                   sa.Column('host_name', sa.String(128), primary_key=True),
                   sa.Column('vmm_domain_name', sa.String(64)),
                   sa.Column('physical_domain_name', sa.String(64)))


def upgrade():
    session = sa.orm.Session(bind=op.get_bind())
    additions = get_values(session, domains)

    op.drop_table(AIM_HOST_DOMAIN_MAPPING)
    op.create_table(
        AIM_HOST_DOMAIN_MAPPING,
        sa.Column('host_name', sa.String(128)),
        sa.Column('domain_name', sa.String(64)),
        sa.Column('domain_type', sa.Enum('PhysDom',
                                         'OpenStack',
                                         'Kubernetes',
                                         'VMware')),
        sa.PrimaryKeyConstraint('host_name', 'domain_name', 'domain_type')
    )
    # We need a new table reflecting the updated schema
    domains_new = sa.Table(AIM_HOST_DOMAIN_MAPPING, sa.MetaData(),
                           sa.Column('host_name',
                                     sa.String(128), primary_key=True),
                           sa.Column('domain_name',
                                     sa.String(64), primary_key=True),
                           sa.Column('domain_type',
                                     sa.Enum('PhysDom',
                                             'OpenStack',
                                             'Kubernetes',
                                             'VMware'), primary_key=True))
    op.bulk_insert(domains_new, additions)


def get_values(session, domains):
    """Get pre-migration DB rows.

    This gets the rows from the DB before the migration, using
    the schema defined locally in this file (since the class
    has already been updated with the new schema, and therefore
    can't be used for the pre-migrated table).
    """
    additions = []
    for row in session.query(domains).all():
        host, vmm_dom, phys_dom = row
        if vmm_dom:
            additions.append({'host_name': host,
                              'domain_name': vmm_dom,
                              'domain_type': 'OpenStack'})
        if phys_dom:
            additions.append({'host_name': host,
                              'domain_name': phys_dom,
                              'domain_type': 'PhysDom'})
    # this commit appears to be necessary to allow further operations
    session.commit()
    return additions


def downgrade():
    pass
