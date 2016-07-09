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


from aim import config
from aim.db import config_model
from aim import exceptions as exc
from aim.tests import base


class TestAimConfig(base.TestAimDBBase):

    def setUp(self):
        super(TestAimConfig, self).setUp()
        self.cfg_mgr = config.ConfigManager(self.ctx)
        self.db_mgr = config_model.ConfigurationDBManager()

    def test_to_db(self):
        config.CONF.set_override(
            'apic_hosts', ['1.1.1.1', '1.1.1.2', '1.1.1.3'], 'apic')
        config.CONF.set_override('openstack_user', 'user1', 'apic')
        config.CONF.set_override('verify_ssl_certificate', True, 'apic')
        config.CONF.set_override('apic_request_timeout', 15, 'apic')
        config.CONF.set_override('apic_system_id', 'my_id')
        self.cfg_mgr.to_db(self.ctx, config.CONF)
        self.assertEqual(
            ['1.1.1.1', '1.1.1.2', '1.1.1.3'],
            self.cfg_mgr.get_option('apic_hosts', 'apic'))
        self.assertEqual(
            'user1', self.cfg_mgr.get_option('openstack_user', 'apic'))
        self.assertEqual(
            True, self.cfg_mgr.get_option('verify_ssl_certificate', 'apic'))
        self.assertEqual(
            15, self.cfg_mgr.get_option('apic_request_timeout', 'apic'))
        self.assertEqual(
            'my_id', self.cfg_mgr.get_option('apic_system_id'))

    def test_get_wrong_conf(self):
        self.assertRaises(
            exc.UnsupportedAIMConfig,
            self.cfg_mgr.get_option, 'somestuff', 'apic')
        self.assertRaises(
            exc.UnsupportedAIMConfigGroup,
            self.cfg_mgr.get_option, 'apic_hosts', 'no')

    def test_update_idempotent(self):
        config.CONF.set_override(
            'apic_hosts', ['1.1.1.1', '1.1.1.2', '1.1.1.3'], 'apic')
        self.cfg_mgr.to_db(self.ctx, config.CONF)
        self.cfg_mgr.to_db(self.ctx, config.CONF)
        self.assertEqual(
            ['1.1.1.1', '1.1.1.2', '1.1.1.3'],
            self.cfg_mgr.get_option('apic_hosts', 'apic'))
