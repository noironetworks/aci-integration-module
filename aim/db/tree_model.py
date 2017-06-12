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

from oslo_log import log as logging
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.sql.expression import func

from aim.db import model_base


LOG = logging.getLogger(__name__)


class AgentToHashTreeAssociation(model_base.Base):
    """Many to many relation between Agents and the trees they serve."""
    __tablename__ = 'aim_agent_to_tree_associations'
    agent_id = sa.Column(
        sa.String(255), sa.ForeignKey('aim_agents.id', ondelete='CASCADE'),
        primary_key=True,)
    tree_root_rn = sa.Column(
        sa.String(64), sa.ForeignKey('aim_tenant_trees.tenant_rn',
                                     ondelete='CASCADE'),
        primary_key=True, name='tree_tenant_rn')


class Tree(model_base.Base, model_base.AttributeMixin):
    """DB model for Tree."""

    __tablename__ = 'aim_tenant_trees'

    root_rn = sa.Column(sa.String(64), primary_key=True, name='tenant_rn')
    needs_reset = sa.Column(sa.Boolean, default=False)
    agents = orm.relationship(AgentToHashTreeAssociation,
                              backref='hash_trees',
                              cascade='all, delete-orphan',
                              lazy="joined")


class TypeTreeBase(object):
    root_rn = sa.Column(sa.String(64), primary_key=True, name='tenant_rn')
    root_full_hash = sa.Column(sa.String(256), nullable=True)
    tree = sa.Column(sa.LargeBinary(length=2 ** 24), nullable=True)


class ConfigTree(model_base.Base, TypeTreeBase, model_base.AttributeMixin):
    __tablename__ = 'aim_config_tenant_trees'


class OperationalTree(model_base.Base, TypeTreeBase,
                      model_base.AttributeMixin):
    __tablename__ = 'aim_operational_tenant_trees'


class MonitoredTree(model_base.Base, TypeTreeBase, model_base.AttributeMixin):
    __tablename__ = 'aim_monitored_tenant_trees'


class ActionLog(model_base.Base, model_base.AttributeMixin):
    __tablename__ = 'aim_action_logs'
    __table_args__ = (model_base.uniq_column(__tablename__, 'uuid') +
                      model_base.to_tuple(model_base.Base.__table_args__))

    id = sa.Column(sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
                   primary_key=True)
    uuid = sa.Column(sa.Integer)
    root_rn = sa.Column(sa.String(64), nullable=False)
    action = sa.Column(sa.String(25), nullable=False)
    object_type = sa.Column(sa.String(50), nullable=False)
    object_dict = sa.Column(sa.LargeBinary(length=2 ** 24), nullable=False)
    timestamp = sa.Column(sa.TIMESTAMP, server_default=func.now())
