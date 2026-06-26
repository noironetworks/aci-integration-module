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

import contextlib
import importlib
import os
import runpy

import mock
import sqlalchemy as sa

from aim import aim_manager
from aim.api import infra
from aim.api import resource
from aim.api import service_graph
from aim.api import status as aim_status
from aim.api import tree
from aim.common import utils
from aim import config
from aim.db.migration.data_migration import add_host_column
from aim.db.migration.data_migration import fix_bd_garp
from aim.db.migration.data_migration import host_domain_mapping_v2
from aim.db.migration.data_migration import status_add_tenant
from aim.tests import base
from aim.tools.cli.commands import db_migration


class TestAlembicTransactions(base.BaseTestCase):

    @staticmethod
    @contextlib.contextmanager
    def _transaction_context():
        yield

    def test_env_does_not_close_external_connection(self):
        class FakeConfig(object):
            config_file_name = base.etcdir('aim.conf.test')

            def __init__(self, connection):
                self.attributes = {'connection': connection}

        class FakeContext(object):
            def __init__(self, connection):
                self.config = FakeConfig(connection)
                self.configured_connection = None

            def is_offline_mode(self):
                return False

            def configure(self, **kwargs):
                self.configured_connection = kwargs['connection']

            def begin_transaction(self):
                return TestAlembicTransactions._transaction_context()

            def run_migrations(self):
                pass

        engine = sa.create_engine('sqlite://')
        connection = engine.connect()
        transaction = connection.begin()
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'db', 'migration', 'alembic_migrations', 'env.py')
        fake_context = FakeContext(connection)
        try:
            with mock.patch('alembic.context', fake_context):
                with mock.patch('logging.config.fileConfig'):
                    runpy.run_path(env_path)
            self.assertIs(connection, fake_context.configured_connection)
            self.assertFalse(connection.closed)
            self.assertTrue(transaction.is_active)
        finally:
            if transaction.is_active:
                transaction.rollback()
            if not connection.closed:
                connection.close()

    def test_hashring_params_migration_does_not_commit(self):
        migration = importlib.import_module(
            'aim.db.migration.alembic_migrations.versions.'
            'cf83ad8832f0_hashring_parameters_vnodes')

        class NoCommitSession(object):
            def execute(self, stmt):
                pass

            def commit(self):
                raise AssertionError(
                    'Alembic migrations must not commit explicitly')

        session = NoCommitSession()
        with mock.patch.object(migration.op, 'create_table'):
            with mock.patch.object(migration.op, 'get_bind',
                                   return_value=mock.Mock()):
                with mock.patch.object(migration.sa.orm, 'Session',
                                       return_value=session):
                    migration.upgrade()

    def test_remoteip_container_migration_does_not_commit(self):
        migration = importlib.import_module(
            'aim.db.migration.alembic_migrations.versions.'
            'a94984a4452b_security_groups_remoteipcont')

        class NoCommitSession(object):
            def execute(self, stmt):
                pass

            def commit(self):
                raise AssertionError(
                    'Alembic migrations must not commit explicitly')

        session = NoCommitSession()
        with mock.patch.object(migration.op, 'create_table'):
            with mock.patch.object(migration.op, 'get_bind',
                                   return_value=mock.Mock()):
                with mock.patch.object(migration.sa.orm, 'Session',
                                       return_value=session):
                    migration.upgrade()

    def test_bd_ip_learning_migration_does_not_commit(self):
        migration = importlib.import_module(
            'aim.db.migration.alembic_migrations.versions.'
            'dd2f91cf1b1e_set_nat_bd_ip_learn')

        class FakeQuery(object):
            def all(self):
                return [(1, 'l3out')]

        class NoCommitSession(object):
            def query(self, table):
                return FakeQuery()

            def commit(self):
                raise AssertionError(
                    'Alembic migrations must not commit explicitly')

        values = migration.get_bd_l3out_values(NoCommitSession())
        self.assertEqual([{'bd_aim_id': 1}], values)


class TestDBMigrationCommand(base.BaseTestCase):

    def test_fix_no_nat_l3out_ownership_select_is_sqlalchemy_13_safe(self):
        engine = sa.create_engine('sqlite://')
        metadata = sa.MetaData()
        sa.Table(
            'aim_lib_save_l3out', metadata,
            sa.Column('tenant_name', sa.String(), primary_key=True),
            sa.Column('name', sa.String(), primary_key=True),
            sa.Column('monitored', sa.Boolean()),
            sa.Column('vrf_name', sa.String()))
        metadata.create_all(engine)
        session = db_migration.sa.orm.Session(bind=engine)

        class Store(object):
            db_session = session

        class AimContext(object):
            store = Store()

        with mock.patch.object(
                db_migration.sa, 'select',
                side_effect=AssertionError(
                    'Use table.select() for SQLAlchemy 1.3 compatibility')):
            db_migration.fix_no_nat_l3out_ownership(AimContext())


class TestDataMigration(base.TestAimDBBase):

    def setUp(self, *args, **kwargs):
        super(TestDataMigration, self).setUp(*args, mock_store=False, **kwargs)
        self.mgr = aim_manager.AimManager()

    def test_host_data_migration(self):
        self.mgr.create(self.ctx, infra.HostLink(
            host_name='h1', interface_name='eth0', path='h1/path/VPC'))
        self.mgr.create(self.ctx, infra.HostLink(
            host_name='h1', interface_name='eth1', path='h1/path/2'))
        self.mgr.create(self.ctx, infra.HostLink(
            host_name='h1', interface_name='eth2', path='h1/path/VPC'))
        self.mgr.create(self.ctx, infra.HostLink(
            host_name='h2', interface_name='eth2', path='h2/path'))

        epg1 = self.mgr.create(self.ctx, resource.EndpointGroup(
            tenant_name='t1', app_profile_name='ap', name='epg1'))
        epg2 = self.mgr.create(self.ctx, resource.EndpointGroup(
            tenant_name='t1', app_profile_name='ap', name='epg2'))
        dc = self.mgr.create(self.ctx, service_graph.DeviceCluster(
            tenant_name='t2', name='dc',
            devices=[{'path': 'h1/path/2', 'name': '1'},
                     {'path': 'h2/path', 'name': '2'}]))
        cdi1 = self.mgr.create(self.ctx, service_graph.ConcreteDeviceInterface(
            tenant_name='t2', device_cluster_name='dc', device_name='1',
            name='dc', path='h1/path/VPC'))
        cdi2 = self.mgr.create(self.ctx, service_graph.ConcreteDeviceInterface(
            tenant_name='t2', device_cluster_name='dc', device_name='2',
            name='dc', path='h2/path'))
        l3out_iface1 = self.mgr.create(
            self.ctx, resource.L3OutInterface(
                tenant_name='t2', l3out_name='dc', node_profile_name='1',
                interface_profile_name='dc1', interface_path='h1/path/VPC'))
        l3out_iface2 = self.mgr.create(
            self.ctx, resource.L3OutInterface(
                tenant_name='t2', l3out_name='dc', node_profile_name='1',
                interface_profile_name='dc2', interface_path='h2/path'))
        add_host_column.migrate(self.ctx.db_session)
        epg1 = self.mgr.get(self.ctx, epg1)
        epg2 = self.mgr.get(self.ctx, epg2)
        dc = self.mgr.get(self.ctx, dc)
        cdi1 = self.mgr.get(self.ctx, cdi1)
        self.assertEqual('h1', cdi1.host)
        cdi2 = self.mgr.get(self.ctx, cdi2)
        self.assertEqual('h2', cdi2.host)
        l3out_iface1 = self.mgr.get(self.ctx, l3out_iface1)
        self.assertEqual('h1', l3out_iface1.host)
        l3out_iface2 = self.mgr.get(self.ctx, l3out_iface2)
        self.assertEqual('h2', l3out_iface2.host)

    def test_status_add_tenant(self):
        for res_klass in self.mgr.aim_resources:
            if res_klass in [aim_status.AciStatus, aim_status.AciFault,
                             resource.Agent, infra.HostDomainMappingV2,
                             infra.HostDomainMapping, tree.ActionLog]:
                continue
            res = self.mgr.create(
                self.ctx, res_klass(
                    **{k: utils.generate_uuid()
                       for k in list(res_klass.identity_attributes.keys())}))
            status = self.mgr.get_status(self.ctx, res)
            if not status:
                continue
            status_add_tenant.migrate(self.ctx.db_session)
            status = self.mgr.get_status(self.ctx, res)
            self.assertEqual(res.root, status.resource_root)

    def test_host_domain_mapping_v2(self):
        hm1 = self.mgr.create(self.ctx, infra.HostDomainMapping(
            host_name='h1', vmm_domain_name='vmm1',
            physical_domain_name='phys1'))
        hm2 = self.mgr.create(self.ctx, infra.HostDomainMapping(
            host_name='h2', physical_domain_name='phys1'))
        host_domain_mapping_v2.migrate(self.ctx.db_session)
        self.assertIsNone(self.mgr.get(self.ctx, hm1))
        self.assertIsNone(self.mgr.get(self.ctx, hm2))
        new_mappings = self.mgr.find(self.ctx, infra.HostDomainMappingV2)
        self.assertEqual(3, len(new_mappings))

    def test_status_add_dn(self):
        for res_klass in self.mgr.aim_resources:
            if res_klass in [aim_status.AciStatus, aim_status.AciFault,
                             resource.Agent, infra.HostDomainMappingV2,
                             infra.HostDomainMapping, tree.ActionLog]:
                continue
            res = self.mgr.create(
                self.ctx, res_klass(
                    **{k: utils.generate_uuid()
                       for k in list(res_klass.identity_attributes.keys())}))
            status = self.mgr.get_status(self.ctx, res)
            if not status:
                continue
            status_add_tenant.migrate(self.ctx.db_session)
            status = self.mgr.get_status(self.ctx, res)
            self.assertEqual(res.dn, status.resource_dn)

    def test_fix_bd_garp(self):
        self.mgr.create(self.ctx, resource.BridgeDomain(
            tenant_name='t1', name='bd1', ep_move_detect_mode='garp'))
        self.mgr.create(self.ctx, resource.BridgeDomain(
            tenant_name='t1', name='bd2', ep_move_detect_mode='garp',
            monitored=True))
        fix_bd_garp.migrate(self.ctx.db_session)
        bds = self.mgr.find(self.ctx, resource.BridgeDomain)
        self.assertEqual(len(bds), 2)
        for bd in bds:
            if bd.monitored is True:
                self.assertEqual(bd.ep_move_detect_mode, 'garp')
            else:
                self.assertEqual(bd.ep_move_detect_mode, '')

    def test_no_fix_bd_garp(self):
        config.CONF.set_override('support_gen1_hw_gratarps', True, 'aim')
        self.mgr.create(self.ctx, resource.BridgeDomain(
            tenant_name='t1', name='bd1', ep_move_detect_mode='garp'))
        self.mgr.create(self.ctx, resource.BridgeDomain(
            tenant_name='t1', name='bd2', ep_move_detect_mode='garp',
            monitored=True))
        fix_bd_garp.migrate(self.ctx.db_session)
        bds = self.mgr.find(self.ctx, resource.BridgeDomain)
        self.assertEqual(len(bds), 2)
        for bd in bds:
            self.assertEqual(bd.ep_move_detect_mode, 'garp')
