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
import signal
import sys

import cherrypy
from oslo_log import log as logging

from aim import aim_manager
from aim.api import resource as api_res
from aim.api import status as api_status
from aim.common import utils
from aim import config as aim_cfg
from aim import context
from aim.db import api

LOG = logging.getLogger(__name__)
STATIC_QUERY_PARAMS = {
    'include-status',
    'object-type',
    'include-config'
}


class Root(object):

    def __init__(self, config):
        self.aimc = AIMController(config)

    def _cp_dispatch(self, vpath):
        if vpath[0] == 'aim':
            cherrypy.request.params['path_'] = copy.copy(vpath)
            while vpath:
                vpath.pop(0)
            return self.aimc
        raise cherrypy.HTTPError(404)


class AIMController(object):

    def __init__(self, config):
        self.cfg = config
        self.ctx = context.AimContext(store=api.get_store())
        self.mgr = aim_manager.AimManager()
        self.sneak_name_to_klass = {utils.camel_to_snake(x.__name__): x
                                    for x in self.mgr.aim_resources}

    @cherrypy.expose()
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def index(self, path_, *args, **kwargs):
        self._validate_path(path_)
        method = self._get_method()
        try:
            func = getattr(self, method)
        except AttributeError:
            raise cherrypy.HTTPError(405)
        return func(path_, *args, **kwargs)

    def GET(self, path_, *args, **kwargs):
        # Get the whole state unless filtered
        get_status, klasses, filters = self._inspect_selection_query(**kwargs)
        # Get status and faults only if explicitly requested
        klasses.discard(api_status.AciStatus)
        klasses.discard(api_status.AciFault)
        all_resources = []
        data = []
        for klass in klasses:
            all_resources.extend(self.mgr.find(
                self.ctx, klass, include_aim_id=True, **filters))
        for obj in all_resources:
            if get_status:
                status = self.mgr.get_status(self.ctx, obj,
                                             create_if_absent=False)
                if status:
                    faults = status.faults
                    del status.faults
                    data.append(self._generate_data_item(status))
                    data.extend([self._generate_data_item(f) for f in faults])
            data.append(self._generate_data_item(obj))
        return self._generate_response(data)

    def POST(self, path_, *args, **kwargs):
        # Replace the whole model
        self.DELETE(path_)
        self.PUT(path_)

    def PUT(self, path_, *args, **kwargs):
        try:
            body = cherrypy.request.json
        except AttributeError:
            body = json.loads(cherrypy.request.body.read())
        for item in body:
            res = self._generate_aim_resource(item)
            self.mgr.create(self.ctx, res, overwrite=True)

    def DELETE(self, path_, *args, **kwargs):
        _, klasses, filters = self._inspect_selection_query(**kwargs)
        for klass in klasses:
            self.mgr.delete_all(self.ctx, klass, **filters)

    def _inspect_selection_query(self, **kwargs):
        include_status = kwargs.pop('include-status', False)
        obj_type = kwargs.pop('object-type', None)
        include_config = kwargs.pop('include-config', None)
        if obj_type:
            klasses = {self.sneak_name_to_klass.get(obj_type)}
            filters = {x: y for x, y in list(kwargs.items())
                       if x not in STATIC_QUERY_PARAMS}
        else:
            klasses = {x for x in self.mgr.aim_resources}
            filters = {}
        if not include_config:
            klasses.discard(api_res.Configuration)
        return include_status, klasses, filters

    def _generate_data_item(self, aim_resource):
        return {'type': utils.camel_to_snake(type(aim_resource).__name__),
                'aim_id': aim_resource.__dict__.pop('_aim_id', ''),
                'attributes': aim_resource.__dict__}

    def _generate_aim_resource(self, data_item):
        return self.sneak_name_to_klass[data_item['type']](
            **data_item['attributes'])

    def _get_method(self):
        return cherrypy.request.method

    def _generate_response(self, data):
        return {'count': len(data), 'data': data}

    def _generate_error(self, code, text):
        pass

    def _validate_path(self, path):
        if path != ['aim']:
            raise cherrypy.HTTPError(404)

    def generate_http_error(self, status, code, text='Unknown Error'):
        cherrypy.response.status = status
        return self._generate_response([self._generate_error(code, text)])


def run(config, retry=True):
    cherry_conf = {
        'log.screen': False, 'tools.trailing_slash.on': False,
        'server.socket_port': config.aim_server.port,
        'tools.json_in.force': False
    }
    socket_file = config.aim_server.socket_file
    binding_ip = config.aim_server.binding_ip
    if socket_file:
        cherry_conf['server.socket_file'] = socket_file
    elif binding_ip:
        cherry_conf['server.socket_host'] = binding_ip
    cherrypy.config.update(cherry_conf)
    root = Root(config=config)
    cherrypy.tree.mount(root)
    try:
        cherrypy.engine.start()
    except cherrypy.process.wspbus.ChannelFailures:
        shutdown()
        if retry:
            run(config)
    if socket_file:
        return socket_file, None, root
    else:
        return cherrypy.server.bound_addr + (root, )


def shutdown():
    cherrypy.engine.stop()
    cherrypy.process.bus.exit()


def main():
    aim_cfg.init(sys.argv[1:])
    aim_cfg.setup_logging()
    signal.signal(signal.SIGTERM, shutdown)
    try:
        run(aim_cfg.CONF, False)
    except (RuntimeError, ValueError) as e:
        LOG.error("%s CherryPy Server terminated!" % e)
        sys.exit(1)
