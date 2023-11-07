from aim import aim_manager
import copy

from oslo_log import log as logging

from aim.api import infra as api_infra
from aim.api import resource as api_res
from aim.api import service_graph as api_service_graph
from aim.api import status as api_status
from aim.api import tree as api_tree
from aim.common import utils
from aim import exceptions as exc


class AimManager(object):

    aim_resources = {api_res.BridgeDomain,
                     api_res.Agent,
                     api_res.Tenant,
                     api_res.Subnet,
                     api_res.EPGSubnet,
                     api_res.VRF,
                     api_res.ApplicationProfile,
                     api_res.EndpointGroup,
                     api_res.Filter,
                     api_res.FilterEntry,
                     api_res.OutOfBandContract,
                     api_res.OutOfBandContractSubject,
                     api_res.Contract,
                     api_res.ContractSubject,
                     api_status.AciStatus,
                     api_status.AciFault,
                     api_res.Endpoint,
                     api_res.VMMDomain,
                     api_res.PhysicalDomain,
                     api_res.L3Outside,
                     api_res.L3OutNodeProfile,
                     api_res.L3OutNode,
                     api_res.L3OutStaticRoute,
                     api_res.L3OutInterfaceProfile,
                     api_res.L3OutInterface,
                     api_res.ExternalNetwork,
                     api_res.ExternalNetworkProvidedContract,
                     api_res.ExternalNetworkConsumedContract,
                     api_res.ExternalSubnet,
                     api_res.L3OutInterfaceBgpPeerP,
                     api_infra.HostLink,
                     api_infra.OpflexDevice,
                     api_infra.HostDomainMapping,
                     api_infra.HostDomainMappingV2,
                     api_infra.HostLinkNetworkLabel,
                     api_infra.ApicAssignment,
                     api_res.SecurityGroup,
                     api_res.SecurityGroupSubject,
                     api_res.SecurityGroupRule,
                     api_res.Configuration,
                     api_service_graph.DeviceCluster,
                     api_service_graph.DeviceClusterInterface,
                     api_service_graph.ConcreteDevice,
                     api_service_graph.ConcreteDeviceInterface,
                     api_service_graph.ServiceGraph,
                     api_service_graph.ServiceGraphConnection,
                     api_service_graph.ServiceGraphNode,
                     api_service_graph.ServiceRedirectPolicy,
                     api_service_graph.DeviceClusterContext,
                     api_service_graph.DeviceClusterInterfaceContext,
                     api_service_graph.ServiceRedirectMonitoringPolicy,
                     api_service_graph.ServiceRedirectHealthGroup,
                     api_res.VMMPolicy,
                     api_res.Pod,
                     api_res.Topology,
                     api_res.VMMController,
                     api_res.VmmInjectedNamespace,
                     api_res.VmmInjectedDeployment,
                     api_res.VmmInjectedReplicaSet,
                     api_res.VmmInjectedService,
                     api_res.VmmInjectedHost,
                     api_res.VmmInjectedContGroup,
                     api_res.Infra,
                     api_res.NetflowVMMExporterPol,
                     api_res.QosRequirement,
                     api_res.QosDppPol,
                     api_res.VmmVswitchPolicyGroup,
                     api_res.VmmRelationToExporterPol,
                     api_res.SpanVsourceGroup,
                     api_res.SpanVsource,
                     api_res.SpanVdestGroup,
                     api_res.SpanVdest,
                     api_res.SpanVepgSummary,
                     api_res.InfraAccBundleGroup,
                     api_res.InfraAccPortGroup,
                     api_res.SpanSpanlbl,
                     api_tree.ActionLog,
                     api_res.SystemSecurityGroup,
                     api_res.SystemSecurityGroupSubject,
                     api_res.SystemSecurityGroupRule}

    # # Keep _db_model_map in AIM manager for backward compatibility
    # _db_model_map = {k: None for k in aim_resources}

    # # Build adjacency graph (Key: <ACI Resource> Value: <Key's children>)
    # _model_tree = {}
    # _res_by_aci_type = {}
    # for klass in aim_resources:
    #     try:
    #         _model_tree.setdefault(klass._tree_parent, []).append(klass)
    #         _res_by_aci_type[klass._aci_mo_name] = klass
    #     except AttributeError:
    #         pass
    
    def __init__(self):
        self.aim_manager = aim_manager.AimManager()

    def create(self, context, resource, overwrite=False, fix_ownership=False):
        with context.store.db_session.begin():
            self.aim_manager.create(context, resource, overwrite,
                                    fix_ownership)

    def update(self, context, resource, fix_ownership=False,
               force_update=False, **update_attr_val):
        with context.store.db_session.begin():
            return self.aim_manager.update(context, resource, fix_ownership,
                                           force_update, **update_attr_val)

    def delete(self, context, resource, force=False, cascade=False):
        with context.store.db_session.begin():
            self.aim_manager.delete(context, resource, force, cascade)

    def delete_all(self, context, resource_class, for_update=False, **kwargs):
        with context.store.db_session.begin():
            self.aim_manager.delete_all(context, resource_class, for_update,
                                        **kwargs)

    def get(self, context, resource, for_update=False, include_aim_id=False):
        with context.store.db_session.begin():
            return self.aim_manager.get(context, resource, for_update,
                                        include_aim_id)

    def get_by_id(self, context, resource_class, aim_id, for_update=False,
                  include_aim_id=False):
        with context.store.db_session.begin():
            return self.aim_manager.get_by_id(context, resource_class, aim_id,
                                              for_update, include_aim_id)

    def find(self, context, resource_class, for_update=False,
             include_aim_id=False, **kwargs):
        with context.store.db_session.begin():
            return self.aim_manager.find(context, resource_class, for_update,
                                         include_aim_id, **kwargs)

    def count(self, context, resource_class, **kwargs):
        with context.store.db_session.begin():
            return self.aim_manager.count(context, resource_class, **kwargs)

    def get_status(self, context, resource, for_update=False,
                   create_if_absent=True):
        with context.store.db_session.begin():
            return self.aim_manager.get_status(context, resource, for_update,
                                               create_if_absent)

    def get_statuses(self, context, resources):
        with context.store.db_session.begin():
            return self.aim_manager.get_statuses(context, resources)

    def update_status(self, context, resource, status):
        with context. store.db_session.begin():
            return self.aim_manager.update_status(context, resource, status)

    def set_resource_sync_synced(self, context, resource):
        with context.store.db_session.begin():
            self.aim_manager.set_resource_sync_synced(context, resource)

    def recover_root_errors(self, context, root):
        with context.store.db_session.begin():
            self.aim_manager.recover_root_errors(context, root)

    def set_resource_sync_pending(self, context, resource, top=True,
                                  cascade=True):
        with context.store.db_session.begin():
            self.aim_manager.set_resource_sync_pending(context, resource,
                                                       top, cascade)

    def set_resource_sync_error(self, context, resource, message='', top=True):
        with context.store.db_session.begin():
            self.aim_manager.set_resource_sync_error(context, resource,
                                                     message, top)

    def set_fault(self, context, resource, fault):
        with context.store.db_session.begin():
            self.aim_manager.set_fault(context, resource, fault)

    def clear_fault(self, context, fault, **kwargs):
        self.aim_manager.clear_fault(context, fault, **kwargs)

    def get_subtree(self, context, resource):
        self.aim_manager.get_subtree(context, resource)
