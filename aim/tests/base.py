# Copyright (c) 2016 Cisco Systems
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os

from oslo_config import cfg
from oslotest import base
from sqlalchemy import engine as sa_engine
from sqlalchemy.orm import sessionmaker as sa_sessionmaker

from aim.api import resource
from aim import context
from aim.db import model_base

CONF = cfg.CONF
ROOTDIR = os.path.dirname(__file__)
ETCDIR = os.path.join(ROOTDIR, 'etc')


def etcdir(*p):
    return os.path.join(ETCDIR, *p)


def resource_equal(self, other):
    if type(self) != type(other):
        return False
    for attr in self.identity_attributes:
        if getattr(self, attr) != getattr(other, attr):
            return False
    for attr in self.other_attributes:
        if getattr(self, attr, None) != getattr(other, attr, None):
            return False
    return True


class BaseTestCase(base.BaseTestCase):
    """Test case base class for all unit tests."""

    def config_parse(self, conf=None, args=None):
        """Create the default configurations."""
        # neutron.conf.test includes rpc_backend which needs to be cleaned up
        if args is None:
            args = []
        args += ['--config-file', self.test_conf_file]
        if conf is None:
            CONF(args=args, project='aim')
        else:
            conf(args)

    def setUp(self):
        super(BaseTestCase, self).setUp()
        self.addCleanup(CONF.reset)
        self.test_conf_file = etcdir('aim.conf.test')
        self.config_parse()


class TestAimDBBase(base.BaseTestCase):

    def setUp(self):
        super(TestAimDBBase, self).setUp()
        self.engine = sa_engine.create_engine('sqlite:///:memory:')
        model_base.Base.metadata.create_all(self.engine)
        session = sa_sessionmaker(bind=self.engine)()
        self.ctx = context.AimContext(db_session=session)
        resource.ResourceBase.__eq__ = resource_equal

    def get_new_context(self):
        return context.AimContext(
            db_session=sa_sessionmaker(bind=self.engine)())

    def _get_example_bridge_domain(self, **kwargs):
        example = resource.BridgeDomain(tenant_rn='test-tenant',
                                        vrf_rn='default',
                                        rn='test', enable_arp_flood=False,
                                        enable_routing=True,
                                        limit_ip_learn_to_subnets=False,
                                        l2_unknown_unicast_mode='proxy',
                                        ep_move_detect_mode='')
        example.__dict__.update(kwargs)
        return example
