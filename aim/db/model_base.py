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

import six
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.ext import declarative

from aim.common import utils


def to_tuple(obj):
    return obj if isinstance(obj, tuple) else (obj,)


def uniq_column(table, *args, **kwargs):
    name = kwargs.pop('name', None)
    return (sa.UniqueConstraint(
        *args, name=('uniq_' + (name or ('%s_identity' % table)))),
        sa.Index('idx_' + (name or ('%s_identity' % table)), *args))


def name_column(**kwargs):
    return sa.Column(sa.String(64), **kwargs)


def dn_column(**kwargs):
    return sa.Column(mysql.VARCHAR(512, charset='latin1'), **kwargs)


def id_column(**kwargs):
    return sa.Column(sa.String(255), primary_key=True,
                     default=utils.generate_uuid, **kwargs)


class AimBase(object):
    """Base class for AIM DB models"""

    @declarative.declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    __table_args__ = {'mysql_engine': 'InnoDB'}


class HasName(object):
    """Add to subclasses that have a name (identifier)."""
    name = name_column(nullable=False)


class HasId(object):
    """id mixin, add to subclasses that have an id."""

    id = id_column()


class HasAimId(object):
    """Add to subclasses that have an internal-id."""
    aim_id = id_column()


class HasDisplayName(object):
    """Add to subclasses that have a display name."""
    display_name = sa.Column(sa.String(256), nullable=False, default='')


class HasDescription(object):
    """Add to subclasses that have a description."""
    descr = sa.Column(sa.String(128), nullable=False, default='')


class HasTenantName(object):
    """Add to subclasses that reference a tenant."""
    tenant_name = name_column(nullable=False)


class IsMonitored(object):
    """Add to subclasses for objects that can be monitored."""
    monitored = sa.Column(sa.Boolean, nullable=False, default=False)


class IsSynced(object):
    """Add to subclasses for objects that can be synced."""
    sync = sa.Column(sa.Boolean, nullable=False, default=True)


class AttributeMixin(object):
    """Mixin class for translating between resource and model."""

    epoch = sa.Column(
        sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
        server_default='0', nullable=False)

    __mapper_args__ = {
        "version_id_col": epoch,
        "version_id_generator": False,
        "confirm_deleted_rows": False,
    }

    def bump_epoch(self):
        if self.epoch is None:
            # this is a brand new object uncommitted so we don't bump now
            self.epoch = 0
        self.epoch += 1

    def from_attr(self, session, resource_attr):
        """Populate model from resource attribute dictionary.

        Child classes should override this method to specify a custom
        mapping of resource attributes to model properties.
        """
        # "object_dict" and "tree" uses LargeBinary sqlalchemy datatype.
        # LargeBinary sqlalchemy datatype needs "bytes-like" object
        # and in Py2, string are bytes-like objects while in Py3 they aren't.
        # So we need to store "bytes-like" object in DB objects.
        # For storing the DB model object,
        # we need to encode to utf-8 bytes format (for Py3 compatibility).
        # Since in Py2, string are bytes-like objects, encoding won't
        # make a difference.
        encoded_attr_dict = {}
        for k, v in list(resource_attr.items()):
            if k not in getattr(self, '_exclude_from', []):
                if k == 'object_dict':
                    if isinstance(v, six.text_type):
                        v = v.encode('utf-8')
                elif k == 'tree':
                    if isinstance(v, six.text_type):
                        v = v.encode('utf-8')
                encoded_attr_dict[k] = v
                self.set_attr(session, k, v, **encoded_attr_dict)

    def to_attr(self, session):
        """Get resource attribute dictionary for a model object.

        Child classes should override this method to specify a custom
        mapping of model properties to resource attributes.
        """
        # "object_dict" and "tree" uses LargeBinary sqlalchemy datatype.
        # LargeBinary sqlalchemy datatype needs "bytes-like" object
        # and in Py2, string are bytes-like objects while in Py3 they aren't.
        # So we need to store "bytes-like" object in DB objects.
        # For getting the resource attr dict from model object
        # we need to decode to native string (for Py3 compatibility).
        # Since in Py2, string are bytes-like objects, decoding won't
        # make a difference.
        attr_dict = {}
        for k in dir(self):
            if (not k.startswith('_') and
                    k not in getattr(self, '_exclude_to', []) and
                    not callable(getattr(self, k))):
                if k == 'object_dict':
                    v = self.get_attr(session, k)
                    if isinstance(v, bytes):
                        attr_dict[k] = v.decode('utf-8')
                    else:
                        attr_dict[k] = v
                elif k == 'tree':
                    v = self.get_attr(session, k)
                    if isinstance(v, bytes):
                        attr_dict[k] = v.decode('utf-8')
                    else:
                        attr_dict[k] = v
                else:
                    attr_dict[k] = self.get_attr(session, k)
        return attr_dict

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
