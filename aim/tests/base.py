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

import logging      # noqa
import os

from oslo_config import cfg
from oslo_log import log as o_log
from oslotest import base
from sqlalchemy.orm import sessionmaker as sa_sessionmaker

from aim.api import resource
from aim.api import status as aim_status
from aim import config as aim_cfg
from aim import context
from aim.db import api
from aim.db import model_base

CONF = cfg.CONF
ROOTDIR = os.path.dirname(__file__)
ETCDIR = os.path.join(ROOTDIR, 'etc')
CONF.register_opts(aim_cfg.global_opts + aim_cfg.common_opts)


def etcdir(*p):
    return os.path.join(ETCDIR, *p)


def sort_if_list(attr):
    return sorted(attr) if isinstance(attr, list) else attr


def resource_equal(self, other):

    if type(self) != type(other):
        return False
    for attr in self.identity_attributes:
        if getattr(self, attr) != getattr(other, attr):
            return False
    for attr in self.other_attributes:
        if (sort_if_list(getattr(self, attr, None)) !=
                sort_if_list(getattr(other, attr, None))):
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
        o_log.setup(cfg.CONF, 'aim')

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
        self.cfg_manager = aim_cfg.ConfigManager(self.ctx, '')
        resource.ResourceBase.__eq__ = resource_equal
        self.cfg_manager.replace_all(CONF)

        # Uncomment the line below to log SQL statements. Additionally, to
        # log results of queries, change INFO to DEBUG
        #
        # logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

        def clear_tables():
            with self.engine.begin() as conn:
                for table in reversed(
                        model_base.Base.metadata.sorted_tables):
                    conn.execute(table.delete())
        self.addCleanup(clear_tables)

    def get_new_context(self):
        return context.AimContext(
            db_session=sa_sessionmaker(bind=self.engine)())

    def set_override(self, item, value, group=None, host='', poll=False):
        # Override DB config as well
        if group:
            CONF.set_override(item, value, group)
        else:
            CONF.set_override(item, value)
        self.cfg_manager.to_db(CONF, host=host)
        if poll:
            self.cfg_manager.subs_mgr._poll_and_execute()

    @classmethod
    def _get_example_aim_bd(cls, **kwargs):
        example = resource.BridgeDomain(tenant_name='test-tenant',
                                        vrf_name='default',
                                        name='test', enable_arp_flood=False,
                                        enable_routing=True,
                                        limit_ip_learn_to_subnets=False,
                                        l2_unknown_unicast_mode='proxy',
                                        ep_move_detect_mode='')
        example.__dict__.update(kwargs)
        return example

    @classmethod
    def _get_example_aci_bd(cls, **kwargs):
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

    @classmethod
    def _get_example_aim_vrf(cls, **kwargs):
        example = resource.VRF(
            tenant_name='test-tenant',
            name='test',
            policy_enforcement_pref=resource.VRF.POLICY_ENFORCED)
        example.__dict__.update(kwargs)
        return example

    @classmethod
    def _get_example_aci_vrf(cls, **kwargs):
        example_vrf = {
            "fvCtx": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ctx-test",
                    "descr": "",
                    "knwMcastAct": "permit",
                    "name": "default",
                    "ownerKey": "",
                    "ownerTag": "",
                    "pcEnfDir": "ingress",
                    "pcEnfPref": "enforced"
                }
            }
        }
        example_vrf['fvCtx']['attributes'].update(kwargs)
        return example_vrf

    @classmethod
    def _get_example_aim_app_profile(cls, **kwargs):
        example = resource.ApplicationProfile(
            tenant_name='test-tenant', name='test')
        example.__dict__.update(kwargs)
        return example

    @classmethod
    def _get_example_aci_app_profile(cls, **kwargs):
        example_ap = {
            "fvAp": {
                "attributes": {
                    "dn": "uni/tn-test-tenant/ap-test",
                    "descr": ""
                }
            }
        }
        example_ap['fvAp']['attributes'].update(kwargs)
        return example_ap

    @classmethod
    def _get_example_aim_subnet(cls, **kwargs):
        example = resource.Subnet(
            tenant_name='t1', bd_name='test', gw_ip_mask='10.10.10.0/28')
        example.__dict__.update(kwargs)
        return example

    @classmethod
    def _get_example_aci_subnet(cls, **kwargs):
        example_sub = {
            "fvSubnet": {
                "attributes": {
                    "dn": "uni/tn-t1/BD-test/subnet-[10.10.10.0/28]",
                    "scope": "private"
                }
            }
        }
        example_sub['fvSubnet']['attributes'].update(kwargs)
        return example_sub

    @classmethod
    def _get_example_aim_tenant(cls, **kwargs):
        example = resource.Tenant(name='test-tenant')
        example.__dict__.update(kwargs)
        return example

    @classmethod
    def _get_example_aci_tenant(cls, **kwargs):
        example_tenant = {
            "fvTenant": {
                "attributes": {
                    "dn": "uni/tn-test-tenant",
                    "descr": ""
                }
            }
        }
        example_tenant['fvTenant']['attributes'].update(kwargs)
        return example_tenant

    @classmethod
    def _get_example_aim_epg(cls, **kwargs):
        example = resource.EndpointGroup(
            tenant_name='t1', app_profile_name='a1', name='test',
            bd_name='net1')
        example.__dict__.update(kwargs)
        return example

    @classmethod
    def _get_example_aci_epg(cls, **kwargs):
        example_epg = {
            "fvAEPg": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test",
                    "descr": ""
                }
            }
        }
        example_epg['fvAEPg']['attributes'].update(kwargs)
        return example_epg

    @classmethod
    def _get_example_aim_fault(cls, **kwargs):
        example = aim_status.AciFault(
            fault_code='951',
            external_identifier='uni/tn-t1/ap-a1/epg-test/fault-951',
            severity='warning')
        example.__dict__.update(kwargs)
        return example

    @classmethod
    def _get_example_aci_fault(cls, **kwargs):
        example_epg = {
            "faultInst": {
                "attributes": {
                    "dn": "uni/tn-t1/ap-a1/epg-test/fault-951",
                    "descr": "cannot resolve",
                    "code": "951",
                    "severity": "warning",
                    "cause": "resolution-failed",
                }
            }
        }
        example_epg['faultInst']['attributes'].update(kwargs)
        return example_epg
