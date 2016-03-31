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
from sqlalchemy.orm import sessionmaker as sa_sessionmaker

from aim.api import resource
from aim import context
from aim.db import api
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

    def _check_call_list(self, expected, mocked, check_all=True):
        observed = mocked.call_args_list
        for call in expected:
            self.assertTrue(call in observed,
                            msg='Call not found, expected:\n%s\nobserved:'
                                '\n%s' % (str(call), str(observed)))
            observed.remove(call)
        if check_all:
            self.assertFalse(
                len(observed),
                msg='There are more calls than expected: %s' % str(observed))


class TestAimDBBase(BaseTestCase):

    _TABLES_ESTABLISHED = False

    def setUp(self):
        super(TestAimDBBase, self).setUp()
        self.engine = api.get_engine()
        if not TestAimDBBase._TABLES_ESTABLISHED:
            model_base.Base.metadata.create_all(self.engine)
            TestAimDBBase._TABLES_ESTABLISHED = True
        self.session = api.get_session(expire_on_commit=True)
        self.ctx = context.AimContext(db_session=self.session)
        resource.ResourceBase.__eq__ = resource_equal

        def clear_tables():
            with self.engine.begin() as conn:
                for table in reversed(
                        model_base.Base.metadata.sorted_tables):
                    conn.execute(table.delete())
        self.addCleanup(clear_tables)

    def get_new_context(self):
        return context.AimContext(
            db_session=sa_sessionmaker(bind=self.engine)())

    def _get_example_bridge_domain(self, **kwargs):
        example = resource.BridgeDomain(tenant_name='test-tenant',
                                        vrf_name='default',
                                        name='test', enable_arp_flood=False,
                                        enable_routing=True,
                                        limit_ip_learn_to_subnets=False,
                                        l2_unknown_unicast_mode='proxy',
                                        ep_move_detect_mode='')
        example.__dict__.update(kwargs)
        return example

    def _get_example_bd(self, **kwargs):
        example_bd = {
            "fvBD": {
                "attributes": {
                    "arpFlood": "no", "descr": "test",
                    "dn": "uni/tn-test-tenant/BD-test",
                    "epMoveDetectMode": "",
                    "limitIpLearnToSubnets": "no",
                    "llAddr": "::",
                    "mac": "00:22:BD:F8:19:FF",
                    "multiDstPktAct": "bd-flood",
                    "name": "test",
                    "ownerKey": "", "ownerTag": "", "unicastRoute": "yes",
                    "unkMacUcastAct": "proxy", "unkMcastAct": "flood",
                    "vmac": "not-applicable"}}}
        example_bd['fvBD']['attributes'].update(kwargs)
        return example_bd
