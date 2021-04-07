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

from aim.common import utils
import sqlalchemy as sa
from sqlalchemy.ext import declarative
from sqlalchemy import orm

Base = declarative.declarative_base()

ContractSubjFilter = sa.Table(
    'aim_contract_subject_filter_relation', sa.MetaData(),
    sa.Column('aim_id', sa.String(255),
              default=utils.generate_uuid, primary_key=True),
    sa.Column('tenant_name', sa.String(64), primary_key=True),
    sa.Column('contract_name', sa.String(64), primary_key=True),
    sa.Column('contract_subject_name', sa.String(64), primary_key=True),
    sa.Column('filter_name', sa.String(64), primary_key=True),
    sa.Column('display_name', sa.String(64)),
    sa.Column('monitored', sa.Boolean),
    sa.Column('action', sa.Enum('permit', 'deny'))
)


ContractSubjInFilter = sa.Table(
    'aim_contract_subject_in_filter_relation', sa.MetaData(),
    sa.Column('aim_id', sa.String(255),
              default=utils.generate_uuid, primary_key=True),
    sa.Column('tenant_name', sa.String(64), primary_key=True),
    sa.Column('contract_name', sa.String(64), primary_key=True),
    sa.Column('contract_subject_name', sa.String(64), primary_key=True),
    sa.Column('filter_name', sa.String(64), primary_key=True),
    sa.Column('display_name', sa.String(64)),
    sa.Column('monitored', sa.Boolean),
    sa.Column('action', sa.Enum('permit', 'deny'))
)


ContractSubjOutFilter = sa.Table(
    'aim_contract_subject_out_filter_relation', sa.MetaData(),
    sa.Column('aim_id', sa.String(255),
              default=utils.generate_uuid, primary_key=True),
    sa.Column('tenant_name', sa.String(64), primary_key=True),
    sa.Column('contract_name', sa.String(64), primary_key=True),
    sa.Column('contract_subject_name', sa.String(64), primary_key=True),
    sa.Column('filter_name', sa.String(64), primary_key=True),
    sa.Column('display_name', sa.String(64)),
    sa.Column('monitored', sa.Boolean),
    sa.Column('action', sa.Enum('permit', 'deny'))
)


ContractSubjGraph = sa.Table(
    'aim_contract_subject_graph_relation', sa.MetaData(),
    sa.Column('aim_id', sa.String(255),
              default=utils.generate_uuid, primary_key=True),
    sa.Column('tenant_name', sa.String(64), primary_key=True),
    sa.Column('contract_name', sa.String(64), primary_key=True),
    sa.Column('contract_subject_name', sa.String(64), primary_key=True),
    sa.Column('graph_name', sa.String(64)),
    sa.Column('display_name', sa.String(64)),
    sa.Column('monitored', sa.Boolean)
)


ContractSubjInGraph = sa.Table(
    'aim_contract_subject_graph_relation', sa.MetaData(),
    sa.Column('aim_id', sa.String(255),
              default=utils.generate_uuid, primary_key=True),
    sa.Column('tenant_name', sa.String(64), primary_key=True),
    sa.Column('contract_name', sa.String(64), primary_key=True),
    sa.Column('contract_subject_name', sa.String(64), primary_key=True),
    sa.Column('graph_name', sa.String(64)),
    sa.Column('display_name', sa.String(64)),
    sa.Column('monitored', sa.Boolean)
)


ContractSubjOutGraph = sa.Table(
    'aim_contract_subject_graph_relation', sa.MetaData(),
    sa.Column('aim_id', sa.String(255),
              default=utils.generate_uuid, primary_key=True),
    sa.Column('tenant_name', sa.String(64), primary_key=True),
    sa.Column('contract_name', sa.String(64), primary_key=True),
    sa.Column('contract_subject_name', sa.String(64), primary_key=True),
    sa.Column('graph_name', sa.String(64)),
    sa.Column('display_name', sa.String(64)),
    sa.Column('monitored', sa.Boolean))


class ContractSubjectFilter(Base):
    __tablename__ = 'aim_contract_subject_filters'
    subject_aim_id = sa.Column(sa.Integer,
                               sa.ForeignKey('aim_contract_subjects.aim_id'),
                               primary_key=True)
    name = sa.Column(sa.String(64), primary_key=True)
    direction = sa.Column(sa.Enum('bi', 'in', 'out'), primary_key=True)


class ContractSubject(Base):
    __tablename__ = 'aim_contract_subjects'
    aim_id = sa.Column(sa.Integer, primary_key=True)
    tenant_name = sa.Column(sa.String(64), primary_key=True)
    contract_name = sa.Column(sa.String(64), primary_key=True)
    name = sa.Column(sa.String(64), primary_key=True)
    service_graph_name = sa.Column(sa.String(64))
    in_service_graph_name = sa.Column(sa.String(64))
    out_service_graph_name = sa.Column(sa.String(64))
    filters = orm.relationship(ContractSubjectFilter,
                               backref='contract',
                               cascade='all, delete-orphan',
                               lazy='joined')


def migrate(session):
    with session.begin(subtransactions=True):
        migrations_in = []
        migrations_out = []
        migrations_bi = []
        migrations_graph = []
        migrations_in_graph = []
        migrations_out_graph = []
        contract_subjects = session.query(ContractSubject).all()
        for subj in contract_subjects:
            for flt in subj.filters:
                if flt.direction == 'in':
                    migrations_in.append({'tenant_name': subj.tenant_name,
                                          'contract_name': subj.contract_name,
                                          'contract_subject_name': subj.name,
                                          'filter_name': flt.name,
                                          'display_name': '',
                                          'monitored': False,
                                          'action': 'permit'})
                if flt.direction == 'out':
                    migrations_out.append({'tenant_name': subj.tenant_name,
                                           'contract_name': subj.contract_name,
                                           'contract_subject_name': subj.name,
                                           'filter_name': flt.name,
                                           'display_name': '',
                                           'monitored': False,
                                           'action': 'permit'})
                if flt.direction == 'bi':
                    migrations_bi.append({'tenant_name': subj.tenant_name,
                                          'contract_name': subj.contract_name,
                                          'contract_subject_name': subj.name,
                                          'filter_name': flt.name,
                                          'display_name': '',
                                          'monitored': False,
                                          'action': 'permit'})
            if subj.service_graph_name:
                migrations_graph.append({'tenant_name': subj.tenant_name,
                                         'contract_name': subj.contract_name,
                                         'contract_subject_name': subj.name,
                                         'graph_name': subj.service_graph_name,
                                         'display_name': '',
                                         'monitored': False})
            if subj.in_service_graph_name:
                migrations_in_graph.append({'tenant_name': subj.tenant_name,
                                            'contract_name':
                                                subj.contract_name,
                                            'contract_subject_name': subj.name,
                                            'graph_name':
                                                subj.in_service_graph_name,
                                            'display_name': '',
                                            'monitored': False})
            if subj.service_graph_name:
                migrations_out_graph.append({'tenant_name': subj.tenant_name,
                                             'contract_name':
                                                 subj.contract_name,
                                             'contract_subject_name':
                                                 subj.name,
                                             'graph_name':
                                                 subj.out_service_graph_name,
                                             'display_name': '',
                                             'monitored': False})
        if migrations_bi:
            session.execute(ContractSubjFilter.insert().values(
                migrations_bi))
        if migrations_in:
            session.execute(ContractSubjInFilter.insert().values(
                migrations_in))
        if migrations_out:
            session.execute(ContractSubjOutFilter.insert().values(
                migrations_out))
        if migrations_graph:
            session.execute(ContractSubjOutFilter.insert().values(
                migrations_graph))
        if migrations_in_graph:
            session.execute(ContractSubjOutFilter.insert().values(
                migrations_in_graph))
        if migrations_out_graph:
            session.execute(ContractSubjOutFilter.insert().values(
                migrations_out_graph))
