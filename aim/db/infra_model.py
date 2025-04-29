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

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.sql.expression import func

from aim.api import infra
from aim.db import model_base


class HostLink(model_base.Base, model_base.AttributeMixin):
    __tablename__ = 'aim_host_links'

    host_name = sa.Column(sa.String(128), primary_key=True)
    interface_name = sa.Column(sa.String(32), primary_key=True)
    interface_mac = sa.Column(sa.String(24))

    switch_id = sa.Column(sa.String(128))
    module = sa.Column(sa.String(128))
    port = sa.Column(sa.String(128))
    path = sa.Column(VARCHAR(512, charset='latin1'))
    pod_id = sa.Column(sa.String(128))
    from_config = sa.Column(sa.Boolean, default=False)
    timestamp = sa.Column(sa.TIMESTAMP, onupdate=func.now())


class HostLinkManager(object):

    """DB Model to manage all APIC DB interactions."""

    def __init__(self, aim_context, aim_manager):
        self.aim_context = aim_context
        self.aim_manager = aim_manager

    def add_hostlink(self, host, ifname, ifmac, swid, module,
                     port, path, pod_id='1', from_config=False,
                     timestamp=func.now()):
        link = infra.HostLink(
            host_name=host, interface_name=ifname,
            interface_mac=ifmac, switch_id=swid, module=module,
            port=port, path=path, pod_id=pod_id, from_config=from_config,
            timestamp=timestamp)
        self.aim_manager.create(self.aim_context, link, overwrite=True)

    def delete_hostlink(self, host, ifname):
        self.aim_manager.delete(
            self.aim_context, infra.HostLink(host_name=host,
                                             interface_name=ifname))

    # Leaving the following read methods as direct DB calls, apicapi expects
    # things like "count" to exist in the result.

    def get_hostlink(self, host, ifname):
        db_type = self.aim_context.store.resource_to_db_type(infra.HostLink)
        res = self.aim_context.store.query(db_type, infra.HostLink,
                                           host_name=host,
                                           interface_name=ifname)
        return res[0] if res else None

    def get_hostlinks_for_host_switchport(self, host, swid, module, port):
        db_type = self.aim_context.store.resource_to_db_type(infra.HostLink)
        return self.aim_context.store.query(db_type, infra.HostLink,
                                            host_name=host, switch_id=swid,
                                            module=module, port=port)

    def get_hostlinks_for_switchport(self, swid, module, port):
        db_type = self.aim_context.store.resource_to_db_type(infra.HostLink)
        return self.aim_context.store.query(
            db_type, infra.HostLink, switch_id=swid, module=module, port=port)

    def get_hostlinks(self):
        db_type = self.aim_context.store.resource_to_db_type(infra.HostLink)
        return self.aim_context.store.query(db_type, infra.HostLink)

    def get_hostlinks_for_host(self, host):
        db_type = self.aim_context.store.resource_to_db_type(infra.HostLink)
        return self.aim_context.store.query(db_type, infra.HostLink,
                                            host_name=host)

    def get_switches(self):
        res = self.get_hostlinks()
        return list(set([(x.switch_id,) for x in res]))

    def get_modules_for_switch(self, swid):
        db_type = self.aim_context.store.resource_to_db_type(infra.HostLink)
        res = self.aim_context.store.query(db_type, infra.HostLink,
                                           switch_id=swid)
        return list(set([(x.module,) for x in res]))

    def get_ports_for_switch_module(self, swid, module):
        db_type = self.aim_context.store.resource_to_db_type(infra.HostLink)
        res = self.aim_context.store.query(db_type, infra.HostLink,
                                           switch_id=swid, module=module)
        return list(set([(x.port,) for x in res]))

    def get_switch_and_port_for_host(self, host):
        res = self.get_hostlinks_for_host(host)
        return list(set([(x.switch_id, x.module, x.port,
                          x.interface_name, x.pod_id) for x in res]))


class OpflexDevice(model_base.Base, model_base.AttributeMixin,
                   model_base.HasAimId):
    __tablename__ = 'aim_opflex_devices'
    __table_args__ = (
        model_base.uniq_column(__tablename__, 'pod_id', 'node_id',
                               'bridge_interface', 'dev_id') +
        model_base.to_tuple(model_base.Base.__table_args__))

    pod_id = sa.Column(sa.String(36))
    node_id = sa.Column(sa.String(36))
    bridge_interface = sa.Column(sa.String(36))
    dev_id = sa.Column(sa.String(36))

    host_name = sa.Column(sa.String(128))
    ip = sa.Column(sa.String(64))
    fabric_path_dn = sa.Column(sa.String(512))
    domain_name = sa.Column(sa.String(64))
    controller_name = sa.Column(sa.String(64))


class HostDomainMapping(model_base.Base, model_base.AttributeMixin):
    __tablename__ = 'aim_host_domain_mapping'

    host_name = sa.Column(sa.String(128), primary_key=True)

    vmm_domain_name = sa.Column(sa.String(64))
    physical_domain_name = sa.Column(sa.String(64))


class HostDomainMappingV2(model_base.Base, model_base.AttributeMixin):
    __tablename__ = 'aim_host_domain_mapping_v2'

    host_name = sa.Column(sa.String(128), primary_key=True)
    domain_name = sa.Column(sa.String(64), primary_key=True)
    domain_type = sa.Column(sa.Enum('PhysDom',
                                    'OpenStack',
                                    'Kubernetes',
                                    'VMware'), primary_key=True)


class HostLinkNetworkLabel(model_base.Base, model_base.AttributeMixin):
    __tablename__ = 'aim_host_link_network_label'

    host_name = sa.Column(sa.String(128), primary_key=True)
    network_label = sa.Column(sa.String(64), primary_key=True)
    interface_name = sa.Column(sa.String(32), primary_key=True)


class ApicAssignment(model_base.Base, model_base.AttributeMixin):
    __tablename__ = 'aim_apic_assignment'

    apic_host = sa.Column(sa.String(128), primary_key=True)
    aim_aid_id = sa.Column(sa.String(64))
    last_update_timestamp = sa.Column(sa.TIMESTAMP, server_default=func.now(),
                                      onupdate=func.now())


class ACISupportedMo(model_base.Base, model_base.AttributeMixin):
    """DB model for ACI version supports Remote IP Container"""

    __tablename__ = 'aim_aci_supported_mos'

    name = sa.Column(sa.String(64), nullable=False,
                     primary_key=True)
    supports = sa.Column(sa.Boolean, nullable=False)


class ACISupportedMoManager(object):
    """DB model for managing all getting/setting aci mo support"""

    def __init__(self, aim_context, aim_manager):
        self.aim_context = aim_context
        self.aim_manager = aim_manager

    def get_current_support_status(self, name):
        db_type = self.aim_context.store.resource_to_db_type(
            infra.ACISupportedMo)
        return self.aim_context.store.query(db_type, infra.ACISupportedMo,
                                            name=name)

    def set_support_status(self, name, status):
        with self.aim_context.store.begin(subtransactions=True):
            db_objs = self.get_current_support_status(name)
            for obj in db_objs:
                setattr(obj, "supports", status)
                self.aim_context.store.add(obj)


class AimHashRing(model_base.Base, model_base.AttributeMixin):
    """DB model for configurable params for consistent hashing algo"""

    __tablename__ = 'aim_consistent_hashring_params'

    name = sa.Column(sa.String(16), nullable=False,
                     primary_key=True)
    value = sa.Column(sa.Integer, nullable=False)
