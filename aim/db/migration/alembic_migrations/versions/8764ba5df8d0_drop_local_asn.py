# Copyright (c) 2018 Cisco Systems
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

"""drop local asn

Revision ID: 8764ba5df8d0
Revises: 4abf11e33ef1
Create Date: 2018-02-13 01:16:17.083127

"""

# revision identifiers, used by Alembic.
revision = '8764ba5df8d0'
down_revision = '4abf11e33ef1'
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    with op.batch_alter_table('aim_l3out_interface_bgp_peer_prefix') as \
        batch_op:
        batch_op.drop_column('local_asn')


def downgrade():
    pass
