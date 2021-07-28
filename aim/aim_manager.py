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

import copy

from oslo_log import log as logging

from aim.api import infra as api_infra
from aim.api import resource as api_res
from aim.api import service_graph as api_service_graph
from aim.api import status as api_status
from aim.api import tree as api_tree
from aim.common import utils
from aim import exceptions as exc


LOG = logging.getLogger(__name__)


class AimManager(object):
    """Main object for performing operations on AIM.

    To manipulate AIM database objects, invoke the appropriate
    operation specifying an AimContext and the resource to operate on. The
    resource should be an object of type that inherits from
    aim.api.ResourceBase.
    The AimContext must have property 'db_session' set to sqlalchemy
    ORM session object; the database operation is performed in the
    context of that session.
    Example: Create a BridgeDomain object and then retrieve it

        db = ...
        a_ctx = AimContext(db_session=db)
        mgr = AimManager(...)

        bd = aim.api.resource.BridgeDomain(...)
        mgr.create(a_ctx, bd)

        retrieved_bd = mgr.get(a_ctx, bd)
    """

    # TODO(ivar): aim_resources should eventually replace _db_model_map
    # Set of managed AIM resources.
    aim_resources = {api_res.BridgeDomain,
                     api_res.Agent,
                     api_res.Tenant,
                     api_res.Subnet,
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
                     api_res.SystemSecurityGroup,
                     api_res.SystemSecurityGroupSubject,
                     api_res.SystemSecurityGroupRule,
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
                     api_tree.ActionLog}

    # Keep _db_model_map in AIM manager for backward compatibility
    _db_model_map = {k: None for k in aim_resources}

    # Build adjacency graph (Key: <ACI Resource> Value: <Key's children>)
    _model_tree = {}
    _res_by_aci_type = {}
    for klass in aim_resources:
        try:
            _model_tree.setdefault(klass._tree_parent, []).append(klass)
            _res_by_aci_type[klass._aci_mo_name] = klass
        except AttributeError:
            pass

    def __init__(self):
        pass

    @utils.log
    def create(self, context, resource, overwrite=False, fix_ownership=False):
        """Persist AIM resource to the database.

        If 'overwrite' is True, and an object exists in the database
        with the same identity attribute values, then that object will
        be over-written with the specified resource. Otherwise an
        integrity constraint violation is raised.
        """
        self._validate_resource_class(resource)
        with context.store.begin(subtransactions=True):
            old_db_obj = None
            old_monitored = None
            new_monitored = None
            if overwrite:
                old_db_obj = self._query_db_obj(context.store, resource)
                if old_db_obj:
                    old_monitored = getattr(old_db_obj, 'monitored', None)
                    new_monitored = getattr(resource, 'monitored', None)
                    if (fix_ownership and old_monitored is not None and
                            old_monitored != new_monitored):
                        raise exc.InvalidMonitoredStateUpdate(object=resource)
                    attr_val = context.store.extract_attributes(resource,
                                                                "other")
                    old_resource = self._make_resource(context, resource,
                                                       old_db_obj)
                    if old_resource.user_equal(resource):
                        # No need to update. Return old_resource for
                        # updated DB attributes
                        return old_resource
                    context.store.from_attr(old_db_obj, type(resource),
                                            attr_val)
            db_obj = old_db_obj or context.store.make_db_obj(resource)
            if 'name' in dir(db_obj):
                resource.name = db_obj.name
            context.store.add(db_obj)
            if self._should_set_pending(old_db_obj, old_monitored,
                                        new_monitored):
                # NOTE(ivar): we shouldn't change status in the AIM manager
                # as this goes against the "AIM as a schema" principles.
                # However, we need to do this at least for cases where
                # we take ownership of the objects, which should be removed
                # soon as it's causing most of our bugs.
                self.set_resource_sync_pending(context, resource)
            return self.get(context, resource)

    @utils.log
    def update(self, context, resource, fix_ownership=False,
               force_update=False, **update_attr_val):
        """Persist updates to AIM resource to the database.

        Values of identity attributes of parameter 'resource' are used
        to determine the database object to update; no other attributes
        from 'resource' are used during the update. Param 'update_attr_val'
        specifies the values of the attributes to update.
        If the object does not exist in the database, no changes are
        made to the database.
        """
        self._validate_resource_class(resource)
        with context.store.begin(subtransactions=True):
            db_obj = self._query_db_obj(context.store, resource)
            if db_obj:
                old_resource = self._make_resource(context, resource, db_obj)
                old_monitored = getattr(db_obj, 'monitored', None)
                new_monitored = update_attr_val.get('monitored')
                if (fix_ownership and old_monitored is not None and
                        old_monitored != new_monitored):
                    raise exc.InvalidMonitoredStateUpdate(object=resource)
                attr_val = {k: v for k, v in update_attr_val.items()
                            if k in resource.other_attributes.keys()}
                if attr_val:
                    old_resource_copy = copy.deepcopy(old_resource)
                    for k, v in attr_val.items():
                        setattr(old_resource, k, v)
                    if old_resource.user_equal(
                            old_resource_copy) and not force_update:
                        # Nothing to do here
                        return old_resource
                elif resource.identity_attributes:
                    # force update
                    id_attr_0 = list(resource.identity_attributes.keys())[0]
                    attr_val = {id_attr_0: getattr(resource, id_attr_0)}
                context.store.from_attr(db_obj, type(resource), attr_val)
                context.store.add(db_obj)
                if self._should_set_pending(db_obj, old_monitored,
                                            new_monitored):
                    # NOTE(ivar): we shouldn't change status in the AIM manager
                    # as this goes against the "AIM as a schema" principles.
                    # However, we need to do this at least for cases where
                    # we take ownership of the objects, which should be removed
                    # soon as it's causing most of our bugs.
                    self.set_resource_sync_pending(context, resource)
                return self.get(context, resource)

    def _should_set_pending(self, old_obj, old_monitored, new_monitored):
        return old_obj and old_monitored is False and new_monitored is True

    @utils.log
    def delete(self, context, resource, force=False, cascade=False):
        """Delete AIM resource from the database.

        Only values of identity attributes of parameter 'resource' are
        used; other attributes may be left unspecified.
        If the object does not exist in the database, no error is reported.
        """
        self._validate_resource_class(resource)
        with context.store.begin(subtransactions=True):
            db_obj = self._query_db_obj(context.store, resource)
            if db_obj:
                if isinstance(resource, api_res.AciResourceBase):
                    status = self.get_status(
                        context, resource, create_if_absent=False)
                    if status and getattr(
                            db_obj, 'monitored', None) and not force:
                        if status.sync_status == status.SYNC_PENDING:
                            # Cannot delete monitored objects if sync status
                            # is pending, or ownership flip might fail
                            raise exc.InvalidMonitoredObjectDelete(
                                object=resource)
                    if status:
                        self.delete(context, status, force=force)
                context.store.delete(db_obj)
            # When cascade is specified, delete the object's subtree even if
            # the resource itself doesn't exist.
            if cascade:
                for child_res in self.get_subtree(context, resource):
                    # Delete without cascade
                    self.delete(context, child_res, force=force)

    @utils.log
    def delete_all(self, context, resource_class, for_update=False, **kwargs):
        """Delete many AIM resources from the database that match criteria.

        Parameter 'resource_class' indicates the type of resource to
        look for. Matching criteria are specified as keyword-arguments.
        Only equality matches are supported.
        Returns a list of resources that match.
        """
        self._validate_resource_class(resource_class)
        attr_val = {k: v for k, v in kwargs.items()
                    if k in resource_class.attributes() +
                    ['in_', 'notin_', 'order_by']}
        return self._delete_db(context.store, resource_class, **attr_val)

    def get(self, context, resource, for_update=False, include_aim_id=False):
        """Get AIM resource from the database.

        Values of identity attributes of parameter 'resource' are used
        to determine the database object to fetch; other attributes may
        be left unspecified.
        Returns a resource with all the attributes populated with contents
        of the object in the database if the object is found, None
        otherwise.
        """
        self._validate_resource_class(resource)
        db_obj = self._query_db_obj(context.store, resource,
                                    for_update=for_update)
        return self._make_resource(context, resource, db_obj,
                                   include_aim_id=include_aim_id)

    def _make_resource(self, context, resource, db_obj, include_aim_id=None):
        return context.store.make_resource(
            type(resource), db_obj,
            include_aim_id=include_aim_id) if db_obj else None

    def get_by_id(self, context, resource_class, aim_id, for_update=False,
                  include_aim_id=False):
        self._validate_resource_class(resource_class)
        db_obj = self._query_db(context.store, resource_class,
                                for_update=for_update, aim_id=aim_id)
        return context.store.make_resource(
            resource_class, db_obj[0],
            include_aim_id=include_aim_id) if db_obj else None

    def find(self, context, resource_class, for_update=False,
             include_aim_id=False, **kwargs):
        """Find AIM resources from the database that match specified criteria.

        Parameter 'resource_class' indicates the type of resource to
        look for. Matching criteria are specified as keyword-arguments.
        Only equality matches are supported.
        Returns a list of resources that match.
        """
        self._validate_resource_class(resource_class)
        attr_val = {k: v for k, v in kwargs.items()
                    if k in resource_class.attributes() +
                    ['in_', 'notin_', 'order_by']}
        result = []
        for obj in self._query_db(context.store, resource_class,
                                  for_update=for_update, **attr_val):
            result.append(
                context.store.make_resource(resource_class, obj,
                                            include_aim_id=include_aim_id))
        return result

    def count(self, context, resource_class, **kwargs):
        self._validate_resource_class(resource_class)
        attr_val = {k: v for k, v in kwargs.items()
                    if k in resource_class.attributes() +
                    ['in_', 'notin_', 'order_by']}
        return self._count_db(context.store, resource_class, **attr_val)

    def get_status(self, context, resource, for_update=False,
                   create_if_absent=True):
        """Get status of an AIM resource, if any.

        Values of identity attributes of parameter 'resource' are used
        to determine the object to get status for; other attributes may
        be left unspecified.
        """

        with context.store.begin(subtransactions=True):
            if isinstance(resource, api_res.AciResourceBase):
                res_type, res_id = self._get_status_params(context, resource)
                if res_type and res_id is not None:
                    status = self.get(context, api_status.AciStatus(
                        resource_type=res_type, resource_id=res_id,
                        resource_root=resource.root), for_update=for_update)
                    if not status:
                        if not create_if_absent:
                            return
                        # Create one with default values
                        # NOTE(ivar): Sometimes we need the status of an object
                        # even if AID wasn't able to calculate it yet
                        # (eg. storing faults). In this case the status object
                        # will be created with N/A sync_status.
                        return self.update_status(
                            context, resource, api_status.AciStatus(
                                resource_type=res_type, resource_id=res_id,
                                resource_root=resource.root,
                                resource_dn=resource.dn))
                    status.faults = self.find(context, api_status.AciFault,
                                              status_id=status.id)
                    return status
        return None

    def get_statuses(self, context, resources):
        with context.store.begin(subtransactions=True):
            return context.store.query_statuses(resources)

    @utils.log
    def update_status(self, context, resource, status):
        """Update the status of an AIM resource.

        Values of identity attributes of parameter 'resource' are used
        to determine the object whose status will be updated; other
        attributes may be left unspecified.
        """
        with context.store.begin(subtransactions=True):
            if isinstance(resource, api_res.AciResourceBase):
                res_type, res_id = self._get_status_params(context, resource)
                if res_type and res_id is not None:
                    status.resource_type = res_type
                    status.resource_id = res_id
                    return self.create(context, status, overwrite=True)

    def _set_resource_sync(self, context, resource, sync_status, message='',
                           exclude=None):
        if isinstance(resource, api_status.AciStatus):
            return False
        with context.store.begin(subtransactions=True):
            self._validate_resource_class(resource)
            status = self.get_status(context, resource)
            exclude = exclude or []
            if status and status.sync_status not in exclude:
                self.update(context, status, sync_status=sync_status,
                            sync_message=message, force_update=True)
                return True
            return False

    def set_resource_sync_synced(self, context, resource):
        self._set_resource_sync(context, resource, api_status.AciStatus.SYNCED)

    def recover_root_errors(self, context, root):
        with context.store.begin(subtransactions=True):
            context.store.update_all(
                api_status.AciStatus,
                filters={'sync_status': api_status.AciStatus.SYNC_FAILED,
                         'resource_root': root},
                sync_status=api_status.AciStatus.SYNC_PENDING,
                sync_message='')

    def set_resource_sync_pending(self, context, resource, top=True,
                                  cascade=True):
        # When a resource goes in pending state, propagate to both parent
        # and subtree
        with context.store.begin(subtransactions=True):
            # If resource is already in pending or synced state stop
            # propagation
            if self._set_resource_sync(
                    context, resource, api_status.AciStatus.SYNC_PENDING,
                    exclude=[api_status.AciStatus.SYNCED,
                             api_status.AciStatus.SYNC_PENDING,
                             api_status.AciStatus.SYNC_NA]
                    if not top else [api_status.AciStatus.SYNC_PENDING]):
                # Change parent first
                parent_klass = resource._tree_parent
                if parent_klass:
                    identity = {v: resource.identity[i]
                                for i, v in enumerate(
                        parent_klass.identity_attributes)}
                    self.set_resource_sync_pending(context,
                                                   parent_klass(**identity),
                                                   top=False)
                if cascade:
                    for child_res in self.get_subtree(context, resource):
                        self.set_resource_sync_pending(context, child_res,
                                                       top=False,
                                                       cascade=False)

    def set_resource_sync_error(self, context, resource, message='', top=True):
        with context.store.begin(subtransactions=True):
            # No need to set sync_error for resources already in that state
            if self._set_resource_sync(
                    context, resource, api_status.AciStatus.SYNC_FAILED,
                    message=message,
                    exclude=[api_status.AciStatus.SYNC_FAILED]) and top:
                # Set sync_error for the whole subtree
                for child_res in self.get_subtree(context, resource):
                    self.set_resource_sync_error(
                        context, child_res,
                        message="Parent resource %s is "
                                "in error state" % str(resource), top=False)

    @utils.log
    def set_fault(self, context, resource, fault):
        fault = copy.deepcopy(fault)
        with context.store.begin(subtransactions=True):
            status = self.get_status(context, resource)
            if status:
                fault.status_id = status.id
                self.create(context, fault, overwrite=True)

    @utils.log
    def clear_fault(self, context, fault, **kwargs):
        self.delete(context, fault)

    def _validate_resource_class(self, resource_or_class):
        res_cls = (resource_or_class if isinstance(resource_or_class, type)
                   else type(resource_or_class))
        if res_cls not in self.aim_resources:
            raise exc.UnknownResourceType(type=res_cls)

    def _query_db(self, store, resource_class, for_update=False, **kwargs):
        db_cls = store.resource_to_db_type(resource_class)
        return (store.query(db_cls, resource_class, lock_update=for_update,
                            **kwargs) if db_cls else None)

    def _count_db(self, store, resource_class, **kwargs):
        db_cls = store.resource_to_db_type(resource_class)
        return (store.count(db_cls, resource_class, **kwargs)
                if db_cls else None)

    def _delete_db(self, store, resource_class, **kwargs):
        db_cls = store.resource_to_db_type(resource_class)
        return (store.delete_all(db_cls, resource_class, **kwargs)
                if db_cls else None)

    def _query_db_obj(self, store, resource, for_update=False):
        id_attr = store.extract_attributes(resource, "id")
        cls = type(resource)
        objs = self._query_db(store, cls, for_update=for_update, **id_attr)
        return objs[0] if objs else None

    def _get_status_params(self, context, resource):
        res_type = type(resource).__name__
        # Try to avoid DB call
        inj_id = getattr(resource, '_injected_aim_id',
                         getattr(resource, '_aim_id', None))
        if inj_id:
            return res_type, inj_id
        db_obj = self._query_db_obj(context.store, resource)
        if db_obj is None:
            # TODO(ivar): should we raise a proper exception?
            return None, None
        try:
            res_id = db_obj.aim_id
        except AttributeError:
            LOG.warn("Resource with type %s doesn't support status" %
                     res_type)
            return None, None
        return res_type, res_id

    def get_subtree(self, context, resource):
        return self._get_subtree(context, type(resource), *resource.identity)

    def _get_subtree(self, context, klass, *identity, **kwargs):
        subtree_resources = []

        def get_subtree_klasses(klass):
            for child_klass in self._model_tree.get(klass, []):
                id = {list(child_klass.identity_attributes.keys())[i]: v
                      for i, v in enumerate(identity)}
                # Extra search attributes
                id.update(kwargs)
                subtree_resources.extend(self.find(context, child_klass, **id))
                get_subtree_klasses(child_klass)
        get_subtree_klasses(klass)
        return subtree_resources
