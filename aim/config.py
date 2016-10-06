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

import copy
import socket
import time
import traceback

from apicapi import config as apic_config  # noqa
import gevent
from oslo_config import cfg
from oslo_log import log as logging

from aim.common import utils
from aim import context as aim_ctx
from aim.db import api
from aim.db import config_model
from aim import exceptions as exc


LOG = logging.getLogger(__name__)

global_opts = [
    cfg.StrOpt('apic_system_id',
               default='openstack',
               help="Prefix for APIC domain/names/profiles created"),
]


common_opts = [
    cfg.StrOpt('host', default=socket.gethostname(),
               help="Host where this agent/controller is running")
]


agent_opts = [
    cfg.IntOpt('agent_down_time', default=75,
               help=("Seconds to regard the agent is down; should be at "
                     "least twice agent_report_interval.")),
    cfg.IntOpt('agent_polling_interval', default=5,
               help=("Seconds that need to pass before the agent starts each "
                     "new cycle.")),
    cfg.IntOpt('agent_report_interval', default=30,
               help=("Number of seconds after which an agent reports his "
                     "state")),
    cfg.IntOpt('config_polling_interval', default=30,
               help=("Number of seconds the config subscriber thread needs "
                     "to wait between checks.")),
    # Setting to False until further testing is done
    cfg.BoolOpt('poll_config', default=False,
                help=("Check whether to run the configuration poller or "
                      "not.")),
    cfg.StrOpt('aim_system_id', required=True, default='openstack_aid',
               help="Identifier of the AIM system used to mark object "
                    "ownership in ACI"),
    cfg.IntOpt('aci_tenant_polling_yield', default=2,
               help="how long the ACITenant yield to other processed"),
]

cfg.CONF.register_opts(agent_opts, 'aim')
CONF = cfg.CONF


def init(args, **kwargs):
    CONF(args=args, project='aim')


def setup_logging():
    """Sets up the logging options for a log with supplied name."""
    product_name = "aim"
    logging.setup(cfg.CONF, product_name)


class ConfigManager(object):
    """Configuration Manager

    Proxy between the AIM modules and the configuration DB. Will take care of
    correctly parsing DB results.
    """

    # Configurations that will be found in the database. Organized by group
    common_opts = {
        'apic': {
            x.dest: x for x in
            apic_config.apic_opts + apic_config.apic_opts_from_ml2},
        'aim': {
            x.dest: x for x in agent_opts},
        'default': {x.dest: x for x in global_opts},
    }

    true = ['true', 'yes', '1', 't']

    def __init__(self, context, host=''):
        # Use some of the above init params to restrict the manager scope
        # during option GET
        self.map = ConfigManager.common_opts
        self.db = config_model.ConfigurationDBManager()
        self.context = context
        self.host = host
        self.subs_mgr = _get_option_subscriber_manager(self)

    def _to_query_format(self, cfg_obj, host=None):
        """Returns config objects in DB format

        :param cfg_obj: oslo conf object
        :param host: host specific config
        :return:
        """
        host = host or ''
        # Create a DB session
        result = {}
        for group, congifs in self.map.iteritems():
            for k, v in congifs.iteritems():
                try:
                    if group == 'default':
                        value = getattr(cfg_obj, k)
                    else:
                        value = getattr(getattr(cfg_obj, group), k)
                except cfg.NoSuchOptError as e:
                    LOG.debug("Option %s is not registered in group %s"
                              % (k, group))
                    raise e
                if isinstance(v, cfg.IntOpt):
                    value = str(value)
                elif isinstance(v, cfg.StrOpt):
                    pass
                elif isinstance(v, cfg.ListOpt):
                    value = ','.join(value) if value else None
                elif isinstance(v, cfg.BoolOpt):
                    value = str(value)
                result[group, k, host] = value
        return result

    def to_db(self, cfg_obj, host=None, context=None):
        configs = self._to_query_format(cfg_obj, host=host)
        self.db.update_bulk(context or self.context, configs)

    def replace_all(self, cfg_obj, host=None, context=None):
        # If not restricted by host, all the config will be deleted
        configs = self._to_query_format(cfg_obj, host=host)
        LOG.info("Replacing existing configuration for host %s "
                 "with: %s" % (host, configs))
        self.db.replace_all(context or self.context, configs, host=host)

    def _get_option(self, item, group, host):
        # Get per host config if any, or default one
        try:
            if group not in self.map:
                raise exc.UnsupportedAIMConfigGroup(group=group)
            if item not in self.map[group]:
                raise exc.UnsupportedAIMConfig(group=group, conf=item)

            db_conf = self.db.get(self.context, group, item, host=host)
            obj = self.map[group][item]
            value = db_conf['value']
            if isinstance(obj, cfg.IntOpt):
                db_conf['value'] = self._int_opt(value)
            elif isinstance(obj, cfg.StrOpt):
                db_conf['value'] = self._str_opt(value)
            elif isinstance(obj, cfg.ListOpt):
                db_conf['value'] = self._list_opt(value)
            elif isinstance(obj, cfg.BoolOpt):
                db_conf['value'] = self._bool_opt(value)
            else:
                LOG.warn(
                    "Unsupported option type %s of item %s in group %s for "
                    "host %s. Returning None" % (type(obj), item, group, host))
            return db_conf
        except exc.ConfigurationUndefined:
            if host == '':
                raise
            LOG.debug(
                "item %s in group %s for host %s doesn't exist. "
                "Trying with default group." % (item, group, host))
            return self._get_option(item, group, '')

    def get_option(self, item, group='default', host=None):
        host = host or self.host
        return (self._get_option(item, group, host) or {}).get('value')

    def option_subscribe(self, callback, item, group, host, version):
        """Subscribe to a specific option.

        the AIM ConfigManager can be used to subscribe to certain options. The
        subscription requires, besides the option description, the caller to
        pass a callback that will be executed once that specific option is
        modified.

        The caller should guarantee that the callback is idempotent and
        thread-safe. Each subscription gets removed once one option change
        happens, so the subscriber should re-apply for that configuration
        within the callback.

        :param callback: functor to be called when a specific option
        is modified. the callback signature must be:
        def callback([self,]option_dict)
        :param item:
        :param group:
        :param host:
        :param version:
        :return:
        """
        if not host:
            # TODO(ivar): we should rise an exception
            return
        self.subs_mgr.register_callback(callback, item, group, host, version)

    def get_option_and_subscribe(self, callback, item, group='default',
                                 host=None):
        host = host or self.host
        opt = self._get_option(item, group, host)
        self.option_subscribe(callback, item, group, host, opt['version'])
        return opt['value']

    def option_unsubscribe(self, callback, item, group='default', host=None):
        host = host or self.host
        self.subs_mgr.unregister_callback_option(callback, item, group, host)

    def callback_unsubscribe(self, callback):
        self.subs_mgr.unregister_callback(callback)

    def _int_opt(self, value):
        return int(value) if value is not None else None

    def _str_opt(self, value):
        return value

    def _list_opt(self, value):
        return value.split(',') if value is not None else []

    def _bool_opt(self, value):
        if value is None:
            return None
        else:
            return value.lower() in self.true


class ConfigSubscriber(gevent.Greenlet):
    """Configuration Subscriber.

    For each AIM process that requires dynamic configuration, one
    ConfigSubscriber class will be instantiated as an attribute of the
    ConfigManager.
    A configuration subscriber instance consists of:

    - A poller thread: A thread that polls the configuration database to
    find modified configurations.

    - A subscription map: A map of the current subscriptions having the
    following schema:
    {
        conf_group_1: {conf_key_1: {callback_id_1: {'callback': <callback>,
                                                    'version': <version>,
                                                    'hosts': set(<hosts>)},
                                    callback_id_2: {'callback': <callback>,
                                                    'version': <version>,
                                                    'hosts': set(<hosts>)}
                                    },
                       conf_key_2: {<...>},
                    },
        config_group_2: <...>

    }

    - A subscription map by call id: It makes unsubscribe operations faster:
    {
        <call_id_1>: {<group_1>: set(<conf_keys>)}

    }

    Each callback for a specific configuration can only be at a specific
    config version (idempotency is guaranteed by the caller). Multiple hosts
    can be specified on any callback, fallback to the default host is
    provided if the host specific configuration is missing. Whenever one or
    multiple host-specific configurations are found, the callback will be
    called multiple times for every host.
    """

    def __init__(self, config_mgr, *args, **kwargs):
        super(ConfigSubscriber, self).__init__(*args, **kwargs)
        self.subscription_map = {}
        self.map_by_callback_id = {}  # for easier unsubscribe
        self.config_mgr = config_mgr
        # Configuration poller  has its own DB session
        self.session = api.get_session()
        self.context = aim_ctx.AimContext(self.session)
        self._polling_interval = None

    @property
    def polling_interval(self):
        if not self._polling_interval:
            self._polling_interval = self.config_mgr.get_option_and_subscribe(
                self._change_polling_interval, 'config_polling_interval',
                group='aim')
        return self._polling_interval

    @utils.log
    def register_callback(self, callback, item, group, host, version):
        """Main callback subscription method.

        Thread safeness is guaranteed here by the absence of blocking calls
        :param callback: functor to be called when a specific option
        is modified. the callback signature must be:
        def callback([self,]option_dict, config_manager)
        By default, each subscription will be renewed after a change occurs.
        In order to avoid that, an explicit unsubscribe must be sent.
        :param item:
        :param group:
        :param host:
        :param version:
        :return:
        """
        call_id = self._get_call_id(callback)
        in_map = (self.subscription_map.
                  setdefault(group, {}).
                  setdefault(item, {}).
                  setdefault(call_id, {'callback': callback,
                                       'hosts': set()}))
        in_map['version'] = version
        if host not in in_map['hosts'] and len(in_map['hosts']) >= 1:
            raise exc.OneHostPerCallbackItemSubscriptionAllowed(
                tentative_host=host, key=item, group=group, callback=callback,
                curr_hosts=in_map['hosts'])
        in_map['hosts'].add(host)
        self.map_by_callback_id.setdefault(
            call_id, {}).setdefault(group, set()).add(item)

    def renew_subscription(self, callback, item, group, version):
        # Renew a subscription's version if exists
        call_id = self._get_call_id(callback)
        sub = self.subscription_map.get(group, {}).get(item, {}).get(call_id,
                                                                     {})
        sub['version'] = version

    def unregister_callback_option(self, callback, item, group, host=None):
        call_id = self._get_call_id(callback)
        map_group = self.subscription_map.get(group, {})
        map_item = map_group.get(item, {})
        map_callback = map_item.get(call_id, {'hosts': set('')})
        if host:
            map_callback['hosts'].discard(host)
        else:
            # Remove all hosts
            map_callback['hosts'] = set()

        # Eliminate entries if needed
        if len(map_callback['hosts']) == 0:
            # Callback needs to be removed for this item
            self.subscription_map.get(group, {}).get(item, {}).pop(call_id,
                                                                   None)
            if not map_item:
                # Remove item itself as nobody is subscribed
                self.subscription_map.get(group, {}).pop(item, None)
                if not map_group:
                    # Group can be removed
                    self.subscription_map.pop(group, None)
            # Since the item has been removed from the group, need to clean
            # the reverse map as well
            rev_groups = self.map_by_callback_id.get(call_id, {})
            rev_items = rev_groups.get(group, set())
            rev_items.discard(item)
            if not rev_items:
                # Remove group from callback registration
                rev_groups.pop(group, None)
                if not rev_groups:
                    # Callback is not serving anything anymore
                    self.map_by_callback_id.pop(call_id, None)

    def unregister_callback(self, callback):
        # Unsubscribe all the options of a callback
        call_id = self._get_call_id(callback)
        # Copy to avoid runtime changes
        for group, items in copy.deepcopy(self.map_by_callback_id.get(
                call_id, {})).iteritems():
            for item in items:
                self.unregister_callback_option(callback, item, group)

    def _run(self):
        LOG.debug("Starting main loop for config subscriber")
        try:
            while True:
                self._main_loop()
        except gevent.GreenletExit:
            try:
                # Unsubscribe all the config callbacks
                self.config_mgr.callback_unsubscribe(
                    self._change_polling_interval)
            finally:
                # We need to make sure that this thread dies upon
                # GreenletExit
                return

    def _main_loop(self):
        try:
            start = time.time()
            self._poll_and_execute()
            utils.wait_for_next_cycle(start, self.polling_interval, LOG,
                                      readable_caller='Config Subscriber')
        except gevent.GreenletExit:
            # Raise GreenletExit to make sure that the thread dies
            raise
        except Exception as e:
            LOG.error("An exception has occurred in config subscriber thread "
                      "%s" % e.message)
            LOG.debug(traceback.format_exc())

    def _poll_and_execute(self):
        # prepare call
        configs = {}
        # Copy the sub dictionary which might change during the iteration
        for group, items in copy.copy(self.subscription_map).iteritems():
            for item, callbacks in items.iteritems():
                for call_id, values in callbacks.iteritems():
                    for host in values['hosts']:
                        try:
                            # TODO(ivar): optimize to make a single DB call
                            # Get cached option or retrieve it from DB
                            conf = configs.setdefault(
                                (group, item), {}).setdefault(
                                host,
                                self.config_mgr._get_option(item, group, host))
                            # Set the requesting host value, can be used to
                            # resubscribe
                            if conf['version'] != values['version']:
                                # Configuration has changed, invoke callback
                                # TODO(ivar): spawn a thread?
                                values['callback'](conf)
                                # Renew the subscription
                                self.renew_subscription(
                                    values['callback'], item, group,
                                    conf['version'])
                        except Exception as e:
                            LOG.error(
                                "An exception has occurred while "
                                "executing callback %s: %s" % (
                                    values['callback'], e.message))
                            LOG.debug(traceback.format_exc())

    def _get_call_id(self, callback):
        return id(callback)

    def _change_polling_interval(self, new_conf):
        # TODO(ivar): interrupt current sleep and restart with new value
        self._polling_interval = new_conf['value']


OPTION_SUBSCRIBER_MANAGER = None


def _get_option_subscriber_manager(config_mgr, *args, **kwargs):
    global OPTION_SUBSCRIBER_MANAGER
    if OPTION_SUBSCRIBER_MANAGER is None:
        OPTION_SUBSCRIBER_MANAGER = ConfigSubscriber(config_mgr, *args,
                                                     **kwargs)
        # Start the config subscriber thread
        if CONF.aim.poll_config:
            OPTION_SUBSCRIBER_MANAGER.start()
    return OPTION_SUBSCRIBER_MANAGER
