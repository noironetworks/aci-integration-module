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

)


def get_parent_class(resource_type):
    parent_class = None
    for path in resource_paths:
        try:
            parent_class = importutils.import_class(path + '.%s' %
                                                    resource_type)
        except ImportError:
            continue
    return aim_store.SqlAlchemyStore.db_model_map[parent_class], parent_class


def get_root_klass(resource):
    if not resource._tree_parent:
        return resource
    return get_root_klass(resource._tree_parent)


def migrate(session):
    with db_api.CONTEXT_WRITER.using(session):
        for st in session.query(Status).all():
            parent_table, parent_class = get_parent_class(st.resource_type)
            root_klass = get_root_klass(parent_class)
            if parent_class.__name__.startswith('VmmInjected'):
                rn = 'comp'
            elif len(root_klass.identity_attributes) == 0:
                rn = root_klass().rn
            else:
                parent_root_attr = list(
                    parent_class.identity_attributes.keys())[0]
                parent_root = getattr(parent_table, parent_root_attr)
                parent = session.query(parent_root).one()
                root_name = getattr(parent, parent_root_attr)
                rn = root_klass(
                    **{list(root_klass.identity_attributes.keys(
                        ))[0]: root_name}).rn
            session.execute(update(Status).where(
                Status.c.id == st.id).values(resource_root=rn))
