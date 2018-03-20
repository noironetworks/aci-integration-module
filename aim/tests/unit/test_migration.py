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

from aim import aim_manager
from aim.api import infra
from aim.api import resource
from aim.api import service_graph
from aim.db.migration.data_migration import add_host_column
from aim.tests import base


class TestDataMigration(base.TestAimDBBase):

    def setUp(self, *args, **kwargs):
        super(TestDataMigration, self).setUp(*args, **kwargs)
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
            tenant_name='t1', app_profile_name='ap', name='epg1',
            static_paths=[{'path': 'h1/path/2', 'encap': '100'},
                          {'path': 'h2/path', 'encap': '100'},
                          {'path': 'not_known', 'encap': '100'}]))
        epg2 = self.mgr.create(self.ctx, resource.EndpointGroup(
            tenant_name='t1', app_profile_name='ap', name='epg2',
            static_paths=[{'path': 'h1/path/2', 'encap': '100'},
                          {'path': 'h1/path/VPC', 'encap': '100'}]))
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
        self.assertEqual(sorted([{'path': 'h1/path/2', 'encap': '100',
                                  'host': 'h1'},
                                 {'path': 'h2/path', 'encap': '100',
                                  'host': 'h2'},
                                 {'path': 'not_known', 'encap': '100'}]),
                         sorted(epg1.static_paths))
        epg2 = self.mgr.get(self.ctx, epg2)
        self.assertEqual(sorted([{'path': 'h1/path/2', 'encap': '100',
                                  'host': 'h1'},
                                 {'path': 'h1/path/VPC', 'encap': '100',
                                  'host': 'h1'}]),
                         sorted(epg2.static_paths))
        dc = self.mgr.get(self.ctx, dc)
        self.assertEqual(sorted([{'path': 'h1/path/2', 'name': '1',
                                  'host': 'h1'},
                                 {'path': 'h2/path', 'name': '2',
                                  'host': 'h2'}]), sorted(dc.devices))
        cdi1 = self.mgr.get(self.ctx, cdi1)
        self.assertEqual('h1', cdi1.host)
        cdi2 = self.mgr.get(self.ctx, cdi2)
        self.assertEqual('h2', cdi2.host)

        l3out_iface1 = self.mgr.get(self.ctx, l3out_iface1)
        self.assertEqual('h1', l3out_iface1.host)
        l3out_iface2 = self.mgr.get(self.ctx, l3out_iface2)
        self.assertEqual('h2', l3out_iface2.host)
