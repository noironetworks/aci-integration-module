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

from oslo_config import cfg

from aim import aim_manager
from aim.api import resource
from aim import config
from aim.tests.unit.tools.cli import test_shell as base


cfg.CONF.register_opts(config.global_opts)


class TestManager(base.TestShell):

    def setUp(self):
        super(TestManager, self).setUp()
        self.mgr = aim_manager.AimManager()

    def test_load_domains(self):
        # create a VMM and PhysDom first
        pre_phys = resource.PhysicalDomain(name='pre-phys')
        pre_vmm = resource.PhysicalDomain(type='OpenStack', name='pre-vmm')
        ap = resource.ApplicationProfile(tenant_name='tn1', name='ap')
        pre_epg1 = resource.EndpointGroup(
            tenant_name='tn1', app_profile_name='ap', name='epg1')
        pre_epg2 = resource.EndpointGroup(
            tenant_name='tn1', app_profile_name='ap', name='epg2')
        self.mgr.create(self.ctx, ap)
        self.mgr.create(self.ctx, pre_phys)
        self.mgr.create(self.ctx, pre_vmm)
        self.mgr.create(self.ctx, pre_epg2)
        self.mgr.create(self.ctx, pre_epg1)
        self.run_command('manager load-domains')
        # Verify pre-existing domains are still there
        self.assertIsNotNone(self.mgr.get(self.ctx, pre_phys))
        self.assertIsNotNone(self.mgr.get(self.ctx, pre_vmm))
        # Also the Domains defined in the config files exist
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.PhysicalDomain(name='phys')))
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.PhysicalDomain(name='phys2')))
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.VMMDomain(type='OpenStack',
                                                      name='ostack')))
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.VMMDomain(type='OpenStack',
                                                      name='ostack2')))
        # EPGs are still empty
        pre_epg1 = self.mgr.get(self.ctx, pre_epg1)
        pre_epg2 = self.mgr.get(self.ctx, pre_epg2)

        self.assertEqual([], pre_epg1.openstack_vmm_domain_names)
        self.assertEqual([], pre_epg1.physical_domain_names)
        self.assertEqual([], pre_epg2.openstack_vmm_domain_names)
        self.assertEqual([], pre_epg2.physical_domain_names)

        # Delete one of them, and use the replace flag
        self.mgr.delete(self.ctx, resource.VMMDomain(type='OpenStack',
                                                     name='ostack2'))
        self.run_command('manager load-domains --replace')

        # Now only 2 Domains each exist
        self.assertEqual(2, len(self.mgr.find(self.ctx, resource.VMMDomain)))
        self.assertEqual(2, len(self.mgr.find(self.ctx,
                                              resource.PhysicalDomain)))

        # EPGs are still empty
        pre_epg1 = self.mgr.get(self.ctx, pre_epg1)
        pre_epg2 = self.mgr.get(self.ctx, pre_epg2)

        self.assertEqual([], pre_epg1.openstack_vmm_domain_names)
        self.assertEqual([], pre_epg1.physical_domain_names)
        self.assertEqual([], pre_epg2.openstack_vmm_domain_names)
        self.assertEqual([], pre_epg2.physical_domain_names)

        # now update the current environment
        self.run_command('manager load-domains --replace --enforce')
        pre_epg1 = self.mgr.get(self.ctx, pre_epg1)
        pre_epg2 = self.mgr.get(self.ctx, pre_epg2)

        self.assertEqual(set(['ostack', 'ostack2']),
                         set(pre_epg1.openstack_vmm_domain_names))
        self.assertEqual(set(['phys', 'phys2']),
                         set(pre_epg1.physical_domain_names))
        self.assertEqual(set(['ostack', 'ostack2']),
                         set(pre_epg2.openstack_vmm_domain_names))
        self.assertEqual(set(['phys2', 'phys']),
                         set(pre_epg2.physical_domain_names))
