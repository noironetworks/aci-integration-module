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

import sqlalchemy as sa
from sqlalchemy.ext import declarative

from aim.common import utils


def name_column(**kwargs):
    return sa.Column(sa.String(64), **kwargs)


class AimBase(object):
    """Base class for AIM DB models.

    Defines a mandatory primary-key column named 'rn' for all tables.
    Child classes may define additional primary-key columns.
    """

    @declarative.declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    __table_args__ = {'mysql_engine': 'InnoDB'}


class HasName(object):
    """Add to subclasses that have a name (identifier)."""
    name = name_column(nullable=False)


class HasId(object):
    """id mixin, add to subclasses that have an id."""

    id = sa.Column(sa.String(36),
                   primary_key=True,
                   default=utils.generate_uuid)


class HasAimId(object):
    """Add to subclasses that have an internal-id."""
    aim_id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)


class HasDisplayName(object):
    """Add to subclasses that have a display name."""
    display_name = sa.Column(sa.String(256))


class HasTenantName(object):
    """Add to subclasses that reference a tenant."""
    tenant_name = name_column(nullable=False)


class IsMonitored(object):
    """Add to subclasses for objects that can be monitored."""
    monitored = sa.Column(sa.Boolean, nullable=False, default=False)


class AttributeMixin(object):
    """Mixin class for translating between resource and model."""

    def from_attr(self, session, resource_attr):
        """Populate model from resource attribute dictionary.

        Child classes should override this method to specify a custom
        mapping of resource attributes to model properties.
        """
        for k, v in resource_attr.iteritems():
            if k not in getattr(self, '_exclude_from', []):
                self.set_attr(session, k, v, **resource_attr)

    def to_attr(self, session):
        """Get resource attribute dictionary for a model object.

        Child classes should override this method to specify a custom
        mapping of model properties to resource attributes.
        """
        return {k: self.get_attr(session, k) for k in dir(self)
                if (not k.startswith('_') and
                    k not in getattr(self, '_exclude_to', []) and
                    not callable(getattr(self, k)))}

    def set_attr(self, session, k, v, **kwargs):
        """Utility for setting DB attributes

        :param session: current DB session
        :param k: name of the attribute that needs to be set
        :param v: value of the attribute that needs to be set
        :param kwargs: all the other attributes for this object. Often useful
        for retrieving the object identifiers.
        :return:
        """
        if getattr(self, 'set_' + k, None):
            # setter method exists
            getattr(self, 'set_' + k)(session, v, **kwargs)
        else:
            setattr(self, k, v)

    def get_attr(self, session, k):
        if getattr(self, 'get_' + k, None):
            # getter method exists
            return getattr(self, 'get_' + k)(session)
        else:
            return getattr(self, k)


Base = declarative.declarative_base(cls=AimBase)
