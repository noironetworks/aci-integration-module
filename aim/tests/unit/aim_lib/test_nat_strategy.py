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

"""
test_nat_strategy
----------------------------------

Tests for `nat_strategy` module.
"""

import copy

from aim.aim_lib import nat_strategy
from aim import aim_manager
from aim.api import resource as a_res
from aim.tests import base


class TestNatStrategyBase(object):

    def setUp(self):
        super(TestNatStrategyBase, self).setUp()
        self.mgr = aim_manager.AimManager()
        self.ns = self.strategy(self.mgr)
        self.ns.app_profile_name = 'myapp'
        self.mgr.create(self.ctx, a_res.VMMPolicy(type='OpenStack'))
        self.mgr.create(self.ctx, a_res.VMMDomain(type='OpenStack',
                                                  name='ostack'))
        self.mgr.create(self.ctx, a_res.PhysicalDomain(name='phys'))

    def _assert_res_eq(self, lhs, rhs):
        def sort_if_list(obj):
            return sorted(obj) if isinstance(obj, list) else obj

        self.assertEqual(type(lhs), type(rhs))
        for attr in lhs.attributes():
            self.assertEqual(sort_if_list(getattr(lhs, attr, None)),
                             sort_if_list(getattr(rhs, attr, None)),
                             'Attribute %s of %s' % (attr, lhs))

    def _assert_res_list_eq(self, lhs, rhs):
        self.assertEqual(len(lhs), len(rhs),
                         '\nExpected: %s\nFound %s' % (lhs, rhs))
        lhs = sorted(lhs, key=lambda x: x.dn)
        rhs = sorted(rhs, key=lambda x: x.dn)
        for idx in range(0, len(lhs)):
            self._assert_res_eq(lhs[idx], rhs[idx])

    def _verify(self, present=None, absent=None):
        for o in (present or []):
            db_obj = self.mgr.get(self.ctx, o)
            self.assertIsNotNone(db_obj, 'Resource %s' % o)
            self._assert_res_eq(o, db_obj)

        for o in (absent or []):
            self.assertIsNone(self.mgr.get(self.ctx, o),
                              'Resource %s' % o)

    def _get_l3out_objects(self, l3out_name=None, l3out_display_name=None,
                           nat_vrf_name=None):
        name = 'EXT-%s' % (l3out_name or 'o1')
        d_name = 'EXT-%s' % (l3out_display_name or 'OUT')
        nat_vrf = a_res.VRF(tenant_name='t1', name=name, display_name=d_name)
        return ([
            a_res.Filter(tenant_name='t1', name=name,
                         display_name=d_name),
            a_res.FilterEntry(tenant_name='t1', filter_name=name,
                              name='Any', display_name='Any'),
            a_res.Contract(tenant_name='t1', name=name,
                           display_name=d_name),
            a_res.ContractSubject(tenant_name='t1', contract_name=name,
                                  name='Allow', display_name='Allow',
                                  bi_filters=[name]),
            a_res.BridgeDomain(tenant_name='t1', name=name,
                               display_name=d_name,
                               vrf_name=nat_vrf_name or name,
                               l3out_names=[l3out_name or 'o1']),
            a_res.ApplicationProfile(tenant_name='t1', name='myapp',
                                     display_name='myapp'),
            a_res.EndpointGroup(tenant_name='t1', app_profile_name='myapp',
                                name=name, display_name=d_name,
                                bd_name=name,
                                provided_contract_names=[name],
                                consumed_contract_names=[name],
                                # NOTE(ivar): Need to keep both VMM
                                # representations since a GET on the EPG
                                # will also return the domain name list
                                # for backward compatibility
                                openstack_vmm_domain_names=['ostack'],
                                physical_domain_names=['phys'],
                                vmm_domains=[{'type': 'OpenStack',
                                              'name': 'ostack'}],
                                physical_domains=[{'name': 'phys'}])] +
                ([nat_vrf] if nat_vrf_name is None else []))

    @base.requires(['foreign_keys'])
    def test_l3outside(self):
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT')
        res = self.ns.create_l3outside(self.ctx, l3out)
        self.assertIsNotNone(res)
        other_objs = self._get_l3out_objects()
        l3out.vrf_name = 'EXT-o1'
        self._verify(present=[l3out] + other_objs)

        get_objs = self.ns.get_l3outside_resources(self.ctx, l3out)
        other_objs.append(l3out)
        self._assert_res_list_eq(get_objs, other_objs)

        self.ns.delete_l3outside(self.ctx, l3out)
        self._verify(absent=[l3out] + other_objs)

        get_objs = self.ns.get_l3outside_resources(self.ctx, l3out)
        self.assertEqual([], get_objs)

    @base.requires(['foreign_keys'])
    def test_l3outside_multiple(self):
        l3out1 = a_res.L3Outside(tenant_name='t1', name='o1',
                                 display_name='OUT')
        self.ns.create_l3outside(self.ctx, l3out1)
        other_objs1 = self._get_l3out_objects()
        l3out1.vrf_name = 'EXT-o1'

        l3out2 = a_res.L3Outside(tenant_name='t1', name='o2',
                                 display_name='OUT2')
        self.ns.create_l3outside(self.ctx, l3out2)
        other_objs2 = self._get_l3out_objects('o2', 'OUT2')
        l3out2.vrf_name = 'EXT-o2'
        self._verify(present=[l3out1, l3out2] + other_objs1 + other_objs2)

        self.ns.delete_l3outside(self.ctx, l3out1)
        self._verify(present=[l3out2] + other_objs2)

        self.ns.delete_l3outside(self.ctx, l3out2)
        self._verify(absent=[l3out1, l3out2] + other_objs1 + other_objs2)

    @base.requires(['foreign_keys'])
    def test_l3outside_pre(self, ownership_change=False):
        self.mgr.create(self.ctx, a_res.Tenant(name='t1'))
        vrf = a_res.VRF(tenant_name='t1', name='ctx1', monitored=True)
        self.mgr.create(self.ctx, vrf)
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT', vrf_name='ctx1',
                                monitored=True)
        self.mgr.create(self.ctx, l3out)
        self.ns.create_l3outside(self.ctx, l3out)
        other_objs = self._get_l3out_objects(nat_vrf_name='ctx1')
        if ownership_change:
            l3out.monitored = False
        self._verify(present=[l3out, vrf] + other_objs)

        get_objs = self.ns.get_l3outside_resources(self.ctx, l3out)
        self._assert_res_list_eq(other_objs + [l3out, vrf], get_objs)

        self.ns.delete_l3outside(self.ctx, l3out)
        if ownership_change:
            l3out.monitored = True
        self._verify(present=[l3out, vrf], absent=other_objs)

        get_objs = self.ns.get_l3outside_resources(self.ctx, l3out)
        self.assertEqual([l3out, vrf], get_objs)

    @base.requires(['foreign_keys'])
    def test_subnet(self):
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT')
        self.ns.create_l3outside(self.ctx, l3out)

        self.ns.create_subnet(self.ctx, l3out, '200.10.20.1/28')
        sub = a_res.Subnet(tenant_name='t1', bd_name='EXT-o1',
                           gw_ip_mask='200.10.20.1/28')
        self._verify(present=[sub])

        self._assert_res_eq(sub,
                            self.ns.get_subnet(self.ctx, l3out,
                                               '200.10.20.1/28'))

        self.ns.delete_subnet(self.ctx, l3out, '200.10.20.1/28')
        self._verify(absent=[sub])

        self.assertIsNone(self.ns.get_subnet(self.ctx, l3out,
                                             '200.10.20.1/28'))

    @base.requires(['foreign_keys'])
    def test_external_network(self):
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT')
        self.ns.create_l3outside(self.ctx, l3out)

        ext_net = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1',
            provided_contract_names=['foo'],
            consumed_contract_names=['bar'])
        self.ns.create_external_network(self.ctx, ext_net)
        ext_net.provided_contract_names.append('EXT-o1')
        ext_net.consumed_contract_names.append('EXT-o1')
        self._verify(present=[ext_net])

        self.ns.delete_external_network(self.ctx, ext_net)
        self._verify(absent=[ext_net])

    @base.requires(['foreign_keys'])
    def test_external_network_pre(self):
        self.mgr.create(self.ctx, a_res.Tenant(name='t1'))
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT',
                                monitored=True)
        self.mgr.create(self.ctx, l3out)
        self.ns.create_l3outside(self.ctx, l3out)

        ext_net = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1',
            monitored=True,
            provided_contract_names=['foo'],
            consumed_contract_names=['bar'])
        self.mgr.create(self.ctx, ext_net)

        self.ns.create_external_network(self.ctx, ext_net)
        ext_net.provided_contract_names.append('EXT-o1')
        ext_net.consumed_contract_names.append('EXT-o1')
        self._verify(present=[ext_net])

        self.ns.delete_external_network(self.ctx, ext_net)
        ext_net.provided_contract_names = ['foo']
        ext_net.consumed_contract_names = ['bar']
        self._verify(present=[ext_net])

    @base.requires(['foreign_keys'])
    def test_connect_vrfs(self):
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT')
        ext_net = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1')
        self.mgr.create(self.ctx, a_res.Tenant(name=self.vrf1_tenant_name))
        self.mgr.create(self.ctx, a_res.Tenant(name=self.vrf2_tenant_name))
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_external_network(self.ctx, ext_net)
        self.ns.update_external_cidrs(self.ctx, ext_net,
                                      ['20.20.20.0/24', '50.50.0.0/16'])

        # connect vrf_1
        vrf1 = a_res.VRF(tenant_name=self.vrf1_tenant_name, name='vrf1',
                         display_name='VRF1')
        if self.vrf1_tenant_name != self.bd1_tenant_name:
            self.mgr.create(self.ctx, a_res.Tenant(name='dept1'))
        bd1 = a_res.BridgeDomain(tenant_name=self.bd1_tenant_name, name='bd1',
                                 vrf_name='vrf1')
        self.mgr.create(self.ctx, vrf1)
        self.mgr.create(self.ctx, bd1)
        ext_net.provided_contract_names = ['p1_vrf1', 'p2_vrf1']
        ext_net.consumed_contract_names = ['c1_vrf1', 'c2_vrf1']
        self.ns.connect_vrf(self.ctx, ext_net, vrf1)
        connected_vrfs = self.ns.read_vrfs(self.ctx, ext_net)
        self.assertEqual(vrf1, connected_vrfs[0])
        self._check_connect_vrfs('stage1')

        # connect vrf_1 again - should be no-op
        self.ns.connect_vrf(self.ctx, ext_net, vrf1)
        self._check_connect_vrfs('stage1')

        # connect vrf_2
        vrf2 = a_res.VRF(tenant_name=self.vrf2_tenant_name, name='vrf2',
                         display_name='VRF2')
        bd2 = a_res.BridgeDomain(tenant_name=self.vrf2_tenant_name, name='bd2',
                                 vrf_name='vrf2')
        self.mgr.create(self.ctx, vrf2)
        self.mgr.create(self.ctx, bd2)
        ext_net.provided_contract_names = ['p1_vrf2', 'p2_vrf2']
        ext_net.consumed_contract_names = ['c1_vrf2', 'c2_vrf2']
        self.ns.connect_vrf(self.ctx, ext_net, vrf2)
        self._check_connect_vrfs('stage2')

        # disconnect vrf_1
        self.ns.disconnect_vrf(self.ctx, ext_net, vrf1)
        self._check_connect_vrfs('stage3')

        # disconnect vrf_2
        self.ns.disconnect_vrf(self.ctx, ext_net, vrf2)
        self._check_connect_vrfs('stage4')

    @base.requires(['foreign_keys'])
    def test_vrf_contract_update(self):
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT')
        ext_net = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1')
        self.mgr.create(self.ctx, a_res.Tenant(name=self.vrf1_tenant_name))
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_external_network(self.ctx, ext_net)

        vrf1 = a_res.VRF(tenant_name=self.vrf1_tenant_name, name='vrf1',
                         display_name='VRF1')
        self.mgr.create(self.ctx, vrf1)
        ext_net.provided_contract_names = ['p1_vrf1', 'p2_vrf1']
        ext_net.consumed_contract_names = ['c1_vrf1', 'c2_vrf1']

        self.ns.connect_vrf(self.ctx, ext_net, vrf1)
        self._check_vrf_contract_update('stage1')

        # update contracts
        ext_net.provided_contract_names = ['arp', 'p2_vrf1']
        ext_net.consumed_contract_names = ['arp', 'c2_vrf1']
        self.ns.connect_vrf(self.ctx, ext_net, vrf1)
        self._check_vrf_contract_update('stage2')

        # unset contracts
        ext_net.provided_contract_names = []
        ext_net.consumed_contract_names = []
        self.ns.connect_vrf(self.ctx, ext_net, vrf1)
        self._check_vrf_contract_update('stage3')

    @base.requires(['foreign_keys'])
    def test_external_subnet_update(self):
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT')
        ext_net = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1')
        self.mgr.create(self.ctx, a_res.Tenant(name=self.vrf1_tenant_name))
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_external_network(self.ctx, ext_net)
        self.ns.update_external_cidrs(self.ctx, ext_net,
                                      ['20.20.20.0/24', '50.50.0.0/16'])

        # Connect vrf1 to ext_net
        vrf1 = a_res.VRF(tenant_name=self.vrf1_tenant_name, name='vrf1',
                         display_name='VRF1')
        self.mgr.create(self.ctx, vrf1)
        ext_net.provided_contract_names = ['p1_vrf1', 'p2_vrf1']
        ext_net.consumed_contract_names = ['c1_vrf1', 'c2_vrf1']
        self.ns.connect_vrf(self.ctx, ext_net, vrf1)
        self._check_external_subnet_update("stage1")

        # Add & remove external-subnet
        self.ns.update_external_cidrs(self.ctx, ext_net,
                                      ['100.200.0.0/28', '50.50.0.0/16'])
        self._check_external_subnet_update("stage2")

        # Remove all external-subnets
        self.ns.update_external_cidrs(self.ctx, ext_net, [])
        self._check_external_subnet_update("stage3")

    @base.requires(['foreign_keys'])
    def test_connect_vrf_multiple(self):
        l3out1 = a_res.L3Outside(tenant_name='t1', name='o1',
                                 display_name='OUT')
        ext_net1 = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1')
        self.mgr.create(self.ctx, a_res.Tenant(name=self.vrf1_tenant_name))
        self.ns.create_l3outside(self.ctx, l3out1)
        self.ns.create_external_network(self.ctx, ext_net1)
        self.ns.update_external_cidrs(self. ctx, ext_net1,
                                      ['20.20.20.0/24', '50.50.0.0/16'])

        l3out2 = a_res.L3Outside(tenant_name='t2', name='o2',
                                 display_name='OUT2')
        ext_net2 = a_res.ExternalNetwork(
            tenant_name='t2', l3out_name='o2', name='inet2',
            display_name='INET2')
        self.ns.create_l3outside(self.ctx, l3out2)
        self.ns.create_external_network(self.ctx, ext_net2)
        self.ns.update_external_cidrs(self. ctx, ext_net2,
                                      ['0.0.0.0/0'])

        vrf1 = a_res.VRF(tenant_name=self.vrf1_tenant_name, name='vrf1',
                         display_name='VRF1')
        bd1 = a_res.BridgeDomain(tenant_name=self.vrf1_tenant_name, name='bd1',
                                 vrf_name='vrf1')
        self.mgr.create(self.ctx, vrf1)
        self.mgr.create(self.ctx, bd1)
        ext_net1.provided_contract_names = ['p1_vrf1', 'p2_vrf1']
        ext_net1.consumed_contract_names = ['c1_vrf1', 'c2_vrf1']
        ext_net2.provided_contract_names = ['p3_vrf1', 'p4_vrf1']
        ext_net2.consumed_contract_names = ['c3_vrf1', 'c4_vrf1']
        self.ns.connect_vrf(self.ctx, ext_net1, vrf1)
        self.ns.connect_vrf(self.ctx, ext_net2, vrf1)
        self._check_connect_vrf_multiple('stage1')

        self.ns.disconnect_vrf(self.ctx, ext_net1, vrf1)
        self._check_connect_vrf_multiple('stage2')

        self.ns.disconnect_vrf(self.ctx, ext_net2, vrf1)
        self._check_connect_vrf_multiple('stage3')

    @base.requires(['foreign_keys'])
    def test_delete_ext_net_with_vrf(self):
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT')
        ext_net = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1')
        self.mgr.create(self.ctx, a_res.Tenant(name=self.vrf1_tenant_name))
        self.mgr.create(self.ctx, a_res.Tenant(name=self.vrf2_tenant_name))
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_external_network(self.ctx, ext_net)
        self.ns.update_external_cidrs(self. ctx, ext_net,
                                      ['20.20.20.0/24', '50.50.0.0/16'])

        # Connect vrf1 & vrf2 to ext_net with external-subnet
        vrf1 = a_res.VRF(tenant_name=self.vrf1_tenant_name, name='vrf1',
                         display_name='VRF1')
        self.mgr.create(self.ctx, vrf1)
        ext_net.provided_contract_names = ['p1_vrf1', 'p2_vrf1']
        ext_net.consumed_contract_names = ['c1_vrf1', 'c2_vrf1']
        self.ns.connect_vrf(self.ctx, ext_net, vrf1)

        vrf2 = a_res.VRF(tenant_name=self.vrf2_tenant_name, name='vrf2',
                         display_name='VRF2')
        self.mgr.create(self.ctx, vrf2)
        ext_net.provided_contract_names = ['p1_vrf2', 'p2_vrf2']
        ext_net.consumed_contract_names = ['c1_vrf2', 'c2_vrf2']
        self.ns.connect_vrf(self.ctx, ext_net, vrf2)
        self._check_delete_ext_net_with_vrf('stage1')

        self.ns.delete_external_network(self.ctx, ext_net)
        self._check_delete_ext_net_with_vrf('stage2')

    @base.requires(['foreign_keys'])
    def test_delete_l3outside_with_vrf(self):
        self.mgr.create(self.ctx, a_res.Tenant(name=self.vrf1_tenant_name))
        l3out = a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT')
        ext_net = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1')
        ext_net2 = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1_1',
            display_name='INET1_1')
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_subnet(self.ctx, l3out, '200.10.20.1/28')
        self.ns.create_external_network(self.ctx, ext_net)
        self.ns.create_external_network(self.ctx, ext_net2)
        self.ns.update_external_cidrs(self. ctx, ext_net,
                                      ['20.20.20.0/24', '50.50.0.0/16'])

        # Connect vrf1 to ext_net with external-subnet
        vrf1 = a_res.VRF(tenant_name=self.vrf1_tenant_name, name='vrf1',
                         display_name='VRF1')
        self.mgr.create(self.ctx, vrf1)
        ext_net.provided_contract_names = ['p1_vrf1', 'p2_vrf1']
        ext_net.consumed_contract_names = ['c1_vrf1', 'c2_vrf1']
        self.ns.connect_vrf(self.ctx, ext_net, vrf1)
        self._check_delete_l3outside_with_vrf('stage1')

        self.ns.delete_l3outside(self.ctx, l3out)
        self._check_delete_l3outside_with_vrf('stage2')


class TestDistributedNatStrategy(TestNatStrategyBase,
                                 base.TestAimDBBase):
    strategy = nat_strategy.DistributedNatStrategy
    with_nat_epg = True
    vrf1_tenant_name = 'dept1'
    vrf2_tenant_name = 'dept2'
    bd1_tenant_name = 'dept1'

    def _get_vrf_1_ext_net_1_objects(self):
        return [
            a_res.L3Outside(tenant_name='dept1', name='o1-vrf1',
                            display_name='OUT-VRF1', vrf_name='vrf1'),
            a_res.ExternalNetwork(
                tenant_name='dept1', l3out_name='o1-vrf1',
                name='inet1', display_name='INET1',
                provided_contract_names=['p1_vrf1', 'p2_vrf1'],
                consumed_contract_names=['c1_vrf1', 'c2_vrf1'],
                nat_epg_dn=('uni/tn-t1/ap-myapp/epg-EXT-o1'
                            if self.with_nat_epg else '')),
            a_res.ExternalSubnet(
                tenant_name='dept1', l3out_name='o1-vrf1',
                external_network_name='inet1', cidr='20.20.20.0/24'),
            a_res.ExternalSubnet(
                tenant_name='dept1', l3out_name='o1-vrf1',
                external_network_name='inet1', cidr='50.50.0.0/16')]

    def _get_vrf_1_ext_net_2_objects(self):
        return [
            a_res.L3Outside(tenant_name='dept1', name='o2-vrf1',
                            display_name='OUT2-VRF1', vrf_name='vrf1'),
            a_res.ExternalNetwork(
                tenant_name='dept1', l3out_name='o2-vrf1',
                name='inet2', display_name='INET2',
                provided_contract_names=['p3_vrf1', 'p4_vrf1'],
                consumed_contract_names=['c3_vrf1', 'c4_vrf1'],
                nat_epg_dn=('uni/tn-t2/ap-myapp/epg-EXT-o2'
                            if self.with_nat_epg else '')),
            a_res.ExternalSubnet(
                tenant_name='dept1', l3out_name='o2-vrf1',
                external_network_name='inet2', cidr='0.0.0.0/0')]

    def _get_vrf_2_ext_net_1_objects(self):
        return [
            a_res.L3Outside(tenant_name='dept2', name='o1-vrf2',
                            display_name='OUT-VRF2', vrf_name='vrf2'),
            a_res.ExternalNetwork(
                tenant_name='dept2', l3out_name='o1-vrf2',
                name='inet1', display_name='INET1',
                provided_contract_names=['p1_vrf2', 'p2_vrf2'],
                consumed_contract_names=['c1_vrf2', 'c2_vrf2'],
                nat_epg_dn=('uni/tn-t1/ap-myapp/epg-EXT-o1'
                            if self.with_nat_epg else '')),
            a_res.ExternalSubnet(
                tenant_name='dept2', l3out_name='o1-vrf2',
                external_network_name='inet1', cidr='20.20.20.0/24'),
            a_res.ExternalSubnet(
                tenant_name='dept2', l3out_name='o1-vrf2',
                external_network_name='inet1', cidr='50.50.0.0/16')]

    def _check_connect_vrfs(self, stage):
        en = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1',
            provided_contract_names=['EXT-o1'],
            consumed_contract_names=['EXT-o1'])
        l3out_objs = self._get_l3out_objects()
        v1_e1 = self._get_vrf_1_ext_net_1_objects()
        v2_e1 = self._get_vrf_2_ext_net_1_objects()
        if stage == 'stage1':
            self._verify(present=l3out_objs + [en] + v1_e1)
        elif stage == 'stage2':
            self._verify(present=l3out_objs + [en] + v1_e1 + v2_e1)
        elif stage == 'stage3':
            self._verify(present=l3out_objs + [en] + v2_e1, absent=v1_e1)
        elif stage == 'stage4':
            self._verify(present=l3out_objs + [en], absent=v1_e1 + v2_e1)
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    def _check_connect_vrf_multiple(self, stage):
        v1_e1 = self._get_vrf_1_ext_net_1_objects()
        v1_e2 = self._get_vrf_1_ext_net_2_objects()
        if stage == 'stage1':
            self._verify(present=(v1_e1 + v1_e2))
        elif stage == 'stage2':
            self._verify(present=v1_e2, absent=v1_e1)
        elif stage == 'stage3':
            self._verify(absent=(v1_e1 + v1_e2))
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    def _check_vrf_contract_update(self, stage):
        e1 = a_res.ExternalNetwork(
            tenant_name='dept1', l3out_name='o1-vrf1',
            name='inet1', display_name='INET1',
            provided_contract_names=['p1_vrf1', 'p2_vrf1'],
            consumed_contract_names=['c1_vrf1', 'c2_vrf1'],
            nat_epg_dn=('uni/tn-t1/ap-myapp/epg-EXT-o1'
                        if self.with_nat_epg else ''))
        e2 = copy.deepcopy(e1)
        e2.provided_contract_names = ['arp', 'p2_vrf1']
        e2.consumed_contract_names = ['arp', 'c2_vrf1']

        e3 = copy.deepcopy(e1)
        e3.provided_contract_names = []
        e3.consumed_contract_names = []

        if stage == 'stage1':
            self._verify(present=[e1])
        elif stage == 'stage2':
            self._verify(present=[e2])
        elif stage == 'stage3':
            self._verify(present=[e3])
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    def _check_external_subnet_update(self, stage):
        s1 = a_res.ExternalSubnet(
            tenant_name='dept1', l3out_name='o1-vrf1',
            external_network_name='inet1', cidr='20.20.20.0/24')
        s2 = a_res.ExternalSubnet(
            tenant_name='dept1', l3out_name='o1-vrf1',
            external_network_name='inet1', cidr='100.200.0.0/28')
        s3 = a_res.ExternalSubnet(
            tenant_name='dept1', l3out_name='o1-vrf1',
            external_network_name='inet1', cidr='50.50.0.0/16')

        if stage == 'stage1':
            self._verify(present=[s1])
        elif stage == 'stage2':
            self._verify(present=[s2, s3], absent=[s1])
        elif stage == 'stage3':
            self._verify(absent=[s2, s3])
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    def _check_delete_ext_net_with_vrf(self, stage):
        objs = [a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1',
            display_name='INET1',
            provided_contract_names=['EXT-o1'],
            consumed_contract_names=['EXT-o1'])]
        objs += self._get_vrf_1_ext_net_1_objects()
        objs += self._get_vrf_2_ext_net_1_objects()
        if stage == 'stage1':
            self._verify(present=objs)
        elif stage == 'stage2':
            self._verify(absent=objs)
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    def _check_delete_l3outside_with_vrf(self, stage):
        objs = [a_res.L3Outside(tenant_name='t1', name='o1',
                                display_name='OUT', vrf_name='EXT-o1'),
                a_res.Subnet(tenant_name='t1', bd_name='EXT-o1',
                             gw_ip_mask='200.10.20.1/28'),
                a_res.ExternalNetwork(
                    tenant_name='t1', l3out_name='o1', name='inet1',
                    display_name='INET1',
                    provided_contract_names=['EXT-o1'],
                    consumed_contract_names=['EXT-o1']),
                a_res.ExternalNetwork(
                    tenant_name='t1', l3out_name='o1', name='inet1_1',
                    display_name='INET1_1',
                    provided_contract_names=['EXT-o1'],
                    consumed_contract_names=['EXT-o1'])]
        objs += self._get_vrf_1_ext_net_1_objects()
        objs += self._get_l3out_objects()
        if stage == 'stage1':
            self._verify(present=objs)
        elif stage == 'stage2':
            self._verify(absent=objs)
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)


class TestEdgeNatStrategy(TestDistributedNatStrategy):
    strategy = nat_strategy.EdgeNatStrategy
    with_nat_epg = False


class TestNoNatStrategy(TestNatStrategyBase, base.TestAimDBBase):
    strategy = nat_strategy.NoNatStrategy
    vrf1_tenant_name = 'common'
    vrf2_tenant_name = 't1'
    bd1_tenant_name = 't1'

    @base.requires(['foreign_keys'])
    def test_l3outside_pre(self):
        super(TestNoNatStrategy, self).test_l3outside_pre(
            ownership_change=True)

    def _get_vrf_1_ext_net_1_objects(self, connected=True):
        return {
            'l3out': a_res.L3Outside(
                tenant_name='t1', name='o1',
                display_name='OUT',
                vrf_name='vrf1' if connected else 'EXT-o1'),
            'ext_net': a_res.ExternalNetwork(
                tenant_name='t1', l3out_name='o1',
                name='inet1', display_name='INET1',
                provided_contract_names=(
                    ['EXT-o1', 'p1_vrf1', 'p2_vrf1']
                    if connected else ['EXT-o1']),
                consumed_contract_names=(
                    ['EXT-o1', 'c1_vrf1', 'c2_vrf1']
                    if connected else ['EXT-o1'])),
            'nat_bd': a_res.BridgeDomain(
                tenant_name='t1', name='EXT-o1',
                display_name='EXT-OUT',
                vrf_name='vrf1' if connected else 'EXT-o1',
                l3out_names=['o1']),
            'ext_sub_1': a_res.ExternalSubnet(
                tenant_name='t1', l3out_name='o1',
                external_network_name='inet1', cidr='20.20.20.0/24'),
            'ext_sub_2': a_res.ExternalSubnet(
                tenant_name='t1', l3out_name='o1',
                external_network_name='inet1', cidr='50.50.0.0/16')}

    def _get_vrf_1_ext_net_2_objects(self, connected=True):
        return {
            'l3out': a_res.L3Outside(
                tenant_name='t2', name='o2',
                display_name='OUT2',
                vrf_name='vrf1' if connected else 'EXT-o2'),
            'ext_net': a_res.ExternalNetwork(
                tenant_name='t2', l3out_name='o2',
                name='inet2', display_name='INET2',
                provided_contract_names=(
                    ['EXT-o2', 'p3_vrf1', 'p4_vrf1']
                    if connected else ['EXT-o2']),
                consumed_contract_names=(
                    ['EXT-o2', 'c3_vrf1', 'c4_vrf1']
                    if connected else ['EXT-o2'])),
            'nat_bd': a_res.BridgeDomain(
                tenant_name='t2', name='EXT-o2',
                display_name='EXT-OUT2',
                vrf_name='vrf1' if connected else 'EXT-o2',
                l3out_names=['o2']),
            'ext_sub_1': a_res.ExternalSubnet(
                tenant_name='t2', l3out_name='o2',
                external_network_name='inet2', cidr='0.0.0.0/0')}

    def _check_connect_vrfs(self, stage):
        objs = self._get_vrf_1_ext_net_1_objects()
        l3out = objs['l3out']
        ext_net = objs['ext_net']
        nat_bd = objs['nat_bd']
        l3out_objs = [o for o in self._get_l3out_objects()
                      if not isinstance(o, a_res.BridgeDomain)]
        bd1 = a_res.BridgeDomain(tenant_name='t1', name='bd1',
                                 vrf_name='vrf1',
                                 l3out_names=['o1'])
        bd2 = a_res.BridgeDomain(tenant_name='t1', name='bd2',
                                 vrf_name='vrf2',
                                 l3out_names=['o1'])
        if stage == 'stage1':
            self._verify(present=objs.values() + l3out_objs + [bd1])
        elif stage == 'stage2' or stage == 'stage3':
            bd1.l3out_names = []
            l3out.vrf_name = 'vrf2'
            nat_bd.vrf_name = 'vrf2'
            ext_net.provided_contract_names = ['EXT-o1', 'p1_vrf2', 'p2_vrf2']
            ext_net.consumed_contract_names = ['EXT-o1', 'c1_vrf2', 'c2_vrf2']
            self._verify(present=objs.values() + l3out_objs + [bd1, bd2])
        elif stage == 'stage4':
            bd1.l3out_names = []
            bd2.l3out_names = []
            l3out.vrf_name = 'EXT-o1'
            nat_bd.vrf_name = 'EXT-o1'
            ext_net.provided_contract_names = ['EXT-o1']
            ext_net.consumed_contract_names = ['EXT-o1']
            self._verify(present=objs.values() + l3out_objs + [bd1, bd2])
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    def _check_vrf_contract_update(self, stage):
        objs = self._get_vrf_1_ext_net_1_objects()
        objs.pop('ext_sub_1')
        objs.pop('ext_sub_2')
        e1 = objs.pop('ext_net')
        objs = objs.values()

        e2 = copy.deepcopy(e1)
        e2.provided_contract_names = ['EXT-o1', 'arp', 'p2_vrf1']
        e2.consumed_contract_names = ['EXT-o1', 'arp', 'c2_vrf1']

        e3 = copy.deepcopy(e1)
        e3.provided_contract_names = ['EXT-o1']
        e3.consumed_contract_names = ['EXT-o1']

        if stage == 'stage1':
            self._verify(present=objs + [e1])
        elif stage == 'stage2':
            self._verify(present=objs + [e2])
        elif stage == 'stage3':
            self._verify(present=objs + [e3])
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    def _check_external_subnet_update(self, stage):
        s1 = a_res.ExternalSubnet(
            tenant_name='t1', l3out_name='o1',
            external_network_name='inet1', cidr='20.20.20.0/24')
        s2 = a_res.ExternalSubnet(
            tenant_name='t1', l3out_name='o1',
            external_network_name='inet1', cidr='100.200.0.0/28')
        s3 = a_res.ExternalSubnet(
            tenant_name='t1', l3out_name='o1',
            external_network_name='inet1', cidr='50.50.0.0/16')

        if stage == 'stage1':
            self._verify(present=[s1])
        elif stage == 'stage2':
            self._verify(present=[s2, s3], absent=[s1])
        elif stage == 'stage3':
            self._verify(absent=[s2, s3])
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    def _check_connect_vrf_multiple(self, stage):
        if stage == 'stage1':
            v1_e1 = self._get_vrf_1_ext_net_1_objects().values()
            v1_e2 = self._get_vrf_1_ext_net_2_objects().values()
        elif stage == 'stage2':
            v1_e1 = self._get_vrf_1_ext_net_1_objects(connected=False).values()
            v1_e2 = self._get_vrf_1_ext_net_2_objects().values()
        elif stage == 'stage3':
            v1_e1 = self._get_vrf_1_ext_net_1_objects(connected=False).values()
            v1_e2 = self._get_vrf_1_ext_net_2_objects(connected=False).values()
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)
        self._verify(present=(v1_e1 + v1_e2))

    def _check_delete_ext_net_with_vrf(self, stage):
        if stage == 'stage1':
            objs = self._get_vrf_1_ext_net_1_objects()
            objs['l3out'].vrf_name = 'vrf2'
            objs['nat_bd'].vrf_name = 'vrf2'
            objs['ext_net'].provided_contract_names = ['EXT-o1', 'p1_vrf2',
                                                       'p2_vrf2']
            objs['ext_net'].consumed_contract_names = ['EXT-o1', 'c1_vrf2',
                                                       'c2_vrf2']
            self._verify(present=objs.values())
        elif stage == 'stage2':
            objs = self._get_vrf_1_ext_net_1_objects(connected=False)
            l3out = objs.pop('l3out')
            nat_bd = objs.pop('nat_bd')
            l3out.vrf_name = 'EXT-o1'
            nat_bd.vrf_name = 'EXT-o1'
            self._verify(present=[l3out, nat_bd], absent=objs.values())
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    def _check_delete_l3outside_with_vrf(self, stage):
        objs = self._get_vrf_1_ext_net_1_objects()
        if stage == 'stage1':
            self._verify(present=objs.values())
        elif stage == 'stage2':
            self._verify(absent=objs.values())
        else:
            self.assertFalse(True, 'Unknown test stage %s' % stage)

    @base.requires(['foreign_keys'])
    def test_connect_vrf_wrong_tenant(self):
        vrf = a_res.VRF(tenant_name='dept1', name='vrf', display_name='VRF')

        l3out = a_res.L3Outside(tenant_name='t1', name='o1')
        ext_net = a_res.ExternalNetwork(
            tenant_name='t1', l3out_name='o1', name='inet1')
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_external_network(self.ctx, ext_net)

        self.assertRaises(nat_strategy.VrfNotVisibleFromExternalNetwork,
                          self.ns.connect_vrf, self.ctx, ext_net, vrf)

        l3out.tenant_name = 'common'
        ext_net.tenant_name = 'common'
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_external_network(self.ctx, ext_net)

        self.assertRaises(nat_strategy.VrfNotVisibleFromExternalNetwork,
                          self.ns.connect_vrf, self.ctx, ext_net, vrf)

    @base.requires(['foreign_keys'])
    def test_bd_l3out_vrf_in_common(self):
        self.mgr.create(self.ctx, a_res.Tenant(name='common'))
        self.mgr.create(self.ctx, a_res.Tenant(name='dept1'))
        self.mgr.create(self.ctx, a_res.Tenant(name='dept2'))
        self.mgr.create(self.ctx, a_res.Tenant(name='dept3'))

        vrf = a_res.VRF(tenant_name='common', name='default')
        bd1_dept1 = a_res.BridgeDomain(tenant_name='dept1', name='bd1',
                                       vrf_name='default')
        bd2_dept1 = a_res.BridgeDomain(tenant_name='dept1', name='bd2',
                                       vrf_name='default')
        bd1_dept2 = a_res.BridgeDomain(tenant_name='dept2', name='bd1',
                                       vrf_name='default')
        vrf_dept2 = a_res.VRF(tenant_name='dept2', name='default')
        bd1_dept3 = a_res.BridgeDomain(tenant_name='dept3', name='bd1',
                                       vrf_name='default')
        bd2_dept3 = a_res.BridgeDomain(tenant_name='dept3', name='bd2',
                                       vrf_name='foo')
        for o in [vrf, bd1_dept1, bd2_dept1, bd1_dept2, vrf_dept2,
                  bd1_dept3, bd2_dept3]:
            self.mgr.create(self.ctx, o)

        # test with 'common' l3out
        l3out = a_res.L3Outside(tenant_name='common', name='o1')
        ext_net = a_res.ExternalNetwork(
            tenant_name='common', l3out_name='o1', name='inet1')
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_external_network(self.ctx, ext_net)

        self._verify(present=[bd1_dept1, bd2_dept1, bd1_dept2, bd1_dept3,
                              bd2_dept3])

        self.ns.connect_vrf(self.ctx, ext_net, vrf)
        bd1_dept1.l3out_names = ['o1']
        bd2_dept1.l3out_names = ['o1']
        bd1_dept3.l3out_names = ['o1']
        self._verify(present=[bd1_dept1, bd2_dept1, bd1_dept2, bd1_dept3,
                              bd2_dept3])

        self.ns.disconnect_vrf(self.ctx, ext_net, vrf)
        bd1_dept1.l3out_names = []
        bd2_dept1.l3out_names = []
        bd1_dept3.l3out_names = []
        self._verify(present=[bd1_dept1, bd2_dept1, bd1_dept2, bd1_dept3,
                              bd2_dept3])

        # test with l3out in specific tenant
        l3out.tenant_name = 'dept1'
        ext_net.tenant_name = 'dept1'
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_external_network(self.ctx, ext_net)

        self.ns.connect_vrf(self.ctx, ext_net, vrf)
        bd1_dept1.l3out_names = ['o1']
        bd2_dept1.l3out_names = ['o1']
        self._verify(present=[bd1_dept1, bd2_dept1, bd1_dept2, bd1_dept3,
                              bd2_dept3])

        self.ns.disconnect_vrf(self.ctx, ext_net, vrf)
        bd1_dept1.l3out_names = []
        bd2_dept1.l3out_names = []
        self._verify(present=[bd1_dept1, bd2_dept1, bd1_dept2, bd1_dept3,
                              bd2_dept3])

    @base.requires(['foreign_keys'])
    def test_bd_l3out_vrf_in_tenant(self):
        self.mgr.create(self.ctx, a_res.Tenant(name='dept1'))
        vrf = a_res.VRF(tenant_name='dept1', name='default')
        bd1_dept1 = a_res.BridgeDomain(tenant_name='dept1', name='bd1',
                                       vrf_name='default')
        bd2_dept1 = a_res.BridgeDomain(tenant_name='dept1', name='bd2',
                                       vrf_name='foo')
        for o in [vrf, bd1_dept1, bd2_dept1]:
            self.mgr.create(self.ctx, o)

        l3out = a_res.L3Outside(tenant_name='dept1', name='o1')
        ext_net = a_res.ExternalNetwork(
            tenant_name='dept1', l3out_name='o1', name='inet1')
        self.ns.create_l3outside(self.ctx, l3out)
        self.ns.create_external_network(self.ctx, ext_net)

        self._verify(present=[bd1_dept1, bd2_dept1])

        self.ns.connect_vrf(self.ctx, ext_net, vrf)
        bd1_dept1.l3out_names = ['o1']
        self._verify(present=[bd1_dept1, bd2_dept1])

        self.ns.disconnect_vrf(self.ctx, ext_net, vrf)
        bd1_dept1.l3out_names = []
        self._verify(present=[bd1_dept1, bd2_dept1])
