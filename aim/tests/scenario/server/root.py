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

import copy
import json
from Queue import Queue

from apicapi import apic_client
import cherrypy
from ws4py.server.cherrypyserver import WebSocketPlugin
from ws4py.server.cherrypyserver import WebSocketTool
from ws4py.websocket import WebSocket

from aim.agent.aid.universes.aci import tenant
from aim.common import utils
from aim.tests.scenario.server import error_msg
from aim.tests.unit.agent.aid_universes import test_aci_tenant


COOKIE_NAME = 'APIC-cookie'
LOGIN_URL = 'aaaLogin'
LOGIN_REFRESH = 'aaaRefresh'
SUB_REFRESH = 'subscriptionRefresh'


class ApicStorage(object):

    def __init__(self, controller):
        self.root = controller.root
        self.store = self.root.store
        self.class_store = self.root.class_store
        self.controller = controller

    def post_server_data(self, url, data):
        dn_mgr = apic_client.DNManager()
        decomposed = test_aci_tenant.decompose_aci_dn(url)
        root_name = decomposed[0][1]
        root_key = decomposed[0]
        events = []
        with utils.get_rlock(root_key):
            store = {}
            if root_key in self.store:
                store[root_key] = self.store.pop(root_key)
            for resource in data:
                status = resource.values()[0]['attributes'].pop('status',
                                                                'created')
                raise_if_not_found = resource.values()[0]['attributes'].pop(
                    '_raise_if_not_found', True)
                res_copy = copy.deepcopy(resource)
                add = status != 'deleted'
                data_type = resource.keys()[0]
                try:
                    dn = resource.values()[0]['attributes']['dn']
                    decomposed = dn_mgr.aci_decompose_dn_guess(dn,
                                                               data_type)[1]
                    if decomposed[0][1] != root_name:
                        return self.controller.generate_http_error('400', '0')
                    if add:
                        curr = store.setdefault(root_key, [])
                    else:
                        curr = store.get(root_key, [])
                except Exception:
                    return self.controller.generate_http_error('400', '0')
                prev = None
                child_index = None
                last_index = len(decomposed) - 1
                is_new = False
                for out_index, part in enumerate(decomposed):
                    # Look at the current's children and find the proper node.
                    # if not found, it's a new node
                    if part[0] in apic_client.MULTI_PARENT:
                        partial_dn = (
                            dn_mgr.build(
                                decomposed[:out_index]) + '/' +
                            apic_client.ManagedObjectClass.mos_to_prefix[
                                part[0]] +
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
                                return self.controller.generate_http_error(
                                    '404', '0')
                            else:
                                # Append newly created object
                                obj = {
                                    part[0]: {'attributes': {'dn': partial_dn},
                                              'children': []}
                                }
                                curr.append(obj)
                                resource.values()[0].pop('children', None)
                                obj[part[0]].update(resource.values()[0])
                                res_copy.values()[0][
                                    'attributes']['status'] = 'created'
                                events.append(res_copy)
                                is_new = True
                        else:
                            # Not found
                            if raise_if_not_found:
                                return self.controller.generate_http_error(
                                    '404', '0')
                            else:
                                continue
                # Update body
                if not add:
                    if child_index is not None:
                        deleted = [prev.pop(child_index)]
                        tenant.AciTenantManager.flat_events(deleted)
                        for obj in deleted:
                            attrs = {'status': 'deleted',
                                     'dn': obj.values()[0]['attributes']['dn']}
                            obj.values()[0]['attributes'] = attrs
                            obj.values()[0].pop('children', None)
                            events.append(obj)
                        if prev is store[root_key]:
                            # Tenant is now empty
                            store.pop(root_key)
                    else:
                        # Root node
                        store.pop(root_key)
                elif child_index is not None and not is_new:
                    children = prev[child_index].values()[0]['children']
                    prev[child_index].update(resource)
                    prev[child_index].values()[0]['children'] = children
                    res_copy.values()[0]['attributes']['status'] = 'modified'
                    events.append(res_copy)
            for event in events:
                class_set = self.class_store.setdefault(event.keys()[0], set())
                dn = event.values()[0]['attributes']['dn']
                if event.values()[0]['attributes']['status'] == 'deleted':
                    class_set.discard(dn)
                else:
                    class_set.add(dn)
                self.root.internal_events.put(
                    self.controller.generate_response([event]))
            self.store.update(store)

    def remove_server_data(self, dn):
        decomposed = test_aci_tenant.decompose_aci_dn(dn)
        data = [{decomposed[-1][0]: {'attributes': {
            'dn': dn, 'status': 'deleted', '_raise_if_not_found': False}}}]
        return self.post_server_data(dn, data)

    def get_server_data(self, dn, **kwargs):
        query_target = kwargs.get('query-target')
        rsp_subtree_include = kwargs.get('rsp-subtree-include')
        target_subtree_class = kwargs.get('target-subtree-class')
        try:
            decomposed = test_aci_tenant.decompose_aci_dn(dn)
            root_key = decomposed[0]
            return test_aci_tenant.mock_get_data(
                None, dn, store=self.store, root_key=root_key,
                query_target=query_target,
                rsp_subtree_include=rsp_subtree_include,
                target_subtree_class=target_subtree_class), None
        except apic_client.cexc.ApicResponseNotOk as e:
            return None, self.controller.generate_http_error(
                e.err_status, e.err_code, e.message)


class Root(object):

    def __init__(self):
        self.ws_handlers = {}
        self.subscriptions = {}
        self.store = {}
        self.class_store = {}
        self.tokens = set()
        self.internal_events = Queue()
        self.apic = ApicController(self)
        self.ws = WebSocketController(self)

    def _cp_dispatch(self, vpath):
        if vpath[0] == 'api':
            cherrypy.config.update({'tools.websocket.on': False})
            cherrypy.request.params['path'] = copy.copy(vpath)
            while vpath:
                vpath.pop(0)
            return self.apic
        elif vpath[0].startswith('socket'):
            cherrypy.request.params['token'] = vpath[0].split('socket')[-1]
            vpath.pop(0)
            cherrypy.config.update({'tools.websocket.on': True,
                                    'tools.websocket.handler_cls': WebSocket})
            return self.ws
        return vpath

    @cherrypy.expose
    def index(self, path, *args, **kwargs):
        return "Hello world!"


class WebSocketController(object):

    def __init__(self, root):
        self.root = root
        utils.spawn_thread(target=self.handle_events)

    @cherrypy.expose
    def index(self, token):
        self.root.ws_handlers[token] = cherrypy.request.ws_handler

    def handle_events(self):
        while True:
            event = self.root.internal_events.get()
            # TODO(ivar): only send to the right subscription
            for token, subs in self.root.subscriptions.iteritems():
                handler = self.root.ws_handlers.get(token)
                if not handler:
                    # TODO(ivar): log something
                    pass
                for sub in subs:
                    event = copy.deepcopy(event)
                    event['subscriptionId'] = [sub[1]]
                    handler.send(json.dumps(event))


class ApicController(object):

    def __init__(self, root):
        self.root = root
        self.backend = ApicStorage(self)

    def _validate_path(self, vpath):
        if not vpath[-1].endswith('.json'):
            return None, None, self.generate_http_error(
                '405', '6', error_msg.OUTPUT_FORMAT)
        vpath[-1] = vpath[-1][:-5]

        dn, is_class = self.build_dn(vpath)
        return dn, is_class, None

    def _validate_auth(self, method, dn):
        if dn == LOGIN_URL and method == 'POST':
            return
        elif COOKIE_NAME not in cherrypy.request.cookie:
            raise cherrypy.HTTPError(401)
        elif self._get_request_token() not in self.root.tokens:
            raise cherrypy.HTTPError(401)

    def _get_request_token(self):
        return cherrypy.request.cookie[COOKIE_NAME].value

    @cherrypy.expose()
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def index(self, path, *args, **kwargs):
        dn, is_class, err = self._validate_path(path)
        if err:
            return err
        method = self.get_method()
        # self._validate_auth(method, dn)
        try:
            func = getattr(self, method)
        except AttributeError:
            raise cherrypy.HTTPError(405)
        return func(dn, is_class, *args, **kwargs)

    def GET(self, dn, is_class, *args, **kwargs):
        if dn == LOGIN_URL:
            return self.generate_login_token(token=self._get_request_token())
        if dn == SUB_REFRESH:
            return
        if kwargs.get('subscription') == 'yes':
            return self.handle_subscription_request(dn, is_class, **kwargs)
        dns = [dn]
        result = []
        if is_class:
            dns = self.root.class_store.setdefault(dn, [])
        for dn in dns:
            data, err = self.backend.get_server_data(dn, **kwargs)
            if err:
                return err
            else:
                result.extend(data)
        resp = self.generate_response(result)
        return resp

    def POST(self, dn, *args, **kwargs):
        try:
            body = [cherrypy.request.json]
        except AttributeError:
            body = [json.loads(cherrypy.request.body.read())]
        if dn == LOGIN_URL:
            return self.generate_login_token()
        else:
            tenant.AciTenantManager.flat_events(body)
            return self.backend.post_server_data(dn, body)

    def DELETE(self, dn, *args, **kwargs):
        return self.backend.remove_server_data(dn)

    def handle_subscription_request(self, dn, is_class, **kwargs):
        sub_id = utils.generate_uuid()
        self.root.subscriptions.setdefault(
            self._get_request_token(), []).append((dn, sub_id))
        dns = [dn]
        result = []
        if is_class:
            dns = self.root.class_store.setdefault(dn, [])
        for dn in dns:
            decomposed = test_aci_tenant.decompose_aci_dn(dn)
            root_key = decomposed[0]
            with utils.get_rlock(root_key):
                data, err = self.backend.get_server_data(dn, **kwargs)
                if err:
                    if err['imdata'][0][
                            'error']['attributes']['code'] == '404':
                        cherrypy.response.status = 200
                        continue
                    else:
                        return err
                else:
                    result.extend(data)
        return self.generate_subscription_response(result, sub_id)

    def get_method(self):
        return cherrypy.request.method

    def generate_subscription_response(self, data, sub_id):
        resp = self.generate_response(data)
        resp['subscriptionId'] = sub_id
        return resp

    def generate_response(self, data):
        return {"totalCount": str(len(data)), "imdata": data}

    def generate_error(self, code, text):
        return self._create_aci_object('error', code=code, text=text)

    def generate_http_error(self, status, code, text='Unknown Error'):
        cherrypy.response.status = status
        return self.generate_response([self.generate_error(code, text)])

    def generate_login_token(self, token=None):
        token = token or utils.generate_uuid()
        self.root.tokens.add(token)
        cookie = cherrypy.response.cookie
        cookie[COOKIE_NAME] = token
        cookie[COOKIE_NAME]['path'] = '/'
        cookie[COOKIE_NAME]['version'] = 0
        return self.generate_response(
            [self._create_aci_object(LOGIN_URL, token=token,
                                     refreshTimeoutSeconds=86400)])

    def _create_aci_object(self, type, **kwargs):
        obj = {type: {'attributes': kwargs}}
        return obj

    def build_dn(self, path):
        is_class = False
        while path[0] in ['node', 'api', 'mo', 'class']:
            if path[0] == 'class':
                is_class = True
            path = path[1:]
        return '/'.join(path), is_class


def run(retry=True):
    # TODO(ivar): find free port instead of randomly generate one
    cherrypy.config.update(
        {'log.screen': False, 'tools.trailing_slash.on': False,
         'server.socket_port': 0,
         'tools.json_in.force': False})
    WebSocketPlugin(cherrypy.engine).subscribe()
    cherrypy.tools.websocket = WebSocketTool()
    cherrypy.tree.mount(Root(), config={
        '/socket': {'tools.websocket.on': True,
                    'tools.websocket.handler_cls': WebSocket}})
    try:
        cherrypy.engine.start()
    except cherrypy.process.wspbus.ChannelFailures:
        shutdown()
        if retry:
            run()
    return cherrypy.server.bound_addr


def shutdown():
    cherrypy.engine.stop()
    cherrypy.process.bus.exit()
