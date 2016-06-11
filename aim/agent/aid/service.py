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

import sys
import time
import traceback

import gevent
from oslo_log import log as logging
import semantic_version

from aim.agent.aid.universes.aci import aci_universe
from aim.agent.aid.universes import aim_universe
from aim import aim_manager
from aim.api import resource
from aim.common import hashring
from aim import config
from aim import context
from aim.db import api
from aim.db import tree_model

LOG = logging.getLogger(__name__)
AGENT_TYPE = 'Aci Synchronization Module'
AGENT_VERSION = '1.0.0'
AGENT_BINARY = 'aci-inconsistency-detector'
AGENT_DESCRIPTION = ('This Agent synchronizes the AIM state with ACI for a '
                     'certain amount of Tenants.')


class AID(object):

    def __init__(self, conf):
        # Have 5 sessions
        self.session = api.get_session()
        self.desired_universe = aim_universe.AimDbUniverse().initialize(
            api.get_session())
        self.current_universe = aci_universe.AciUniverse().initialize(
            api.get_session())
        # Operational Universes. ACI operational info will be synchronized into
        # AIM's
        self.desired_operational_universe = (
            aci_universe.AciOperationalUniverse().initialize(
                api.get_session()))
        self.current_operational_universe = (
            aim_universe.AimDbOperationalUniverse().initialize(
                api.get_session()))

        self.context = context.AimContext(self.session)
        self.manager = aim_manager.AimManager()
        self.tree_manager = tree_model.TenantHashTreeManager()
        self.polling_interval = conf.aim.agent_polling_interval
        self.host = conf.host
        self.agent_id = 'aid-%s' % self.host
        self.agent = resource.Agent(id=self.agent_id, agent_type=AGENT_TYPE,
                                    host=self.host, binary_file=AGENT_BINARY,
                                    description=AGENT_DESCRIPTION,
                                    version=AGENT_VERSION, beat_count=0)
        # Register agent
        self._send_heartbeat()
        # Report procedure should happen asynchronously
        report_interval = conf.aim.agent_report_interval
        gevent.spawn(self._heartbeat_loop, report_interval)

    def daemon_loop(self):
        while True:
            try:
                start_time = time.time()
                self._daemon_loop()
                self._wait_for_next_cycle(start_time)
            except Exception:
                LOG.error('A error occurred in agent')
                LOG.error(traceback.format_exc())

    def _daemon_loop(self):
        tenants = self._calculate_tenants(self.context)
        # Serve tenants
        self.desired_universe.serve(tenants)
        self.current_universe.serve(tenants)

        self.desired_operational_universe.serve(tenants)
        self.current_operational_universe.serve(tenants)
        # REVISIT(ivar) Might be wise to wait here upon tenant serving to allow
        # time for events to happen

        # Observe the two universes to fix their current state
        self.desired_universe.observe()
        self.current_universe.observe()

        self.desired_operational_universe.observe()
        self.current_operational_universe.observe()

        # Reconcile everything
        self.current_universe.reconcile(self.desired_universe)
        self.current_operational_universe.reconcile(
            self.desired_operational_universe)

    def _heartbeat_loop(self, interval):
        while True:
            start = time.time()
            self._send_heartbeat()
            gevent.sleep(max(0, interval - (time.time() - start)))

    def _send_heartbeat(self):
        LOG.debug("Sending Heartbeat for agent %s" % self.agent_id)
        self.agent.beat_count += 1
        self.agent = self.manager.create(self.context, self.agent,
                                         overwrite=True)

    def _calculate_tenants(self, context):
        # REVISIT(ivar): should we lock the Agent table?
        with context.db_session.begin(subtransactions=True):
            # Refresh this agent
            self.agent = self.manager.get(context, self.agent)
            # Get peers
            agents = [
                x for x in self.manager.find(context, resource.Agent,
                                             admin_state_up=True)
                if not x.is_down()]
            # Validate agent version
            if not agents:
                return []
            max_version = max(agents, key=lambda x: x.version).version
            if self._major_vercompare(self.agent.version, max_version) < 0:
                LOG.error("Agent version is outdated: Current %s Required %s"
                          % (self.agent.version, max_version))
                return []
            # Purge outdated agents
            agents = [x for x in agents if
                      self._major_vercompare(x.version, max_version) == 0]
            result = self._tenant_assignation_algorithm(context, agents)
            # Store result in DB
            self.agent.hash_trees = result
            self.manager.create(context, self.agent, overwrite=True)
            LOG.debug("Calculated tenant list: %s" % result)
            return result

    def _tenant_assignation_algorithm(self, context, agents):
        # TODO(ivar): just randomly hash each tenant to agents for now. This
        # algorithm should be made way more optimal (through the use of
        # consistent hashing) and possibly pluggable.
        result = []
        try:
            agents.index(self.agent)
        except ValueError:
            # This agent is down
            return result
        # TODO(ivar): In future, for better resource usage, each agent
        # could have a weight value in the DB definition
        ring = hashring.ConsistentHashRing(dict([(x.id, None)
                                                 for x in agents]))
        # retrieve tenants
        for tenant in self.tree_manager.get_tenants(self.context):
            allocations = ring.assign_key(tenant)
            if self.agent_id in allocations:
                result.append(tenant)
        return result

    def _wait_for_next_cycle(self, start_time):
        # sleep till end of polling interval
        elapsed = time.time() - start_time
        LOG.debug("AID loop - completed in %(time).3f. ", {'time': elapsed})
        if elapsed < self.polling_interval:
            gevent.sleep(self.polling_interval - elapsed)
        else:
            LOG.debug("Loop iteration exceeded interval "
                      "(%(polling_interval)s vs. %(elapsed)s)!",
                      {'polling_interval': self.polling_interval,
                       'elapsed': elapsed})
            gevent.sleep(0)

    def _major_vercompare(self, x, y):
        return (semantic_version.Version(x).major -
                semantic_version.Version(y).major)


def main():
    config.init(sys.argv[1:])
    try:
        agent = AID(config.CONF)
    except (RuntimeError, ValueError) as e:
        LOG.error("%s Agent terminated!" % e)
        sys.exit(1)
    agent.daemon_loop()


if __name__ == '__main__':
    main()
