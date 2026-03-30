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
test_utils
----------------------------------

Tests for `utils` module.
"""

import mock

from aim.common import utils as internal_utils
from aim.db import model_base
from aim.tests import base
from aim import utils


class TestUtils(base.TestAimDBBase):

    def test_sanitize_display_name(self):
        self.assertEqual(
            's0m_e_N.a_me-_',
            utils.sanitize_display_name('s0m_e N.a/me-+'))

        self.assertEqual(
            'some' * 14 + 'som',
            utils.sanitize_display_name('some' * 15))

    def test_sanitize_description(self):
        self.assertEqual(
            '', utils.sanitize_description(None))
        self.assertEqual(
            '_eF5\\!#$%()*,-./:;@ _{|}~?&+_',
            utils.sanitize_description('\'eF5\\!#$%()*,-./:;@ _{|}~?&+\"'))
        self.assertEqual(
            'somed' * 24 + 'some',
            utils.sanitize_description('somed' * 25))

    def test_get_backoff_time_with_big_tentative(self):
        tentative = 10240
        tentative = internal_utils.get_backoff_time(600, tentative)
        self.assertEqual(600, tentative)

    def test_exponential_backoff(self):
        with mock.patch.object(internal_utils.random, 'random',
                               return_value=1):
            with mock.patch.object(internal_utils.time, 'sleep') as sleep:
                tentative = None
                tentative = internal_utils.exponential_backoff(10, tentative)
                self.assertEqual(1, tentative.get())
                sleep.assert_called_with(1)
                tentative.increment()
                tentative = internal_utils.exponential_backoff(10, tentative)
                self.assertEqual(3, tentative.get())
                sleep.assert_called_with(4)
                tentative.increment()
                tentative.increment()
                internal_utils.exponential_backoff(10, tentative)
                sleep.assert_called_with(10)

    def test_harakiri(self):
        original = self.cfg_manager.get_option('recovery_restart', 'aim')
        self.set_override('recovery_restart', False, 'aim')
        with mock.patch.object(internal_utils.os, '_exit') as ex:
            internal_utils.perform_harakiri(mock.Mock(), '')
            self.assertEqual(0, ex.call_count)
            self.set_override('recovery_restart', True, 'aim')
            internal_utils.perform_harakiri(mock.Mock(), '')
            ex.assert_called_once_with(1)
        self.set_override('recovery_restart', original, 'aim')

    def test_sanitize_name(self):
        self.assertEqual(
            'z23tosoitfutobxn4hrqzgjjwp6v3wjgcy4ddqx3rpkb43x3ceta',
            internal_utils.sanitize_name('test'))
        self.assertEqual(
            'xz4j2rrayb4ebrjdzc4rmrudirw6sp7bggcpjrihdav4zrw3mtnq',
            internal_utils.sanitize_name('test', 'a', 'b', 'c'))
        self.assertEqual(
            'esy7rw6xsfko2pbtocshyccpkcni7rrsngh7wehjskc66pgh2gha',
            internal_utils.sanitize_name('test', '0', '1', '9'))
        self.assertEqual(
            'ksult6xm2m6vu47vcmwfvsly27x7ai4whduys5mruzcn5qogs6pq',
            internal_utils.sanitize_name('test', 'AA', 'BB', 'ZZ'))
        self.assertEqual(
            'vvxojw5rwlmq6abg3trx6nchbffez4lxfhalgidxlyhtlh3r4jwq',
            internal_utils.sanitize_name('test', 'a -', '-', '_'))

    def test_decompose_dn(self):
        dn = 'uni/tn-common/brc-p/subj-p/intmnl/rsfiltAtt-p'
        type = 'vzRsFiltAtt'
        self.assertEqual(
            [('fvTenant', 'common'), ('vzBrCP', 'p'), ('vzSubj', 'p'),
             ('vzInTerm', 'intmnl'), ('vzRsFiltAtt', 'p')],
            internal_utils.decompose_dn(type, dn))

    def test_decompose_dn_preserves_case(self):
        dn = 'uni/tn-TenantA/ap-AppProfileA/epg-MyEPG'
        type = 'fvAEPg'
        self.assertEqual(
            [('fvTenant', 'TenantA'), ('fvAp', 'AppProfileA'),
             ('fvAEPg', 'MyEPG')],
            internal_utils.decompose_dn(type, dn))

    def test_decompose_dn_preserves_case_for_relation_dn(self):
        dn = 'uni/tn-common/out-fab2021_2/instP-fab2021_2/'
        dn += 'rsprov-ostack-pt-1-s1_EXT-fab2021_2'
        type = 'fvRsProv'
        self.assertEqual(
            [('fvTenant', 'common'), ('l3extOut', 'fab2021_2'),
             ('l3extInstP', 'fab2021_2'),
             ('fvRsProv', 'ostack-pt-1-s1_EXT-fab2021_2')],
            internal_utils.decompose_dn(type, dn))

    def test_decompose_dn_no_arg_rn(self):
        dn = 'uni/vmmp-OpenStack/dom-ostack-pt-1-s1/rsvlanNs'
        type = 'infraRsVlanNs'
        self.assertEqual(
            [('vmmProvP', 'OpenStack'), ('vmmDomP', 'ostack-pt-1-s1'),
             ('infraRsVlanNs', 'rsvlanNs')],
            internal_utils.decompose_dn(type, dn))

    def test_retrieve_rns_skips_no_arg_rns(self):
        dn = 'uni/vmmp-OpenStack/dom-ostack-pt-1-s1/rsvlanNs'
        type = 'infraRsVlanNs'
        self.assertEqual(
            ['OpenStack', 'ostack-pt-1-s1'],
            internal_utils.retrieve_rns(dn, type))

    def test_retrieve_rns_flattens_multi_param_rns(self):
        dn = 'uni/infra/vlanns-[ostack-pt-1-s1_vlan_ns]-dynamic'
        type = 'fvnsVlanInstP'
        self.assertEqual(
            ['ostack-pt-1-s1_vlan_ns', 'dynamic'],
            internal_utils.retrieve_rns(dn, type))

    def test_decompose_dn_prefers_explicit_type_for_oob_contract(self):
        dn = 'uni/tn-common/oobbrc-default/subj-default'
        type = 'vzSubj__tn'
        self.assertEqual(
            [('fvTenant', 'common'), ('vzOOBBrCP', 'default'),
             ('vzSubj__tn', 'default')],
            internal_utils.decompose_dn(type, dn))

    def test_name_columns_are_case_sensitive(self):
        column = model_base.name_column()
        self.assertEqual(64, column.type.length)
        self.assertEqual('latin1', column.type.charset)
        self.assertEqual('latin1_bin', column.type.collation)

    @internal_utils.rlock('test')
    def locked_func(self):
        with internal_utils.get_rlock('test2'):
            pass

    def test_cover_lock(self):
        internal_utils.all_locks = {}
        self.assertTrue('test' not in internal_utils.all_locks)
        self.locked_func()
        self.assertTrue('test' in internal_utils.all_locks)
        self.assertTrue('test2' in internal_utils.all_locks)
        self.assertEqual(2, len(internal_utils.all_locks))
