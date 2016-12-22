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

from aim import aim_manager
from aim.api import infra
from aim import config  # noqa
from aim.db import infra_model
from aim.tests import base


class TestAimInfraManager(base.TestAimDBBase):

    def setUp(self):
        super(TestAimInfraManager, self).setUp()
        self.mgr = aim_manager.AimManager()
        self.infra_mgr = infra_model.HostLinkManager(self.ctx, self.mgr)

    def test_infra_manager(self):
        host, ifname, ifmac, swid, module, port, path = (
            'f5-compute-2.noiro.lab', 'opflex1', 'd4:6d:50:dc:72:5f', 101,
            1, 1, 'topology/pod-1/paths-101/pathep-[eth1/1]')
        self.infra_mgr.add_hostlink(host, ifname, ifmac, swid, module, port,
                                    path)
        hlinks_mgr = self.mgr.find(self.ctx, infra.HostLink)
        self.assertEqual(1, len(hlinks_mgr))

        hlink = self.infra_mgr.get_hostlink(host, ifname)
        self.assertEqual(hlink.path, hlinks_mgr[0].path)

        hlinks = self.infra_mgr.get_hostlinks()
        self.assertEqual(1, len(hlinks))
        self.assertEqual(hlinks[0].path, hlinks_mgr[0].path)

        host2, ifname2, ifmac2, swid2, module2, port2, path2 = (
            'f6-compute-2.noiro.lab', 'opflex1', 'd4:6d:50:dc:72:55', 102,
            2, 2, 'topology/pod-1/paths-102/pathep-[eth2/2]')
        self.infra_mgr.add_hostlink(
            host2, ifname2, ifmac2, swid2, module2, port2, path2)

        hlinks = self.infra_mgr.get_hostlinks_for_host(
            'f5-compute-2.noiro.lab')
        self.assertEqual(hlinks[0].path, hlinks_mgr[0].path)

        hlinks = self.infra_mgr.get_hostlinks_for_host_switchport(
            host, swid, module, port)
        self.assertEqual(hlinks[0].path, hlinks_mgr[0].path)

        hlinks = self.infra_mgr.get_hostlinks_for_switchport(
            swid, module, port)
        self.assertEqual(hlinks[0].path, hlinks_mgr[0].path)

        hlinks = self.infra_mgr.get_modules_for_switch(swid)
        self.assertEqual(hlinks[0][0], hlinks_mgr[0].module)

        hlinks = self.infra_mgr.get_ports_for_switch_module(swid, module)
        self.assertEqual(hlinks[0][0], hlinks_mgr[0].port)

        hlinks = self.infra_mgr.get_switch_and_port_for_host(host)
        self.assertEqual(hlinks[0][0], hlinks_mgr[0].switch_id)

        self.infra_mgr.delete_hostlink(host, ifname)
        # Idempotent
        self.infra_mgr.delete_hostlink(host, ifname)
        self.infra_mgr.delete_hostlink(host2, ifname2)
        self.assertEqual(0, len(self.mgr.find(self.ctx, infra.HostLink)))
