# Copyright (c) 2017 Cisco Systems
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

"""Remove AIM DB tables' dipendencies

Revision ID: baccabeffa81
Revises: de3ed29972f1
Create Date: 2016-07-07 15:29:38.013141

"""

# revision identifiers, used by Alembic.
revision = 'baccabeffa81'
down_revision = 'de3ed29972f1'
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    FK = 'foreignkey'
    with op.batch_alter_table('aim_bridge_domains') as batch_op:
        batch_op.drop_constraint('fk_bd_tn', type_=FK)

    with op.batch_alter_table('aim_subnets') as batch_op:
        batch_op.drop_constraint('fk_bd', type_=FK)

    with op.batch_alter_table('aim_vrfs') as batch_op:
        batch_op.drop_constraint('fk_vrf_tn', type_=FK)

    with op.batch_alter_table('aim_app_profiles') as batch_op:
        batch_op.drop_constraint('fk_ap_tn', type_=FK)

    with op.batch_alter_table('aim_endpoint_groups') as batch_op:
        batch_op.drop_constraint('fk_app_profile', type_=FK)

    with op.batch_alter_table('aim_filters') as batch_op:
        batch_op.drop_constraint('fk_flt_tn', type_=FK)

    with op.batch_alter_table('aim_filter_entries') as batch_op:
        batch_op.drop_constraint('fk_filter', type_=FK)

    with op.batch_alter_table('aim_contracts') as batch_op:
        batch_op.drop_constraint('fk_brc_tn', type_=FK)

    with op.batch_alter_table('aim_contract_subjects') as batch_op:
        batch_op.drop_constraint('fk_contract', type_=FK)

    with op.batch_alter_table('aim_endpoints') as batch_op:
        batch_op.drop_constraint('fk_epg', type_=FK)

    with op.batch_alter_table('aim_l3outsides') as batch_op:
        batch_op.drop_constraint('fk_l3o_tn', type_=FK)

    with op.batch_alter_table('aim_external_networks') as batch_op:
        batch_op.drop_constraint('fk_l3out', type_=FK)

    with op.batch_alter_table('aim_external_subnets') as batch_op:
        batch_op.drop_constraint('fk_ext_net', type_=FK)

    with op.batch_alter_table('aim_vmm_controllers') as batch_op:
        batch_op.drop_constraint('fk_vmm_controller_vmm_domain', type_=FK)

    with op.batch_alter_table('aim_vmm_inj_deployments') as batch_op:
        batch_op.drop_constraint('fk_inj_depl_inj_ns', type_=FK)

    with op.batch_alter_table('aim_vmm_inj_replica_sets') as batch_op:
        batch_op.drop_constraint('fk_inj_repl_set_inj_ns', type_=FK)

    with op.batch_alter_table('aim_vmm_inj_services') as batch_op:
        batch_op.drop_constraint('fk_inj_service_inj_ns', type_=FK)

    with op.batch_alter_table('aim_vmm_inj_cont_groups') as batch_op:
        batch_op.drop_constraint('fk_inj_group_inj_ns', type_=FK)

    with op.batch_alter_table('aim_device_clusters') as batch_op:
        batch_op.drop_constraint('fk_ldc_tn', type_=FK)

    with op.batch_alter_table('aim_device_cluster_ifs') as batch_op:
        batch_op.drop_constraint('fk_dci_dc', type_=FK)

    with op.batch_alter_table('aim_concrete_devices') as batch_op:
        batch_op.drop_constraint('fk_conc_dev_dc', type_=FK)

    with op.batch_alter_table('aim_concrete_device_ifs') as batch_op:
        batch_op.drop_constraint('fk_conc_dev_if_conc_dev', type_=FK)

    with op.batch_alter_table('aim_service_graph_connections') as batch_op:
        batch_op.drop_constraint('fk_sgc_sg', type_=FK)

    with op.batch_alter_table('aim_service_graph_nodes') as batch_op:
        batch_op.drop_constraint('fk_sgn_sg', type_=FK)

    with op.batch_alter_table('aim_service_graphs') as batch_op:
        batch_op.drop_constraint('fk_svcgr_tn', type_=FK)

    with op.batch_alter_table('aim_service_redirect_policies') as batch_op:
        batch_op.drop_constraint('fk_srp_tn', type_=FK)

    with op.batch_alter_table('aim_device_cluster_contexts') as batch_op:
        batch_op.drop_constraint('fk_dcctx_tn', type_=FK)

    with op.batch_alter_table('aim_device_cluster_if_contexts') as batch_op:
        batch_op.drop_constraint('fk_dc_if_ctx_dcctx', type_=FK)

    with op.batch_alter_table('aim_security_group_subjects') as batch_op:
        batch_op.drop_constraint('fk_sg_subject', type_=FK)

    with op.batch_alter_table('aim_security_group_rules') as batch_op:
        batch_op.drop_constraint('fk_sg_rule', type_=FK)

    with op.batch_alter_table('aim_security_groups') as batch_op:
        batch_op.drop_constraint('fk_sg_tn', type_=FK)


def downgrade():
    pass
