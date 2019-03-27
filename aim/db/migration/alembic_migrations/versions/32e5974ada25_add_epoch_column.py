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
#

"""Add epoch column

Revision ID: 32e5974ada25
Revises: 1b58ffa871bb
Create Date: 2018-03-15 00:22:47.618593

"""

# revision identifiers, used by Alembic.
revision = '32e5974ada25'
down_revision = '1b58ffa871bb'

from alembic import op
import sqlalchemy as sa


TABLES = ('aim_agents', 'aim_config', 'aim_host_domain_mapping',
          'aim_host_domain_mapping_v2', 'aim_host_links',
          'aim_host_link_network_label', 'aim_opflex_devices',
          'aim_app_profiles', 'aim_bridge_domains', 'aim_contracts',
          'aim_endpoint_groups', 'aim_external_networks',
          'aim_contract_subjects', 'aim_endpoints',
          'aim_external_subnets', 'aim_filters', 'aim_filter_entries',
          'aim_l3out_interfaces', 'aim_vmm_inj_cont_groups',
          'aim_l3out_interface_profiles', 'aim_l3out_nodes',
          'aim_l3out_node_profiles', 'aim_l3outsides',
          'aim_l3out_static_routes', 'aim_physical_domains', 'aim_pods',
          'aim_security_groups', 'aim_security_group_rules',
          'aim_security_group_subjects', 'aim_subnets',
          'aim_tenants', 'aim_topologies', 'aim_vmm_controllers',
          'aim_vmm_domains', 'aim_vmm_inj_deployments', 'aim_vmm_inj_hosts',
          'aim_vmm_inj_namespaces', 'aim_vmm_inj_replica_sets',
          'aim_vmm_inj_services', 'aim_vmm_policies', 'aim_vrfs',
          'aim_concrete_devices', 'aim_concrete_device_ifs',
          'aim_device_clusters', 'aim_device_cluster_contexts',
          'aim_device_cluster_ifs', 'aim_device_cluster_if_contexts',
          'aim_service_graphs', 'aim_service_graph_connections',
          'aim_service_graph_nodes', 'aim_service_redirect_policies',
          'aim_faults', 'aim_statuses', 'aim_action_logs',
          'aim_config_tenant_trees', 'aim_monitored_tenant_trees',
          'aim_operational_tenant_trees', 'aim_tenant_trees',
          'aim_l3out_interface_bgp_peer_prefix')


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column('epoch', sa.BigInteger(),
                                       nullable=False, server_default='0'))
    with op.batch_alter_table('aim_agents') as batch_op:
        batch_op.drop_column('beat_count')
