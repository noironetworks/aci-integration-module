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

"""Modify aim_id column

Revision ID: 444afa12da26
Revises: 2c47aab91fff
Create Date: 2018-04-23 00:22:47.618593

"""

# revision identifiers, used by Alembic.
revision = '444afa12da26'
down_revision = '2c47aab91fff'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


# Obtained the following by running:
# [x.__tablename__ for x in aim_store.SqlAlchemyStore.db_model_map.values()
#  if issubclass(x, model_base.HasAimId)]
# on 2018-04-23


TABLES = ('aim_l3outsides', 'aim_device_clusters', 'aim_external_networks',
          'aim_topologies', 'aim_contract_subjects',
          'aim_service_redirect_health_group',
          'aim_external_subnets', 'aim_filter_entries',
          'aim_device_cluster_contexts', 'aim_app_profiles', 'aim_tenants',
          'aim_service_graphs', 'aim_device_cluster_ifs',
          'aim_l3out_interface_profiles', 'aim_security_group_rules',
          'aim_l3out_node_profiles', 'aim_vmm_domains',
          'aim_vmm_inj_namespaces', 'aim_pods', 'aim_opflex_devices',
          'aim_filters', 'aim_security_groups', 'aim_concrete_devices',
          'aim_contracts', 'aim_l3out_interface_bgp_peer_prefix',
          'aim_vmm_inj_deployments', 'aim_service_graph_nodes', 'aim_subnets',
          'aim_device_cluster_if_contexts', 'aim_vmm_inj_hosts',
          'aim_vmm_inj_cont_groups', 'aim_l3out_nodes', 'aim_vmm_policies',
          'aim_physical_domains', 'aim_vmm_inj_services',
          'aim_service_redirect_monitoring_policy', 'aim_vrfs',
          'aim_security_group_subjects', 'aim_l3out_interfaces',
          'aim_concrete_device_ifs', 'aim_service_graph_connections',
          'aim_bridge_domains', 'aim_vmm_controllers',
          'aim_service_redirect_policies', 'aim_endpoint_groups',
          'aim_vmm_inj_replica_sets', 'aim_l3out_static_routes')

TABLES_FKS = (('aim_device_cluster_devices', 'aim_device_clusters',
               'dc_aim_id'),
              ('aim_external_network_contracts', 'aim_external_networks',
               'ext_net_aim_id'),
              ('aim_endpoint_group_vmm_domains', 'aim_endpoint_groups',
               'epg_aim_id'),
              ('aim_endpoint_group_physical_domains', 'aim_endpoint_groups',
               'epg_aim_id'),
              ('aim_contract_subject_filters', 'aim_contract_subjects',
               'subject_aim_id'),
              ('aim_vmm_inj_service_ports', 'aim_vmm_inj_services',
               'svc_aim_id'),
              ('aim_vmm_inj_service_endpoints', 'aim_vmm_inj_services',
               'svc_aim_id'),
              ('aim_l3out_next_hops', 'aim_l3out_static_routes',
               'static_route_aim_id'),
              ('aim_l3out_interface_secondary_ip_a', 'aim_l3out_interfaces',
               'interface_aim_id'),
              ('aim_l3out_interface_secondary_ip_b', 'aim_l3out_interfaces',
               'interface_aim_id'),
              ('aim_endpoint_group_contracts', 'aim_endpoint_groups',
               'epg_aim_id'),
              ('aim_bridge_domain_l3outs', 'aim_bridge_domains',
               'bd_aim_id'),
              ('aim_security_group_rule_remote_ips',
               'aim_security_group_rules', 'security_group_rule_aim_id'),
              ('aim_endpoint_group_static_paths', 'aim_endpoint_groups',
               'epg_aim_id'),
              ('aim_endpoint_group_contract_masters', 'aim_endpoint_groups',
               'epg_aim_id'),
              ('aim_device_cluster_if_concrete_ifs', 'aim_device_cluster_ifs',
               'dci_aim_id'),
              ('aim_service_graph_connection_conns',
               'aim_service_graph_connections', 'sgc_aim_id'),
              ('aim_service_graph_node_conns', 'aim_service_graph_nodes',
               'sgn_aim_id'),
              ('aim_service_graph_linear_chain_nodes', 'aim_service_graphs',
               'sg_aim_id'),
              ('aim_service_redirect_policy_destinations',
               'aim_service_redirect_policies',
               'srp_aim_id')
              )


def upgrade():

    for table, _, col in TABLES_FKS:
        inspector = reflection.Inspector.from_engine(op.get_bind())
        fk_name = [fk['name'] for fk in
                   inspector.get_foreign_keys(table)
                   if col in fk['constrained_columns']]
        try:
            op.drop_constraint(fk_name[0], table, 'foreignkey')
        except (NotImplementedError, IndexError):
            pass
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(col, existing_type=sa.Integer,
                                  type_=sa.String(255))

    for table in TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("aim_id", existing_type=sa.Integer,
                                  type_=sa.String(255))

    with op.batch_alter_table("aim_statuses") as batch_op:
        batch_op.alter_column("resource_id", existing_type=sa.Integer,
                              type_=sa.String(255))

    for table, other, col in TABLES_FKS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.create_foreign_key('fk_' + table + '_' + col,
                                        other, [col], ['aim_id'])
