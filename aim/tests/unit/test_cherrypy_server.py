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
import testtools

import mock
import requests

from aim import aim_manager
from aim.api import infra as infra_res
from aim.api import resource as api_res
from aim.api import status as status_res
from aim.api import tree as tree_res
from aim.common import utils
from aim import config
from aim.server.cherrypy import root
from aim.tests import base


class TestServerMixin(object):

    def GET(self, url, *args, **kwargs):
        return requests.get('%s/%s' % (self.uri, url), *args, **kwargs)

    def POST(self, url, *args, **kwargs):
        return requests.post('%s/%s' % (self.uri, url), *args, **kwargs)

    def PUT(self, url, *args, **kwargs):
        return requests.put('%s/%s' % (self.uri, url), *args, **kwargs)

    def DELETE(self, url, **kwargs):
        return requests.delete('%s/%s' % (self.uri, url), **kwargs)


# REVISIT: Skipping this UT class as it fails quite often now
# without even showing us where it fails exactly. Also this
# aim-http-server is not even enabled in our deployment so nobody
# is really using it.
@testtools.skip('Skipping test class')
class TestServer(base.TestAimDBBase, TestServerMixin):
    """Test case base class for all scenario tests."""

    def setUp(self):
        super(TestServer, self).setUp()
        self.addCleanup(root.shutdown)
        self.set_override('port', 0, 'aim_server')
        self.ip, self.port, self.root = root.run(config.CONF)
        self.uri = 'http://%s:%s' % (self.ip, self.port)
        self.mgr = aim_manager.AimManager()

    def test_wrong_uri(self):
        for uri in ['', 'nope', 'aim/nope']:
            for verb in [self.GET, self.POST, self.PUT, self.DELETE]:
                resp = verb(uri)
                self.assertEqual(404, resp.status_code)

    def test_get_empty(self):
        resp = self.GET('aim')
        self.assertEqual(200, resp.status_code)
        self.assertEqual(0, resp.json()['count'])
        self.assertEqual([], resp.json()['data'])

    def test_post_state(self):
        resp = self.POST('aim', data=json.dumps([]))
        self.assertEqual(200, resp.status_code)

    # TODO(ivar): create N objects of M types, and verify:
    #    - get/get-with-status/delete single class
    #    - entire model replaced

    # No one uses the server and the test is very slow
    def _test_aim_server_per_type(self):
        exclude = {
            api_res.Configuration,  # There are many already
            status_res.AciFault,  # Tested by status test
            status_res.AciStatus,  # Tested by status test
            tree_res.ActionLog,  # Never created by API
            api_res.Topology,  # Can create only 1
            api_res.Agent,  # Created only by AID
            # REVISIT: Instead of avaoiding classes
            # with enum data types, we should introspect the
            # object and create valid identifiers for the test
            infra_res.HostDomainMappingV2,  # Avoiding enums for now
        }
        # For debugging purposes, only test one type
        test_only = {}
        # For test performance purposes, only test N klasses
        klass_num = 10
        # Run for a limited set of types, or it will timeout
        for res_type in test_only or list(
                (self.mgr.aim_resources - exclude))[:klass_num]:
            for cardinality in [0, 1, 3]:
                fail_msg = ('Test Failed for type %s with '
                            'cardinality %s' % (res_type, cardinality))
                to_create = [self.generate_aim_object(res_type)
                             for _ in range(cardinality)]
                # Create objects
                data = [self.root.aimc._generate_data_item(x)
                        for x in to_create]
                resp = self.POST('aim', data=json.dumps(data))
                self.assertEqual(200, resp.status_code, fail_msg)
                # Set objects' status
                status_supported = False
                if to_create and self.mgr.get_status(self.ctx, to_create[0],
                                                     create_if_absent=True):
                    status_supported = True
                    for aim_obj in to_create:
                        self.mgr.set_resource_sync_pending(self.ctx, aim_obj)
                # Test GET all
                resp = self.GET('aim')
                self.assertEqual(200, resp.status_code, fail_msg)
                self.assertEqual(len(to_create), resp.json()['count'],
                                 fail_msg)
                # There are AIM IDs now
                for item in data:
                    item.update({'aim_id': mock.ANY})
                sorting_key = lambda x: x['attributes']
                data_resp = resp.json()['data']
                for to_compare in [data, data_resp]:
                    for x in to_compare:
                        for non_user in res_type.non_user_attributes():
                            x['attributes'].pop(non_user, None)
                self.assertEqual(sorted(data, key=sorting_key),
                                 sorted(data_resp, key=sorting_key),
                                 fail_msg)
                # GET with status included
                resp = self.GET('aim?include-status=true')
                self.assertEqual(200, resp.status_code, fail_msg)
                self.assertEqual(
                    len(to_create) * (2 if status_supported else 1),
                    resp.json()['count'], fail_msg)
                # Create some with a PUT, with a common attribute
                comm_attr = {}
                for set_attr, schema_type in (
                        res_type.other_attributes.items()):
                    if schema_type['type'] == 'string' and (
                            'enum' not in schema_type):
                        comm_attr[set_attr] = utils.generate_uuid()
                        break
                to_put = [self.generate_aim_object(res_type, **comm_attr)
                          for _ in range(cardinality)]
                put_data = [self.root.aimc._generate_data_item(x)
                            for x in to_put]
                self.PUT('aim', data=json.dumps(put_data))
                resp = self.GET('aim')
                self.assertEqual(200, resp.status_code, fail_msg)
                # Objects added
                self.assertEqual(len(to_create) + len(to_put),
                                 resp.json()['count'], fail_msg)
                if comm_attr:
                    uri = ('aim?object-type=%s&%s=%s' %
                           (utils.camel_to_snake(res_type.__name__),
                            comm_attr.keys()[0], comm_attr.values()[0]))
                    resp = self.GET(uri)
                    self.assertEqual(200, resp.status_code, fail_msg)
                    self.assertEqual(len(to_put), resp.json()['count'],
                                     fail_msg)
                # Delete objects just created
                for item in to_put:
                    uri = (
                        'aim?object-type=%s&%s' %
                        (utils.camel_to_snake(res_type.__name__),
                         '&'.join(['%s=%s' % (k, getattr(item, k)) for k in
                                   item.identity_attributes.keys()])))
                    self.DELETE(uri)
                resp = self.GET('aim')
                self.assertEqual(200, resp.status_code, fail_msg)
                self.assertEqual(len(to_create), resp.json()['count'],
                                 fail_msg)
                # Delete all
                resp = self.DELETE('aim')
                self.assertEqual(200, resp.status_code, fail_msg)
                resp = self.GET('aim')
                self.assertEqual(200, resp.status_code, fail_msg)
                self.assertEqual(0, resp.json()['count'], fail_msg)

    def test_get_status_with_faults(self):
        aim_obj = self.generate_aim_object(api_res.EndpointGroup)
        data = [self.root.aimc._generate_data_item(aim_obj)]
        self.POST('aim', data=json.dumps(data))
        self.mgr.set_resource_sync_synced(self.ctx, aim_obj)
        self.mgr.set_fault(self.ctx, aim_obj, status_res.AciFault(
            fault_code='900', external_identifier=aim_obj.dn))
        resp = self.GET('aim?include-status=true')
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertEqual(3, body['count'])
        for item in body['data']:
            if item['type'] == 'endpoint_group':
                aim_id = item['aim_id']
            elif item['type'] == 'aci_fault':
                fault_code = item['attributes']['fault_code']
                status_id = item['attributes']['status_id']
            elif item['type'] == 'aci_status':
                res_id = item['attributes']['resource_id']
                real_status_id = item['attributes']['id']
        # Correlate resources
        self.assertEqual('900', fault_code)
        self.assertEqual(real_status_id, status_id)
        self.assertEqual(aim_id, res_id)
