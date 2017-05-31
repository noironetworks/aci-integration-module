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

"""Tables for VMM injected objects

Revision ID: 5d975a5c2d60
Revises: 32e4c4d73dfc
Create Date: 2017-04-17 16:07:35.571565

"""

# revision identifiers, used by Alembic.
revision = '5d975a5c2d60'
down_revision = 'aabce110030f'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'aim_vmm_controllers',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('domain_type', sa.String(64), nullable=False),
        sa.Column('domain_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('monitored', sa.Boolean, nullable=False, default=False),
        sa.Column('scope', sa.Enum('unmanaged', 'vm', 'iaas', 'network',
                                   'MicrosoftSCVMM', 'openstack',
                                   'kubernetes')),
        sa.Column('root_cont_name', sa.String(64)),
        sa.Column('host_or_ip', sa.String(128)),
        sa.Column('mode', sa.Enum('default', 'n1kv', 'unknown', 'ovs',
                                  'k8s')),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('domain_type', 'domain_name', 'name',
                            name='uniq_aim_vmm_controllers_identity'),
        sa.Index('idx_aim_vmm_controllers_identity',
                 'domain_type', 'domain_name', 'name'),
        sa.ForeignKeyConstraint(
            ['domain_type', 'domain_name'],
            ['aim_vmm_domains.type', 'aim_vmm_domains.name'],
            name='fk_vmm_controller_vmm_domain'))

    op.create_table(
        'aim_vmm_inj_namespaces',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('domain_type', sa.String(64), nullable=False),
        sa.Column('domain_name', sa.String(64), nullable=False),
        sa.Column('controller_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('domain_type', 'domain_name', 'controller_name',
                            'name',
                            name='uniq_aim_vmm_inj_namespaces_identity'),
        sa.Index('idx_aim_vmm_inj_namespaces_identity',
                 'domain_type', 'domain_name', 'controller_name', 'name'))

    op.create_table(
        'aim_vmm_inj_deployments',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('domain_type', sa.String(64), nullable=False),
        sa.Column('domain_name', sa.String(64), nullable=False),
        sa.Column('controller_name', sa.String(64), nullable=False),
        sa.Column('namespace_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('replicas', sa.Integer),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('domain_type', 'domain_name', 'controller_name',
                            'namespace_name', 'name',
                            name='uniq_aim_vmm_inj_deployments_identity'),
        sa.Index('idx_aim_vmm_inj_deployments_identity',
                 'domain_type', 'domain_name', 'controller_name',
                 'namespace_name', 'name'),
        sa.ForeignKeyConstraint(
            ['domain_type', 'domain_name', 'controller_name',
             'namespace_name'],
            ['aim_vmm_inj_namespaces.domain_type',
             'aim_vmm_inj_namespaces.domain_name',
             'aim_vmm_inj_namespaces.controller_name',
             'aim_vmm_inj_namespaces.name'],
            name='fk_inj_depl_inj_ns'))

    op.create_table(
        'aim_vmm_inj_replica_sets',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('domain_type', sa.String(64), nullable=False),
        sa.Column('domain_name', sa.String(64), nullable=False),
        sa.Column('controller_name', sa.String(64), nullable=False),
        sa.Column('namespace_name', sa.String(64), nullable=False),
        sa.Column('deployment_name', sa.String(64)),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('domain_type', 'domain_name', 'controller_name',
                            'namespace_name', 'name',
                            name='uniq_aim_vmm_inj_replica_sets_identity'),
        sa.Index('idx_aim_vmm_inj_replica_sets_identity',
                 'domain_type', 'domain_name', 'controller_name',
                 'namespace_name', 'name'),
        sa.ForeignKeyConstraint(
            ['domain_type', 'domain_name', 'controller_name',
             'namespace_name'],
            ['aim_vmm_inj_namespaces.domain_type',
             'aim_vmm_inj_namespaces.domain_name',
             'aim_vmm_inj_namespaces.controller_name',
             'aim_vmm_inj_namespaces.name'],
            name='fk_inj_repl_set_inj_ns'))

    op.create_table(
        'aim_vmm_inj_services',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('domain_type', sa.String(64), nullable=False),
        sa.Column('domain_name', sa.String(64), nullable=False),
        sa.Column('controller_name', sa.String(64), nullable=False),
        sa.Column('namespace_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.Column('service_type', sa.Enum('clusterIp', 'externalName',
                                          'nodePort', 'loadBalancer')),
        sa.Column('cluster_ip', sa.String(64)),
        sa.Column('load_balancer_ip', sa.String(64)),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('domain_type', 'domain_name', 'controller_name',
                            'namespace_name', 'name',
                            name='uniq_aim_vmm_inj_services_identity'),
        sa.Index('idx_aim_vmm_inj_services_identity',
                 'domain_type', 'domain_name', 'controller_name',
                 'namespace_name', 'name'),
        sa.ForeignKeyConstraint(
            ['domain_type', 'domain_name', 'controller_name',
             'namespace_name'],
            ['aim_vmm_inj_namespaces.domain_type',
             'aim_vmm_inj_namespaces.domain_name',
             'aim_vmm_inj_namespaces.controller_name',
             'aim_vmm_inj_namespaces.name'],
            name='fk_inj_service_inj_ns'))

    op.create_table(
        'aim_vmm_inj_hosts',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('domain_type', sa.String(64), nullable=False),
        sa.Column('domain_name', sa.String(64), nullable=False),
        sa.Column('controller_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('host_name', sa.String(128)),
        sa.Column('kernel_version', sa.String(32)),
        sa.Column('os', sa.String(64)),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('domain_type', 'domain_name', 'controller_name',
                            'name',
                            name='uniq_aim_vmm_inj_hosts_identity'),
        sa.Index('idx_aim_vmm_inj_hosts_identity',
                 'domain_type', 'domain_name', 'controller_name', 'name'))

    op.create_table(
        'aim_vmm_inj_service_ports',
        sa.Column('svc_aim_id', sa.Integer, nullable=False),
        sa.Column('port', sa.String(32), nullable=False),
        sa.Column('protocol', sa.String(32), nullable=False),
        sa.Column('target_port', sa.String(32), nullable=False),
        sa.Column('node_port', sa.String(32)),
        sa.PrimaryKeyConstraint('svc_aim_id', 'port', 'protocol',
                                'target_port'),
        sa.ForeignKeyConstraint(
            ['svc_aim_id'], ['aim_vmm_inj_services.aim_id']))

    op.create_table(
        'aim_vmm_inj_service_endpoints',
        sa.Column('svc_aim_id', sa.Integer, nullable=False),
        sa.Column('ip', sa.String(64)),
        sa.Column('pod_name', sa.String(64)),
        sa.PrimaryKeyConstraint('svc_aim_id', 'ip', 'pod_name'),
        sa.ForeignKeyConstraint(
            ['svc_aim_id'], ['aim_vmm_inj_services.aim_id']))

    op.create_table(
        'aim_vmm_inj_cont_groups',
        sa.Column('aim_id', sa.Integer, autoincrement=True),
        sa.Column('domain_type', sa.String(64), nullable=False),
        sa.Column('domain_name', sa.String(64), nullable=False),
        sa.Column('controller_name', sa.String(64), nullable=False),
        sa.Column('namespace_name', sa.String(64), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('host_name', sa.String(64), nullable=False),
        sa.Column('compute_node_name', sa.String(64), nullable=False),
        sa.Column('replica_set_name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False, default=''),
        sa.PrimaryKeyConstraint('aim_id'),
        sa.UniqueConstraint('domain_type', 'domain_name', 'controller_name',
                            'namespace_name', 'name',
                            name='uniq_aim_vmm_inj_groups_identity'),
        sa.Index('idx_aim_vmm_inj_groups_identity',
                 'domain_type', 'domain_name', 'controller_name',
                 'namespace_name', 'name'),
        sa.ForeignKeyConstraint(
            ['domain_type', 'domain_name', 'controller_name',
             'namespace_name'],
            ['aim_vmm_inj_namespaces.domain_type',
             'aim_vmm_inj_namespaces.domain_name',
             'aim_vmm_inj_namespaces.controller_name',
             'aim_vmm_inj_namespaces.name'],
            name='fk_inj_group_inj_ns'))


def downgrade():
    pass
