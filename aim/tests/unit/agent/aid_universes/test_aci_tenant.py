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
import time

from apicapi import apic_client
import json
import mock

from aim.agent.aid.universes.aci import aci_universe
from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes.aci import tenant as aci_tenant
from aim.api import infra as api_infra
from aim.api import resource as a_res
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim import config as aim_cfg
from aim.tests import base
from aim import tree_manager

AMBIGUOUS_TYPES = [aci_tenant.TAG_KEY, aci_tenant.FAULT_KEY]


class FakeResponse(object):

    def __init__(self, ok=True, text=None, status_code=200):
        self.ok = ok
        self.text = text or json.dumps({'imdata': {}})
        self.status_code = status_code
        self.content = self.text.encode('utf-8')


def _flat_result(result):
    flattened = []
    result = copy.deepcopy(result)
    children = list(result.values())[0].pop('children', [])
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
            for child in list(curr.values())[0]['children']:
                if list(child.values())[0]['attributes']['dn'] == partial_dn:
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
                        list(x.keys())[0] in target_subtree_class]
        else:
            list(curr.values())[0].pop('children', [])
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
        removed = None
        manager = manager if manager is not None else self.manager
        try:
            manager.ac_context.aci_session._data_stash
        except Exception:
            manager.ac_context.aci_session._data_stash = {}

        def _tag_format(dn):
            return {
                'tagInst': {
                    'attributes': {
                        'dn': (dn + '/tag-' + self.sys_id)},
                    'children': []}
            }

        dn_mgr = apic_client.DNManager()
        for resource in copy.deepcopy(data):
            list(resource.values())[0]['attributes'].pop('status', None)
            data_type = list(resource.keys())[0]
            if data_type == 'tagInst' and tag and add:
                continue
            decomposed = dn_mgr.aci_decompose_dn_guess(
                list(resource.values())[0]['attributes']['dn'], data_type)[1]
            if add:
                curr = manager.ac_context.aci_session._data_stash.setdefault(
                    decomposed[0][1], [])
            else:
                curr = manager.ac_context.aci_session._data_stash.get(
                    decomposed[0][1], [])
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
                    if list(child.values())[0]['attributes'][
                            'dn'] == partial_dn:
                        child_index = index
                        prev = curr
                        curr = list(child.values())[0]['children']
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
                                    request='create', err_code=104,
                                    err_text='bad request')
                        else:
                            # Append newly created object
                            obj = {
                                part[0]: {'attributes': {'dn': partial_dn},
                                          'children': [] if not tag else
                                          [_tag_format(partial_dn)]}}
                            curr.append(obj)
                            list(resource.values())[0].pop('children', None)
                            obj[part[0]].update(list(resource.values())[0])
                            is_new = True
                    else:
                        # Not found
                        return
            # Update body
            if not add:
                if child_index is not None:
                    removed = prev.pop(child_index)
                    if prev is manager.ac_context.aci_session._data_stash[
                            decomposed[0][1]]:
                        # Tenant is now empty
                        manager.ac_context.aci_session._data_stash.pop(
                            decomposed[0][1])
                else:
                    # Root node
                    removed = manager.ac_context.aci_session._data_stash.pop(
                        decomposed[0][1])
            elif child_index is not None and not is_new:
                children = list(prev[child_index].values())[0]['children']
                prev[child_index].update(resource)
                list(prev[child_index].values())[0]['children'] = children
        return removed

    def _add_server_data(self, data, manager=None, tag=True,
                         create_parents=False):
        self._manipulate_server_data(data, manager=manager, add=True, tag=tag,
                                     create_parents=create_parents)

    def _remove_server_data(self, data, manager=None):
        return self._manipulate_server_data(data, manager=manager, add=False)

    def _add_data_to_tree(self, data, state):
        aim_res = converter.AciToAimModelConverter().convert(data)
        by_root = {}
        for res in aim_res:
            by_root.setdefault(res.root, []).append(res)
        for root, updates in list(by_root.items()):
            tree_manager.AimHashTreeMaker().update(
                state.setdefault(root, structured_tree.StructuredHashTree()),
                updates)

    def _remove_data_from_tree(self, data, state):
        aim_res = converter.AciToAimModelConverter().convert(data)
        by_root = {}
        for res in aim_res:
            by_root.setdefault(res.root, []).append(res)
        for root, updates in list(by_root.items()):
            tree_manager.AimHashTreeMaker().delete(
                state.setdefault(root, structured_tree.StructuredHashTree()),
                updates)

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
                    dn = list(item.values())[0]['attributes']['dn']
                    dn += '/tag-%s' % tag
                    tags.append({"tagInst__%s" % list(item.keys())[0]:
                                 {"attributes": {"dn": dn}}})

            for item in conversion + tags:
                getattr(transaction, list(item.keys())[0]).add(
                    *self._extract_rns(
                        list(item.values())[0]['attributes'].pop('dn'),
                        list(item.keys())[0]),
                    **list(item.values())[0]['attributes'])
            result.append(transaction)
        return result

    def _objects_transaction_delete(self, objs, top_send=True):
        result = []
        for obj in objs:
            transaction = apic_client.Transaction(mock.Mock(),
                                                  top_send=top_send)
            result.append(transaction)
            item = copy.deepcopy(obj)
            attr = list(item.values())[0]['attributes']
            attr['status'] = converter.DELETED_STATUS
            getattr(transaction, list(obj.keys())[0]).add(
                *self._extract_rns(
                    attr.pop('dn'),
                    list(item.keys())[0]),
                **attr)
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
                "tnFvCtxName": "test"}}},
            {"hostprotPol": {"attributes": {
                "dn": "uni/tn-test-tenant/pol-foo",
                "name": "foo"
            }}},
            {"hostprotRemoteIpContainer": {"attributes": {
                "dn": "uni/tn-test-tenant/pol-foo/remoteipcont",
            }}},
            {"hostprotRemoteIp": {"attributes": {
                'addr': '4.5.3.2/2',
                'descr': '',
                'dn': 'uni/tn-test-tenant/pol-foo/remoteipcont/ip-[4.5.3.2/2]',
                'name': '',
                'nameAlias': '',
                'ownerKey': '',
                'ownerTag': '',
                'rn': ''}}}]

    def _set_events(self, event_list, manager=None, tag=True,
                    create_parents=False):
        # Greenlets have their own weird way of calculating bool
        event_list_copy = copy.deepcopy(event_list)
        manager = manager if manager is not None else self.manager
        # Add events to server
        aci_tenant.AciTenantManager.flat_events(event_list_copy)
        deleted_dns = set([list(x.values())[0]['attributes']['dn']
                          for x in event_list_copy
                          if list(x.values())[0]['attributes'].get('status') ==
                          'deleted'])
        for event in event_list_copy:
            if list(event.values())[0]['attributes'].get(
                    'status') != 'deleted':
                self._add_server_data([event], manager=manager, tag=tag,
                                      create_parents=create_parents)
            else:
                removed = [self._remove_server_data([event], manager=manager)]
                if removed[0]:
                    aci_tenant.AciTenantManager.flat_events(removed)
                    for item in removed:
                        if (list(item.values())[0]['attributes']['dn'] not in
                                deleted_dns):
                            list(item.values())[0]['attributes']['status'] = (
                                'deleted')
                            event_list.append(item)
        manager.ac_context.session.subscription_thread._events.setdefault(
            manager.tenant._get_instance_subscription_urls()[0], []).extend([
                dict([('imdata', [x])]) for x in event_list])

    def _do_aci_mocks(self):
        self.monitors = mock.patch(
            'aim.agent.aid.universes.aci.aci_universe.ApicClientsContext.'
            '_spawn_monitors')
        self.monitors.start()

        self.set_override('apic_hosts', ['1.1.1.1'], 'apic')
        self.ws_login = mock.patch('acitoolkit.acitoolkit.Session.login')
        self.ws_login.start()

        self.mock_auth_mgr = mock.patch(
            'aim.agent.aid.universes.aci.aci_universe.AciCRUDLoginManager')
        self.mock_auth_mgr.start()

        self.ws_logged_in = mock.patch(
            'acitoolkit.acitoolkit.Session.logged_in', return_value=True)
        self.ws_logged_in.start()

        self.tn_subscribe = mock.patch(
            'aim.agent.aid.universes.aci.aci_universe.ApicClientsContext.'
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
        self.addCleanup(self.mock_auth_mgr.stop)
        self.addCleanup(self.ws_logged_in.stop)
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
        self.backend_state = {}
        universe = aci_universe.AciUniverse().initialize(
            aim_cfg.ConfigManager(self.ctx, 'h1'), [])
        self.manager = aci_tenant.AciTenantManager(
            'tn-tenant-1', self.cfg_manager,
            aci_universe.get_apic_clients_context(self.cfg_manager,
                                                  universe.manager),
            get_resources=universe.get_resources)
        self.manager._get_full_state = mock.Mock(
            return_value=[self.backend_state])

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
            with mock.patch('acitoolkit.acitoolkit.Session.logged_in',
                            return_value=False):
                with mock.patch('aim.common.utils.perform_harakiri') as hara:
                    self.set_override('apic_hosts',
                                      ['1.1.1.1', '2.2.2.2', '3.3.3.3'],
                                      'apic')
                    self.manager.ac_context.establish_sessions(max_retries=1)
                    self.assertEqual(1, hara.call_count)
                    self.assertEqual(['https://1.1.1.1', 'https://2.2.2.2',
                                      'https://3.3.3.3'],
                                     list(self.manager.ac_context.ws_urls))
                    self.manager.ac_context.establish_sessions(max_retries=1)
                    self.assertEqual(2, hara.call_count)
                    self.assertEqual(['https://1.1.1.1', 'https://2.2.2.2',
                                      'https://3.3.3.3'],
                                     list(self.manager.ac_context.ws_urls))

    def test_login_good(self):
        # Mock response and login
        with mock.patch('acitoolkit.acitoolkit.Session.login',
                        return_value=FakeResponse(ok=True)):
            self.set_override(
                'apic_hosts', ['1.1.1.1', '2.2.2.2'], 'apic')
            self.manager.ac_context.establish_sessions()
            self.assertEqual(self.manager.ac_context.session.ipaddr, '1.1.1.1')
            self.assertEqual(self.manager.ac_context.need_recovery, False)

            # Simulate a situation that 1.1.1.1 has been taken by
            # another aim-aid.
            self.manager.ac_context.agent_id = 'test_id'
            self.manager.ac_context.establish_sessions()
            self.assertEqual(self.manager.ac_context.session.ipaddr, '2.2.2.2')
            self.assertEqual(self.manager.ac_context.need_recovery, False)

            # Simulate a situation that both IPs are taken, then
            # it will have to share with somebody.
            self.manager.ac_context.agent_id = 'test_id1'
            self.manager.ac_context.establish_sessions()
            self.assertEqual(self.manager.ac_context.need_recovery, True)

            # Simulate running in the recovery mode where we will just
            # resume the ownership in the DB.
            api_infra.ApicAssignment.is_available = mock.Mock(
                return_value=True)
            self.manager.ac_context.establish_sessions(recovery_mode=True)
            self.assertEqual(self.manager.ac_context.session.ipaddr, '1.1.1.1')
            self.assertEqual(self.manager.ac_context.need_recovery, False)

            # Simulate running in the recovery mode where we will really
            # establish a new web socket session.
            self.manager.ac_context.need_recovery = True
            self.manager.ac_context.session.ipaddr = '2.2.2.2'
            self.manager.ac_context.establish_sessions(recovery_mode=True)
            self.assertEqual(self.manager.ac_context.session.ipaddr, '1.1.1.1')
            self.assertEqual(self.manager.ac_context.need_recovery, False)

    def test_is_dead(self):
        self.assertFalse(self.manager.is_dead())

    def test_event_loop_failure(self):
        manager = aci_tenant.AciTenantManager(
            'tn-1', self.cfg_manager,
            aci_universe.get_apic_clients_context(self.cfg_manager, None))
        manager.ac_context.has_event = mock.Mock(side_effect=KeyError)
        # Main loop is not raising
        manager._main_loop()

    def test_event_loop_refresh(self):
        ac_context = aci_universe.get_apic_clients_context(self.cfg_manager,
                                                           None)
        manager = aci_tenant.AciTenantManager(
            'tn-1', self.cfg_manager,
            ac_context)
        # Set resubscription timeout artificially low for the test, and make
        # sure we do enough iterations of the main loop to trigger a refresh
        # (two iterations with a 1 second pause after each one).
        manager.ws_subscription_to = '2'
        manager.num_loop_runs = 2
        manager.polling_yield = 1
        manager.ac_context.refresh_subscriptions = mock.Mock()
        self.assertIsNone(getattr(manager, 'scheduled_reset', None))
        manager._main_loop()
        manager.ac_context.refresh_subscriptions.assert_called_once_with(
            urls=[manager.tenant._get_instance_subscription_urls()[0]])

    def test_tenant_reset(self):
        manager = aci_tenant.AciTenantManager(
            'tn-1', self.cfg_manager,
            aci_universe.get_apic_clients_context(self.cfg_manager, None))
        manager.polling_yield = 0
        self.assertIsNone(getattr(manager, 'scheduled_reset', None))
        min = time.time() + (aci_tenant.RESET_INTERVAL -
                             aci_tenant.RESET_INTERVAL * 0.2)
        max = time.time() + (aci_tenant.RESET_INTERVAL +
                             aci_tenant.RESET_INTERVAL * 0.2) + 1
        manager._unsubscribe_tenant = mock.Mock()
        manager.num_loop_runs = 1
        manager._main_loop()
        self.assertTrue(min < manager.scheduled_reset < max)
        manager.scheduled_reset = 0
        # We don't want subscribe tenant to screw up the reset time
        manager._subscribe_tenant = mock.Mock()
        self.assertEqual(0, manager._unsubscribe_tenant.call_count)
        manager.num_loop_runs = 1
        # Exception is raised here
        manager._main_loop()
        self.assertEqual(1, manager._unsubscribe_tenant.call_count)

    def test_push_aim_resources(self):
        # Create some AIM resources
        bd1 = self._get_example_aim_bd()
        bd2 = self._get_example_aim_bd(name='test2')
        bda1 = self._get_example_aci_bd()
        bda2 = self._get_example_aci_bd(dn='uni/tn-test-tenant/BD-test2',
                                        descr='test2')
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
        self._check_call_list(
            exp_calls, self.manager.ac_context.aci_session.post_body_dict)

        # Delete AIM resources
        self.manager.ac_context.aci_session.post_body_dict.reset_mock()
        f1 = {'vzRsFiltAtt__In': {'attributes': {
            'dn': 'uni/tn-test-tenant/brc-c/subj-s/intmnl/rsfiltAtt-i1'}}}
        f2 = {'vzRsFiltAtt__Out': {'attributes': {
            'dn': 'uni/tn-test-tenant/brc-c/subj-s/outtmnl/rsfiltAtt-o1'}}}
        # We should only send the delete request of 2 SGs below to APIC since
        # all others are just children of first SG
        sg1 = {'hostprotPol': {'attributes': {
            'dn': 'uni/tn-test-tenant/pol-sg'}}}
        sg2 = {'hostprotPol': {'attributes': {
            'dn': 'uni/tn-test-tenant/pol-sg2'}}}
        sg_subj = {'hostprotSubj': {'attributes': {
            'dn': 'uni/tn-test-tenant/pol-sg/subj-default'}}}
        sg_rule1 = {'hostprotRule': {'attributes': {
            'dn': 'uni/tn-test-tenant/pol-sg/subj-default/rule-r1'}}}
        sg_rule2 = {'hostprotRule': {'attributes': {
            'dn': 'uni/tn-test-tenant/pol-sg/subj-default/rule-r2'}}}
        self.manager.push_aim_resources({'delete': [
            bda1, bda2, f1, f2, sg_rule2, sg_rule1, sg_subj, sg2, sg1]})
        self.manager._push_aim_resources()
        # Verify expected calls, add deleted status
        transactions = self._objects_transaction_delete([
            bda1, bda2, f1, f2, sg1, sg2], top_send=True)
        exp_calls = [
            mock.call(mock.ANY, transactions[0].get_top_level_roots()[0][1],
                      'test-tenant', 'test'),
            mock.call(mock.ANY, transactions[1].get_top_level_roots()[0][1],
                      'test-tenant', 'test2'),
            mock.call(mock.ANY, transactions[2].get_top_level_roots()[0][1],
                      'test-tenant', 'c', 's', 'i1'),
            mock.call(mock.ANY, transactions[3].get_top_level_roots()[0][1],
                      'test-tenant', 'c', 's', 'o1'),
            mock.call(mock.ANY, transactions[4].get_top_level_roots()[0][1],
                      'test-tenant', 'sg'),
            mock.call(mock.ANY, transactions[5].get_top_level_roots()[0][1],
                      'test-tenant', 'sg2')]
        self._check_call_list(
            exp_calls, self.manager.ac_context.aci_session.post_body_dict)

        # Create AND delete aim resources
        self.manager.ac_context.aci_session.post_body_dict.reset_mock()
        self.manager.push_aim_resources(collections.OrderedDict(
            [('create', [bd1]), ('delete', [bda2])]))
        self.manager._push_aim_resources()
        transactions_create = self._objects_transaction_create([bd1])
        transactions_delete = self._objects_transaction_delete([bda2])
        exp_calls = [
            mock.call(mock.ANY,
                      transactions_create[0].get_top_level_roots()[0][1],
                      'test-tenant', 'test'),
            mock.call(mock.ANY,
                      transactions_delete[0].get_top_level_roots()[0][1],
                      'test-tenant', 'test2')]
        self._check_call_list(
            exp_calls, self.manager.ac_context.aci_session.post_body_dict)
        # Failure in pushing object
        self.manager.ac_context.aci_session.DELETE = mock.Mock(
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
        self.assertEqual(utils.deep_sort(events),
                         utils.deep_sort(events_copy))

    def test_get_unsupported_faults(self):
        objs = [
            {'faultInst': {
                'attributes': {'domain': 'infra',
                               'code': 'F0951', 'occur': '1',
                               'subject': 'relation-resolution',
                               'severity': 'cleared',
                               'origSeverity': 'warning', 'rn': '',
                               'childAction': '', 'type': 'config',
                               'dn': 'uni/tn-prj_35e6d34e81a84091854ddf388d1e5'
                                     '5d1/BD-net_c6e85f2a-eb05-44b6-9b04-c065'
                                     '6d72a2b8/rsbdToEpRet/fault-F0951'}}}]
        result = self.manager.retrieve_aci_objects(objs)
        self.assertEqual([], result)
        objs = [
            {'faultInst': {
                'attributes': {'domain': 'infra',
                               'code': 'F1123', 'occur': '1',
                               'subject': 'relation-resolution',
                               'severity': 'cleared',
                               'origSeverity': 'warning', 'rn': '',
                               'childAction': '', 'type': 'config',
                               'dn': 'uni/tn-common/cif-any-ip/rsif/'
                                     'fault-F1123'}}}]
        result = self.manager.retrieve_aci_objects(objs)
        self.assertEqual([], result)

    def test_get_fault_deletage(self):
        objs = [
            {'faultDelegate': {
                'attributes': {'status': 'modified',
                               'dn': 'uni/vmmp-OpenStack/dom-ostack/ctrlr-'
                                     'ostack/fd-[topology/pod-1/node-301/s'
                                     'ys/br-[eth1/33]/odev-167817343]-faul'
                                     't-F1698'}}}]
        result = self.manager.retrieve_aci_objects(objs)
        self.assertEqual([], result)

    def test_fill_events(self):
        events = [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test", "status": "modified"}}},
        ]
        complete = {"fvRsCtx": {"attributes": {
            "dn": "uni/tn-test-tenant/BD-test/rsctx",
            "tnFvCtxName": "test"}}}
        parent_bd = {
            'fvBD': {
                'attributes': {
                    'arpFlood': 'no', 'dn': 'uni/tn-test-tenant/BD-test',
                    'epMoveDetectMode': '', 'ipLearning': 'yes',
                    'limitIpLearnToSubnets': 'no', 'nameAlias': '',
                    'unicastRoute': 'yes', 'unkMacUcastAct': 'proxy'}}}
        self._add_data_to_tree([parent_bd, complete], self.backend_state)
        events = self.manager.ownership_mgr.filter_ownership(
            self.manager._fill_events(events))
        self.assertEqual(utils.deep_sort([complete, parent_bd]),
                         utils.deep_sort(events))

        # Now start from BD
        events = [{"fvBD": {"attributes": {
            "arpFlood": "yes", "descr": "test",
            "dn": "uni/tn-test-tenant/BD-test", "status": "modified"}}}]
        parent_bd['fvBD']['attributes'].update(events[0]['fvBD']['attributes'])
        parent_bd['fvBD']['attributes'].pop('status')
        events = self.manager.ownership_mgr.filter_ownership(
            self.manager._fill_events(events))
        self.assertEqual(utils.deep_sort([parent_bd, complete]),
                         utils.deep_sort(events))

    def test_fill_events_not_found(self):
        events = [
            {"fvRsCtx": {"attributes": {
                "dn": "uni/tn-test-tenant/BD-test/rsctx",
                "tnFvCtxName": "test", "status": "modified"}}},
        ]
        events = self.manager.ownership_mgr.filter_ownership(
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
        result = self.manager.ownership_mgr.filter_ownership(events)
        self.assertEqual(set(), self.manager.ownership_mgr.owned_set)
        self.assertEqual(events, result)

        # Now a tag is added to set ownership of one of the to contexts
        tag = {'tagInst': {
               'attributes': {
                   'dn': 'uni/tn-ivar-wstest/BD-test-2/rsctx/'
                         'tag-' + self.sys_id}}}
        events_with_tag = events + [tag]
        result = self.manager.ownership_mgr.filter_ownership(events_with_tag)
        self.assertEqual(set(['uni/tn-ivar-wstest/BD-test-2/rsctx']),
                         self.manager.ownership_mgr.owned_set)
        self.assertEqual(events, result)

        # Now delete the tag
        tag['tagInst']['attributes']['status'] = 'deleted'
        result = self.manager.ownership_mgr.filter_ownership(events_with_tag)
        self.assertEqual(set(), self.manager.ownership_mgr.owned_set)
        self.assertEqual(events, result)

    def test_fill_events_fault(self):
        events = [
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                               'tnFvCtxName': 'asasa'}}},
            {'faultInst': {'attributes': {
                'dn': 'uni/tn-ivar-wstest/BD-test/rsctx/fault-F0952',
                'code': 'F0952'}}}
        ]
        complete = [
            {'fvBD': {'attributes': {'arpFlood': 'yes',
                                     'dn': 'uni/tn-ivar-wstest/BD-test',
                                     'epMoveDetectMode': 'garp',
                                     'ipLearning': 'yes',
                                     'limitIpLearnToSubnets': 'no',
                                     'nameAlias': '',
                                     'unicastRoute': 'yes',
                                     'unkMacUcastAct': 'proxy'}}},
            {'fvRsCtx': {
                'attributes': {'dn': 'uni/tn-ivar-wstest/BD-test/rsctx',
                               'tnFvCtxName': 'asasa'}}},
            {'faultInst': {'attributes': {
             'dn': 'uni/tn-ivar-wstest/BD-test/rsctx/fault-F0952',
             'code': 'F0952'}}},
        ]
        self._add_data_to_tree(complete, self.backend_state)
        events = self.manager.ownership_mgr.filter_ownership(
            self.manager._fill_events(events))
        self.assertEqual(utils.deep_sort(complete),
                         utils.deep_sort(events))

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
        self.assertEqual({'hostprotPol': ['hostprotPol'],
                          'hostprotRemoteIp': ['hostprotRule'],
                          'hostprotRule': ['hostprotRule'],
                          'hostprotSubj': ['hostprotSubj'],
                          'hostprotRemoteIpContainer': (
                              ['hostprotRemoteIpContainer']),
                          'hostprotRsRemoteIpContainer': (['hostprotRule']),
                          'infraRsSpanVSrcGrp': ['infraAccBndlGrp'],
                          'infraRsSpanVDestGrp': ['infraAccBndlGrp']},
                         aci_tenant.ACI_TYPES_NOT_CONVERT_IF_MONITOR)

    def test_tenant_dn_root(self):
        manager = aci_tenant.AciTenantManager(
            'tn-test', self.cfg_manager,
            aci_universe.get_apic_clients_context(self.cfg_manager, None))
        self.assertEqual('uni/tn-test', manager.tenant.dn)
        manager = aci_tenant.AciTenantManager(
            'phys-test', self.cfg_manager,
            aci_universe.get_apic_clients_context(self.cfg_manager, None))
        self.assertEqual('uni/phys-test', manager.tenant.dn)
        manager = aci_tenant.AciTenantManager(
            'pod-test', self.cfg_manager,
            aci_universe.get_apic_clients_context(self.cfg_manager, None))
        self.assertEqual('topology/pod-test', manager.tenant.dn)
