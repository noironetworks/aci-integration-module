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

"""Add tables for service graph

Revision ID: dc598e78e318
Revises: abf7bb5a4100
Create Date: 2017-03-15 12:33:07.716431

"""

# revision identifiers, used by Alembic.
revision = 'dc598e78e318'
down_revision = 'babbefa38870'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import VARCHAR


def upgrade():
    op.add_column('aim_contract_subjects',
                  sa.Column('service_graph_name', sa.String(64),
                            server_default=''))

    op.create_table(
        'aim_device_cluster_devices',
        sa.Column('dc_aim_id', sa.Integer, nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('path', sa.String(512)),
        sa.PrimaryKeyConstraint('dc_aim_id', 'name'),
        sa.ForeignKeyConstraint(
            ['dc_aim_id'], ['aim_device_clusters.aim_id']))

    op.create_table(
        'aim_device_clusters',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('device_type', sa.Enum("PHYSICAL", "VIRTUAL")),
        sa.Column('service_type',
                  sa.Enum("ADC", "FW", "OTHERS", "IDSIPS", "COPY")),
        sa.Column('context_aware',
                  sa.Enum("single-Context", "multi-Context")),
        sa.Column('managed', sa.Boolean),
        sa.Column('physical_domain_name', sa.String(64)),
        sa.Column('encap', sa.String(24)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_device_clusters_identity'),
        sa.Index('idx_device_clusters_identity', 'tenant_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name'], ['aim_tenants.name'], name='fk_ldc_tn'))

    op.create_table(
        'aim_device_cluster_if_concrete_ifs',
        sa.Column('dci_aim_id', sa.Integer, nullable=False),
        sa.Column('interface', sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint('dci_aim_id', 'interface'),
        sa.ForeignKeyConstraint(
            ['dci_aim_id'], ['aim_device_cluster_ifs.aim_id']))

    op.create_table(
        'aim_device_cluster_ifs',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('device_cluster_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('encap', sa.String(24)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'device_cluster_name', 'name',
                            name='uniq_device_cluster_ifs_identity'),
        sa.Index('idx_device_cluster_ifs_identity',
                 'tenant_name', 'device_cluster_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'device_cluster_name'],
            ['aim_device_clusters.tenant_name', 'aim_device_clusters.name'],
            name='fk_dci_dc'))

    op.create_table(
        'aim_concrete_devices',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('device_cluster_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'device_cluster_name', 'name',
                            name='uniq_concrete_device_identity'),
        sa.Index('idx_concrete_device_identity',
                 'tenant_name', 'device_cluster_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'device_cluster_name'],
            ['aim_device_clusters.tenant_name', 'aim_device_clusters.name'],
            name='fk_conc_dev_dc'))

    op.create_table(
        'aim_concrete_device_ifs',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('device_name', sa.String(64), nullable=False),
        sa.Column('device_cluster_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('path', sa.String(512)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'device_cluster_name',
                            'device_name', 'name',
                            name='uniq_concrete_device_if_identity'),
        sa.Index('idx_concrete_device_if_identity',
                 'tenant_name', 'device_cluster_name', 'device_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'device_cluster_name', 'device_name'],
            ['aim_concrete_devices.tenant_name',
             'aim_concrete_devices.device_cluster_name',
             'aim_concrete_devices.name'],
            name='fk_conc_dev_if_conc_dev'))

    op.create_table(
        'aim_service_graph_connection_conns',
        sa.Column('sgc_aim_id', sa.Integer, nullable=False),
        sa.Column('connector', VARCHAR(512, charset='latin1'), nullable=False),
        sa.PrimaryKeyConstraint('sgc_aim_id', 'connector'),
        sa.ForeignKeyConstraint(
            ['sgc_aim_id'], ['aim_service_graph_connections.aim_id']))

    op.create_table(
        'aim_service_graph_connections',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('service_graph_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('adjacency_type', sa.Enum('L2', 'L3')),
        sa.Column('connector_direction', sa.Enum('consumer', 'provider')),
        sa.Column('connector_type', sa.Enum('internal', 'external')),
        sa.Column('direct_connect', sa.Boolean),
        sa.Column('unicast_route', sa.Boolean),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'service_graph_name', 'name',
                            name='uniq_sg_conn_identity'),
        sa.Index('idx_sg_conn_identity',
                 'tenant_name', 'service_graph_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'service_graph_name'],
            ['aim_service_graphs.tenant_name', 'aim_service_graphs.name'],
            name='fk_sgc_sg'))

    op.create_table(
        'aim_service_graph_node_conns',
        sa.Column('sgn_aim_id', sa.Integer, nullable=False),
        sa.Column('connector', VARCHAR(512, charset='latin1'), nullable=False),
        sa.PrimaryKeyConstraint('sgn_aim_id', 'connector'),
        sa.ForeignKeyConstraint(
            ['sgn_aim_id'], ['aim_service_graph_nodes.aim_id']))

    op.create_table(
        'aim_service_graph_nodes',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('service_graph_name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('function_type', sa.Enum('GoTo', 'GoThrough')),
        sa.Column('managed', sa.Boolean),
        sa.Column('routing_mode', sa.Enum('unspecified', 'Redirect')),
        sa.Column('device_cluster_name', sa.String(64)),
        sa.Column('device_cluster_tenant_name', sa.String(64)),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'service_graph_name', 'name',
                            name='uniq_sg_node_identity'),
        sa.Index('idx_sg_node_identity',
                 'tenant_name', 'service_graph_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'service_graph_name'],
            ['aim_service_graphs.tenant_name', 'aim_service_graphs.name'],
            name='fk_sgn_sg'))

    op.create_table(
        'aim_service_graph_linear_chain_nodes',
        sa.Column('sg_aim_id', sa.Integer, nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('device_cluster_name', sa.String(64)),
        sa.Column('device_cluster_tenant_name', sa.String(64)),
        sa.PrimaryKeyConstraint('sg_aim_id', 'name'),
        sa.ForeignKeyConstraint(
            ['sg_aim_id'], ['aim_service_graphs.aim_id']))

    op.create_table(
        'aim_service_graphs',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_service_graph_identity'),
        sa.Index('idx_service_graph_identity', 'tenant_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name'], ['aim_tenants.name'], name='fk_svcgr_tn'))

    op.create_table(
        'aim_service_redirect_policy_destinations',
        sa.Column('srp_aim_id', sa.Integer, nullable=False),
        sa.Column('ip', sa.String(64), nullable=False),
        sa.Column('mac', sa.String(24)),
        sa.PrimaryKeyConstraint('srp_aim_id', 'ip'),
        sa.ForeignKeyConstraint(
            ['srp_aim_id'], ['aim_service_redirect_policies.aim_id']))

    op.create_table(
        'aim_service_redirect_policies',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'name',
                            name='uniq_srp_identity'),
        sa.Index('idx_srp_identity', 'tenant_name', 'name'),
        sa.ForeignKeyConstraint(
            ['tenant_name'], ['aim_tenants.name'], name='fk_srp_tn'))

    op.create_table(
        'aim_device_cluster_contexts',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('service_graph_name', sa.String(64), nullable=False),
        sa.Column('node_name', sa.String(64), nullable=False),
        sa.Column('device_cluster_name', sa.String(64)),
        sa.Column('device_cluster_tenant_name', sa.String(64)),
        sa.Column('service_redirect_policy_name', sa.String(64)),
        sa.Column('service_redirect_policy_tenant_name', sa.String(64)),
        sa.Column('bridge_domain_name', sa.String(64)),
        sa.Column('bridge_domain_tenant_name', sa.String(64)),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name',
                            'service_graph_name', 'node_name',
                            name='uniq_dcctx_identity'),
        sa.Index('idx_dcctx_identity', 'tenant_name',
                 'contract_name', 'service_graph_name', 'node_name'),
        sa.ForeignKeyConstraint(
            ['tenant_name'], ['aim_tenants.name'], name='fk_dcctx_tn'))

    op.create_table(
        'aim_device_cluster_if_contexts',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('tenant_name', sa.String(64), nullable=False),
        sa.Column('contract_name', sa.String(64), nullable=False),
        sa.Column('service_graph_name', sa.String(64), nullable=False),
        sa.Column('node_name', sa.String(64), nullable=False),
        sa.Column('connector_name', sa.String(64), nullable=False),
        sa.Column('device_cluster_interface_dn', sa.String(1024)),
        sa.Column('service_redirect_policy_dn', sa.String(1024)),
        sa.Column('bridge_domain_dn', sa.String(1024)),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('tenant_name', 'contract_name',
                            'service_graph_name', 'node_name',
                            'connector_name',
                            name='uniq_dc_if_ctx_identity'),
        sa.Index('idx_dc_if_ctx_identity', 'tenant_name',
                 'contract_name', 'service_graph_name', 'node_name',
                 'connector_name'),
        sa.ForeignKeyConstraint(
            ['tenant_name', 'contract_name', 'service_graph_name',
             'node_name'],
            ['aim_device_cluster_contexts.tenant_name',
             'aim_device_cluster_contexts.contract_name',
             'aim_device_cluster_contexts.service_graph_name',
             'aim_device_cluster_contexts.node_name'],
            name='fk_dc_if_ctx_dcctx'))


def downgrade():
    pass
