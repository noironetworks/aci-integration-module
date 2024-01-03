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

from oslo_log import log as logging
import semantic_version
import sqlalchemy as sa

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
AGENT_VERSION = '2.0.0'
AGENT_BINARY = 'aci-inconsistency-detector'
AGENT_DESCRIPTION = ('This Agent synchronizes the AIM state with ACI for a '
                     'certain amount of Tenants.')
DESIRED = 'desired'
CURRENT = 'current'
AID_EXIT_CHECK_INTERVAL = 5
DAEMON_LOOP_MAX_WAIT = 5
DAEMON_LOOP_MAX_RETRIES = 5
HB_LOOP_MAX_WAIT = 60
HB_LOOP_MAX_RETRY = 10
DEFAULT_VNODES_HASHRING = 40

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
        self.k8s_watcher = None
        self.single_aid = False
        if conf.aim.aim_store == 'k8s':
            self.single_aid = True
            self.k8s_watcher = k8s_watcher.K8sWatcher()
            self.k8s_watcher.run()

        self.multiverse = []
        # Define multiverse pairs, First position is desired state
        self.multiverse += [
            # Configuration Universe (AIM to ACI)
            {DESIRED: aim_universe.AimDbUniverse().initialize(
                self.conf_manager, self.multiverse),
             CURRENT: aci_universe.AciUniverse().initialize(
                 self.conf_manager, self.multiverse)},
            # Operational Universe (ACI to AIM)
            {DESIRED: aci_universe.AciOperationalUniverse().initialize(
                self.conf_manager, self.multiverse),
             CURRENT: aim_universe.AimDbOperationalUniverse().initialize(
                 self.conf_manager, self.multiverse)},
            # Monitored Universe (ACI to AIM)
            {DESIRED: aci_universe.AciMonitoredUniverse().initialize(
                self.conf_manager, self.multiverse),
             CURRENT: aim_universe.AimDbMonitoredUniverse().initialize(
                 self.conf_manager, self.multiverse)},
        ]
        # Operational Universes. ACI operational info will be synchronized into
        # AIM's
        self.manager = aim_manager.AimManager()
        self.tree_manager = tree_manager.HashTreeManager()
        self.agent_id = 'aid-%s' % self.host
        self.agent = resource.Agent(id=self.agent_id, agent_type=AGENT_TYPE,
                                    host=self.host, binary_file=AGENT_BINARY,
                                    description=AGENT_DESCRIPTION,
                                    version=AGENT_VERSION)
        # Register agent
        self.agent = self.manager.create(aim_ctx, self.agent, overwrite=True)
        # Report procedure should happen asynchronously
        self.polling_interval = self.conf_manager.get_option_and_subscribe(
            self._change_polling_interval, 'agent_polling_interval',
            group='aim')
        self.report_interval = self.conf_manager.get_option_and_subscribe(
            self._change_report_interval, 'agent_report_interval', group='aim')
        self.squash_time = self.conf_manager.get_option_and_subscribe(
            self._change_squash_time, 'agent_event_squash_time', group='aim')
        self.deadlock_time = self.conf_manager.get_option_and_subscribe(
            self._change_deadlock_time, 'agent_deadlock_time', group='aim')
        self._spawn_heartbeat_loop()
        self.events = event_handler.EventHandler().initialize(
            self.conf_manager)
        self.max_down_time = 4 * self.report_interval
        self.daemon_loop_time = time.time()

    def daemon_loop(self):
        # Serve tenants the very first time regardless of the events received
        self.events.serve()
        self._daemon_loop()

    @utils.retry_loop(DAEMON_LOOP_MAX_WAIT, DAEMON_LOOP_MAX_RETRIES, 'AID',
                      fail=True)
    def _daemon_loop(self):
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
                    raise utils.StopLoop()
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
        self._reconciliation_cycle(serve)
        utils.wait_for_next_cycle(start_time, self.polling_interval,
                                  LOG, readable_caller='AID',
                                  notify_exceeding_timeout=False)

    @utils.retry_loop(DAEMON_LOOP_MAX_WAIT, DAEMON_LOOP_MAX_RETRIES, 'AID-REC',
                      fail=False, return_=True)
    def _reconciliation_cycle(self, serve=True):
        # Regenerate context at each reconciliation cycle
        # TODO(ivar): set request-id so that oslo log can track it
        aim_ctx = context.AimContext(store=api.get_store())
        if serve:
            LOG.info("Start serving cycle.")
            tenants = self._calculate_tenants(aim_ctx)
            # Serve tenants
            for pair in self.multiverse:
                pair[DESIRED].serve(aim_ctx, tenants)
                pair[CURRENT].serve(aim_ctx, tenants)
            LOG.info("AID %s is currently serving: "
                     "%s" % (self.agent.id, tenants))

        LOG.info("Start reconciliation cycle.")
        # REVISIT(ivar) Might be wise to wait here upon tenant serving to allow
        # time for events to happen

        # Observe the two universes to fix their current state
        for pair in self.multiverse:
            pair[DESIRED].observe(aim_ctx)
            pair[CURRENT].observe(aim_ctx)

        delete_candidates = set()
        vetoes = set()
        for pair in self.multiverse:
            pair[DESIRED].vote_deletion_candidates(
                aim_ctx, pair[CURRENT], delete_candidates, vetoes)
            pair[CURRENT].vote_deletion_candidates(
                aim_ctx, pair[DESIRED], delete_candidates, vetoes)
        # Reconcile everything
        changes = False
        for pair in self.multiverse:
            changes |= pair[CURRENT].reconcile(aim_ctx, pair[DESIRED],
                                               delete_candidates)
        if not changes:
            LOG.info("Congratulations! your multiverse is nice and synced :)")

        for pair in self.multiverse:
            pair[DESIRED].finalize_deletion_candidates(aim_ctx, pair[CURRENT],
                                                       delete_candidates)
            pair[CURRENT].finalize_deletion_candidates(aim_ctx, pair[DESIRED],
                                                       delete_candidates)

        # Delete tenants if there's consensus
        for tenant in delete_candidates:
            # All the universes agree on this tenant cleanup
            for pair in self.multiverse:
                for universe in list(pair.values()):
                    LOG.info("%s removing tenant from AID %s" %
                             (universe.name, tenant))
                    universe.cleanup_state(aim_ctx, tenant)
        self.daemon_loop_time = time.time()

    def _spawn_heartbeat_loop(self):
        utils.spawn_thread(self._heartbeat_loop)

    @utils.retry_loop(HB_LOOP_MAX_WAIT, HB_LOOP_MAX_WAIT, 'AID-HB', fail=True)
    def _heartbeat_loop(self):
        start_time = time.time()
        aim_ctx = context.AimContext(store=api.get_store())
        self._send_heartbeat(aim_ctx)
        # REVISIT: This code should be removed once we've
        #          removed all the locking in AID.
        if start_time > self.daemon_loop_time:
            down_time = start_time - self.daemon_loop_time
            if down_time > self.deadlock_time:
                utils.perform_harakiri(LOG, "Agent has been down for %s "
                                       "seconds." % down_time)

        utils.wait_for_next_cycle(start_time, self.report_interval,
                                  LOG, readable_caller='AID-HB',
                                  notify_exceeding_timeout=False)

    def _send_heartbeat(self, aim_ctx):
        LOG.info("Sending Heartbeat for agent %s" % self.agent_id)
        self.agent = self.manager.update(aim_ctx, self.agent)

    def get_vnodes_value(self, aim_ctx):
        dbsession = aim_ctx.store.db_session
        dbsession.get_bind()
        with dbsession.begin():
            aim_consistent_hashring_params_table = sa.Table(
                'aim_consistent_hashring_params', sa.MetaData(),
                sa.Column('value', sa.Integer, nullable=False),
                sa.Column('name', sa.String(16), nullable=False,
                          primary_key=True))
            query = (sa.select(aim_consistent_hashring_params_table.c.value).
                     where(aim_consistent_hashring_params_table.c.name ==
                           'vnodes'))
            result = dbsession.execute(query).fetchone()
            vnodes_value = result[0] if result else DEFAULT_VNODES_HASHRING
            return vnodes_value

    def _calculate_tenants(self, aim_ctx):
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
        LOG.info("Vnodes value %s" % self.get_vnodes_value(aim_ctx))
        ring = hashring.ConsistentHashRing(
            dict([(x.id, None) for x in agents]),
            vnodes=self.get_vnodes_value(aim_ctx))
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
        LOG.warning("Agent caught SIGTERM, quitting daemon loop.")
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

    def _change_deadlock_time(self, new_conf):
        # REVISIT: interrupt current sleep and restart with new value
        self.deadlock_time = new_conf['value']


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
