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
test_aim_manager
----------------------------------

Tests for `aim_manager` module.
"""

import mock

from aim import aim_manager
from aim.api import resource
from aim import exceptions as exc
from aim.tests import base


class TestAimManager(base.TestAimDBBase):

    def setUp(self):
        super(TestAimManager, self).setUp()
        self.mgr = aim_manager.AimManager()

    def test_resource_ops(self):
        bd = resource.BridgeDomain(tenant_rn='foo', rn='net1')
        self.mgr.create(self.ctx, bd)

        r1 = self.mgr.get(self.ctx, bd)
        self.assertEqual('net1', r1.rn)
        self.assertEqual('foo', r1.tenant_rn)
        self.assertIsNone(r1.vrf_rn)

        bd.vrf_tenant_rn = 'common'
        self.mgr.create(self.ctx, bd, overwrite=True)

        r2 = self.mgr.get(self.ctx, bd)
        self.assertEqual('net1', r2.rn)
        self.assertEqual('foo', r2.tenant_rn)
        self.assertEqual('common', r2.vrf_tenant_rn)

        rs1 = self.mgr.find(self.ctx, resource.BridgeDomain, tenant_rn='foo')
        self.assertEqual(1, len(rs1))
        self.assertEqual('net1', rs1[0].rn)
        self.assertEqual('foo', rs1[0].tenant_rn)

        self.mgr.update(self.ctx, bd, vrf_rn='shared')
        r3 = self.mgr.get(self.ctx, bd)
        self.assertEqual('net1', r3.rn)
        self.assertEqual('shared', r3.vrf_rn)

        rs2 = self.mgr.find(self.ctx, resource.BridgeDomain, vrf_rn='shared')
        self.assertEqual(1, len(rs2))
        self.assertEqual('net1', rs2[0].rn)
        self.assertEqual('foo', rs2[0].tenant_rn)

        self.mgr.delete(self.ctx, bd)
        self.assertIsNone(self.mgr.get(self.ctx, bd))
        self.assertEqual([], self.mgr.find(self.ctx, resource.BridgeDomain))

    def test_resource_negative(self):
        self.assertRaises(
            exc.IdentityAttributesMissing, resource.BridgeDomain, foo='a')

        class bad_resource(object):
            pass

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.create, self.ctx, bad_resource())

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.update, self.ctx, bad_resource())

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.delete, self.ctx, bad_resource())

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.get, self.ctx, bad_resource())

        self.assertRaises(
            exc.UnknownResourceType, self.mgr.find, self.ctx, bad_resource)

    def test_commit_hook(self):
        listener = mock.Mock()
        listener.__name__ = 'mock-listener'
        self.mgr.register_update_listener(listener)

        bd = resource.BridgeDomain(tenant_rn='foo', rn='net1')
        self.mgr.create(self.ctx, bd)
        listener.assert_called_with(mock.ANY, [bd], [], [])

        listener.reset_mock()
        self.mgr.update(self.ctx, bd, vrf_rn='shared')
        bd.vrf_rn = 'shared'
        listener.assert_called_with(mock.ANY, [], [bd], [])

        listener.reset_mock()
        bd.rn = 'net2'
        self.mgr.create(self.ctx, bd)
        listener.assert_called_with(mock.ANY, [bd], [], [])

        listener.reset_mock()
        self.mgr.delete(self.ctx, bd)
        listener.assert_called_with(mock.ANY, [], [], [bd])

        self.mgr.unregister_update_listener(listener)

        listener.reset_mock()
        bd.rn = 'net1'
        self.mgr.delete(self.ctx, bd)
        self.assertFalse(listener.called)
