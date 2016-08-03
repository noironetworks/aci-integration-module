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

from aim import config
from aim.tests.unit.tools.cli import test_shell as base


cfg.CONF.register_opts(config.global_opts)


class TestDBConfig(base.TestShell):

    def setUp(self):
        super(TestDBConfig, self).setUp()
        self.manager = config.ConfigManager(self.ctx, '')

    def test_aim_db_config(self):
        # aim config
        result = self.run_command('config')
        self.assertTrue('Usage:' in result.output)

    def test_config_update_no_host(self):
        self.run_command('config update')
        self.assertEqual(
            ['1.1.1.1', '1.1.1.2', '1.1.1.3'],
            self.manager.get_option('apic_hosts', 'apic'))

    def test_replace_all_no_host(self):
        self.run_command('config replace')
        self.assertEqual(
            ['1.1.1.1', '1.1.1.2', '1.1.1.3'],
            self.manager.get_option('apic_hosts', 'apic'))
        self.run_command('config replace', config_file='aim.conf.test.2')
        self.assertEqual(
            ['1.1.1.4', '1.1.1.5', '1.1.1.6'],
            self.manager.get_option('apic_hosts', 'apic'))

    def test_set_default_values(self):
        self.run_command('config replace', config_file='aim.conf.test.empty')
        # All default values are set, can be useful for first time
        # installations
        self.assertEqual(
            5, self.manager.get_option('agent_polling_interval', 'aim'))
        self.assertEqual(
            [], self.manager.get_option('apic_hosts', 'apic'))
