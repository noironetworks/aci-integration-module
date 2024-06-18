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

"""Tables for configuring the parameters for consistent hashing algo
Revision ID: cf83ad8832f0
Revises: 79deb77b4719
Create date: 2024-05-31 10:19:03.236000000
"""

# revision identifiers, used by Alembic.

from alembic import op
import sqlalchemy as sa

revision = 'cf83ad8832f0'
down_revision = '79deb77b4719'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'aim_consistent_hashring_params',
        sa.Column('name', sa.String(16), nullable=False),
        sa.Column('value', sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint('name'))

    aim_consistent_hashring_params_table = sa.Table(
        'aim_consistent_hashring_params', sa.MetaData(),
        sa.Column('value', sa.Integer, nullable=False),
        sa.Column('name', sa.String(16), nullable=False, primary_key=True))
    stmt = sa.insert(aim_consistent_hashring_params_table).values(
        name="vnodes",
        value=40)
    dbsession = sa.orm.Session(bind=op.get_bind())
    dbsession.execute(stmt)
    dbsession.commit()


def downgrade():
    pass
