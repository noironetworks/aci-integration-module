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

"""Turn off GARP EP move detection flg on all BDs

Revision ID: 5e285945cf4d
Revises: 60399662af3c
Create Date: 2023-10-04 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = '5e285945cf4d'
down_revision = '60399662af3c'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

from aim.db.migration.data_migration import fix_bd_garp


def upgrade():

    session = sa.orm.Session(bind=op.get_bind(), autocommit=True)
    fix_bd_garp.migrate(session)


def downgrade():
    pass
