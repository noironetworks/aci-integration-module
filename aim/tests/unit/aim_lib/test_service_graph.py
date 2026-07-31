# Copyright (c) 2026 Cisco Systems
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

from aim.aim_lib import service_graph
from aim.tests import base


class TestServiceGraph(base.TestAimDBBase):

    def test_node_connector_dn(self):
        self.assertEqual(
            'uni/tn-common/AbsGraph-sg1/AbsNode-loadbalancer/'
            'AbsFConn-consumer',
            service_graph.get_node_connector_dn(
                'common', 'sg1', 'loadbalancer', 'consumer'))
        self.assertEqual(
            'uni/tn-common/AbsGraph-sg1/AbsNode-loadbalancer/'
            'AbsFConn-provider',
            service_graph.get_node_connector_dn(
                'common', 'sg1', 'loadbalancer', 'provider'))

    def test_terminal_connector_dn(self):
        self.assertEqual(
            'uni/tn-common/AbsGraph-sg1/AbsTermNodeCon-T1/AbsTConn',
            service_graph.get_terminal_connector_dn(
                'common', 'sg1', 'consumer'))
        self.assertEqual(
            'uni/tn-common/AbsGraph-sg1/AbsTermNodeProv-T2/AbsTConn',
            service_graph.get_terminal_connector_dn(
                'common', 'sg1', 'provider'))

    def test_provider_connection_connector_dns(self):
        self.assertEqual(
            ['uni/tn-common/AbsGraph-sg1/AbsTermNodeProv-T2/AbsTConn',
             'uni/tn-common/AbsGraph-sg1/AbsNode-loadbalancer/'
             'AbsFConn-provider'],
            service_graph.get_connection_connector_dns(
                'common', 'sg1', 'loadbalancer', 'provider'))

    def test_consumer_connection_connector_dns(self):
        self.assertEqual(
            ['uni/tn-common/AbsGraph-sg1/AbsNode-loadbalancer/'
             'AbsFConn-consumer',
             'uni/tn-common/AbsGraph-sg1/AbsTermNodeCon-T1/AbsTConn'],
            service_graph.get_connection_connector_dns(
                'common', 'sg1', 'loadbalancer', 'consumer'))

    def test_invalid_connection_connector_name(self):
        self.assertRaises(
            ValueError, service_graph.get_connection_connector_dns,
            'common', 'sg1', 'loadbalancer', 'invalid')

    def test_invalid_terminal_connector_name(self):
        self.assertRaises(
            ValueError, service_graph.get_terminal_connector_dn,
            'common', 'sg1', 'invalid')
