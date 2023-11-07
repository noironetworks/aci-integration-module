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

from oslo_utils import importutils
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy import update

from aim import aim_store
from neutron_lib.db import api as db_api

resource_paths = ('aim.api.resource', 'aim.api.service_graph',
                  'aim.api.infra')

Status = sa.Table(
    'aim_statuses', sa.MetaData(),
    sa.Column('resource_type', sa.String(255), nullable=False),
    sa.Column('resource_id', sa.Integer, nullable=False),
    sa.Column('resource_root', sa.String(255), nullable=False),
    sa.Column('sync_status', sa.String(50), nullable=True),
    sa.Column('sync_message', sa.TEXT, default=''),
    sa.Column('health_score', sa.Integer, nullable=False),
    sa.Column('id', sa.String(255), primary_key=True),
    sa.Column('resource_dn', mysql.VARCHAR(512, charset='latin1'),
              nullable=False),
)


def get_resource_class(resource_type):
    resource_class = None
    for path in resource_paths:
        try:
            resource_class = importutils.import_class(path + '.%s' %
                                                      resource_type)
        except ImportError:
            continue
    return aim_store.SqlAlchemyStore.db_model_map[
        resource_class], resource_class


def migrate(session):
    with db_api.CONTEXT_WRITER.using(session):
        store = aim_store.SqlAlchemyStore(None)
        for st in session.query(Status).all():
            res_table, res_class = get_resource_class(st.resource_type)
            db_res = session.query(res_table).filter_by(
                aim_id=st.resource_id).first()
            try:
                res = store.make_resource(res_class, db_res)
                session.execute(update(Status).where(
                    Status.c.id == st.id).values(resource_dn=res.dn))
            except Exception:
                # Silently ignore
                pass
