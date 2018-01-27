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
from sqlalchemy.orm import exc as sql_exc
from sqlalchemy.sql.expression import func

from aim.common.hashtree import exceptions as exc
from aim.db import model_base
from aim.db import tree_model


LOG = logging.getLogger(__name__)


class Agent(model_base.Base, model_base.HasId, model_base.AttributeMixin):
    """Represents agents running in aim deployments."""

    __table_args__ = (
        sa.UniqueConstraint('agent_type', 'host',
                            name='uniq_agents0agent_type0host'),
        model_base.Base.__table_args__
    )

    __tablename__ = 'aim_agents'

    agent_type = sa.Column(sa.String(255), nullable=False)
    host = sa.Column(sa.String(255), nullable=False)
    binary_file = sa.Column(sa.String(255), nullable=False)
    admin_state_up = sa.Column(sa.Boolean, default=True,
                               nullable=False)
    heartbeat_timestamp = sa.Column(
        sa.TIMESTAMP, server_default=func.now(), onupdate=func.now())
    description = sa.Column(sa.String(255))
    beat_count = sa.Column(sa.Integer, default=0)
    version = sa.Column(sa.String, nullable=False)
    hash_trees = orm.relationship(tree_model.AgentToHashTreeAssociation,
                                  backref='agents',
                                  cascade='all, delete-orphan',
                                  lazy="joined")

    def set_hash_trees(self, session, trees, **kwargs):
        if trees is None:
            return
        keep = []
        trees = set(trees)
        for curr in self.hash_trees:
            if curr.tree_root_rn in trees:
                keep.append(curr)
                trees.remove(curr.tree_root_rn)
        self.hash_trees = keep
        with session.begin(subtransactions=True):
            for tree in trees:
                self.tree_exists(session, tree)
                # Check whether the current object already has an ID, use
                # the one passed in the getter otherwise.
                db_obj = tree_model.AgentToHashTreeAssociation(
                    agent_id=self.id or kwargs.get('id'), tree_root_rn=tree)
                self.hash_trees.append(db_obj)

    def get_hash_trees(self, session):
        # Only return the trees' identifier
        return [getattr(x, 'tree_root_rn') for x in self.hash_trees or []]

    def tree_exists(self, session, root_rn):
        try:
            session.query(tree_model.ConfigTree).filter(
                tree_model.ConfigTree.root_rn == root_rn).one()
        except sql_exc.NoResultFound:
            raise exc.HashTreeNotFound(root_rn=root_rn)
