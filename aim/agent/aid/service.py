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

import signal
import sys
import time
import traceback

from oslo_log import log as logging
import semantic_version

from aim.agent.aid import event_handler
from aim.agent.aid.universes.aci import aci_universe
from aim.agent.aid.universes import aim_universe
from aim.agent.aid.universes.k8s import k8s_watcher
from aim import aim_manager
from aim.api import resource
from aim.common import hashring
from aim.common import utils
from aim import config as aim_cfg
from aim import context
from aim.db import api
from aim import tree_manager

LOG = logging.getLogger(__name__)
AGENT_TYPE = 'Aci Synchronization Module'
AGENT_VERSION = '1.0.0'
AGENT_BINARY = 'aci-inconsistency-detector'
AGENT_DESCRIPTION = ('This Agent synchronizes the AIM state with ACI for a '
                     'certain amount of Tenants.')
DESIRED = 'desired'
CURRENT = 'current'
AID_EXIT_CHECK_INTERVAL = 5

logging.register_options(aim_cfg.CONF)


class AID(object):

    def __init__(self, conf):
        self.run_daemon_loop = True
        self.host = conf.aim.aim_service_identifier

        aim_ctx = context.AimContext(store=api.get_store())
        # This config manager is shared between multiple threads. Therefore
        # all DB activity through this config manager will use the same
        # DB session which can result in conflicts.
        # TODO(amitbose) Fix ConfigManager to not use cached AimContext
        self.conf_manager = aim_cfg.ConfigManager(aim_ctx, self.host)

        # Define multiverse pairs, First position is desired state
        self.multiverse = [
            # Configuration Universe (AIM to ACI)
            {DESIRED: aim_universe.AimDbUniverse().initialize(
                api.get_store(), self.conf_manager),
             CURRENT: aci_universe.AciUniverse().initialize(
                 api.get_store(), self.conf_manager)},
            # Operational Universe (ACI to AIM)
            {DESIRED: aci_universe.AciOperationalUniverse().initialize(
                api.get_store(), self.conf_manager),
             CURRENT: aim_universe.AimDbOperationalUniverse().initialize(
                 api.get_store(), self.conf_manager)},
            # Monitored Universe (ACI to AIM)
            {DESIRED: aci_universe.AciMonitoredUniverse().initialize(
                api.get_store(), self.conf_manager),
             CURRENT: aim_universe.AimDbMonitoredUniverse().initialize(
                 api.get_store(), self.conf_manager)},
        ]
        # delete_candidates contains tenants that are candidate for deletion.
        # when the consensus is reach by all the universe, the state will
        # be cleaned up by the reconcile action
        self.delete_candidates = {}
        self.consensus = len(self.multiverse)
        # Operational Universes. ACI operational info will be synchronized into
        # AIM's
        self.manager = aim_manager.AimManager()
        self.tree_manager = tree_manager.HashTreeManager()
        self.agent_id = 'aid-%s' % self.host
        self.agent = resource.Agent(id=self.agent_id, agent_type=AGENT_TYPE,
                                    host=self.host, binary_file=AGENT_BINARY,
                                    description=AGENT_DESCRIPTION,
                                    version=AGENT_VERSION, beat_count=0)
        # Register agent
        self._send_heartbeat(aim_ctx)
        # Report procedure should happen asynchronously
        self.polling_interval = self.conf_manager.get_option_and_subscribe(
            self._change_polling_interval, 'agent_polling_interval',
            group='aim')
        self.report_interval = self.conf_manager.get_option_and_subscribe(
            self._change_report_interval, 'agent_report_interval', group='aim')
        self.squash_time = self.conf_manager.get_option_and_subscribe(
            self._change_squash_time, 'agent_event_squash_time', group='aim')
        self._spawn_heartbeat_loop()
        self.events = event_handler.EventHandler().initialize(
            self.conf_manager)
        self.max_down_time = 4 * self.report_interval
        self.k8s_watcher = None
        self.single_aid = False
        if conf.aim.aim_store == 'k8s':
            self.single_aid = True
            self.k8s_watcher = k8s_watcher.K8sWatcher()
            self.k8s_watcher.run()

    def daemon_loop(self):
        aim_ctx = context.AimContext(store=api.get_store())
        # Serve tenants the very first time regardless of the events received
        self._daemon_loop(aim_ctx, True)
        while True:
            try:
                serve = False
                # wait first event
                first_event_time = None
                squash_time = AID_EXIT_CHECK_INTERVAL
                while squash_time > 0:
                    event = self.events.get_event(squash_time)
                    if not event and first_event_time is None:
                        # This is a lone timeout, just check if we need to exit
                        if not self.run_daemon_loop:
                            LOG.info("Stopping AID main loop.")
                            return
                        continue
                    if not first_event_time:
                        first_event_time = time.time()
                    if event in event_handler.EVENTS + [None]:
                        # Set squash timeout
                        squash_time = (first_event_time + self.squash_time -
                                       time.time())
                        if event == event_handler.EVENT_SERVE:
                            # Serving tenants is required as well
                            serve = True
                start_time = time.time()
                self._daemon_loop(aim_ctx, serve)
                utils.wait_for_next_cycle(start_time, self.polling_interval,
                                          LOG, readable_caller='AID',
                                          notify_exceeding_timeout=False)
            except Exception:
                LOG.error('A error occurred in agent')
                LOG.error(traceback.format_exc())

    def _daemon_loop(self, aim_ctx, serve=True):
        if serve:
            LOG.info("Start serving cycle.")
            tenants = self._calculate_tenants(aim_ctx)
            # Filter delete candidates with currently served tenants
            self.delete_candidates = {k: v for k, v in
                                      self.delete_candidates.iteritems()
                                      if k in tenants}
            # Serve tenants
            for pair in self.multiverse:
                pair[DESIRED].serve(tenants)
                pair[CURRENT].serve(tenants)
            LOG.info("AID %s is currently serving: "
                     "%s" % (self.agent.id, tenants))

        LOG.info("Start reconciliation cycle.")
        # REVISIT(ivar) Might be wise to wait here upon tenant serving to allow
        # time for events to happen

        # Observe the two universes to fix their current state
        for pair in self.multiverse:
            pair[DESIRED].observe()
            pair[CURRENT].observe()

        # Reconcile everything
        changes = False
        for pair in self.multiverse:
            changes |= pair[CURRENT].reconcile(pair[DESIRED],
                                               self.delete_candidates)
        if not changes:
            LOG.info("Congratulations! your multiverse is nice and synced :)")

        # Delete tenants if there's consensus
        for tenant, votes in self.delete_candidates.iteritems():
            if len(votes) == self.consensus:
                # All the universes agree on this tenant cleanup
                for pair in self.multiverse:
                    for universe in pair.values():
                        LOG.info("%s removing tenant from AIM %s" %
                                 (universe.name, tenant))
                        universe.cleanup_state(tenant)

    def _spawn_heartbeat_loop(self):
        utils.spawn_thread(self._heartbeat_loop)

    def _heartbeat_loop(self):
        aim_ctx = context.AimContext(store=api.get_store())
        while True:
            start = time.time()
            self._send_heartbeat(aim_ctx)
            time.sleep(
                max(0, self.report_interval - (time.time() - start)))

    def _send_heartbeat(self, aim_ctx):
        LOG.debug("Sending Heartbeat for agent %s" % self.agent_id)
        self.agent.beat_count += 1
        self.agent = self.manager.create(aim_ctx, self.agent,
                                         overwrite=True)

    def _calculate_tenants(self, aim_ctx):
        # REVISIT(ivar): should we lock the Agent table?
        with aim_ctx.store.begin(subtransactions=True):
            # Refresh this agent
            self.agent = self.manager.get(aim_ctx, self.agent)
            if not self.single_aid:
                down_time = self.agent.down_time(aim_ctx)
                if max(0, down_time or 0) > self.max_down_time:
                    utils.perform_harakiri(LOG, "Agent has been down for %s "
                                                "seconds." % down_time)
                # Get peers
                agents = [
                    x for x in self.manager.find(aim_ctx, resource.Agent,
                                                 admin_state_up=True)
                    if not x.is_down(aim_ctx)]
                # Validate agent version
                if not agents:
                    return []
                max_version = max(agents, key=lambda x: x.version).version
                if self._major_vercompare(self.agent.version, max_version) < 0:
                    LOG.error("Agent version is outdated: Current %s Required "
                              "%s" % (self.agent.version, max_version))
                    return []
                # Purge outdated agents
                agents = [x for x in agents if
                          self._major_vercompare(x.version, max_version) == 0]
            else:
                agents = [self.agent]
            result = self._tenant_assignation_algorithm(aim_ctx, agents)
            # Store result in DB
            self.agent.hash_trees = result
            self.manager.create(aim_ctx, self.agent, overwrite=True)
            return result

    def _tenant_assignation_algorithm(self, aim_ctx, agents):
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
        for tenant in self.tree_manager.get_roots(aim_ctx):
            allocations = ring.assign_key(tenant)
            if self.agent_id in allocations:
                result.append(tenant)
        return result

    def _major_vercompare(self, x, y):
        return (semantic_version.Version(x).major -
                semantic_version.Version(y).major)

    def _handle_sigterm(self, signum, frame):
        LOG.warn("Agent caught SIGTERM, quitting daemon loop.")
        self.run_daemon_loop = False
        if self.k8s_watcher:
            self.k8s_watcher.stop_threads()

    def _change_polling_interval(self, new_conf):
        # TODO(ivar): interrupt current sleep and restart with new value
        self.polling_interval = new_conf['value']

    def _change_report_interval(self, new_conf):
        # TODO(ivar): interrupt current sleep and restart with new value
        self.report_interval = new_conf['value']

    def _change_squash_time(self, new_conf):
        # TODO(ivar): interrupt current sleep and restart with new value
        self.squash_time = new_conf['value']


def main():
    aim_cfg.init(sys.argv[1:])
    aim_cfg.setup_logging()
    try:
        agent = AID(aim_cfg.CONF)
    except (RuntimeError, ValueError) as e:
        LOG.error("%s Agent terminated!" % e)
        sys.exit(1)

    signal.signal(signal.SIGTERM, agent._handle_sigterm)
    agent.daemon_loop()


if __name__ == '__main__':
    main()
