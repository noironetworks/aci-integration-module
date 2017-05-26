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

import traceback

from oslo_log import log as logging
import oslo_messaging

from aim.common import utils
from aim import config as aim_cfg


LOG = logging.getLogger(__name__)
TOPIC_AID_EVENT = 'aid_event'


class AIDEventRpcApi(object):
    """RPC client"""

    AID_RPC_VERSION = "1.0"

    def __init__(self):
        target = oslo_messaging.Target(
            topic=TOPIC_AID_EVENT, version=self.AID_RPC_VERSION)
        # If a transport backend is explicitly set in the config file, this
        # module will become a proper RPC client. If not, we make sure the
        # default is an invalid string and all the RPCs called from this
        # class will be noop.
        aim_cfg.cfg.set_defaults(oslo_messaging.transport._transport_opts,
                                 rpc_backend='')
        try:
            transport = oslo_messaging.get_transport(aim_cfg.CONF)
            self.client = oslo_messaging.RPCClient(transport, target)
        except (oslo_messaging.DriverLoadFailure,
                oslo_messaging.InvalidTransportURL) as ex:
            LOG.debug(traceback.format_exc())
            LOG.debug("Couldn't initialize RPC transport, this API will be a "
                      "noop: %s" % ex.message)
            self.client = None

    @utils.log
    def serve(self, context, server=None):
        LOG.debug("Sending broadcast 'serve' message")
        return self._cast(context, 'serve', server)

    @utils.log
    def reconcile(self, context, server=None):
        LOG.debug("Sending broadcast 'reconcile' message")
        return self._cast(context, 'reconcile', server)

    def _cast(self, context, method, server):
        if self.client:
            if server:
                cctxt = self.client.prepare(server=server)
            else:
                cctxt = self.client
            return cctxt.cast(context, method, fanout=True)

    def tree_creation_postcommit(self, session, added, updated, deleted):
        if added or deleted:
            self.serve({})
        elif updated:
            # Serve implies a reconcile
            self.reconcile({})


class AIDEventServerRpcCallback(object):
    """Server side event RPC."""

    AID_RPC_VERSION = "1.0"
    target = oslo_messaging.Target(version=AID_RPC_VERSION)

    def __init__(self, sender):
        self.sender = sender

    def serve(self, context, **kwargs):
        return self.sender.serve()

    def reconcile(self, context, **kwargs):
        return self.sender.reconcile()


class Connection(object):

    def __init__(self):
        super(Connection, self).__init__()
        self.servers = []
        self.transport = oslo_messaging.get_transport(aim_cfg.CONF)

    def create_consumer(self, topic, endpoints):
        target = oslo_messaging.Target(
            topic=topic, server=aim_cfg.CONF.aim.aim_service_identifier)
        server = oslo_messaging.get_rpc_server(self.transport, target,
                                               endpoints)
        self.servers.append(server)

    def consume_in_threads(self):
        for server in self.servers:
            server.start()
        return self.servers

    def close(self):
        for server in self.servers:
            server.stop()
        for server in self.servers:
            server.wait()
