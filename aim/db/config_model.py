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
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.orm import exc as sql_exc

from aim.common import utils
from aim.db import model_base
from aim import exceptions as exc


LOG = logging.getLogger(__name__)


class Configuration(model_base.Base):
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

    def _to_dict(self, db_cfg):
        return {'key': db_cfg.key,
                'host': db_cfg.host,
                'group': db_cfg.group,
                'value': db_cfg.value,
                'version': db_cfg.version}

    def _get(self, context, group, key, host='', **kwargs):
        with context.db_session.begin(subtransactions=True):
            try:
                return context.db_session.query(Configuration).filter_by(
                    group=group, key=key, host=host).one()
            except sql_exc.NoResultFound:
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
        with context.db_session.begin(subtransactions=True):
            for conf, v in configs.iteritems():
                group, key, host = conf
                db_obj = self._get(context, group, key, host=host,
                                   default=None)
                # Replace existing
                if db_obj:
                    db_obj.value = v
                    context.db_session.add(db_obj)
                else:
                    obj = Configuration(group=group, key=key, host=host,
                                        value=v)
                    context.db_session.add(obj)

    @utils.log
    def update(self, context, group, key, value, host=''):
        with context.db_session.begin(subtransactions=True):
            return self.update_bulk(
                context, {(group, key, host): value})

    @utils.log
    def get(self, context, group, key, host='', **kwargs):
        return self._to_dict(
            self._get(context, group, key, host=host, **kwargs))

    @utils.log
    def delete_all(self, context, group=None, host=None):
        # Can filter by group, host or both
        with context.db_session.begin(subtransactions=True):
            query = context.db_session.query(Configuration)
            if group is not None:
                query.filter_by(group=group)
            if host is not None:
                query.filter_by(host=host)
            for entry in query.all():
                context.db_session.delete(entry)

    @utils.log
    def replace_all(self, context, configs, host=None):
        """Replace All

        :param context:
        :param configs: dictionary of configurations in the form of
        {(group, key, host): value}
        :return:
        """

        # Remove all the existing config and override with new ones
        with context.db_session.begin(subtransactions=True):
            self.delete_all(context, host=host)
            self.update_bulk(context, configs)

    @utils.log
    def get_changed(self, context, configs):
        """Get changed configurations

        :param context: AIM context
        :param configs: configuration dictionary in the form of
        {(group, key, host): version}
        :return: list configurations that don't match the provided version
        """
        # REVISIT(ivar): shouldn't return DB objects
        with context.db_session.begin(subtransactions=True):
            query = context.db_session.query(Configuration)
            query = query.filter(Configuration.version.notin_(
                configs.values()))
            query = query.filter(
                or_(and_(Configuration.group == data[0],
                         Configuration.key == data[1],
                         Configuration.host == data[2]) for data in configs))
            return [self._to_dict(x) for x in query.all()]
