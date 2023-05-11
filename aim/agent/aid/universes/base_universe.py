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


import abc
import six
import time
import traceback

from apicapi import apic_client
from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes import errors
from aim import aim_manager
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim import exceptions
from aim import tree_manager


LOG = logging.getLogger(__name__)
CREATE = 'create'
DELETE = 'delete'
CONFIG_UNIVERSE = 0
OPER_UNIVERSE = 1
MONITOR_UNIVERSE = 2
ACTION_RESET = 'reset'
ACTION_PURGE = 'purge'


@six.add_metaclass(abc.ABCMeta)
class BaseUniverse(object):
    """Universe Base Class

    A Universe is a component of the AID (ACI Inconsistency Detector) that
    represents the state of a specific system.
    The observed state could either be the Desired or the Operational one.
    Each state is grouped by AIM tenant and should be stored in a format that
    is easily comparable with a state of the same type.
    Any type of observer can choose the favourit storage data structure as
    long as observer inheriting from the same Class are able to compare their
    observed states.
    """

    @abc.abstractmethod
    def initialize(self, conf_mgr, multiverse):
        """Observer initialization method.

        This method will be called before any other.

        :param store: AIM persistent store, can be used to retrieve state
        or useful configuration options.
        :param conf_mgr: configuration manager.
        :return: self
        """

    @abc.abstractmethod
    def observe(self, context):
        """Observes the current state of the Universe

        This method is used to refresh the current state. Some Universes might
        want to run threads at initialization time for this purpose. In that
        case this method can be void.
        :return:
        """

    @abc.abstractmethod
    def reconcile(self, context, other_universe, delete_candidates):
        """State reconciliation method.

        When an universe's reconcile method is called, the state of the passed
        universe is the desired final state, therefore this method will do
        its best to make its own state identical to the desired one.
        In some cases, the reconciliation will ignore some attributes or
        keep its own existing state. The ideal scenario is that after
        reconciliation the desired state is a subset of the current one.

        :param context:
        :param other_universe: universe to which we want to converge
        :param delete_candidates: dictionary that each universe can use to
               vote for tenant deletion. Dictionary keys will be the tenant
               identifier, while the value is a set of universes' instance
               where a specific Universe adds/removes itself to when he
               agrees/desagrees on a tenant being removed.
        :return:
        """

    @abc.abstractmethod
    def reset(self, context, tenants):
        """Tenant state reset method

        Whenever one or multiple tenants are found to be consistently divergent
        from the desired state, this reset method will be called so that the
        universe can put its tenant in a clean state.
        :param context:
        :param tenants: list of tenants that need reset
        :return:
        """

    @abc.abstractproperty
    def state(self):
        """Current state of the universe

        :return: The current state of the universe. Two comparable universes
        should use the same state format.
        """

    @abc.abstractproperty
    def name(self):
        """Name Property

        :return: Readable name for debugging purposes.
        """


@six.add_metaclass(abc.ABCMeta)
class AimUniverse(BaseUniverse):
    """Universe based on the ACI Integration Module."""

    @abc.abstractmethod
    def get_resource(self, resource_key):
        """Given a resource key, returns the AIM resource

        :param resource_key: Key representing the AIM resource. The format
        of the key can be defined by the Universe specialization. Comparable
        Universes must have the same key format.
        :return:
        """

    @abc.abstractmethod
    def get_resources(self, resource_keys):
        """Given a resource key list, returns this universe's resources

        In case the AIM resource doesn't exist in the DB, a non-persistent
        resource will be fine as well as long as the identity attributes
        are correctly set.

        :param resource_keys: List of keys representing the AIM resource.
        The format of the key can be defined by the Universe specialization.
        Comparable Universes must have the same key format.
        :return:
        """

    @abc.abstractmethod
    def get_resource_for_delete(self, resource_key):
        """Given a resource key, returns resource for delete

        :param resource_key: Key representing the resource. The format
        of the key can be defined by the Universe specialization. Comparable
        Universes must have the same key format.
        :return:
        """

    @abc.abstractmethod
    def get_resources_for_delete(self, resource_keys):
        """Given a resource key list, returns resources for delete

        :param resource_keys: List of keys representing the AIM resource.
        The format of the key can be defined by the Universe specialization.
        Comparable Universes must have the same key format.
        :return:
        """

    @abc.abstractmethod
    def push_resources(self, context, resources):
        """Given a resource map, push it in the current Universe

        This method will transform the desired Universe's resources into a
        format that the current Universe understands, and the push them.
        :param context:
        :param resources: The resource map to be pushed. map will organize
        the resources by "create" and "delete"
        :return:
        """

    @abc.abstractmethod
    def serve(self, context, tenants):
        """Set the current Universe to serve a number of tenants

        When the list of served tenants changes, resources for previously
        served ones need to be freed.
        :param context:
        :param tenants: List of tenant identifiers
        :return:
        """

    @abc.abstractmethod
    def cleanup_state(self, context, key):
        """Cleanup state entry

        :param context:
        :param key: root id
        :return:
        """

    @abc.abstractmethod
    def vote_deletion_candidates(self, context, other_universe,
                                 delete_candidates, vetoes):
        """Vote deletion candidates

        Decide whether the cleanup process should be initiated for a specific
        candidate.

        :param context:
        :param other_universe
        :param delete_candidates: set that each universe can use to
               vote for tenant deletion.
        :param
        :return:
        """

    @abc.abstractmethod
    def finalize_deletion_candidates(self, context, other_universe,
                                     delete_candidates):
        """Finalize deletion candidates

        After one reconciliation cycle, decide whether the tenant should be
        completely deleted. Universes can only *remove* candidates at this
        point from the list.

        :param context:
        :param other_universe:
        :param delete_candidates:
        :return:
        """

    @abc.abstractmethod
    def update_status_objects(self, context, my_state, raw_diff, skip_keys):
        """Update status objects

        Given the current state of the tenant, update the proper status objects
        to reflect their sync situation.

        :param context:
        :param my_state: state of the universe
        :param raw_diff: difference dictionary listing hashtree keys
        :return:
        """

    @abc.abstractmethod
    def get_state_by_type(self, type):
        """Get state by type

        Given a universe type (Monitored/Operational/Config) return the
        current state.
        :param type:
        :return:
        """

    @abc.abstractmethod
    def get_relevant_state_for_read(self):
        """Get relevant state for model read

        Whenever we need to read resources from the current universe (see
        get_resources) we need to look at all the relevant universes to
        compose the full object. For example, an EPG can partly exist in the
        Config universe as well as the Monitor universe, therefore we
        need to look both places.
        :return:
        """


class HashTreeStoredUniverse(AimUniverse):
    """Universe storing state in the form of a Hash Tree."""

    def initialize(self, conf_mgr, multiverse):
        super(HashTreeStoredUniverse, self).initialize(conf_mgr, multiverse)
        self.multiverse = multiverse
        self.manager = aim_manager.AimManager()
        self.conf_manager = conf_mgr
        self._state = {}
        self.max_create_retry = self.conf_manager.get_option(
            'max_operation_retry', 'aim')
        self.max_backoff_time = 600
        self.reset_retry_limit = 2 * self.max_create_retry
        self.purge_retry_limit = 2 * self.reset_retry_limit
        self.error_handlers = {
            errors.OPERATION_CRITICAL: self._surrender_operation,
            errors.SYSTEM_CRITICAL: self._fail_agent,
        }
        self._sync_log = {}
        return self

    def _dissect_key(self, key):
        # Returns ('apicType', [identity list])
        aci_type = key[-1][:key[-1].find('|')]
        return aci_type, [x[x.find('|') + 1:] for x in key]

    def _split_key(self, key):
        return [k.split('|', 2) for k in key]

    def _keys_to_bare_aci_objects(self, keys):
        # Transforms hashtree keys into minimal ACI objects
        aci_objects = []
        for key in keys:
            fault_code = None
            key_parts = self._split_key(key)
            mo_type = key_parts[-1][0]
            aci_object = {mo_type: {'attributes': {}}}
            if mo_type == 'faultInst':
                fault_code = key_parts[-1][1]
                key_parts = key_parts[:-1]
            dn = apic_client.DNManager().build(key_parts)
            if fault_code:
                dn += '/fault-%s' % fault_code
                aci_object[mo_type]['attributes']['code'] = fault_code
            aci_object[mo_type]['attributes']['dn'] = dn
            aci_objects.append(aci_object)
        return aci_objects

    def _mask_tenant_state(self, other_universe, delete_candidates):
        for tenant in delete_candidates:
            if tenant in other_universe.state:
                other_universe.state[tenant] = (
                    structured_tree.StructuredHashTree())

    def observe(context, self):
        pass

    def reconcile(self, context, other_universe, delete_candidates):
        return self._reconcile(context, other_universe)

    def vote_deletion_candidates(self, context, other_universe,
                                 delete_candidates, vetoes):
        pass

    def _pop_up_sync_log(self, delete_candidates):
        for root in delete_candidates:
            self._sync_log.pop(root, None)

    def finalize_deletion_candidates(self, context, other_universe,
                                     delete_candidates):
        self._pop_up_sync_log(delete_candidates)

    def _reconcile(self, context, other_universe):
        # "self" is always the current state, "other" the desired
        my_state = self.state
        other_state = other_universe.state
        diff = False
        for tenant in set(my_state.keys()) & set(other_state.keys()):
            # TODO(ivar): parallelize the procedure on Tenant's basis
            try:
                differences = {CREATE: [], DELETE: []}
                other_tenant_state = other_state[tenant]
                my_tenant_state = my_state.get(
                    tenant, structured_tree.StructuredHashTree())
                # Retrieve difference to transform self into other
                difference = other_tenant_state.diff(my_tenant_state)
                differences[CREATE].extend(difference['add'])
                differences[DELETE].extend(difference['remove'])

                if differences.get(CREATE) or differences.get(DELETE):
                    LOG.info("Universe differences between %s and %s: %s",
                             self.name, other_universe.name, differences)
                    diff = True
                result = {
                    CREATE: other_universe.get_resources(differences[CREATE]),
                    DELETE: self.get_resources_for_delete(differences[DELETE])
                }

                reset, fail, skip = self._track_universe_actions(result,
                                                                 tenant)
                if (self._sync_log.get(tenant, {}).get('create') or
                        self._sync_log.get(tenant, {}).get('delete')):
                    LOG.debug('Sync log cache for %s (%s): %s' %
                              (self.name, tenant, self._sync_log))

                if reset:
                    self.reset(context, [tenant])
                    other_universe.reset(context, [tenant])
                    # Don't synchronize resetting roots
                    continue

                for action, res in fail:
                    if action == CREATE:
                        self.creation_failed(
                            context, res,
                            reason='Divergence detected on this object.',
                            error=errors.OPERATION_CRITICAL)
                    if action == DELETE:
                        self.deletion_failed(
                            context, res,
                            reason='Divergence detected on this object.',
                            error=errors.OPERATION_CRITICAL)
                    skip.append((action, res))

                skipset = set()
                if skip:
                    differences[CREATE] = set(differences[CREATE])
                    differences[DELETE] = set(differences[DELETE])

                    for action, res in skip:
                        for key in (tree_manager.AimHashTreeMaker.
                                    aim_res_to_nodes(res)):
                            differences[action].discard(key)
                            skipset.add(key)
                    differences[CREATE] = list(differences[CREATE])
                    differences[DELETE] = list(differences[DELETE])
                    # Need to rebuild results
                    result = {
                        CREATE: other_universe.get_resources(
                            differences[CREATE]),
                        DELETE: self.get_resources_for_delete(
                            differences[DELETE])
                    }
                self.update_status_objects(context, my_tenant_state,
                                           differences, skipset)
                other_universe.update_status_objects(
                    context, other_tenant_state, differences, skipset)
                # Reconciliation method for pushing changes
                self.push_resources(context, result)
            except Exception as e:
                LOG.error("An unexpected error has occurred while "
                          "reconciling tenant %s: %s" % (tenant, str(e)))
                LOG.error(traceback.format_exc())
                # Guess we can't consider the multiverse synced if this happens
                diff = True
        return diff

    def reset(self, context, tenants):
        pass

    def get_resource_for_delete(self, resource_key):
        return self.get_resources_for_delete([resource_key])

    def get_resources_for_delete(self, resource_keys):
        return []

    def get_resource(self, resource_key):
        return self.get_resources([resource_key])

    def get_resources(self, resource_keys, desired_state=None):
        if resource_keys:
            LOG.debug("Requesting resource keys in %s: %s",
                      self.name, resource_keys)
        # NOTE(ivar): state is a copy at the current iteration that was created
        # through the observe() method.
        desired_state = desired_state or self.get_relevant_state_for_read()
        result = []
        id_set = set()
        monitored_set = set()
        for key in resource_keys:
            if key not in id_set:
                attr = self._fill_node(key, desired_state)
                if not attr:
                    continue
                monitored = attr.pop('monitored', None)
                related = attr.pop('related', False)
                attr = attr.get('attributes', {})
                aci_object = self._keys_to_bare_aci_objects([key])[0]
                list(aci_object.values())[0]['attributes'].update(attr)
                dn = list(aci_object.values())[0]['attributes']['dn']
                # Capture related objects
                if desired_state:
                    self._fill_related_nodes(resource_keys, key,
                                             desired_state)
                    if related:
                        self._fill_parent_node(resource_keys, key,
                                               desired_state)
                result.append(aci_object)
                if monitored:
                    if related:
                        try:
                            monitored_set.add(
                                converter.AciToAimModelConverter().convert(
                                    [aci_object])[0].dn)
                        except IndexError:
                            pass
                    else:
                        monitored_set.add(dn)
                id_set.add(key)
        if resource_keys:
            result = self._convert_get_resources_result(result, monitored_set)
            LOG.debug("Result for keys %s\n in %s:\n %s" %
                      (resource_keys, self.name, result))
        return result

    def _get_resources_for_delete(self, resource_keys, mon_uni, action):
        if resource_keys:
            LOG.debug("Requesting resource keys in %s for "
                      "delete: %s" % (self.name, resource_keys))
        result = []
        for key in resource_keys:
            aci_object = self._keys_to_bare_aci_objects([key])[0]
            # If this object exists in the monitored tree it's transitioning
            root = tree_manager.AimHashTreeMaker._extract_root_rn(key)
            try:
                node = mon_uni[root].find(key)
            except KeyError:
                node = None
            action(result, aci_object, node)
        if resource_keys:
            LOG.debug("Result for keys %s\n in ACI Universe for delete:\n %s" %
                      (resource_keys, result))
        return result

    def _fill_node(self, current_key, desired_state):
        root = tree_manager.AimHashTreeMaker._extract_root_rn(current_key)
        for state in desired_state:
            try:
                current_node = state[root].find(current_key)
            except (IndexError, KeyError):
                continue
            if current_node and not current_node.dummy:
                return current_node.metadata.to_dict()

    def _fill_related_nodes(self, resource_keys, current_key, desired_state):
        root = tree_manager.AimHashTreeMaker._extract_root_rn(current_key)
        for state in desired_state:
            try:
                current_node = state[root].find(current_key)
                if not current_node:
                    continue
            except (IndexError, KeyError):
                continue
            for child in current_node.get_children():
                if child.metadata.get('related') and not child.dummy:
                    resource_keys.append(child.key)

    def _fill_parent_node(self, resource_keys, current_key, desired_state):
        root = tree_manager.AimHashTreeMaker._extract_root_rn(current_key)
        for state in desired_state:
            try:
                parent_node = state[root].find(current_key[:-1])
                if not parent_node:
                    continue
            except (IndexError, KeyError):
                continue
            if not parent_node.dummy:
                resource_keys.append(parent_node.key)

    def serve(self, context, tenants):
        pass

    def cleanup_state(self, context, key):
        pass

    def creation_succeeded(self, aim_object):
        pass

    def creation_failed(self, context, aim_object, reason='unknown',
                        error=errors.UNKNOWN):
        self._fail_aim_synchronization(context, aim_object, 'creation', reason,
                                       error)

    def deletion_failed(self, context, aim_object, reason='unknown',
                        error=errors.UNKNOWN):
        self._fail_aim_synchronization(context, aim_object, 'deletion', reason,
                                       error)

    def _fail_aim_synchronization(self, context, aim_object, operation, reason,
                                  error):
        return self.error_handlers.get(error, self._noop)(
            context, aim_object, operation, reason)

    def _surrender_operation(self, context, aim_object, operation, reason):
        self.manager.set_resource_sync_error(context, aim_object,
                                             message=reason)

    def _fail_agent(self, context, aim_object, operation, reason):
        utils.perform_harakiri(LOG, message=reason)

    def _get_aim_object_identifier(self, aim_object):
        # Identify AIM object unequivocally
        return (type(aim_object).__name__,) + tuple(
            [getattr(aim_object, x) for x in aim_object.identity_attributes])

    def _noop(self, *args, **kwargs):
        return

    def _convert_get_resources_result(self, result, monitored_set):
        return result

    def _track_universe_actions(self, actions, root):
        """Track Universe Actions.

        Keep track of what the universe has been doing in the past few
        iterations. Keeping count of any operation repeated over time and
        decreasing count of actions that are not happening in this iteration.
        :param actions: dictionary in the form {'root': {'create': {'hash':},
                                                         'delete': {}}}
        :param root: root under consideration
        :return:
        """
        # TODO(ivar): if tenant is unserved, its action track will leak until
        # AID is restarted. Be aware of this during tracking refactoring.
        curr_time = time.time()
        reset = False
        seen = set()
        fail = []
        skip = []
        root_state = self._sync_log.setdefault(
            root, {'create': {}, 'delete': {}})
        new_state = {'create': {}, 'delete': {}}
        for action in [CREATE, DELETE]:
            for res in self._action_items_to_aim_resources(actions,
                                                           action):
                if res in seen:
                    continue
                seen.add(res)
                # Same resource created twice in the same iteration is
                # increased only once
                if root != res.root:
                    raise exceptions.BadTrackingArgument(
                        exp=root, act=res.root, res=actions)
                new = (new_state[action].setdefault(
                    res, {'limit': self.reset_retry_limit, 'res': res,
                          'retries': -1, 'action': ACTION_RESET,
                          'last': curr_time, 'next': curr_time}))
                curr = root_state[action].get(res, {})
                if curr:
                    new.update(curr)
                curr = new
                if curr_time < curr['next']:
                    # Let's not make any consideration about this object
                    LOG.debug("AIM object %s is being re-tried too soon "
                              "(delta: %s secs). Skipping for now." %
                              (str(res), curr['next'] - curr_time))
                    skip.append((action, res))
                    continue

                curr['next'] = curr_time + utils.get_backoff_time(
                    self.max_backoff_time, curr['retries'])
                curr['retries'] += 1
                if curr['retries'] > curr['limit']:
                    if curr['action'] == ACTION_RESET:
                        LOG.warning("AIM object %s failed %s more than %s "
                                    "times, resetting its root" %
                                    (str(res), action, curr['retries']))
                        reset = True
                        curr['limit'] = self.purge_retry_limit
                        curr['action'] = ACTION_PURGE
                    else:
                        LOG.warning("AIM object %s failed %s more than %s "
                                    "times, going to ERROR state" %
                                    (str(res), action, curr['retries']))
                        curr['limit'] += 5
                        fail.append((action, res))
        self._sync_log[root] = new_state
        return reset, fail, skip

    @property
    def state(self):
        """The state of an HashTreeStoredUniverse has the following format:

        - Dictionary object;
        - Keys in the dictionary are the AIM tenant names;
        - Values are StructuredHashTree objects for that specific tenant.
        - The key format of the StructuredHashTreeNode is a tuple with a list
        for each level of the object's DN. This list has exactly 2 items in the
        following order: relative-type, relative-name.
        EG: (['Tenant', 'tenant-name'], ['BridgeDomain', 'bd-name'],
             ['Subnet', 'subnet-name'])
        - The Keys are identifiers for AIM objects

        :return: Current state of the universe as described above.
        """
        return self._state
