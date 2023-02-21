# Copyright (c) 2013 OpenStack Foundation.
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

from oslo_log import log as logging
import sqlalchemy as sa

from aim import aim_manager
from aim.api import resource
from aim.common import utils
from aim.db import model_base
from aim import exceptions as exc


LOG = logging.getLogger(__name__)


class Configuration(model_base.Base, model_base.AttributeMixin):
    """Represents AIM common configuration across components."""
    __tablename__ = 'aim_config'

    key = sa.Column(sa.String(52), nullable=False, primary_key=True)
    # Host specific config. Use empty string for common conf
    host = sa.Column(sa.String(52), nullable=False, default='',
                     primary_key=True)
    # Configuration group
    group = sa.Column(sa.String(52), nullable=False, default='',
                      primary_key=True)
    # All the values will be stored as strings. Conversions will be handles
    # by the CLI and ConfigManager
    value = sa.Column(sa.String(512), nullable=True)
    # Version is a UUID that changes for every time a row is updated.
    # Using this attribute, we can easily determine whether a set of
    # configurations have changed.
    version = sa.Column(sa.String(36), default=utils.generate_uuid,
                        onupdate=utils.generate_uuid, unique=True)


class ConfigurationDBManager(object):

    def __init__(self):
        self.aim_mgr = aim_manager.AimManager()

    def _to_dict(self, db_cfg):
        return {'key': db_cfg.key,
                'host': db_cfg.host,
                'group': db_cfg.group,
                'value': db_cfg.value,
                'version': db_cfg.version}

    def _get(self, context, group, key, host='', **kwargs):
        with context.store.begin(subtransactions=True):
            curr = self.aim_mgr.get(
                context, resource.Configuration(group=group, key=key,
                                                host=host))
            if curr:
                return curr
            else:
                if 'default' in kwargs:
                    return kwargs['default']
                raise exc.ConfigurationUndefined(group=group, conf=key,
                                                 host=host)

    @utils.log
    def update_bulk(self, context, configs):
        """Update Bulk

        :param context:
        :param configs: dictionary of configurations in the form of
        {(group, key, host): value}
        :return:
        """
        #with context.store.begin(subtransactions=True):
        for conf, v in list(configs.items()):
            group, key, host = conf
            cfg = resource.Configuration(group=group, key=key, host=host,
                                            value=v)
            self.aim_mgr.create(context, cfg, overwrite=True)

    @utils.log
    def update(self, context, group, key, value, host=''):
        with context.store.begin(subtransactions=True):
            return self.update_bulk(
                context, {(group, key, host): value})

    def get(self, context, group, key, host='', **kwargs):
        return self._to_dict(
            self._get(context, group, key, host=host, **kwargs))

    @utils.log
    def delete_all(self, context, group=None, host=None):
        # Can filter by group, host or both
        # with context.store.begin(subtransactions=True):
        filters = {}
        if group:
            filters['group'] = group
        if host:
            filters['host'] = host
        for entry in self.aim_mgr.find(context, resource.Configuration,
                                        **filters):
            self.aim_mgr.delete(context, entry)

    @utils.log
    def replace_all(self, context, configs, host=None):
        """Replace All

        :param context:
        :param configs: dictionary of configurations in the form of
        {(group, key, host): value}
        :return:
        """

        # Remove all the existing config and override with new ones
        with context.store.begin(subtransactions=True):
            self.delete_all(context, host=host)
            self.update_bulk(context, configs)

    def get_changed(self, context, configs):
        """Get changed configurations

        :param context: AIM context
        :param configs: configuration dictionary in the form of
        {(group, key, host): version}
        :return: list configurations that don't match the provided version
        """
        with context.store.begin(subtransactions=True):
            result = []
            all = self.aim_mgr.find(context, resource.Configuration)
            for cfg in all:
                if (cfg.group, cfg.key, cfg.host) in configs:
                    if cfg.version != configs[(cfg.group, cfg.key, cfg.host)]:
                        result.append(cfg)
            return [self._to_dict(x) for x in result]
