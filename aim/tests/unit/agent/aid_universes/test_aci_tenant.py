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

import collections
import copy

from apicapi import apic_client
import gevent
import json
import mock

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes.aci import tenant as aci_tenant
from aim import config
from aim.tests import base


class FakeResponse(object):

    def __init__(self, ok=True, text=None, status_code=200):
        self.ok = ok
        self.text = text or json.dumps({'imdata': {}})
        self.status_code = status_code


def mock_get_data(inst, dn, **kwargs):
    try:
        inst._data_stash
    except Exception:
        inst._data_stash = {}

    try:
        return [inst._data_stash[dn]]
    except KeyError:
        # Simulate 404
        raise apic_client.cexc.ApicResponseNotOk(
            request='get', status='404', reason='Not Found',
            err_text='Not Found', err_code='404')


class TestAciTenant(base.TestAimDBBase):

    def setUp(self):
        super(TestAciTenant, self).setUp()
        config.CONF.set_override('apic_hosts', ['1.1.1.1'], 'apic')
        self.ws_login = mock.patch('acitoolkit.acitoolkit.Session.login')
        self.ws_login.start()

        self.tn_subscribe = mock.patch(
            'aim.agent.aid.universes.aci.tenant.Tenant._instance_subscribe',
            return_value=FakeResponse())
        self.tn_subscribe.start()

        self.process_q = mock.patch(
            'acitoolkit.acisession.Subscriber._process_event_q')
        self.process_q.start()

        self.post_body = mock.patch(
            'apicapi.apic_client.ApicSession.post_body')
        self.post_body.start()

        self.apic_login = mock.patch(
            'apicapi.apic_client.ApicSession.login')
        self.apic_login.start()
        apic_client.ApicSession.get_data = mock_get_data
        # Patch currently unimplemented methods
        self.manager = aci_tenant.AciTenantManager('tenant-1',
                                                   config.CONF.apic)

        # Monkey patch APIC Transactions
        self.old_transaction_commit = apic_client.Transaction.commit

        self.addCleanup(self.ws_login.stop)
        self.addCleanup(self.apic_login.stop)
        self.addCleanup(self.tn_subscribe.stop)
        self.addCleanup(self.process_q.stop)
        self.addCleanup(self.post_body.stop)

    def _add_server_data(self, data, manager=None):
        manager = manager or self.manager
        try:
            manager.aci_session._data_stash
        except Exception:
            manager.aci_session._data_stash = {}

        for resource in data:
            manager.aci_session._data_stash[
                'mo/' + resource.values()[0]['attributes']['dn']] = resource

    def _objects_transaction_create(self, objs):
        result = []
        for obj in objs:
            conversion = converter.AimToAciModelConverter().convert([obj])
            transaction = apic_client.Transaction(mock.Mock())
            for item in conversion:
                getattr(transaction, item.keys()[0]).add(
                    *self.manager.dn_manager.aci_decompose(
                        item.values()[0]['attributes'].pop('dn'),
                        item.keys()[0]),
                    **item.values()[0]['attributes'])
            result.append(transaction)
        return result

    def _objects_transaction_delete(self, objs):
        result = []
        for obj in objs:
            conversion = converter.AimToAciModelConverter().convert([obj])
            transaction = apic_client.Transaction(mock.Mock())
            for item in conversion:
                getattr(transaction, item.keys()[0]).remove(
                    *self.manager.dn_manager.aci_decompose(
                        item.values()[0]['attributes'].pop('dn'),
                        item.keys()[0]))
            result.append(transaction)
        return result

    def _init_event(self):
        return [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test"}}},
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test-2/rsctx",
                "tnFvCtxName": "test"}}},
            {"fvBD": {"attributes": {"arpFlood": "yes", "descr": "test",
                                     "dn": "uni/tn-test-tenant/BD-test",
                                     "epMoveDetectMode": "",
                                     "limitIpLearnToSubnets": "no",
                                     "llAddr": ":: ",
                                     "mac": "00:22:BD:F8:19:FF",
                                     "multiDstPktAct": "bd-flood",
                                     "name": "test",
                                     "ownerKey": "", "ownerTag": "",
                                     "unicastRoute": "yes",
                                     "unkMacUcastAct": "proxy",
                                     "unkMcastAct": "flood",
                                     "vmac": "not-applicable"}}},
            {"fvBD": {"attributes": {"arpFlood": "no", "descr": "",
                                     "dn": "uni/tn-test-tenant/BD-test-2",
                                     "epMoveDetectMode": "",
                                     "limitIpLearnToSubnets": "no",
                                     "llAddr": ":: ",
                                     "mac": "00:22:BD:F8:19:FF",
                                     "multiDstPktAct": "bd-flood",
                                     "name": "test-2", "ownerKey": "",
                                     "ownerTag": "", "unicastRoute": "yes",
                                     "unkMacUcastAct": "proxy",
                                     "unkMcastAct": "flood",
                                     "vmac": "not-applicable"}}},
            {"fvTenant": {"attributes": {"descr": "",
                                         "dn": "uni/tn-test-tenant",
                                         "name": "test-tenant",
                                         "ownerKey": "",
                                         "ownerTag": ""}}}]

    def _set_events(self, event_list):
        self.manager.ws_session.subscription_thread._events[
            self.manager.tenant._get_instance_subscription_urls()[0]] = [
            dict([('imdata', [x])]) for x in event_list]

    def test_event_loop(self):
        self.manager._subscribe_tenant()
        # Runs with no events
        self.manager._event_loop()
        self.assertIsNone(self.manager.get_state_copy().root)
        # Get an initialization event
        self.manager._subscribe_tenant()
        self._set_events(self._init_event())
        self.manager._event_loop()
        # TODO(ivar): Now root will contain all those new objects, check once
        # implemented

    def test_login_failed(self):
        # Create first session
        self.manager._subscribe_tenant()
        # Mock response and login again
        with mock.patch('acitoolkit.acitoolkit.Session.login',
                        return_value=FakeResponse(ok=False)):
            self.assertRaises(aci_tenant.WebSocketSessionLoginFailed,
                              self.manager._subscribe_tenant)

    def test_is_dead(self):
        self.assertFalse(self.manager.is_dead())

    def test_event_loop_failure(self):
        manager = aci_tenant.AciTenantManager('tenant-1', config.CONF.apic)
        manager.tenant.instance_has_event = mock.Mock(side_effect=KeyError)
        # Main loop is not raising
        manager._main_loop()
        # Failure by GreenletExit
        manager.tenant.instance_has_event = mock.Mock(
            side_effect=gevent.GreenletExit)
        self.assertRaises(gevent.GreenletExit, manager._main_loop)
        # Upon GreenExit, even _run stops the loop
        manager._run()
        # Instance unsubscribe could rise an exception itself
        with mock.patch('acitoolkit.acitoolkit.Session.unsubscribe',
                        side_effect=Exception):
            manager._run()

    def test_squash_events(self):
        double_events = [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test"}}},
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test-2"}}}
            ]
        self.manager._subscribe_tenant()
        self._set_events(double_events)
        res = self.manager.tenant.instance_get_event_data(
            self.manager.ws_session)
        self.assertEqual(1, len(res))
        self.assertEqual(double_events[1], res[0])

    def test_push_aim_resources(self):
        # Create some AIM resources
        bd1 = self._get_example_bridge_domain()
        bd2 = self._get_example_bridge_domain(name='test2')
        self.manager.push_aim_resources({'create': [bd1, bd2]})
        self.manager._push_aim_resources()
        # Verify expected calls
        transactions = self._objects_transaction_create([bd1, bd2])
        exp_calls = [
            mock.call(mock.ANY, json.dumps(transactions[0].root),
                      'test-tenant'),
            mock.call(mock.ANY, json.dumps(transactions[1].root),
                      'test-tenant')]
        self._check_call_list(exp_calls, self.manager.aci_session.post_body)

        # Delete AIM resources
        self.manager.aci_session.post_body.reset_mock()
        self.manager.push_aim_resources({'delete': [bd1, bd2]})
        self.manager._push_aim_resources()
        # Verify expected calls, add deleted status
        transactions = self._objects_transaction_delete([bd1, bd2])
        exp_calls = [
            mock.call(mock.ANY, json.dumps(transactions[0].root),
                      'test-tenant'),
            mock.call(mock.ANY, json.dumps(transactions[1].root),
                      'test-tenant')]
        self._check_call_list(exp_calls, self.manager.aci_session.post_body)

        # Create AND delete aim resources
        self.manager.aci_session.post_body.reset_mock()
        self.manager.push_aim_resources(collections.OrderedDict(
            [('create', [bd1]), ('delete', [bd2])]))
        self.manager._push_aim_resources()
        transactions = self._objects_transaction_create([bd1])
        transactions.extend(self._objects_transaction_delete([bd2]))
        exp_calls = [
            mock.call(mock.ANY, json.dumps(transactions[0].root),
                      'test-tenant'),
            mock.call(mock.ANY, json.dumps(transactions[1].root),
                      'test-tenant')]
        self._check_call_list(exp_calls, self.manager.aci_session.post_body)

        # Failure in pushing object
        self.manager.aci_session.post_body = mock.Mock(
            side_effect=apic_client.cexc.ApicResponseNotOk)
        # No exception is externally rised
        self.manager.push_aim_resources({'delete': [bd1, bd2]})
        self.manager._push_aim_resources()

    def test_fill_events_noop(self):
        # On unchanged data, fill events is a noop
        events = self._init_event()
        events_copy = copy.deepcopy(events)
        self.manager._fill_events(events)
        self.assertEqual(events, events_copy)

    def test_fill_events(self):
        events = [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test", "status": "modified"}}},
        ]
        complete = {"fvRsCtx": {"attributes": {
            "dn": "uni/tn-test-tenant/BD-test/rsctx", "status": "modified",
            "tnFvCtxName": "test", "extra": "something_important"}}}
        parent_bd = self._get_example_bd()
        self._add_server_data([complete, parent_bd])
        self.manager._fill_events(events)
        self.assertEqual([complete, parent_bd], events)

        # Now start from BD
        events = [{"fvBD": {"attributes": {
            "arpFlood": "yes", "descr": "test",
            "dn": "uni/tn-test-tenant/BD-test", "status": "modified"}}}]
        parent_bd['fvBD']['attributes']['status'] = 'modified'
        self.manager._fill_events(events)
        self.assertEqual([parent_bd, complete], events)

    def test_fill_events_not_found(self):
        events = [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test", "status": "modified"}}},
        ]
        parent_bd = self._get_example_bd()
        # fvRsCtx is missing on server side
        self._add_server_data([parent_bd])
        self.manager._fill_events(events)
        missing = {"fvRsCtx": {"attributes": {
            "dn": "uni/tn-test-tenant/BD-test/rsctx",
            "tnFvCtxName": "test", "status": "deleted"}}}
        self.assertEqual([missing, parent_bd], events)

        # Test missing counterpart
        complete = {"fvRsCtx": {"attributes": {
            "dn": "uni/tn-test-tenant/BD-test/rsctx", "status": "modified",
            "tnFvCtxName": "test", "extra": "something_important"}}}
        self.manager.aci_session._data_stash = {}
        self._add_server_data([complete])
        events = [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test", "status": "modified"}}},
        ]
        self.manager._fill_events(events)
        self.assertEqual([complete], events)
