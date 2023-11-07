# Copyright (c) 2016 Cisco Systems
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import sqlalchemy as sa

from aim.db import model_base
from neutron_lib.db import api as db_api

# Some aim_lib utilities may require additional DB model for keeping state.
# Use this module for such purpose


class CloneL3Out(model_base.Base):
    """DB model for CloneL3Out.

    Keeps relationship between L3Outs and their clones.
    Each L3Out can be cloned only from one source, while the same source
    can generate multiple clones (1:N)
    """

    __tablename__ = 'aim_lib_clone_l3out'
    __table_args__ = (
        # If the clone L3Out gets deleted, cascade on the corresponding row
        (sa.ForeignKeyConstraint(
            ['tenant_name', 'name'],
            ['aim_l3outsides.tenant_name', 'aim_l3outsides.name'],
            name='fk_clone_l3out_l3out', ondelete='CASCADE'),) +
        (sa.ForeignKeyConstraint(
            ['source_tenant_name', 'source_name'],
            ['aim_l3outsides.tenant_name', 'aim_l3outsides.name'],
            name='fk_clone_src_l3out_l3out'),) +
        model_base.to_tuple(model_base.Base.__table_args__))

    source_tenant_name = model_base.name_column(nullable=False)
    source_name = model_base.name_column(nullable=False)
    # Clone L3Out reference is primary key
    tenant_name = model_base.name_column(nullable=False, primary_key=True)
    name = model_base.name_column(nullable=False, primary_key=True)


class CloneL3OutManager(object):

    def set(self, context, source, clone):
        """Store L3outside clone key and the relationship to its source

        :param context: AIM context
        :param source: L3Outside AIM resource
        :param clone: L3Outside AIM resource
        :return:
        """
        with db_api.CONTEXT_WRITER.using(context):
            obj = CloneL3Out(source_tenant_name=source.tenant_name,
                             source_name=source.name,
                             tenant_name=clone.tenant_name,
                             name=clone.name)
            context.db_session.add(obj)

    def get(self, context, clone):
        rows = self._find_query(context, tenant_name=clone.tenant_name,
                                name=clone.name).all()
        return rows

    def get_clones(self, context, source):
        """Given a source, find its clones' identity attributes

        :param context: AIM context
        :param source: L3Outside AIM resource
        :return: list of tuples where the first position is the clone L3Out
                 tenant_name and the second is its name.
        """
        with db_api.CONTEXT_WRITER.using(context):
            result = []
            db_objs = self._find_query(
                context, source_tenant_name=source.tenant_name,
                source_name=source.name).all()
            for db_obj in db_objs:
                result.append((db_obj.tenant_name, db_obj.name))
            return result

    def _find_query(self, context, **kwargs):
        query = context.db_session.query(CloneL3Out)
        if kwargs:
            query = query.filter_by(**kwargs)
        return query
