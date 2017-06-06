# Copyright (c) 2017 Cisco Systems
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import json
import requests
import time

import acitoolkit

from aim.tests import base
from aim.tests.scenario.server import root


class TestServerMixin(object):

    def GET(self, url, *args, **kwargs):
        return requests.get(
            '%s/%s' % (self.uri, url), *args, **kwargs)

    def POST(self, url, *args, **kwargs):
        return requests.post(
            '%s/%s' % (self.uri, url), *args, **kwargs)

    def DELETE(self, url, **kwargs):
        return requests.delete('%s/%s' % (self.uri, url), **kwargs)

    def _verify_expected_return(self, expected, resp):
        for data in resp.json()['imdata']:
            self.assertTrue(data in expected)
            expected.remove(data)
        self.assertEqual(0, len(expected))

    def _verify_expected_events(self, expected, session, url):
        time.sleep(0.1)
        self.assertTrue(session.has_events(url))
        while session.has_events(url):
            event = session.get_event(url)['imdata'][0]
            self.assertTrue(event in expected,
                            '%s not in %s' % (event, expected))
            expected.remove(event)
        self.assertEqual(0, len(expected))


class TestServer(base.BaseTestCase, TestServerMixin):
    """Test case base class for all scenario tests."""

    def setUp(self):
        super(TestServer, self).setUp()
        self.addCleanup(self.empty_store)
        self.ip, self.port = root.run()
        self.uri = 'http://%s:%s' % (self.ip, self.port)

    def empty_store(self):
        root.shutdown()

    def test_base(self):
        tn = {'fvTenant': {'attributes': {'dn': 'uni/tn-common',
                                          'nameAlies': 'test'}}}
        self.POST('api/mo/uni/tn-common.json', data=json.dumps(tn))
        resp = self.GET('api/mo/uni/tn-common.json')
        self.assertEqual(tn, resp.json()['imdata'][0])
        self.DELETE('api/mo/uni/tn-common.json')
        resp = self.GET('api/mo/uni/tn-common.json')
        self.assertEqual(404, resp.status_code)

    def test_error(self):
        resp = self.GET('api/mo/uni/tn-common')
        self.assertEqual(405, resp.status_code)
        self.assertEqual(
            '6', resp.json()['imdata'][0]['error']['attributes']['code'])

    def test_all_or_none(self):
        tn = {
            'fvTenant': {
                'attributes': {'dn': 'uni/tn-common', 'nameAlies': 'test'},
                'children': [
                    {'fvBD': {'attributes': {'name': 'bd'}}},
                    {'fvBD': {'attributes': {'name': 'bd1',
                                             'status': 'deleted'}}}
                ]
            }
        }
        resp = self.POST('api/mo/uni/tn-common.json', data=json.dumps(tn))
        # Object explicitly marked with deleted is not found
        self.assertEqual(404, resp.status_code)
        resp = self.GET('api/mo/uni/tn-common.json')
        self.assertEqual(404, resp.status_code)

    def test_acitoolkit_subscribe(self):
        session = acitoolkit.Session(self.uri, 'admin', pwd='pwd')
        url = ('/api/node/mo/uni/tn-common.json?'
               'subscription=yes&query-target=subtree')
        resp = session.login()
        self.assertEqual(200, resp.status_code)
        session.subscribe(url)
        tn = {
            'fvTenant': {
                'attributes': {'dn': 'uni/tn-common', 'nameAlies': 'test',
                               'status': 'created'}
            }
        }
        self.POST('api/mo/uni/tn-common.json',
                  data=json.dumps(tn), cookies=resp.cookies)
        self._verify_expected_events([tn], session, url)
        tn = {
            'fvTenant': {
                'attributes': {'dn': 'uni/tn-common', 'nameAlies': 'test2'},
                'children': [
                    {'fvBD': {'attributes': {'name': 'bd'}}},
                    {'fvCtx': {'attributes': {'name': 'ctx'}}},
                ]
            }
        }
        self.POST('api/mo/uni/tn-common.json', data=json.dumps(tn),
                  cookies=resp.cookies)
        expected_events = [
            {'fvTenant': {
                'attributes': {'dn': 'uni/tn-common',
                               'nameAlies': 'test2', 'status': 'modified'}}},
            {'fvBD': {'attributes': {'dn': 'uni/tn-common/BD-bd', 'name': 'bd',
                                     'status': 'created'}}},
            {'fvCtx': {'attributes': {'dn': 'uni/tn-common/ctx-ctx',
                                      'name': 'ctx', 'status': 'created'}}},
        ]
        self._verify_expected_events(expected_events, session, url)
        # Delete something
        self.DELETE('api/mo/uni/tn-common.json', cookies=resp.cookies)
        expected_events = [
            {'fvTenant': {
                'attributes': {'dn': 'uni/tn-common', 'status': 'deleted'}}},
            {'fvBD': {'attributes': {'dn': 'uni/tn-common/BD-bd',
                                     'status': 'deleted'}}},
            {'fvCtx': {'attributes': {'dn': 'uni/tn-common/ctx-ctx',
                                      'status': 'deleted'}}},
        ]
        self._verify_expected_events(expected_events, session, url)

    def test_first_subscription_event(self):
        session = acitoolkit.Session(self.uri, 'admin', pwd='pwd')
        url = ('/api/node/mo/uni/tn-common.json?'
               'subscription=yes&query-target=subtree')
        resp = session.login()
        tn = {
            'fvTenant': {
                'attributes': {'dn': 'uni/tn-common', 'nameAlies': 'test2'},
                'children': [
                    {'fvBD': {'attributes': {'name': 'bd'}}},
                    {'fvCtx': {'attributes': {'name': 'ctx'}}},
                ]
            }
        }
        self.POST('api/mo/uni/tn-common.json', data=json.dumps(tn),
                  cookies=resp.cookies)
        session.subscribe(url)
        expected_events = [
            {'fvTenant': {
                'attributes': {'dn': 'uni/tn-common', 'nameAlies': 'test2'}}},
            {'fvBD': {'attributes': {'dn': 'uni/tn-common/BD-bd',
                                     'name': 'bd'}}},
            {'fvCtx': {'attributes': {'dn': 'uni/tn-common/ctx-ctx',
                                      'name': 'ctx'}}},
        ]
        self._verify_expected_events(expected_events, session, url)

    def test_get_by_class(self):
        tn = {
            'fvTenant': {
                'attributes': {'dn': 'uni/tn-common', 'nameAlies': 'test'},
                'children': [
                    {'fvBD': {'attributes': {'name': 'bd'}}},
                    {'fvBD': {'attributes': {'name': 'bd1'}}}
                ]
            }
        }
        self.POST('api/mo/uni/tn-common.json', data=json.dumps(tn))
        tn2 = {
            'fvTenant': {
                'attributes': {'dn': 'uni/tn-test', 'nameAlies': 'test'},
                'children': [
                    {'fvBD': {'attributes': {'name': 'bd'}}},
                    {'fvBD': {'attributes': {'name': 'bd1'},
                              'children': [{'fvRsCtx': {
                                  'attributes': {'fvCtx': 'test'}}}]}}
                ]
            }
        }
        self.POST('api/mo/uni/tn-test.json', data=json.dumps(tn2))
        resp = self.GET('api/node/class/fvBD.json')
        # All BDs, no children
        expected = [
            {'fvBD': {'attributes': {'name': 'bd',
                                     'dn': 'uni/tn-common/BD-bd'}}},
            {'fvBD': {'attributes': {'name': 'bd1',
                                     'dn': 'uni/tn-common/BD-bd1'}}},
            {'fvBD': {'attributes': {'name': 'bd',
                                     'dn': 'uni/tn-test/BD-bd'}}},
            {'fvBD': {'attributes': {'name': 'bd1',
                                     'dn': 'uni/tn-test/BD-bd1'}}}]
        self._verify_expected_return(expected, resp)
        # Now throw in a query param
        resp = self.GET('api/node/class/fvBD.json?query-target=subtree')
        expected = [
            {'fvBD': {'attributes': {'name': 'bd',
                                     'dn': 'uni/tn-common/BD-bd'}}},
            {'fvBD': {'attributes': {'name': 'bd1',
                                     'dn': 'uni/tn-common/BD-bd1'}}},
            {'fvBD': {'attributes': {'name': 'bd',
                                     'dn': 'uni/tn-test/BD-bd'}}},
            {'fvBD': {'attributes': {'name': 'bd1',
                                     'dn': 'uni/tn-test/BD-bd1'}}},
            {'fvRsCtx': {'attributes': {'fvCtx': 'test',
                                        'dn': 'uni/tn-test/BD-bd1/rsctx'}}}
        ]
        self._verify_expected_return(expected, resp)

    def test_subscription_by_class(self):
        tn = {
            'fvTenant': {
                'attributes': {'dn': 'uni/tn-common', 'nameAlies': 'test'},
                'children': [
                    {'fvBD': {'attributes': {'name': 'bd'}}},
                    {'fvBD': {'attributes': {'name': 'bd1'}}}
                ]
            }
        }
        self.POST('api/mo/uni/tn-common.json', data=json.dumps(tn))
        tn2 = {
            'fvTenant': {
                'attributes': {'dn': 'uni/tn-test', 'nameAlies': 'test'},
                'children': [
                    {'fvBD': {'attributes': {'name': 'bd'}}},
                    {'fvBD': {'attributes': {'name': 'bd1'},
                              'children': [{'fvRsCtx': {
                                  'attributes': {'fvCtx': 'test'}}}]}}
                ]
            }
        }
        self.POST('api/mo/uni/tn-test.json', data=json.dumps(tn2))
        session = acitoolkit.Session(self.uri, 'admin', pwd='pwd')
        url = ('/api/node/class/fvBD.json?'
               'subscription=yes&query-target=subtree')
        session.login()
        session.subscribe(url)
        # Get init events
        expected = [
            {'fvBD': {'attributes': {'name': 'bd',
                                     'dn': 'uni/tn-common/BD-bd'}}},
            {'fvBD': {'attributes': {'name': 'bd1',
                                     'dn': 'uni/tn-common/BD-bd1'}}},
            {'fvBD': {'attributes': {'name': 'bd',
                                     'dn': 'uni/tn-test/BD-bd'}}},
            {'fvBD': {'attributes': {'name': 'bd1',
                                     'dn': 'uni/tn-test/BD-bd1'}}},
            {'fvRsCtx': {'attributes': {'fvCtx': 'test',
                                        'dn': 'uni/tn-test/BD-bd1/rsctx'}}}
        ]
        self._verify_expected_events(expected, session, url)
        # Update event
        self.POST('api/mo/uni/tn-test/BD-bd1/rsctx.json',
                  data=json.dumps({'fvRsCtx': {'attributes': {
                      'fvCtx': 'default', 'dn': 'uni/tn-test/BD-bd1/rsctx'}}}))
        expected = [
            {'fvRsCtx': {'attributes': {'fvCtx': 'default',
                                        'dn': 'uni/tn-test/BD-bd1/rsctx',
                                        'status': 'modified'}}}]
        self._verify_expected_events(expected, session, url)
        # Delete event
        self.DELETE('api/mo/uni/tn-test/BD-bd1/rsctx.json')
        expected = [
            {'fvRsCtx': {'attributes': {'dn': 'uni/tn-test/BD-bd1/rsctx',
                                        'status': 'deleted'}}}]
        self._verify_expected_events(expected, session, url)
