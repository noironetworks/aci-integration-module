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

import mock

from aim import config
from aim.db import config_model
from aim import exceptions as exc
from aim.tests import base


class TestAimConfig(base.TestAimDBBase):

    def setUp(self):
        super(TestAimConfig, self).setUp()
        self._clean_subscriptions()
        self.cfg_mgr = self.cfg_manager
        # Clean current map state for testing
        self.db_mgr = config_model.ConfigurationDBManager()
        self.addCleanup(self._clean_subscriptions)

    def _clean_subscriptions(self):
        # Garbage collect the subs manager
        config.OPTION_SUBSCRIBER_MANAGER = None

    def test_to_db(self):
        config.CONF.set_override(
            'apic_hosts', ['1.1.1.1', '1.1.1.2', '1.1.1.3'], 'apic')
        config.CONF.set_override('openstack_user', 'user1', 'apic')
        config.CONF.set_override('verify_ssl_certificate', True, 'apic')
        config.CONF.set_override('apic_request_timeout', 15, 'apic')
        config.CONF.set_override('aim_system_id', 'my_id', 'aim')
        self.cfg_mgr.to_db(config.CONF, context=self.ctx)
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
            'my_id', self.cfg_mgr.get_option('aim_system_id', 'aim'))

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
        self.cfg_mgr.to_db(config.CONF, context=self.ctx)
        self.cfg_mgr.to_db(config.CONF, context=self.ctx)
        self.assertEqual(
            ['1.1.1.1', '1.1.1.2', '1.1.1.3'],
            self.cfg_mgr.get_option('apic_hosts', 'apic'))

    def test_version_change(self):
        v1 = self.cfg_mgr.db._get(self.ctx, 'apic', 'apic_hosts').version
        self.set_override(
            'apic_hosts', ['1.1.1.4', '1.1.1.5', '1.1.1.6'], 'apic')
        v2 = self.cfg_mgr.db._get(self.ctx, 'apic', 'apic_hosts').version
        self.assertNotEqual(v1, v2)

    def test_get_changed_1(self):
        v1 = self.cfg_mgr.db._to_dict(self.cfg_mgr.db._get(self.ctx, 'apic',
                                                           'apic_hosts'))
        self.set_override(
            'apic_hosts', ['1.1.1.4', '1.1.1.5', '1.1.1.6'], 'apic')
        v2 = self.cfg_mgr.db.get_changed(
            self.ctx, {(v1['group'], v1['key'], v1['host']): v1['version']})
        self.assertEqual(1, len(v2))
        self.assertEqual(v1['key'], v2[0]['key'])
        self.assertNotEqual(v1['version'], v2[0]['version'])
        self.assertNotEqual(v1['value'], v2[0]['value'])

    def test_get_changed_n(self):
        conf_map = {
            ('apic', 'apic_hosts', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'apic',
                                     'apic_hosts'))['version'],

            ('aim', 'aim_system_id', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'aim',
                                     'aim_system_id'))['version'],

            ('apic', 'apic_request_timeout', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'apic',
                                     'apic_request_timeout'))['version'],

            ('apic', 'verify_ssl_certificate', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'apic',
                                     'verify_ssl_certificate'))['version'],

            ('apic', 'openstack_user', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'apic',
                                     'openstack_user'))['version'],
        }

        self.set_override(
            'apic_hosts', ['1.1.1.1', '1.1.1.2', '1.1.1.4'], 'apic')
        self.set_override('verify_ssl_certificate', True, 'apic')
        self.set_override('apic_request_timeout', 20, 'apic')
        self.set_override('aim_system_id', 'my_id_plus', 'aim')

        # Not changing openstack_user
        v2 = self.cfg_mgr.db.get_changed(self.ctx, conf_map)
        self.assertEqual(4, len(v2))

    def test_get_changed_0(self):
        conf_map = {
            ('apic', 'apic_hosts', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'apic',
                                     'apic_hosts'))['version'],

            ('aim', 'aim_system_id', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'aim',
                                     'aim_system_id'))['version'],

            ('apic', 'apic_request_timeout', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'apic',
                                     'apic_request_timeout'))['version'],

            ('apic', 'verify_ssl_certificate', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'apic',
                                     'verify_ssl_certificate'))['version'],

            ('apic', 'openstack_user', ''): self.cfg_mgr.db._to_dict(
                self.cfg_mgr.db._get(self.ctx, 'apic',
                                     'openstack_user'))['version'],
        }
        v2 = self.cfg_mgr.db.get_changed(self.ctx, conf_map)
        self.assertEqual(0, len(v2))

    def test_config_subscribe_noop_no_host(self):
        # Subscription fails if no host is specified
        cfg_mgr = config.ConfigManager(self.ctx)
        # Clean current map state for testing
        cfg_mgr.subs_mgr.map_by_callback_id = {}
        cfg_mgr.subs_mgr.subscription_map = {}
        self.cfg_mgr.get_option_and_subscribe(mock.Mock(), 'apic_hosts',
                                              'apic')
        self.assertEqual({}, cfg_mgr.subs_mgr.subscription_map)
        self.assertEqual({}, cfg_mgr.subs_mgr.map_by_callback_id)

    def test_config_subscribe(self):
        # Get a manager with a host
        cfg_mgr = config.ConfigManager(self.ctx, 'h1')
        # Clean current map state for testing
        cfg_mgr.subs_mgr.map_by_callback_id = {}
        cfg_mgr.subs_mgr.subscription_map = {}
        callback = mock.Mock()
        call_id = cfg_mgr.subs_mgr._get_call_id(callback)
        expected = {'apic': {'apic_hosts': {call_id: {'hosts': set(['h1']),
                                                      'version': mock.ANY,
                                                      'callback': callback}}}}
        expected_rev = {call_id: {'apic': set(['apic_hosts'])}}
        cfg_mgr.get_option_and_subscribe(callback, 'apic_hosts', 'apic')
        self.assertEqual(expected, cfg_mgr.subs_mgr.subscription_map)
        self.assertEqual(expected_rev, cfg_mgr.subs_mgr.map_by_callback_id)

        # Same callback
        cfg_mgr.get_option_and_subscribe(callback, 'aim_system_id', 'aim')
        expected.update(
            {'aim': {'aim_system_id': {call_id: {'hosts': set(['h1']),
                                                 'version': mock.ANY,
                                                 'callback': callback}}}})
        expected_rev[call_id].update({'aim': set(['aim_system_id'])})
        self.assertEqual(expected, cfg_mgr.subs_mgr.subscription_map)
        self.assertEqual(expected_rev, cfg_mgr.subs_mgr.map_by_callback_id)

        # Different callback on same option
        callback_2 = mock.Mock()
        call_id_2 = cfg_mgr.subs_mgr._get_call_id(callback_2)
        cfg_mgr.get_option_and_subscribe(callback_2, 'aim_system_id', 'aim')
        expected['aim']['aim_system_id'].update(
            {call_id_2: {'hosts': set(['h1']),
                         'version': mock.ANY,
                         'callback': callback_2}})
        expected_rev.update({call_id_2: {'aim': set(['aim_system_id'])}})
        self.assertEqual(expected, cfg_mgr.subs_mgr.subscription_map)
        self.assertEqual(expected_rev, cfg_mgr.subs_mgr.map_by_callback_id)

        # Remove specific option
        cfg_mgr.option_unsubscribe(callback, 'apic_hosts', 'apic')
        # This will remove the apic group completely
        expected.pop('apic')
        expected_rev[call_id].pop('apic')
        self.assertEqual(expected, cfg_mgr.subs_mgr.subscription_map)
        self.assertEqual(expected_rev, cfg_mgr.subs_mgr.map_by_callback_id)

        # Now unsubscribe an entire callback
        cfg_mgr.callback_unsubscribe(callback_2)
        # This removed the callback from both maps
        expected_rev.pop(call_id_2)
        expected['aim']['aim_system_id'].pop(call_id_2)
        self.assertEqual(expected, cfg_mgr.subs_mgr.subscription_map)
        self.assertEqual(expected_rev, cfg_mgr.subs_mgr.map_by_callback_id)

        # Unsubscribe last option
        cfg_mgr.option_unsubscribe(callback, 'aim_system_id', 'aim')
        # Maps are now empty
        self.assertEqual({}, cfg_mgr.subs_mgr.subscription_map)
        self.assertEqual({}, cfg_mgr.subs_mgr.map_by_callback_id)

    def test_config_multiple_hosts_same_item_fails(self):
        cfg_mgr = config.ConfigManager(self.ctx, 'h1')
        callback = mock.Mock()
        cfg_mgr.get_option_and_subscribe(callback, 'apic_hosts', 'apic')
        self.assertRaises(
            exc.OneHostPerCallbackItemSubscriptionAllowed,
            cfg_mgr.get_option_and_subscribe, callback, 'apic_hosts', 'apic',
            host='h2')

    def test_poll_and_execute(self):
        cfg_mgr = config.ConfigManager(self.ctx, 'h1')
        callback = mock.Mock()

        # Subscribe to apic hosts
        cfg_mgr.get_option_and_subscribe(callback, 'apic_hosts', 'apic')
        # Polling will have no effect at this time, since apic_hosts hasn't
        # changed
        cfg_mgr.subs_mgr._poll_and_execute()
        self.assertFalse(callback.called)

        # Update apic hosts
        self.set_override('apic_hosts', ['2.2.2.2'], 'apic')
        cfg_mgr.subs_mgr._poll_and_execute()
        callback.assert_called_once_with(
            {'key': 'apic_hosts',
             'host': '',
             'group': 'apic',
             'value': ['2.2.2.2'],
             'version': mock.ANY})
        # Reset mock and verify that the call doesn't happen again
        callback.reset_mock()
        cfg_mgr.subs_mgr._poll_and_execute()
        self.assertFalse(callback.called)

    def test_poll_and_execute_exception(self):
        cfg_mgr = config.ConfigManager(self.ctx, 'h1')
        callback = mock.Mock(side_effect=Exception('expected exception'))

        cfg_mgr.get_option_and_subscribe(callback, 'apic_hosts', 'apic')
        self.set_override('apic_hosts', ['2.2.2.2'], 'apic')

        # Doesn't rise
        cfg_mgr.subs_mgr._poll_and_execute()

    def test_polling_interval_changed(self):
        self._clean_subscriptions()
        cfg_mgr = config.ConfigManager(self.ctx, 'h1')
        # Call property before changing the config value
        cfg_mgr.subs_mgr.polling_interval
        self.set_override('config_polling_interval', 130, 'aim')
        self.assertNotEqual(130, cfg_mgr.subs_mgr.polling_interval)
        cfg_mgr.subs_mgr._poll_and_execute()
        self.assertEqual(130, cfg_mgr.subs_mgr.polling_interval)

    def test_subscriber_singleton(self):
        cfg_mgr1 = config.ConfigManager(self.ctx, 'h1')
        cfg_mgr2 = config.ConfigManager(self.ctx, 'h2')
        self.assertTrue(cfg_mgr1 is not cfg_mgr2)
        self.assertTrue(cfg_mgr1.subs_mgr is cfg_mgr2.subs_mgr)
