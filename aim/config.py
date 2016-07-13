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

import socket

from apicapi import config as apic_config  # noqa
from oslo_config import cfg
from oslo_log import log as logging

from aim.db import config_model
from aim import exceptions as exc


LOG = logging.getLogger(__name__)

global_opts = [
    cfg.StrOpt('apic_system_id',
               default='openstack',
               help="Prefix for APIC domain/names/profiles created"),
]

default_opts = [
    cfg.StrOpt('host', default=socket.gethostname(),
               help="Host where this agent/controller is running")
]

cfg.CONF.register_opts(default_opts)

agent_opts = [
    cfg.IntOpt('agent_down_time', default=75,
               help=("Seconds to regard the agent is down; should be at "
                     "least twice agent_report_interval.")),
    cfg.IntOpt('agent_polling_interval', default=5,
               help=("Seconds that need to pass before the agent starts each "
                     "new cycle.")),
    cfg.IntOpt('agent_report_interval', default=30,
               help=("Number of seconds after which an agent reports his "
                     "state"))
    ]

cfg.CONF.register_opts(agent_opts, 'aim')
logging.register_options(cfg.CONF)
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

    def __init__(self, context=None, group=None, host=None):
        # Use some of the above init params to restrict the manager scope
        # during option GET
        self.map = ConfigManager.common_opts
        self.db = config_model.ConfigurationDBManager()
        self.context = context
        self.group = group
        self.host = host

    def _to_query_format(self, cfg_obj, host=''):
        """Returns config objects in DB format

        :param cfg_obj: oslo conf object
        :param host: host specific config
        :return:
        """
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
                result[group, k, host] = value
        return result

    def to_db(self, context, cfg_obj, host=''):
        configs = self._to_query_format(cfg_obj, host=host)
        self.db.update_bulk(context, configs)

    def replace_all(self, context, cfg_obj, host=None):
        # If not restricted by host, all the config will be deleted
        configs = self._to_query_format(cfg_obj, host=host)
        LOG.info("Replacing existing configuration for host %s "
                 "with: %s" % (host, configs))
        self.db.replace_all(context, configs, host=host)

    def get_option(self, item, group='default', host='', context=None):
        context = context or self.context
        group = self.group or group
        host = self.host or host
        if group not in self.map:
            raise exc.UnsupportedAIMConfigGroup(group=group)
        if item not in self.map[group]:
            raise exc.UnsupportedAIMConfig(group=group, conf=item)
        obj = self.map[group][item]
        # Get per host config if any, or default one
        try:
            value = self.db.get(context, group, item, host=host)
        except exc.ConfigurationUndefined:
            LOG.debug(
                "item %s in group %s for host %s doesn't exist. "
                "Trying with default group." % (item, group, host))
            value = self.db.get(context, group, item, host='')
        if isinstance(obj, cfg.IntOpt):
            return self._int_opt(value)
        elif isinstance(obj, cfg.StrOpt):
            return self._str_opt(value)
        elif isinstance(obj, cfg.ListOpt):
            return self._list_opt(value)
        elif isinstance(obj, cfg.BoolOpt):
            return self._bool_opt(value)
        else:
            LOG.warn(
                "Unsupported option type %s of item %s in group %s for host "
                "%s. Returning None" % (type(obj), item, group, host))

    def _int_opt(self, value):
        return int(value) if value is not None else None

    def _str_opt(self, value):
        return value

    def _list_opt(self, value):
        return value.split(',') if value is not None else []

    def _bool_opt(self, value):
        return bool(value) if value is not None else None
