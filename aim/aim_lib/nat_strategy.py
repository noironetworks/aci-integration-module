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

import abc
import copy
import six

from oslo_log import log as logging

from aim.aim_lib.db import model
from aim.api import resource
from aim import exceptions
from aim import utils as aim_utils

LOG = logging.getLogger(__name__)


class VrfNotVisibleFromExternalNetwork(exceptions.AimException):
    message = "%(vrf)s is not visible from %(ext_net)s."


class L3OutsideVrfChangeDisallowed(exceptions.AimException):
    message = ("Cannot change VRF referenced by no-NAT L3Out %(l3out)s from "
               "%(old_vrf)s to %(vrf)s.")


@six.add_metaclass(abc.ABCMeta)
class NatStrategy(object):
    """Interface for NAT behavior strategies.

    Defines interface for configuring L3Outside in AIM to support
    various kinds of NAT-ing.
    All methods expect AIM resources as input parameters.

    Example usage:

    1. Decide a NAT-strategy to use

    mgr = AimManager()
    ctx = AimContext()
    ns = DistributedNatStrategy(mgr)     # or NoNatEdgeStrategy(mgr),
                                         # or EdgeNatStrategy(mgr)

    2. Create L3Outside and one or more ExternalNetworks. Subnets
    may be created in the L3Outside

    l3out = L3Outside(tenant_name='t1', name='out')
    ext_net1 = ExternalNetwork(tenant_name='t1', l3out_name='out',
                               name='inet1')
    ext_net2 = ExternalNetwork(tenant_name='t1', l3out_name='out',
                               name='inet2')

    ns.create_l3outside(ctx, l3out)
    ns.create_subnet(ctx, l3out, '40.40.40.1/24')
    ns.create_external_network(ctx, ext_net1)
    ns.create_external_network(ctx, ext_net2)

    3. Allow traffic for certain IP-addresses through the external
       networks; by default no traffic is allowed.

    ns.update_external_cidrs(ctx, ext_net1, ['0.0.0.0/0'])
    ns.update_external_cidrs(ctx, ext_net2, ['200.200.0.0/16',
                                             '300.0.0.0/8'])

    4. To provide external-connectivity to a VRF, connect the VRF to
    ExternalNetwork with appropriate contracts.

    ext_net1.provided_contract_names = ['http', 'icmp']
    ext_net1.consumed_contract_names = ['arp']

    vrf = VRF(...)

    ns.connect_vrf(ctx, ext_net1, vrf)

    5. Call connect_vrf() again to update the contracts

    ext_net1.provided_contract_names = ['http', 'https']
    ext_net1.consumed_contract_names = ['ping']

    ns.connect_vrf(ctx, ext_net1, vrf)

    6. Disallow external-connectivity to VRF

    ns.disconnect_vrf(ctx, ext_net1, vrf)

    7. Delete ExternalNetwork, subnet and L3Outside

    ns.delete_external_network(ctx, ext_net1)
    ns.delete_external_network(ctx, ext_net2)
    ns.delete_subnet(ctx, l3out, '40.40.40.1/24')
    ns.delete_l3outside(ctx, l3out)

    """

    @abc.abstractmethod
    def create_l3outside(self, ctx, l3outside,
                         vmm_domains=None, phys_domains=None):
        """Create L3Outside object if needed.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :return: L3Outside resource
        """

    @abc.abstractmethod
    def delete_l3outside(self, ctx, l3outside):
        """Delete L3Outside object.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :return:
        """

    @abc.abstractmethod
    def get_l3outside_resources(self, ctx, l3outside):
        """Get AIM resources that are created for an L3Outside object.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :return: List of AIm resources
        """

    @abc.abstractmethod
    def create_subnet(self, ctx, l3outside, gw_ip_mask):
        """Create Subnet in L3Outside.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :param gw_ip_mask: Gateway+CIDR of subnet to create
        :return:
        """

    @abc.abstractmethod
    def delete_subnet(self, ctx, l3outside, gw_ip_mask):
        """Delete Subnet in L3Outside.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :param gw_ip_mask: Gateway+CIDR of subnet to delete
        :return:
        """

    @abc.abstractmethod
    def get_subnet(self, ctx, l3outside, gw_ip_mask):
        """Get Subnet in L3Outside with specified Gateway+CIDR.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :param gw_ip_mask: Gateway+CIDR of subnet to fetch
        :return: AIM Subnet if one is found
        """

    @abc.abstractmethod
    def create_epg_subnet(self, ctx, l3outside, gw_ip_mask):
        """Create EPGSubnet in L3Outside.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :param gw_ip_mask: Gateway+CIDR of epgsubnet to create
        :return:
        """

    @abc.abstractmethod
    def delete_epg_subnet(self, ctx, l3outside, gw_ip_mask):
        """Delete EPGSubnet in L3Outside.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :param gw_ip_mask: Gateway+CIDR of epgsubnet to delete
        :return:
        """

    @abc.abstractmethod
    def get_epg_subnet(self, ctx, l3outside, gw_ip_mask):
        """Get EPGSubnet in L3Outside with specified Gateway+CIDR.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :param gw_ip_mask: Gateway+CIDR of epgsubnet to fetch
        :return: AIM epgSubnet if one is found
        """

    @abc.abstractmethod
    def create_external_network(self, ctx, external_network,
                                provided_contracts=None,
                                consumed_contracts=None):
        """Create ExternalNetwork object if needed.

        :param ctx: AIM context
        :param external_network: ExternalNetwork AIM resource
        :return: ExternalNetwork resource
        """

    @abc.abstractmethod
    def delete_external_network(self, ctx, external_network,
                                provided_contracts=None,
                                consumed_contracts=None):
        """Delete ExternalNetwork object.

        :param ctx: AIM context
        :param external_network: ExternalNetwork AIM resource
        :return:
        """

    @abc.abstractmethod
    def update_external_cidrs(self, ctx, external_network, external_cidrs):
        """Set the IP addresses for which external traffic is allowed.

        :param ctx: AIM context
        :param external_network: ExternalNetwork AIM resource
        :param external_cidrs: List of CIDRs to allow
        :return:
        """

    @abc.abstractmethod
    def connect_vrf(self, ctx, external_network, vrf,
                    provided_contracts=None,
                    consumed_contracts=None):
        """Allow external connectivity to VRF.

        Create or update NAT machinery to allow external
        connectivity from a given VRF to an ExternalNetwork (L3Outside)
        enforcing the policies specified in the provided_contracts and
        consumed_contracts parameters.

        :param ctx: AIM context
        :param external_network: AIM ExternalNetwork
        :param vrf: AIM VRF
        :return:
        """

    @abc.abstractmethod
    def disconnect_vrf(self, ctx, external_network, vrf):
        """Remove external connectivity for VRF.

        Tear down connectivity between VRF and ExternalNetwork (L3Outside).

        :param ctx: AIM context
        :param external_network: AIM ExternalNetwork
        :param vrf: AIM VRF
        """

    @abc.abstractmethod
    def read_vrfs(self, ctx, external_network):
        """Read external connectivity VRFs.

        :param ctx: AIM context
        :param external_network: AIM ExternalNetwork
        """

    @abc.abstractmethod
    def set_bd_l3out(self, ctx, bridge_domain, l3outside):
        """Add the l3out to the BD's associated l3out list if needed.

        Right now only NoNat needs to do this.

        :param ctx: AIM context
        :param bridge_domain: BridgeDomain AIM resource
        :param l3outside: L3Outside AIM resource
        """

    @abc.abstractmethod
    def unset_bd_l3out(self, ctx, bridge_domain, l3outside):
        """Remove the l3out from the BD's associated l3out list if needed.

        Right now only NoNat needs to do this.

        :param ctx: AIM context
        :param bridge_domain: BridgeDomain AIM resource
        :param l3outside: L3Outside AIM resource
        """


class NatStrategyMixin(NatStrategy):
    """Implements common functionality between different NAT strategies."""

    def __init__(self, mgr):
        self.mgr = mgr
        self.db = model.CloneL3OutManager()

    def create_l3outside(self, ctx, l3outside,
                         vmm_domains=None, phys_domains=None):
        return self._create_l3out(ctx, l3outside,
                                  vmm_domains=vmm_domains,
                                  phys_domains=phys_domains)

    def delete_l3outside(self, ctx, l3outside):
        self._delete_l3out(ctx, l3outside)

    def get_l3outside_resources(self, ctx, l3outside):
        res = []
        l3out = self.mgr.get(ctx, l3outside)
        if l3out:
            res.append(l3out)
            for obj in self._get_nat_objects(ctx, l3out):
                obj_db = self.mgr.get(ctx, obj)
                if obj_db:
                    res.append(obj_db)
            ext_vrf = self._vrf_by_name(ctx, l3out.vrf_name, l3out.tenant_name)
            if ext_vrf:
                res.append(ext_vrf)
        return res

    def create_external_network(self, ctx, external_network,
                                provided_contracts=None,
                                consumed_contracts=None):
        return self._create_ext_net(
            ctx, external_network, provided_contracts=provided_contracts,
            consumed_contracts=consumed_contracts)

    def delete_external_network(self, ctx, external_network,
                                provided_contracts=None,
                                consumed_contracts=None):
        self._delete_ext_net(
            ctx, external_network, provided_contracts=provided_contracts,
            consumed_contracts=consumed_contracts)

    def create_subnet(self, ctx, l3outside, gw_ip_mask):
        l3outside = self.mgr.get(ctx, l3outside)
        if l3outside:
            nat_bd = self._get_nat_bd(ctx, l3outside)
            sub = resource.Subnet(tenant_name=nat_bd.tenant_name,
                                  bd_name=nat_bd.name,
                                  gw_ip_mask=gw_ip_mask)
            if not self.mgr.get(ctx, sub):
                self.mgr.create(ctx, sub)

    def delete_subnet(self, ctx, l3outside, gw_ip_mask):
        l3outside = self.mgr.get(ctx, l3outside)
        if l3outside:
            nat_bd = self._get_nat_bd(ctx, l3outside)
            sub = resource.Subnet(tenant_name=nat_bd.tenant_name,
                                  bd_name=nat_bd.name,
                                  gw_ip_mask=gw_ip_mask)
            self.mgr.delete(ctx, sub)

    def get_subnet(self, ctx, l3outside, gw_ip_mask):
        l3outside = self.mgr.get(ctx, l3outside)
        if l3outside:
            nat_bd = self._get_nat_bd(ctx, l3outside)
            sub = resource.Subnet(tenant_name=nat_bd.tenant_name,
                                  bd_name=nat_bd.name,
                                  gw_ip_mask=gw_ip_mask)
            return self.mgr.get(ctx, sub)

    def create_epg_subnet(self, ctx, l3outside, gw_ip_mask):
        l3outside = self.mgr.get(ctx, l3outside)
        if l3outside:
            ap, nat_epg = self._get_nat_ap_epg(ctx, l3outside)
            sub = resource.EPGSubnet(tenant_name=nat_epg.tenant_name,
                                     app_profile_name=ap.name,
                                     epg_name=nat_epg.name,
                                     gw_ip_mask=gw_ip_mask)
            if not self.mgr.get(ctx, sub):
                self.mgr.create(ctx, sub)

    def delete_epg_subnet(self, ctx, l3outside, gw_ip_mask):
        l3outside = self.mgr.get(ctx, l3outside)
        if l3outside:
            ap, nat_epg = self._get_nat_ap_epg(ctx, l3outside)
            sub = resource.EPGSubnet(tenant_name=nat_epg.tenant_name,
                                     app_profile_name=ap.name,
                                     epg_name=nat_epg.name,
                                     gw_ip_mask=gw_ip_mask)
            self.mgr.delete(ctx, sub)

    def get_epg_subnet(self, ctx, l3outside, gw_ip_mask):
        l3outside = self.mgr.get(ctx, l3outside)
        if l3outside:
            ap, nat_epg = self._get_nat_ap_epg(ctx, l3outside)
            sub = resource.EPGSubnet(tenant_name=nat_epg.tenant_name,
                                     app_profile_name=ap.name,
                                     epg_name=nat_epg.name,
                                     gw_ip_mask=gw_ip_mask)
            return self.mgr.get(ctx, sub)

    def update_external_cidrs(self, ctx, external_network, external_cidrs):
        ext_net_db = self.mgr.get(ctx, external_network)
        if ext_net_db:
            self._manage_external_subnets(ctx, ext_net_db, external_cidrs)

    # This is only needed for NoNat
    def set_bd_l3out(self, ctx, bridge_domain, l3outside):
        pass

    # This is only needed for NoNat
    def unset_bd_l3out(self, ctx, bridge_domain, l3outside):
        pass

    def _create_l3out(self, ctx, l3out, vmm_domains=None, phys_domains=None):
        """Create NAT EPG etc. in addition to creating L3Out."""

        #with ctx.store.begin(subtransactions=True):
        tenant = resource.Tenant(name=l3out.tenant_name)
        if not self.mgr.get(ctx, tenant):
            self.mgr.create(ctx, tenant)
        l3out_db = self.mgr.get(ctx, l3out)
        if not l3out_db:
            ext_vrf = self._get_nat_vrf(ctx, l3out)
            if not self.mgr.get(ctx, ext_vrf):
                self.mgr.create(ctx, ext_vrf)
            l3out_db = copy.copy(l3out)
            l3out_db.vrf_name = ext_vrf.name
            l3out_db = self.mgr.create(ctx, l3out_db)
        self._create_nat_epg(ctx, l3out_db,
                            vmm_domains=vmm_domains,
                            phys_domains=phys_domains)
        return l3out_db

    def _delete_l3out(self, ctx, l3out, delete_epg=True):
        """Delete NAT EPG etc. in addition to deleting L3Out."""

        #with ctx.store.begin(subtransactions=True):
        l3out_db = self.mgr.get(ctx, l3out)
        if l3out_db:
            for en in self.mgr.find(ctx, resource.ExternalNetwork,
                                    tenant_name=l3out.tenant_name,
                                    l3out_name=l3out.name):
                self.delete_external_network(ctx, en)
            if not l3out_db.monitored:
                self.mgr.delete(ctx, l3out)
            if delete_epg:
                self._delete_nat_epg(ctx, l3out_db)
                # delete NAT VRF if any
                self.mgr.delete(ctx, self._get_nat_vrf(ctx, l3out_db))

    def _create_ext_net(self, ctx, ext_net, provided_contracts=None,
                        consumed_contracts=None):
        #with ctx.store.begin(subtransactions=True):
        ext_net_db = self.mgr.get(ctx, ext_net)
        if not ext_net_db:
            ext_net_db = self.mgr.create(ctx, ext_net)
        l3out = self.mgr.get(ctx,
                                self._ext_net_to_l3out(ext_net))
        p_refs = provided_contracts or []
        c_refs = consumed_contracts or []
        contract = self._get_nat_contract(ctx, l3out)
        p_nat = resource.ExternalNetworkProvidedContract(
            tenant_name=contract.tenant_name, l3out_name=l3out.name,
            ext_net_name=ext_net.name, name=contract.name)
        c_nat = resource.ExternalNetworkConsumedContract(
            tenant_name=contract.tenant_name, l3out_name=l3out.name,
            ext_net_name=ext_net.name, name=contract.name)
        p_refs.append(p_nat)
        c_refs.append(c_nat)
        p_refs.extend(c_refs)
        for contract_ref in p_refs:
            if not self.mgr.get(ctx, contract_ref):
                self.mgr.create(ctx, contract_ref)
        return ext_net_db

    def _delete_ext_net(self, ctx, ext_net,
                        provided_contracts=None,
                        consumed_contracts=None):
        #with ctx.store.begin(subtransactions=True):
        ext_net_db = self.mgr.get(ctx, ext_net)
        if ext_net_db:
            self._manage_external_subnets(ctx, ext_net_db, [])
            if not ext_net_db.monitored:
                self._delete_external_contracts(ctx, ext_net_db,
                                                delete_all=True)
                self.mgr.delete(ctx, ext_net)
            else:
                self._delete_external_contracts(
                    ctx, ext_net_db, provided_contracts=provided_contracts,
                    consumed_contracts=consumed_contracts)
                l3out = self.mgr.get(
                    ctx, self._ext_net_to_l3out(ext_net))
                contract = self._get_nat_contract(ctx, l3out)
                self._update_contract(ctx, ext_net_db, contract,
                                        is_remove=True)

    def _delete_external_contracts(self, ctx, ext_net,
                                   provided_contracts=None,
                                   consumed_contracts=None, delete_all=False):
        ext_contract_attr = dict(tenant_name=ext_net.tenant_name,
                                 l3out_name=ext_net.l3out_name,
                                 ext_net_name=ext_net.name)
        if delete_all:
            provided = self.mgr.find(
                ctx, resource.ExternalNetworkProvidedContract,
                **ext_contract_attr)
            consumed = self.mgr.find(
                ctx, resource.ExternalNetworkConsumedContract,
                **ext_contract_attr)
        else:
            provided = provided_contracts or []
            consumed = consumed_contracts or []
        provided.extend(consumed)
        #with ctx.store.begin(subtransactions=True):
        for contract_ref in provided:
            self.mgr.delete(ctx, contract_ref)

    def _manage_external_subnets(self, ctx, ext_net, new_cidrs):
        new_cidrs = new_cidrs[:] if new_cidrs else []
        ext_sub_attr = dict(tenant_name=ext_net.tenant_name,
                            l3out_name=ext_net.l3out_name,
                            external_network_name=ext_net.name)
        old_ext_subs = self.mgr.find(ctx, resource.ExternalSubnet,
                                     **ext_sub_attr)
        #with ctx.store.begin(subtransactions=True):
        for sub in old_ext_subs:
            if sub.cidr in new_cidrs:
                new_cidrs.remove(sub.cidr)
            else:
                self.mgr.delete(ctx, sub)
        for c in new_cidrs:
            self.mgr.create(ctx, resource.ExternalSubnet(cidr=c,
                                                             **ext_sub_attr))

    def _ext_net_to_l3out(self, ext_net):
        return resource.L3Outside(tenant_name=ext_net.tenant_name,
                                  name=ext_net.l3out_name)

    def _display_name(self, res):
        return (getattr(res, 'display_name', None) or res.name)

    def _get_nat_ap_epg(self, ctx, l3out):
        d_name = self._display_name(l3out)
        ap_name = getattr(self, 'app_profile_name', None) or l3out.name
        ap_name = self._scope_name_if_common(l3out.tenant_name, ap_name)
        ap_display_name = aim_utils.sanitize_display_name(ap_name or d_name)
        ap = resource.ApplicationProfile(
            tenant_name=l3out.tenant_name,
            name=ap_name,
            display_name=ap_display_name)
        epg = resource.EndpointGroup(
            tenant_name=ap.tenant_name,
            app_profile_name=ap.name,
            name='EXT-%s' % l3out.name,
            display_name=aim_utils.sanitize_display_name('EXT-%s' % d_name))
        return (ap, epg)

    def _get_nat_contract(self, ctx, l3out):
        d_name = self._display_name(l3out)
        contract_name = self._scope_name_if_common(l3out.tenant_name,
                                                   'EXT-%s' % l3out.name)
        return resource.Contract(
            tenant_name=l3out.tenant_name,
            name=contract_name,
            display_name=self._scope_name_if_common(
                l3out.tenant_name,
                aim_utils.sanitize_display_name('EXT-%s' % d_name)))

    def _get_nat_bd(self, ctx, l3out):
        d_name = self._display_name(l3out)
        bd_name = self._scope_name_if_common(l3out.tenant_name,
                                             'EXT-%s' % l3out.name)
        return resource.BridgeDomain(
            tenant_name=l3out.tenant_name,
            name=bd_name,
            display_name=self._scope_name_if_common(
                l3out.tenant_name,
                aim_utils.sanitize_display_name('EXT-%s' % d_name)),
            limit_ip_learn_to_subnets=True,
            l3out_names=[l3out.name])

    def _get_nat_vrf(self, ctx, l3out):
        d_name = self._display_name(l3out)
        vrf_name = self._scope_name_if_common(l3out.tenant_name,
                                              'EXT-%s' % l3out.name)
        return resource.VRF(
            tenant_name=l3out.tenant_name,
            name=vrf_name,
            display_name=self._scope_name_if_common(
                l3out.tenant_name,
                aim_utils.sanitize_display_name('EXT-%s' % d_name)))

    def _get_nat_objects(self, ctx, l3out):
        sani = aim_utils.sanitize_display_name
        scope = self._scope_name_if_common
        d_name = self._display_name(l3out)
        filter_name = scope(l3out.tenant_name, 'EXT-%s' % l3out.name)
        fltr = resource.Filter(
            tenant_name=l3out.tenant_name,
            name=filter_name,
            display_name=sani(scope(l3out.tenant_name, 'EXT-%s' % d_name)))
        entry = resource.FilterEntry(
            tenant_name=fltr.tenant_name,
            filter_name=fltr.name,
            name='Any',
            display_name='Any')
        contract = self._get_nat_contract(ctx, l3out)
        subject = resource.ContractSubject(
            tenant_name=contract.tenant_name,
            contract_name=contract.name,
            name='Allow', display_name='Allow',
            bi_filters=[fltr.name])
        bd = self._get_nat_bd(ctx, l3out)
        bd.vrf_name = l3out.vrf_name
        ap, epg = self._get_nat_ap_epg(ctx, l3out)
        vm_doms = getattr(
            self, 'vmm_domains',
            [{'type': d.type, 'name': d.name} for d in
             self.mgr.find(ctx, resource.VMMDomain)])
        phy_doms = getattr(
            self, 'physical_domains',
            [{'name': d.name} for d in
             self.mgr.find(ctx, resource.PhysicalDomain)])
        epg.bd_name = bd.name
        epg.provided_contract_names = [contract.name]
        epg.consumed_contract_names = [contract.name]
        epg.vmm_domains = vm_doms
        epg.physical_domains = phy_doms
        return [fltr, entry, contract, subject, bd, ap, epg]

    def _select_domains(self, objs, vmm_domains=None, phys_domains=None):
        for obj in objs:
            if isinstance(obj, resource.EndpointGroup):
                if vmm_domains is not None:
                    obj.vmm_domains = vmm_domains
                if phys_domains is not None:
                    obj.physical_domains = phys_domains

    def _create_nat_epg(self, ctx, l3out, vmm_domains=None, phys_domains=None):
        objs = self._get_nat_objects(ctx, l3out)
        self._select_domains(objs, vmm_domains=vmm_domains,
                             phys_domains=phys_domains)
        #with ctx.store.begin(subtransactions=True):
        for r in objs:
            if not self.mgr.get(ctx, r):
                self.mgr.create(ctx, r)

    def _delete_nat_epg(self, ctx, l3out):
        #with ctx.store.begin(subtransactions=True):
        nat_bd = self._get_nat_bd(ctx, l3out)
        for sub in self.mgr.find(ctx, resource.Subnet,
                                    tenant_name=nat_bd.tenant_name,
                                    bd_name=nat_bd.name):
            self.mgr.delete(ctx, sub)
        for r in reversed(self._get_nat_objects(ctx, l3out)):
            if isinstance(r, resource.ApplicationProfile):
                epgs = self.mgr.find(ctx, resource.EndpointGroup,
                                        tenant_name=r.tenant_name,
                                        app_profile_name=r.name)
                if epgs:
                    continue
            self.mgr.delete(ctx, r)

    def _update_contract(self, ctx, ext_net, contract, is_remove):
        prov = resource.ExternalNetworkProvidedContract(
            tenant_name=ext_net.tenant_name,
            l3out_name=ext_net.l3out_name,
            ext_net_name=ext_net.name, name=contract.name)
        cons = resource.ExternalNetworkConsumedContract(
            tenant_name=ext_net.tenant_name,
            l3out_name=ext_net.l3out_name,
            ext_net_name=ext_net.name, name=contract.name)
        if is_remove:
            prov_db = self.mgr.get(ctx, prov)
            if prov_db:
                self.mgr.delete(ctx, prov_db)
            cons_db = self.mgr.get(ctx, cons)
            if cons_db:
                self.mgr.delete(ctx, cons_db)
        else:
            self.mgr.create(ctx, prov)
            self.mgr.create(ctx, cons)
        return ext_net

    def _is_visible(self, target_tenant, from_tenant):
        return (target_tenant == from_tenant or target_tenant == 'common')

    def _vrf_by_name(self, ctx, vrf_name, tenant_name_hint):
        vrfs = self.mgr.find(ctx, resource.VRF,
                             tenant_name=tenant_name_hint,
                             name=vrf_name)
        if vrfs:
            return vrfs[0]
        vrfs = self.mgr.find(ctx, resource.VRF, tenant_name='common',
                             name=vrf_name)
        if vrfs:
            return vrfs[0]

    def _scope_name_if_common(self, tenant_name, name):
        if tenant_name == 'common':
            scope = getattr(self, 'common_scope', None)
            scope = scope + '_' if scope else ''
            return aim_utils.sanitize_display_name(scope + name)
        return name

    def _update_external_network_contracts(self, ctx, ext_net,
                                           provided_contracts,
                                           consumed_contracts):
        if provided_contracts is None:
            provided_contracts = []
        if consumed_contracts is None:
            consumed_contracts = []
        ext_contract_attr = dict(tenant_name=ext_net.tenant_name,
                                 l3out_name=ext_net.l3out_name,
                                 ext_net_name=ext_net.name)
        # Collect current contracts
        #with ctx.store.begin(subtransactions=True):
        prov = self.mgr.find(
            ctx, resource.ExternalNetworkProvidedContract,
            **ext_contract_attr)
        cons = self.mgr.find(
            ctx, resource.ExternalNetworkConsumedContract,
            **ext_contract_attr)
        # Create dictionaries keyed by conract name
        curr_prov_dict = {p.name: p for p in prov}
        curr_cons_dict = {c.name: c for c in cons}

        new_prov_dict = {p.name: p for p in provided_contracts}
        new_cons_dict = {c.name: c for c in consumed_contracts}

        new_prov_set = set(new_prov_dict.keys())
        new_cons_set = set(new_cons_dict.keys())
        curr_prov_set = set(curr_prov_dict.keys())
        curr_cons_set = set(curr_cons_dict.keys())
        added_prov = new_prov_set - curr_prov_set
        added_cons = new_cons_set - curr_cons_set
        deleted_prov = curr_prov_set - new_prov_set
        deleted_cons = curr_cons_set - new_cons_set

        for con in added_prov:
            self.mgr.create(ctx, new_prov_dict[con], overwrite=True)
        for con in added_cons:
            self.mgr.create(ctx, new_cons_dict[con], overwrite=True)
        for con in deleted_prov:
            self.mgr.delete(ctx, curr_prov_dict[con])
        for con in deleted_cons:
            self.mgr.delete(ctx, curr_cons_dict[con])


class NoNatStrategy(NatStrategyMixin):
    """No NAT Strategy.

    Provides direct external connectivity without any network
    address translation.
    """

    def __init__(self, mgr):
        super(NoNatStrategy, self).__init__(mgr)

    def delete_external_network(self, ctx, external_network,
                                provided_contracts=None,
                                consumed_contracts=None):
        """Clean-up any connected VRFs before deleting the external network."""

        #with ctx.store.begin(subtransactions=True):
        ext_net = self.mgr.get(ctx, external_network)
        if not ext_net:
            return
        l3out = self.mgr.get(ctx,
                                self._ext_net_to_l3out(external_network))
        vrf = self._vrf_by_name(ctx, l3out.vrf_name, l3out.tenant_name)
        if vrf:
            self._disconnect_vrf_from_l3out(ctx, l3out, vrf)
        self._delete_ext_net(
            ctx, ext_net, provided_contracts=provided_contracts,
            consumed_contracts=consumed_contracts)

    def connect_vrf(self, ctx, external_network, vrf,
                    provided_contracts=None,
                    consumed_contracts=None):
        """Allow external connectivity to VRF.

        Make external_network provide/consume specified contracts.
        Locate BDs referring to the VRF, and include L3Outside
        in their l3out_names.
        """
        #with ctx.store.begin(subtransactions=True):
        if not self._is_visible(vrf.tenant_name,
                                external_network.tenant_name):
            raise VrfNotVisibleFromExternalNetwork(
                vrf=vrf, ext_net=external_network)
        l3out = self.mgr.get(ctx,
                                self._ext_net_to_l3out(external_network))
        old_vrf = self._vrf_by_name(ctx, l3out.vrf_name,
                                    l3out.tenant_name)
        if not old_vrf or old_vrf.identity != vrf.identity:
            LOG.error('connect_vrf: cannot change VRF connected to '
                        'no-NAT L3Outside %s',
                        l3out)
            raise L3OutsideVrfChangeDisallowed(l3out=l3out,
                                                old_vrf=old_vrf, vrf=vrf)

        nat_bd = self._get_nat_bd(ctx, l3out)
        self._set_bd_l3out(ctx, l3out, vrf, exclude_bd=nat_bd)

        contract = self._get_nat_contract(ctx, l3out)
        nat_prov = resource.ExternalNetworkProvidedContract(
            tenant_name=external_network.tenant_name,
            l3out_name=external_network.l3out_name,
            ext_net_name=external_network.name, name=contract.name)
        nat_cons = resource.ExternalNetworkConsumedContract(
            tenant_name=external_network.tenant_name,
            l3out_name=external_network.l3out_name,
            ext_net_name=external_network.name, name=contract.name)
        prov = (list(set(provided_contracts + [nat_prov]))
                if provided_contracts else [nat_prov])
        cons = (list(set(consumed_contracts + [nat_cons]))
                if consumed_contracts else [nat_cons])
        # Calculate differences from existing contracts and
        # those that were passed.
        self._update_external_network_contracts(
            ctx, external_network, provided_contracts=prov,
            consumed_contracts=cons)

    def disconnect_vrf(self, ctx, external_network, vrf):
        """Remove external connectivity for VRF.

        Remove contracts provided/consumed by external_network.
        Locate BDs referring to the VRF, and exclude L3Outside
        from their l3out_names.
        """
        #with ctx.store.begin(subtransactions=True):
        l3out = self.mgr.get(ctx,
                                self._ext_net_to_l3out(external_network))
        old_vrf = self._vrf_by_name(ctx, l3out.vrf_name,
                                    l3out.tenant_name)
        if old_vrf and old_vrf.identity != vrf.identity:
            LOG.info('disconnect_vrf: %s is not connected to %s',
                        external_network, vrf)
            return

        self._disconnect_vrf_from_l3out(ctx, l3out, vrf)

        contract = self._get_nat_contract(ctx, l3out)
        nat_prov = resource.ExternalNetworkProvidedContract(
            tenant_name=external_network.tenant_name,
            l3out_name=external_network.l3out_name,
            ext_net_name=external_network.name, name=contract.name)
        nat_cons = resource.ExternalNetworkConsumedContract(
            tenant_name=external_network.tenant_name,
            l3out_name=external_network.l3out_name,
            ext_net_name=external_network.name, name=contract.name)
        self._update_external_network_contracts(
            ctx, external_network, provided_contracts=[nat_prov],
            consumed_contracts=[nat_cons])

    def read_vrfs(self, ctx, external_network):
        l3out = self.mgr.get(ctx,
                             self._ext_net_to_l3out(external_network))
        vrf = self._vrf_by_name(ctx, l3out.vrf_name, l3out.tenant_name)
        return [vrf] if vrf else []

    def set_bd_l3out(self, ctx, bridge_domain, l3outside):
        bridge_domain = self.mgr.get(ctx, bridge_domain)
        if bridge_domain and l3outside.name not in bridge_domain.l3out_names:
            self.mgr.update(
                ctx, bridge_domain,
                l3out_names=bridge_domain.l3out_names + [l3outside.name])

    def unset_bd_l3out(self, ctx, bridge_domain, l3outside):
        bridge_domain = self.mgr.get(ctx, bridge_domain)
        if bridge_domain and l3outside.name in bridge_domain.l3out_names:
            bridge_domain.l3out_names.remove(l3outside.name)
            self.mgr.update(ctx, bridge_domain,
                            l3out_names=bridge_domain.l3out_names)

    def _get_bds_in_vrf_for_l3out(self, ctx, vrf, l3out):
        if vrf.tenant_name == 'common' and l3out.tenant_name == 'common':
            # BDs in all tenants are candidates - locate all BDs whose
            # vrf_name matches vrf.name, and exclude those that have a
            # local VRF aliasing the given VRF.
            all_bds = self.mgr.find(ctx, resource.BridgeDomain,
                                    vrf_name=vrf.name)
            bd_tenants = set([b.tenant_name for b in all_bds])
            bd_tenants = [t for t in bd_tenants
                          if not self.mgr.get(
                              ctx, resource.VRF(tenant_name=t, name=vrf.name))]
            return [b for b in all_bds if b.tenant_name in bd_tenants]
        elif (vrf.tenant_name == 'common' or
              vrf.tenant_name == l3out.tenant_name):
            # VRF and L3out are visible only to BDs in l3out's tenant
            return self.mgr.find(ctx, resource.BridgeDomain,
                                 tenant_name=l3out.tenant_name,
                                 vrf_name=vrf.name)
        # Other combinations of L3Out and VRF are not valid
        # configurations and can be excluded:
        # 1. L3out in common, VRF not in common: VRF is not
        #    visible to L3out
        # 2. L3Out and VRF are in different non-common tenants:
        #    VRF is not visible to L3out
        return []

    def _set_bd_l3out(self, ctx, l3outside, vrf, exclude_bd=None):
        # update all the BDs
        for bd in self._get_bds_in_vrf_for_l3out(ctx, vrf, l3outside):
            if exclude_bd and exclude_bd.identity == bd.identity:
                continue
            # Add L3Out to existing list
            if l3outside.name not in bd.l3out_names:
                self.mgr.update(ctx, bd,
                                l3out_names=bd.l3out_names + [l3outside.name])

    def _unset_bd_l3out(self, ctx, l3outside, vrf, exclude_bd=None):
        # update all the BDs
        for bd in self._get_bds_in_vrf_for_l3out(ctx, vrf, l3outside):
            if exclude_bd and exclude_bd.identity == bd.identity:
                continue
            # Remove L3Out from existing list
            if l3outside.name in bd.l3out_names:
                bd.l3out_names.remove(l3outside.name)
                self.mgr.update(ctx, bd, l3out_names=bd.l3out_names)

    def _disconnect_vrf_from_l3out(self, ctx, l3outside, vrf):
        nat_bd = self._get_nat_bd(ctx, l3outside)
        self._unset_bd_l3out(ctx, l3outside, vrf, exclude_bd=nat_bd)


class DistributedNatStrategy(NatStrategyMixin):
    """Distributed NAT Strategy.

    Provides external connectivity with network address
    translation (DNAT/SNAT) where the translation is distributed
    amongst nodes in the fabric.

    """

    def delete_external_network(self, ctx, external_network,
                                provided_contracts=None,
                                consumed_contracts=None):
        """Delete external-network from main and cloned L3Outs.

        """
        #with ctx.store.begin(subtransactions=True):
        # Delete specified external-network from all cloned L3Outs.
        # Delete external-network from main L3Out.
        l3out = self.mgr.get(ctx,
                                self._ext_net_to_l3out(external_network))
        ext_net_db = self.mgr.get(ctx, external_network)
        if l3out and ext_net_db:
            clone_l3outs = self._find_l3out_clones(ctx, l3out)
            for clone in clone_l3outs:
                clone_ext_net = resource.ExternalNetwork(
                    tenant_name=clone.tenant_name,
                    l3out_name=clone.name,
                    name=ext_net_db.name)
                self._delete_ext_net(
                    ctx, clone_ext_net,
                    provided_contracts=provided_contracts,
                    consumed_contracts=consumed_contracts)
                self._delete_unused_l3out(ctx, clone)
        self._delete_ext_net(
            ctx, ext_net_db, provided_contracts=provided_contracts,
            consumed_contracts=consumed_contracts)

    def update_external_cidrs(self, ctx, external_network, external_cidrs):
        """Update external CIDRs in main and cloned ExternalNetworks."""
        l3out = self.mgr.get(ctx, self._ext_net_to_l3out(external_network))
        ext_net_db = self.mgr.get(ctx, external_network)
        if l3out and ext_net_db:
            clone_l3outs = self._find_l3out_clones(ctx, l3out)
            #with ctx.store.begin(subtransactions=True):
            for clone in clone_l3outs:
                clone_ext_net = resource.ExternalNetwork(
                    tenant_name=clone.tenant_name,
                    l3out_name=clone.name,
                    name=external_network.name)
                self._manage_external_subnets(ctx, clone_ext_net,
                                                external_cidrs)
            self._manage_external_subnets(ctx, ext_net_db,
                                            external_cidrs)

    def connect_vrf(self, ctx, external_network, vrf,
                    provided_contracts=None,
                    consumed_contracts=None):
        """Allow external connectivity to VRF.

        Create shadow L3Outside for L3Outside-VRF combination
        in VRF's tenant, if required.
        Create ExternalNetwork and ExternalSubnet(s) in the shadow
        L3Out, if required.
        Set vrf_name of shadow L3Outside to VRF.

        """
        #with ctx.store.begin(subtransactions=True):
        return self._create_shadow(
            ctx, external_network, vrf,
            provided_contracts=provided_contracts,
            consumed_contracts=consumed_contracts)

    def disconnect_vrf(self, ctx, external_network, vrf):
        """Remove external connectivity for VRF.

        Delete ExternalNetwork and contained ExternalSubnet
        in the shadow L3Outside. Remove shadow L3Outside if
        there are no more ExternalNetworks in the shadow
        L3Outside.
        """
        #with ctx.store.begin(subtransactions=True):
        self._delete_shadow(ctx, external_network, vrf)

    def read_vrfs(self, ctx, external_network):
        l3out = self.mgr.get(ctx,
                             self._ext_net_to_l3out(external_network))
        result = []
        for c in self.db.get_clones(ctx, l3out):
            l3c = self.mgr.get(ctx, resource.L3Outside(tenant_name=c[0],
                                                       name=c[1]))
            if l3c:
                vrf = self.mgr.get(
                    ctx, resource.VRF(tenant_name=l3c.tenant_name,
                                      name=l3c.vrf_name))
                if vrf:
                    result.append(vrf)
        return result

    def _generate_l3out_name(self, l3outside, vrf):
        # Generate a name based on its relationship with VRF
        name = '%s-%s' % (l3outside.name, vrf.name)
        display_name = aim_utils.sanitize_display_name(
            '%s-%s' % (self._display_name(l3outside),
                       self._display_name(vrf)))
        return (name, display_name)

    def _make_l3out_clone(self, ctx, l3out, vrf):
        new_tenant = vrf.tenant_name
        new_name, new_display_name = self._generate_l3out_name(l3out, vrf)

        clone_l3out = resource.L3Outside(
            tenant_name=new_tenant,
            name=new_name,
            display_name=new_display_name,
            vrf_name=vrf.name)
        return clone_l3out

    def _create_shadow(self, ctx, ext_net, vrf, with_nat_epg=True,
                       provided_contracts=None, consumed_contracts=None):
        """Clone ExternalNetwork as a shadow."""

        ext_net_db = self.mgr.get(ctx, ext_net)
        if not ext_net_db:
            return
        l3out = self.mgr.get(ctx, self._ext_net_to_l3out(ext_net_db))
        clone_l3out = self._make_l3out_clone(ctx, l3out, vrf)
        # The real ExternalNetwork contracts need to be
        # converted to the shadow ones, so do that if
        # any were passed.
        clone_ext_net = resource.ExternalNetwork(
            tenant_name=clone_l3out.tenant_name,
            l3out_name=clone_l3out.name,
            display_name=ext_net_db.display_name,
            name=ext_net.name)
        if provided_contracts is None:
            clone_prov = []
        else:
            clone_prov = [resource.ExternalNetworkProvidedContract(
                tenant_name=clone_l3out.tenant_name,
                l3out_name=clone_l3out.name,
                ext_net_name=clone_ext_net.name,
                name=prov.name) for prov in provided_contracts]
        if consumed_contracts is None:
            clone_cons = []
        else:
            clone_cons = [resource.ExternalNetworkConsumedContract(
                tenant_name=clone_l3out.tenant_name,
                l3out_name=clone_l3out.name,
                ext_net_name=clone_ext_net.name,
                name=cons.name) for cons in consumed_contracts]

        if with_nat_epg:
            _, nat_epg = self._get_nat_ap_epg(ctx, l3out)
            clone_ext_net.nat_epg_dn = nat_epg.dn

        #with ctx.store.begin(subtransactions=True):
        self.mgr.create(ctx, clone_l3out, overwrite=True)
        self.mgr.create(ctx, clone_ext_net, overwrite=True)
        self._update_external_network_contracts(
            ctx, clone_ext_net, provided_contracts=clone_prov,
            consumed_contracts=clone_cons)
        cidrs = self.mgr.find(ctx, resource.ExternalSubnet,
                                tenant_name=ext_net_db.tenant_name,
                                l3out_name=ext_net_db.l3out_name,
                                external_network_name=ext_net_db.name)
        cidrs = [c.cidr for c in cidrs]
        self._manage_external_subnets(ctx, clone_ext_net, cidrs)
        # Set this item as a clone
        if not self.db.get(ctx, clone_l3out):
            self.db.set(ctx, l3out, clone_l3out)
        return clone_ext_net

    def _delete_shadow(self, ctx, ext_net, vrf):
        l3out = self.mgr.get(ctx, self._ext_net_to_l3out(ext_net))

        clone_l3out = resource.L3Outside(
            tenant_name=vrf.tenant_name,
            name=self._generate_l3out_name(l3out, vrf)[0])
        clone_ext_net = resource.ExternalNetwork(
            tenant_name=clone_l3out.tenant_name,
            l3out_name=clone_l3out.name,
            name=ext_net.name)

        #with ctx.store.begin(subtransactions=True):
        self._delete_ext_net(ctx, clone_ext_net)
        self._delete_unused_l3out(ctx, clone_l3out)

    def _find_l3out_clones(self, ctx, l3outside):
        clone_keys = self.db.get_clones(ctx, l3outside)
        return [resource.L3Outside(tenant_name=x[0], name=x[1])
                for x in clone_keys]

    def _delete_unused_l3out(self, ctx, l3out):
        ens = self.mgr.find(ctx, resource.ExternalNetwork,
                            tenant_name=l3out.tenant_name,
                            l3out_name=l3out.name)
        if not ens:
            self._delete_l3out(ctx, l3out, delete_epg=False)


class EdgeNatStrategy(DistributedNatStrategy):
    """Edge NAT Strategy.

    Provides external connectivity with network address
    translation (DNAT/SNAT) where the translation is centralized
    in a node at the edge of the fabric.
    """

    def connect_vrf(self, ctx, external_network, vrf, external_cidrs=None,
                    provided_contracts=None,
                    consumed_contracts=None):
        """Allow external connectivity to VRF.

        Create shadow L3Outside for L3Outside-VRF combination
        in VRF's tenant, if required.
        Create ExternalNetwork and ExternalSubnet in the shadow
        L3Out, if required.
        Set vrf_name of shadow L3Outside to VRF.

        """
        #with ctx.store.begin(subtransactions=True):
        return self._create_shadow(ctx, external_network, vrf,
                                    with_nat_epg=False,
                                    provided_contracts=provided_contracts,
                                    consumed_contracts=consumed_contracts)

    def _make_l3out_clone(self, ctx, l3out, vrf):
        clone_l3out = super(EdgeNatStrategy, self)._make_l3out_clone(
            ctx, l3out, vrf)
        # TODO(amitbose) modify the clone_l3out node-profile etc
        return clone_l3out
