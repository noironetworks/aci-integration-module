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
#

"""Add epoch column to remote IPs

Revision ID: 8518cc832afe
Revises: bcdef2211410
Create Date: 2018-09-19 00:22:47.618593

"""

# revision identifiers, used by Alembic.
revision = '8518cc832afe'
down_revision = 'bcdef2211410'

from alembic import op
import sqlalchemy as sa


TABLE = 'aim_security_group_rule_remote_ips'


def upgrade():
    op.add_column(TABLE, sa.Column('epoch', sa.BigInteger(),
                                   nullable=False, server_default='0'))
