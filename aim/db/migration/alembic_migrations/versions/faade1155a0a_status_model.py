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

"""Create Status and Fault model

Revision ID: faade1155a0a
Revises: 7349fa0a2ad8
Create Date: 2016-03-15 16:29:57.408348

"""

# revision identifiers, used by Alembic.
revision = 'faade1155a0a'
down_revision = '7349fa0a2ad8'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.expression import func


def upgrade():

    op.create_table(
        'aim_statuses',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('resource_type', sa.String(255), nullable=False),
        sa.Column('resource_id', sa.Integer, nullable=False),
        sa.Column('sync_status', sa.String(50), nullable=True),
        sa.Column('sync_message', sa.TEXT, default=''),
        sa.Column('health_score', sa.Integer),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('resource_type', 'resource_id',
                            name='uniq_aim_statuses_identity'),
        sa.Index('idx_aim_statuses_identity', 'resource_type', 'resource_id'))

    op.create_table(
        'aim_faults',
        sa.Column('status_id', sa.String(length=255), nullable=False),
        sa.Column('fault_code', sa.String(25), nullable=False),
        sa.Column('severity', sa.String(25), nullable=False),
        sa.Column('description', sa.String(255), default=''),
        sa.Column('cause', sa.String(255), default=''),
        sa.Column('last_update_timestamp', sa.TIMESTAMP,
                  server_default=func.now(), onupdate=func.now()),
        sa.Column('external_identifier', sa.String(255), primary_key=True),
        sa.PrimaryKeyConstraint('external_identifier'),
        sa.ForeignKeyConstraint(['status_id'],
                                ['aim_statuses.id'],
                                ondelete='CASCADE'),
        sa.Index('idx_aim_faults_status_id', 'status_id'))


def downgrade():
    pass
