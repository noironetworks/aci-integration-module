# Copyright (c) 2023 Cisco Systems
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

"""add_timestamp_column

Revision ID: 535c1f419b15
Revises: 60399662af3c
Create Date: 2023-09-27 12:24:17.786497

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.expression import func


# revision identifiers, used by Alembic.
revision = '535c1f419b15'
down_revision = '60399662af3c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('aim_host_links', sa.Column(
        'timestamp', sa.TIMESTAMP, onupdate=func.now()))


def downgrade():
    pass
