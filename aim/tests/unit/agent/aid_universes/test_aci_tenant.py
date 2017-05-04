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
import json
import mock

from aim.agent.aid.universes.aci import aci_universe
from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes.aci import tenant as aci_tenant
from aim.api import resource as a_res
from aim.tests import base


AMBIGUOUS_TYPES = [aci_tenant.TAG_KEY, aci_tenant.FAULT_KEY]


class FakeResponse(object):

    def __init__(self, ok=True, text=None, status_code=200):
        self.ok = ok
        self.text = text or json.dumps({'imdata': {}})
        self.status_code = status_code


def _flat_result(result):
    flattened = []
    result = copy.deepcopy(result)
    children = result.values()[0].pop('children', [])
    flattened.append(result)
    for child in children:
        flattened.extend(_flat_result(child))
    return flattened


def decompose_aci_dn(dn):
    dn_mgr = apic_client.DNManager()
    # Since we have no APIC type, extract the object's RN:
    rn = []
    skip = False
    for x in range(len(dn)):
        # skip everything in square brackets
        c = dn[-1 - x]
        if c == '[':
            skip = False
            continue
        elif skip:
            continue
        elif c == ']':
            skip = True
            continue
        elif c == '/':
            break
        else:
            rn.append(c)
    rn = ''.join(reversed(rn))
    # From RN, infer the type
    if '-' in rn:
        rn = rn[:rn.find('-')]
    aci_type = apic_client.ManagedObjectClass.prefix_to_mos[rn]
    # Now we can decompose the DN, remove the mo/ in front
    return dn_mgr.aci_decompose_dn_guess(dn, aci_type)[1]


def mock_get_data(inst, dn, **kwargs):
    # Expected kwargs: query_target [subtree], target_subtree_class
    try:
        inst._data_stash
    except Exception:
        inst._data_stash = {}

    dn_mgr = apic_client.DNManager()
    # Decompose the DN, remove the mo/ in front
    decomposed = decompose_aci_dn(dn[3:])
    try:
        # Find the proper root node
        curr = copy.deepcopy(inst._data_stash[decomposed[0][1]])[0]
        for index, part in enumerate(decomposed[1:]):
            # Look at the current's children and find the proper node.
            if part[0] in AMBIGUOUS_TYPES:
                partial_dn = (
                    dn_mgr.build(
                        decomposed[:index + 1]) + '/' +
                    apic_client.ManagedObjectClass.mos_to_prefix[part[0]] +
                    '-' + decomposed[index + 1][1])
            else:
                partial_dn = dn_mgr.build(decomposed[:index + 2])
            for child in curr.values()[0]['children']:
                if child.values()[0]['attributes']['dn'] == partial_dn:
                    curr = child
                    break
            else:
                raise KeyError
        # Curr is the looked up node. Look at the query params to filter the
        # result
        query_target = kwargs.get('query_target', 'self')
        if query_target == 'subtree':
            # Look at the target subtree class
            target_subtree_class = kwargs.get(
                'target_subtree_class', '').split(',')
            if not target_subtree_class:
                # Return everything
                return _flat_result(curr)
            else:
                # Only return the expected objects
                return [x for x in _flat_result(curr) if
                        x.keys()[0] in target_subtree_class]
        else:
            curr.values()[0].pop('children', [])
            return [curr]
    except KeyError:
        # Simulate 404
        if 'fault' in dn:
            # non existing faults return empty data
            return []
        raise apic_client.cexc.ApicResponseNotOk(
            request='get', status='404', reason='Not Found',
            err_text='Not Found', err_code='404')


class TestAciClientMixin(object):

    def _manipulate_server_data(self, data, manager=None, add=True, tag=True,
                                create_parents=False):
        manager = manager if manager is not None else self.manager
        try:
            manager.aci_session._data_stash
        except Exception:
            manager.aci_session._data_stash = {}

        def _tag_format(dn):
            return {
                'tagInst': {
                    'attributes': {
                        'dn': (dn + '/tag-' + self.sys_id)},
                    'children': []}
            }

        dn_mgr = apic_client.DNManager()
        for resource in copy.deepcopy(data):
            resource.values()[0]['attributes'].pop('status', None)
            data_type = resource.keys()[0]
            if data_type == 'tagInst' and tag and add:
                continue
            decomposed = dn_mgr.aci_decompose_dn_guess(
                resource.values()[0]['attributes']['dn'], data_type)[1]
            if add:
                curr = manager.aci_session._data_stash.setdefault(
                    decomposed[0][1], [])
            else:
                curr = manager.aci_session._data_stash.get(decomposed[0][1],
                                                           [])
            prev = None
            child_index = None
            last_index = len(decomposed) - 1
            is_new = False
            for out_index, part in enumerate(decomposed):
                # Look at the current's children and find the proper node.
                # if not found, it's a new node
                if part[0] in AMBIGUOUS_TYPES:
                    partial_dn = (
                        dn_mgr.build(
                            decomposed[:out_index]) + '/' +
                        apic_client.ManagedObjectClass.mos_to_prefix[part[0]] +
                        '-' + decomposed[out_index][1])
                else:
                    partial_dn = dn_mgr.build(decomposed[:out_index + 1])

                for index, child in enumerate(curr):
                    if child.values()[0]['attributes']['dn'] == partial_dn:
                        child_index = index
                        prev = curr
                        curr = child.values()[0]['children']
                        break
                else:
                    if add:
                        if out_index < last_index:
                            # Parent is missing
                            if create_parents:
                                next = {
                                    part[0]: {'attributes': {'dn': partial_dn},
                                              'children': [] if not tag else
                                              [_tag_format(partial_dn)]}}
                                curr.append(next)
                                prev = curr
                                curr = next[part[0]]['children']
                            else:
                                raise apic_client.cexc.ApicResponseNotOk(
                                    status=400, reason='bad request',
                                    request='create', err_code=400,
                                    err_text='bad request')
                        else:
                            # Append newly created object
                            obj = {
                                part[0]: {'attributes': {'dn': partial_dn},
                                          'children': [] if not tag else
                                          [_tag_format(partial_dn)]}}
                            curr.append(obj)
                            resource.values()[0].pop('children', None)
                            obj[part[0]].update(resource.values()[0])
                            is_new = True
                    else:
                        # Not found
                        return
            # Update body
            if not add:
                if child_index is not None:
                    prev.pop(child_index)
                    if prev is manager.aci_session._data_stash[
                            decomposed[0][1]]:
                        # Tenant is now empty
                        manager.aci_session._data_stash.pop(decomposed[0][1])
                else:
                    # Root node
                    manager.aci_session._data_stash.pop(decomposed[0][1])
            elif child_index is not None and not is_new:
                children = prev[child_index].values()[0]['children']
                prev[child_index].update(resource)
                prev[child_index].values()[0]['children'] = children

    def _add_server_data(self, data, manager=None, tag=True,
                         create_parents=False):
        self._manipulate_server_data(data, manager=manager, add=True, tag=tag,
                                     create_parents=create_parents)

    def _remove_server_data(self, data, manager=None):
        self._manipulate_server_data(data, manager=manager, add=False)

    def _extract_rns(self, dn, mo):
        FIXED_RNS = ['rsctx', 'rsbd', 'intmnl', 'outtmnl']
        return [rn for rn in self.manager.dn_manager.aci_decompose(dn, mo)
                if rn not in FIXED_RNS]

    def _objects_transaction_create(self, objs, create=True, tag=None,
                                    top_send=True):
        tag = tag or self.sys_id
        result = []
        for obj in objs:
            conversion = converter.AimToAciModelConverter().convert([obj])
            transaction = apic_client.Transaction(mock.Mock(),
                                                  top_send=top_send)
            tags = []
            if create:
                for item in conversion:
                    dn = item.values()[0]['attributes']['dn']
                    dn += '/tag-%s' % tag
                    tags.append({"tagInst__%s" % item.keys()[0]:
                                 {"attributes": {"dn": dn}}})

            for item in conversion + tags:
                getattr(transaction, item.keys()[0]).add(
                    *self._extract_rns(
                        item.values()[0]['attributes'].pop('dn'),
                        item.keys()[0]),
                    **item.values()[0]['attributes'])
            result.append(transaction)
        return result

    def _objects_transaction_delete(self, objs):
        result = []
        for obj in objs:
            transaction = apic_client.Transaction(mock.Mock())
            item = copy.deepcopy(obj)
            getattr(transaction, obj.keys()[0]).remove(
                *self._extract_rns(
                    item.values()[0]['attributes'].pop('dn'),
                    item.keys()[0]))
            result.append(transaction)
        return result

    def _init_event(self):
        return [
            {"fvTenant": {"attributes": {"descr": "",
                                         "dn": "uni/tn-test-tenant",
                                         "name": "test-tenant",
                                         "ownerKey": "",
                                         "ownerTag": ""}}},
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
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test"}}},
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test-2/rsctx",
                "tnFvCtxName": "test"}}}]

    def _set_events(self, event_list, manager=None, tag=True,
                    create_parents=False):
        # Greenlets have their own weird way of calculating bool
        event_list_copy = copy.deepcopy(event_list)
        manager = manager if manager is not None else self.manager
        manager.ws_context.session.subscription_thread._events.setdefault(
            manager.tenant._get_instance_subscription_urls()[0], []).extend([
                dict([('imdata', [x])]) for x in event_list])
        # Add events to server
        aci_tenant.AciTenantManager.flat_events(event_list_copy)
        for event in event_list_copy:
            if event.values()[0]['attributes'].get('status') != 'deleted':
                self._add_server_data([event], manager=manager, tag=tag,
                                      create_parents=create_parents)
            else:
                self._remove_server_data([event], manager=manager)

    def _do_aci_mocks(self):
        self.monitors = mock.patch(
            'aim.agent.aid.universes.aci.aci_universe.WebSocketContext.'
            '_spawn_monitors')
        self.monitors.start()

        self.set_override('apic_hosts', ['1.1.1.1'], 'apic')
        self.ws_login = mock.patch('acitoolkit.acitoolkit.Session.login')
        self.ws_login.start()

        self.tn_subscribe = mock.patch(
            'aim.agent.aid.universes.aci.aci_universe.WebSocketContext.'
            '_subscribe', return_value=FakeResponse())
        self.tn_subscribe.start()

        self.process_q = mock.patch(
            'acitoolkit.acisession.Subscriber._process_event_q')
        self.process_q.start()

        self.post_body = mock.patch(
            'apicapi.apic_client.ApicSession.post_body_dict')
        self.post_body.start()

        self.delete = mock.patch(
            'apicapi.apic_client.ApicSession.DELETE')
        self.delete.start()

        self.get = mock.patch(
            'apicapi.apic_client.ApicSession.GET')
        self.get.start()

        self.apic_login = mock.patch(
            'apicapi.apic_client.ApicSession.login')
        self.apic_login.start()
        apic_client.ApicSession.get_data = mock_get_data

        # Monkey patch APIC Transactions
        self.old_transaction_commit = apic_client.Transaction.commit

        self.addCleanup(self.ws_login.stop)
        self.addCleanup(self.apic_login.stop)
        self.addCleanup(self.tn_subscribe.stop)
        self.addCleanup(self.process_q.stop)
        self.addCleanup(self.post_body.stop)
        self.addCleanup(self.delete.stop)
        self.addCleanup(self.get.stop)
        self.addCleanup(self.monitors.stop)


class TestAciTenant(base.TestAimDBBase, TestAciClientMixin):

    def setUp(self):
        super(TestAciTenant, self).setUp()
        self._do_aci_mocks()
        self.manager = aci_tenant.AciTenantManager(
            'tn-tenant-1', self.cfg_manager,
            aci_universe.AciUniverse.establish_aci_session(self.cfg_manager),
            aci_universe.get_websocket_context(self.cfg_manager))

    def test_event_loop(self):
        old_name = self.manager.tenant_name
        self.manager.tenant_name = 'tn-test-tenant'
        self.manager._subscribe_tenant()
        # Runs with no events
        self.manager._event_loop()
        self.assertIsNone(self.manager.get_state_copy().root)
        # Get an initialization event
        self.manager._subscribe_tenant()
        self._set_events(self._init_event())
        self.manager._event_loop()
        self.manager.tenant_name = old_name

    def test_login_failed(self):
        # Mock response and login
        with mock.patch('acitoolkit.acitoolkit.Session.login',
                        return_value=FakeResponse(ok=False)):
            self.assertRaises(aci_universe.WebSocketSessionLoginFailed,
                              self.manager.ws_context.establish_ws_session)

    def test_is_dead(self):
        self.assertFalse(self.manager.is_dead())

    def test_event_loop_failure(self):
        manager = aci_tenant.AciTenantManager(
            'tenant-1', self.cfg_manager,
            aci_universe.AciUniverse.establish_aci_session(self.cfg_manager),
            aci_universe.get_websocket_context(self.cfg_manager))
        manager.ws_context.has_event = mock.Mock(side_effect=KeyError)
        # Main loop is not raising
        manager._main_loop()

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
        self._set_events(double_events, create_parents=True)
        res = self.manager.ws_context.get_event_data(self.manager.tenant.urls)
        self.assertEqual(1, len(res))
        self.assertEqual(double_events[1], res[0])

    def test_push_aim_resources(self):
        # Create some AIM resources
        bd1 = self._get_example_aim_bd()
        bd2 = self._get_example_aim_bd(name='test2')
        bda1 = self._get_example_aci_bd()
        bda2 = self._get_example_aci_bd(descr='test2')
        subj1 = a_res.ContractSubject(tenant_name='test-tenant',
                                      contract_name='c', name='s',
                                      in_filters=['i1', 'i2'],
                                      out_filters=['o1', 'o2'])
        self.manager.push_aim_resources({'create': [bd1, bd2, subj1]})
        self.manager._push_aim_resources()
        # Verify expected calls
        transactions = self._objects_transaction_create([bd1, bd2, subj1],
                                                        top_send=True)
        exp_calls = [
            mock.call(mock.ANY, transactions[0].get_top_level_roots()[0][1],
                      'test-tenant', 'test'),
            mock.call(mock.ANY, transactions[1].get_top_level_roots()[0][1],
                      'test-tenant', 'test2'),
            mock.call(mock.ANY, transactions[2].get_top_level_roots()[0][1],
                      'test-tenant', 'c', 's')]
        self._check_call_list(exp_calls,
                              self.manager.aci_session.post_body_dict)

        # Delete AIM resources
        self.manager.aci_session.post_body_dict.reset_mock()
        f1 = {'vzRsFiltAtt__In': {'attributes': {
            'dn': 'uni/tn-test-tenant/brc-c/subj-s/intmnl/rsfiltAtt-i1'}}}
        f2 = {'vzRsFiltAtt__Out': {'attributes': {
            'dn': 'uni/tn-test-tenant/brc-c/subj-s/outtmnl/rsfiltAtt-o1'}}}
        self.manager.push_aim_resources({'delete': [bda1, bda2, f1, f2]})
        self.manager._push_aim_resources()
        # Verify expected calls, add deleted status
        transactions = self._objects_transaction_delete([bda1, bda2, f1, f2])
        exp_calls = [
            mock.call('/mo/' + bda1.values()[0]['attributes']['dn'] + '.json'),
            mock.call('/mo/' + bda2.values()[0]['attributes']['dn'] + '.json'),
            mock.call('/mo/' + f1.values()[0]['attributes']['dn'] + '.json'),
            mock.call('/mo/' + f2.values()[0]['attributes']['dn'] + '.json')]
        self._check_call_list(exp_calls, self.manager.aci_session.DELETE)

        # Create AND delete aim resources
        self.manager.aci_session.post_body_dict.reset_mock()
        self.manager.push_aim_resources(collections.OrderedDict(
            [('create', [bd1]), ('delete', [bda2])]))
        self.manager._push_aim_resources()
        transactions = self._objects_transaction_create([bd1])
        exp_calls = [
            mock.call(mock.ANY, transactions[0].get_top_level_roots()[0][1],
                      'test-tenant', 'test')]
        self._check_call_list(exp_calls,
                              self.manager.aci_session.post_body_dict)
        # Failure in pushing object
        self.manager.aci_session.DELETE = mock.Mock(
            side_effect=apic_client.cexc.ApicResponseNotOk
            (request='my_request', status=400,
             reason='bad request', err_text='bad request text', err_code=400))
        # No exception is externally rised
        self.manager.push_aim_resources({'delete': [bda1, bda2]})
        self.manager._push_aim_resources()

    def test_fill_events_noop(self):
        # On unchanged data, fill events is a noop
        events = self._init_event()
        events_copy = copy.deepcopy(events)
        events = self.manager._fill_events(events)
        self.assertEqual(events, events_copy)

    def test_fill_events(self):
        events = [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test", "status": "modified"}}},
        ]
        complete = {"fvRsCtx": {"attributes": {
            "dn": "uni/tn-test-tenant/BD-test/rsctx",
            "tnFvCtxName": "test", "extra": "something_important"}}}
        parent_bd = self._get_example_aci_bd()
        self._add_server_data([parent_bd, complete], create_parents=True)
        events = self.manager._filter_ownership(
            self.manager._fill_events(events))
        self.assertEqual(sorted([complete, parent_bd]), sorted(events))

        # Now start from BD
        events = [{"fvBD": {"attributes": {
            "arpFlood": "yes", "descr": "test",
            "dn": "uni/tn-test-tenant/BD-test", "status": "modified"}}}]
        events = self.manager._filter_ownership(
            self.manager._fill_events(events))
        self.assertEqual(sorted([parent_bd, complete]), sorted(events))

    def test_fill_events_not_found(self):
        events = [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test", "status": "modified"}}},
        ]
        parent_bd = self._get_example_aci_bd()
        # fvRsCtx is missing on server side
        self._add_server_data([parent_bd], create_parents=True)
        events = self.manager._filter_ownership(
            self.manager._fill_events(events))
        self.assertEqual([parent_bd], events)

        self.manager.aci_session._data_stash = {}
        self._add_server_data([], create_parents=True)
        events = [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test", "status": "modified"}}},
        ]
        events = self.manager._filter_ownership(
            self.manager._fill_events(events))
        self.assertEqual([], events)

    def test_flat_events(self):
        events = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx',
                               'tnFvCtxName': 'asasa'},
                'children': [{'faultInst': {
                    'attributes': {'ack': 'no', 'delegated': 'no',
                                   'code': 'F0952', 'type': 'config'}}}]}},
            {'fvRsCtx': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                'tnFvCtxName': 'test'},
                'children': [{'faultInst': {'attributes': {
                    'ack': 'no', 'delegated': 'no',
                    'code': 'F0952', 'type': 'config'}}}]}}]

        self.manager.flat_events(events)
        expected = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx',
                               'tnFvCtxName': 'asasa'}}},
            {'fvRsCtx': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                'tnFvCtxName': 'test'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx/fault-F0952',
                'ack': 'no', 'delegated': 'no',
                'code': 'F0952', 'type': 'config'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx/fault-F0952',
                'ack': 'no', 'delegated': 'no',
                'code': 'F0952', 'type': 'config'}}}
        ]
        self.assertEqual(expected, events)

    def test_flat_events_nested(self):
        events = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx',
                               'tnFvCtxName': 'asasa'},
                'children': [
                    {'faultInst': {
                        'attributes': {'ack': 'no', 'delegated': 'no',
                                       'code': 'F0952', 'type': 'config'},
                        'children': [{'faultInst': {
                            'attributes': {
                                'ack': 'no', 'delegated': 'no',
                                'code': 'F0952', 'type': 'config'}}}]}}]}},
            {'fvRsCtx': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                'tnFvCtxName': 'test'}}}]

        self.manager.flat_events(events)
        expected = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx',
                               'tnFvCtxName': 'asasa'}}},
            {'fvRsCtx': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                'tnFvCtxName': 'test'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx/fault-F0952',
                'ack': 'no', 'delegated': 'no',
                'code': 'F0952', 'type': 'config'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx/fault-F0952/'
                      'fault-F0952',
                'ack': 'no', 'delegated': 'no',
                'code': 'F0952', 'type': 'config'}}}
        ]
        self.assertEqual(expected, events)

    def test_flat_events_unmanaged_object(self):
        events = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx',
                               'tnFvCtxName': 'asasa'},
                'children': [
                    {'faultInst': {
                        'attributes': {'ack': 'no', 'delegated': 'no',
                                       'code': 'F0952', 'type': 'config'}}},
                    # We don't manage faultDelegate objects
                    {'faultDelegate': {
                        'attributes': {'ack': 'no', 'delegated': 'no',
                                       'code': 'F0951', 'type': 'config'}}}]}},
            {'fvRsCtx': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                'tnFvCtxName': 'test'},
                'children': [{'faultInst': {'attributes': {
                    'ack': 'no', 'delegated': 'no',
                    'code': 'F0952', 'type': 'config'}}}]}}]
        self.manager.flat_events(events)
        expected = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx',
                               'tnFvCtxName': 'asasa'}}},
            {'fvRsCtx': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                'tnFvCtxName': 'test'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx/fault-F0952',
                'ack': 'no', 'delegated': 'no',
                'code': 'F0952', 'type': 'config'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx/fault-F0952',
                'ack': 'no', 'delegated': 'no',
                'code': 'F0952', 'type': 'config'}}}
        ]
        self.assertEqual(expected, events)

    def test_operational_tree(self):
        events = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-tenant-1/BD-test-2/rsctx',
                               'tnFvCtxName': 'asasa'},
                'children': [{'faultInst': {
                    'attributes': {'ack': 'no', 'delegated': 'no',
                                   'code': 'F0952', 'type': 'config'}}}]}},
            {'fvRsCtx': {'attributes': {
                'dn': 'uni/tn-tenant-1/BD-test/rsctx',
                'tnFvCtxName': 'test'},
                'children': [{'faultInst': {'attributes': {
                    'ack': 'no', 'delegated': 'no',
                    'code': 'F0952', 'type': 'config'}}}]}}]
        self.manager._subscribe_tenant()
        self._set_events(events, create_parents=True)
        self.manager._event_loop()
        self.assertIsNotNone(self.manager._operational_state)

    def test_filter_ownership(self):
        events = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx',
                               'tnFvCtxName': 'asasa'}}},
            {'fvRsCtx': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                'tnFvCtxName': 'test'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx/fault-F0952',
                'ack': 'no', 'delegated': 'no',
                'code': 'F0952', 'type': 'config'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx/fault-F0952/'
                      'fault-F0952',
                'ack': 'no', 'delegated': 'no',
                'code': 'F0952', 'type': 'config'}}}
        ]
        result = self.manager._filter_ownership(events)
        self.assertEqual(set(), self.manager.tag_set)
        self.assertEqual(events, result)

        # Now a tag is added to set ownership of one of the to contexts
        tag = {'tagInst': {
               'attributes': {
                   'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx/'
                         'tag-' + self.sys_id}}}
        events_with_tag = events + [tag]
        result = self.manager._filter_ownership(events_with_tag)
        self.assertEqual(set(['uni/tn-ivar-wstest/BD-test-2/rsctx']),
                         self.manager.tag_set)
        self.assertEqual(events, result)

        # Now delete the tag
        tag['tagInst']['attributes']['status'] = 'deleted'
        result = self.manager._filter_ownership(events_with_tag)
        self.assertEqual(set(), self.manager.tag_set)
        self.assertEqual(events, result)

    def test_fill_events_fault(self):
        events = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                               'tnFvCtxName': 'asasa', 'status': 'created'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx/fault-F0952',
                'code': 'F0952'}}}
        ]
        complete = [
            {'fvBD': {'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test'}}},
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                               'tnFvCtxName': 'asasa'}}},
            {'faultInst': {'attributes': {
             'dn': 'uni/tn-ivar-wstest/BD-test/rsctx/fault-F0952',
             'ack': 'no', 'delegated': 'no',
             'code': 'F0952', 'type': 'config'}}},
        ]
        self._add_server_data(complete, create_parents=True)
        events = self.manager._filter_ownership(
            self.manager._fill_events(events))
        self.assertEqual(sorted(complete), sorted(events))

    def test_squash_operations(self):
        # Craft some objects and push them
        aim_converter = converter.AimToAciModelConverter()
        tn = a_res.Tenant(name='tn1', display_name='foo')
        bd = a_res.BridgeDomain(tenant_name='tn1', name='bd1',
                                display_name='bar')
        vrf = a_res.VRF(tenant_name='tn1', name='vrf1', display_name='pippo')
        self.manager.push_aim_resources(
            {'create': [tn, bd],
             'delete': aim_converter.convert([vrf])})
        self.assertEqual(1, len(self.manager.object_backlog.queue))
        old = self.manager.object_backlog.queue[0]
        # Idempotent
        self.manager.push_aim_resources(
            {'create': [tn, bd], 'delete': aim_converter.convert([vrf])})
        self.assertEqual(1, len(self.manager.object_backlog.queue))
        curr = self.manager.object_backlog.queue[0]
        self.assertEqual(old, curr)
        # Now replace something
        bd2 = a_res.BridgeDomain(tenant_name='tn1', name='bd2',
                                 display_name='bar')
        bd = copy.deepcopy(bd)
        bd.display_name = 'foobar'
        self.manager.push_aim_resources({'create': [bd2, bd], 'delete': []})
        self.assertEqual(2, len(self.manager.object_backlog.queue))
        self.assertEqual({'create': [bd2], 'delete': []},
                         self.manager.object_backlog.queue[1])
        self.assertEqual(
            'foobar',
            self.manager.object_backlog.queue[0]['create'][1].display_name)
        # Add something completely different
        vrf2 = a_res.VRF(tenant_name='tn1', name='vrf2', display_name='pippo')
        self.manager.push_aim_resources(
            {'create': [vrf2],
             'delete': aim_converter.convert([bd])})
        self.assertEqual(
            {'create': [vrf2],
             'delete': aim_converter.convert([bd])},
            self.manager.object_backlog.queue[2])

    def test_squash_operations_no_key(self):
        aim_converter = converter.AimToAciModelConverter()
        tn = a_res.Tenant(name='tn1', display_name='foo')
        bd = a_res.BridgeDomain(tenant_name='tn1', name='bd1',
                                display_name='bar')
        vrf = a_res.VRF(tenant_name='tn1', name='vrf1', display_name='pippo')
        self.manager.push_aim_resources(
            {'create': [tn, bd]})
        self.manager.push_aim_resources(
            {'delete': aim_converter.convert([vrf])})
        self.assertEqual(2, len(self.manager.object_backlog.queue))

    def test_aci_types_not_convertible_if_monitored(self):
        self.assertEqual({'fvRsProv': ['l3extInstP'],
                          'fvRsCons': ['l3extInstP']},
                         aci_tenant.ACI_TYPES_NOT_CONVERT_IF_MONITOR)

    def test_tenant_dn_root(self):
        manager = aci_tenant.AciTenantManager(
            'tn-test', self.cfg_manager,
            aci_universe.AciUniverse.establish_aci_session(self.cfg_manager),
            aci_universe.get_websocket_context(self.cfg_manager))
        self.assertEqual('uni/tn-test', manager.tenant.dn)
        manager = aci_tenant.AciTenantManager(
            'phys-test', self.cfg_manager,
            aci_universe.AciUniverse.establish_aci_session(self.cfg_manager),
            aci_universe.get_websocket_context(self.cfg_manager))
        self.assertEqual('uni/phys-test', manager.tenant.dn)
        manager = aci_tenant.AciTenantManager(
            'pod-test', self.cfg_manager,
            aci_universe.AciUniverse.establish_aci_session(self.cfg_manager),
            aci_universe.get_websocket_context(self.cfg_manager))
        self.assertEqual('topology/pod-test', manager.tenant.dn)
