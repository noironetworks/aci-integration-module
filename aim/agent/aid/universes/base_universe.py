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

from apicapi import apic_client
from oslo_log import log as logging

from aim.agent.aid.universes import errors
from aim import aim_manager
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim import context
from aim import exceptions
from aim import tree_manager


LOG = logging.getLogger(__name__)
CREATE = 'create'
DELETE = 'delete'


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
    def initialize(self, store, conf_mgr):
        """Observer initialization method.

        This method will be called before any other.

        :param store: AIM persistent store, can be used to retrieve state
        or useful configuration options.
        :param conf_mgr: configuration manager.
        :return: self
        """

    @abc.abstractmethod
    def observe(self):
        """Observes the current state of the Universe

        This method is used to refresh the current state. Some Universes might
        want to run threads at initialization time for this purpose. In that
        case this method can be void.
        :return:
        """

    @abc.abstractmethod
    def reconcile(self, other_universe, delete_candidates):
        """State reconciliation method.

        When an universe's reconcile method is called, the state of the passed
        universe is the desired final state, therefore this method will do
        its best to make its own state identical to the desired one.
        In some cases, the reconciliation will ignore some attributes or
        keep its own existing state. The ideal scenario is that after
        reconciliation the desired state is a subset of the current one.

        :param other_universe: universe to which we want to converge
        :param delete_candidates: dictionary that each universe can use to
               vote for tenant deletion. Dictionary keys will be the tenant
               identifier, while the value is a set of universes' instance
               where a specific Universe adds/removes itself to when he
               agrees/desagrees on a tenant being removed.
        :return:
        """

    @abc.abstractmethod
    def reset(self, tenants):
        """Tenant state reset method

        Whenever one or multiple tenants are found to be consistently divergent
        from the desired state, this reset method will be called so that the
        universe can put its tenant in a clean state.
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
    def push_resources(self, resources):
        """Given a resource map, push it in the current Universe

        This method will transform the desired Universe's resources into a
        format that the current Universe understands, and the push them.
        :param resources: The resource map to be pushed. map will organize
        the resources by "create" and "delete"
        :return:
        """

    @abc.abstractmethod
    def serve(self, tenants):
        """Set the current Universe to serve a number of tenants

        When the list of served tenants changes, resources for previously
        served ones need to be freed.
        :param tenants: List of tenant identifiers
        :return:
        """
    @abc.abstractmethod
    def get_optimized_state(self, other_state):
        """Get optimized state.

        Given a state, return a subset of the current state containing only
        changed tenants. This is useful for interaction with universes that
        don't store in-memory state and are able to make less expensive calls
        by knowing in advance the counterpart's state.

        :param other_state: state object of another universe
        :return:
        """

    @abc.abstractmethod
    def detect_hashtree_divergence(self, differences, not_found, state,
                                   other_state, other_universe):
        """Detect hashtree divergence

        Checks for hashtree inconsistencies and take action when possible in
        order to avoid agent divergence.

        :param differences: hashtree diff calculated between this universe and
        its counterpart
        :param not_found: resources that could not be found from the desired
        state. They can be useful to detect whether certain AIM resources have
        disappeared from the main model, but they are still in the hashtree.
        :param state: the current state on which the differences were
        calculated
        :param other_state: the state of the other universe from which the
        differences were calculated
        :param other_universe: handler to the counterpart universe
        :return:
        """

    @abc.abstractmethod
    def replace_state(self, root, tree):
        """Replace state

        Given a root, replace its current state minding the tree version. A
        tree with a version number different from the one currently set will
        not be replaced.

        :param root:
        :param tree:
        :return:
        """

    @abc.abstractmethod
    def cleanup_state(self, key):
        """Cleanup state entry

        :param key: tenant id
        :return:
        """
    @abc.abstractmethod
    def update_status_objects(self, my_state, other_universe, other_state,
                              raw_diff, transformed_diff):
        """Update status objects

        Given the current state of the system, update the proper status objects
        to reflect their sync situation.

        :param my_state: state of the universe
        :param other_state: state of the comparing universe
        :param other_universe: handler to the other universe
        :param raw_diff: difference dictionary listing hashtree keys
        :param transformed_diff: difference dictionary listing normalized
                                 objects
        :return:
        """


class ResetReconciliation(exceptions.AimException):
    message = 'Reconciliation phase needs to be reset by universe %(name)s'


class HashTreeStoredUniverse(AimUniverse):
    """Universe storing state in the form of a Hash Tree."""

    def initialize(self, store, conf_mgr):
        super(HashTreeStoredUniverse, self).initialize(store, conf_mgr)
        self.context = context.AimContext(store=store)
        self.manager = aim_manager.AimManager()
        self.conf_manager = conf_mgr
        self._state = {}
        self.failure_log = {}
        self.max_create_retry = self.conf_manager.get_option(
            'max_operation_retry', 'aim')
        self.max_consecutive_operations = 2 * self.max_create_retry
        # Don't increase retry value if at least retry_cooldown seconds have
        # passed
        self.retry_cooldown = self.conf_manager.get_option('retry_cooldown',
                                                           'aim')
        self.error_handlers = {
            errors.OPERATION_TRANSIENT: self._retry_until_max,
            errors.UNKNOWN: self._retry_until_max,
            errors.OPERATION_CRITICAL: self._surrender_operation,
            errors.SYSTEM_CRITICAL: self._fail_agent,
        }
        self.tt_maker = tree_manager.AimHashTreeMaker()
        self._action_cache = {}
        return self

    def _dissect_key(self, key):
        # Returns ('apicType', [identity list])
        aci_type = key[-1][:key[-1].find('|')]
        return aci_type, [x[x.find('|') + 1:] for x in key]

    def _split_key(self, key):
        # Returns [['apicType', 'rn'], ['apicType1', 'rn1'] ...]
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

    def observe(self):
        pass

    def reconcile(self, other_universe, delete_candidates):
        return self._reconcile(other_universe, delete_candidates)

    def _vote_tenant_for_deletion(self, other_universe, tenant,
                                  delete_candidates):
        votes = delete_candidates.setdefault(tenant, set())
        votes.add(self)

    def _reconcile(self, other_universe, delete_candidates,
                   skip_dummy=False, always_vote_deletion=False):
        # "self" is always the current state, "other" the desired
        my_state = self.state
        # TODO(ivar): We used get_optimized_state method here. By doing that
        # however, we can't identify what items need to be set in synced state
        # to improve performance, get_optimized_state should return both
        # different tenants and those with at least one hashtree node in
        # pending state.
        other_state = other_universe.state

        differences = {CREATE: [], DELETE: []}
        for tenant in set(my_state.keys()) & set(other_state.keys()):
            tree = other_state[tenant]
            my_tenant_state = my_state.get(
                tenant, structured_tree.StructuredHashTree())
            # Retrieve difference to transform self into other
            difference = tree.diff(my_tenant_state)
            differences[CREATE].extend(difference['add'])
            differences[DELETE].extend(difference['remove'])
            if difference['add'] or difference['remove']:
                LOG.info("Universes %s and %s have differences for tenant "
                         "%s" % (self.name, other_universe.name, tenant))
        # Remove empty tenants
        for tenant, tree in my_state.iteritems():
            if always_vote_deletion or (
                    skip_dummy and (not tree.root or tree.root.dummy)):
                LOG.debug("%s voting for removal of tenant %s" %
                          (self.name, tenant))
                self._vote_tenant_for_deletion(other_universe, tenant,
                                               delete_candidates)
                continue
            if not tree.root:  # A Tenant has no state
                if tenant not in other_state or not other_state[tenant].root:
                    self._vote_tenant_for_deletion(
                        other_universe, tenant, delete_candidates)
                else:
                    # This universe disagrees on deletion
                    delete_candidates.get(tenant, set()).discard(self)

        if not differences.get(CREATE) and not differences.get(DELETE):
            LOG.debug("Universe %s and %s are in sync." %
                      (self.name, other_universe.name))
            diff = False
        else:
            LOG.info("Universe differences between %s and %s: %s",
                     self.name, other_universe.name, differences)
            diff = True

        # Get AIM resources at the end to reduce the number of transactions
        to_create, not_found = other_universe.get_resources(
            differences[CREATE])
        result = {CREATE: to_create,
                  DELETE: self.get_resources_for_delete(differences[DELETE])}
        self._track_universe_actions(result, my_state)

        try:
            self.detect_hashtree_divergence(
                differences, not_found, my_state, other_state, other_universe)
            other_universe.detect_hashtree_divergence(
                differences, not_found, other_state, my_state, self)
        except ResetReconciliation as e:
            LOG.warn(e.message)
            return True

        # Set status objects properly
        self.update_status_objects(my_state, other_universe, other_state,
                                   differences, result)
        other_universe.update_status_objects(other_state, self, my_state,
                                             differences, result)
        # Reconciliation method for pushing changes
        self.push_resources(result)
        return diff

    def reset(self, tenants):
        pass

    def get_resource_for_delete(self, resource_key):
        return self.get_resources_for_delete([resource_key])

    def get_resources_for_delete(self, resource_keys):
        pass

    def get_resource(self, resource_key):
        return self.get_resources([resource_key])[0]

    def serve(self, tenants):
        pass

    def get_optimized_state(self, other_state):
        return self.state

    def cleanup_state(self, key):
        pass

    def creation_succeeded(self, aim_object):
        aim_id = self._get_aim_object_identifier(aim_object)
        self.failure_log.pop(aim_id, None)

    def creation_failed(self, aim_object, reason='unknown',
                        error=errors.UNKNOWN):
        self._fail_aim_synchronization(aim_object, 'creation', reason, error)

    def deletion_failed(self, aim_object, reason='unknown',
                        error=errors.UNKNOWN):
        self._fail_aim_synchronization(aim_object, 'deletion', reason, error)

    def _fail_aim_synchronization(self, aim_object, operation, reason,
                                  error):
        return self.error_handlers.get(error, utils.noop)(aim_object,
                                                          operation, reason)

    def _retry_until_max(self, aim_object, operation, reason):
        aim_id = self._get_aim_object_identifier(aim_object)
        failures, last = self.failure_log.get(aim_id, (0, None))
        curr_time = time.time()
        if not last or curr_time - last >= self.retry_cooldown:
            self.failure_log[aim_id] = (failures + 1, curr_time)
            if self.failure_log[aim_id][0] >= self.max_create_retry:
                LOG.warn("AIM object %s failed %s more than %s times in %s, "
                         "setting its state to Error" %
                         (aim_id, operation, self.max_create_retry, self.name))
                # Surrender
                self.manager.set_resource_sync_error(self.context, aim_object,
                                                     message=reason)
                self.failure_log.pop(aim_id, None)

    def _surrender_operation(self, aim_object, operation, reason):
        aim_id = self._get_aim_object_identifier(aim_object)
        self.manager.set_resource_sync_error(self.context, aim_object,
                                             message=reason)
        self.failure_log.pop(aim_id, None)

    def _fail_agent(self, aim_object, operation, reason):
        utils.perform_harakiri(LOG, message=reason)

    def _get_aim_object_identifier(self, aim_object):
        # Identify AIM object unequivocally
        return (type(aim_object).__name__,) + tuple(
            [getattr(aim_object, x) for x in aim_object.identity_attributes])

    def _action_items_to_aim_resources(self, actions, action):
        return actions[action]

    def _track_universe_actions(self, actions, state):
        """Track Universe Actions.

        Keep track of what the universe has been doing in the past few
        iterations. Keeping count of any operation repeated over time and
        decreasing count of actions that are not happening in this iteration.

        :param actions: dictionary in the form {'create': [..], 'delete': [..]}
        :param state: current state of the tenants that own the objects
               specified in 'actions'
        :return:
        """
        cache = {}
        for action in [CREATE, DELETE]:
            for res in self._action_items_to_aim_resources(actions, action):
                # Same resource created twice in the same iteration is
                # increased only once
                root = self.tt_maker.resource_to_root(res)
                version = state[root].version
                (cache.setdefault(action, {}).
                 setdefault(root, {}).
                 setdefault(version, {}).
                 setdefault(res.hash,
                            (self._action_cache.get(action, {}).get(root, {})
                             .get(version, {}).get(res.hash, (0,))[0] + 1,
                             res)))
        self._action_cache = cache

    def _get_resources_consecutive_actions(self, state, action, limit):
        result = {}
        for root in self._action_cache.get(action, {}):
            for naction, res in self._action_cache[action][root].get(
                    state[root].version, {}).values():
                if naction >= limit:
                    result.setdefault(root, []).append(res)
        return result

    def _desired_state_leaked_node_detection(self, differences, not_found,
                                             state):
        """Leaked node detection for desired state

        Resource present in the ADD section of 'differences' is not
        found in desired state; Solve by removing such node from hashtree,
        """
        if not_found:
            modified = set()
            LOG.warn("Objects with keys %s are leaking in %s state. Removing "
                     "from hashtree." % (not_found, self.name))
            for res in not_found:
                root = self.tt_maker.resource_to_root(res)
                self.tt_maker.delete(state[root], [res])
                modified.add(root)
            for root in modified:
                self.replace_state(root, state[root])
            # TODO(ivar): should we fire a reconcile event?
            return modified

    def _desired_state_missing_node_detection(self, differences, not_found,
                                              state):
        """Missing node detection for desired state

        No way to detect this with the current info.
        """

    def _current_state_leaked_node_detection(self, differences, not_found,
                                             state):
        """Leaked node detection for current state

        Same item is being deleted multiple times for the same tree
        version; Solve by removing node if not found in current state.
        """
        divergent_items = self._get_resources_consecutive_actions(
            state, DELETE, self.max_consecutive_operations)
        modified = set()
        for root, objects in divergent_items.iteritems():
            if objects:
                LOG.warn("Objects %s have reached the limit of consecutive "
                         "DELETE tries on %s, removing them from the "
                         "hashtree" % (objects, self.name))
                self.tt_maker.delete(state[root], objects)
                modified.add(root)
                for object in objects:
                    # Mark deletion failed if possible
                    self.deletion_failed(
                        object, reason='Reached the limit of consecutive '
                                       'DELETE retries',
                        error=errors.OPERATION_CRITICAL)
        for root in modified:
            self.replace_state(root, state[root])
        return modified

    def _current_state_missing_node_detection(self, differences, not_found,
                                              state, other_state,
                                              other_universe):
        """Missing node detection for current state

        Same item is being created multiple times for the same tree version;
        Solve by removing the object from the other universe's tree and place
        the item in error state.
        """
        divergent_items = self._get_resources_consecutive_actions(
            state, CREATE, self.max_consecutive_operations)
        modified = set()
        for root, objects in divergent_items.iteritems():
            if objects:
                LOG.warn("Objects %s have reached the limit of consecutive "
                         "CREATE tries on %s, removing them from the "
                         "desired state hashtree in "
                         "%s" % (objects, self.name, other_universe.name))
                self.tt_maker.delete(other_state[root], objects)
                modified.add(root)
        for root in modified:
            other_universe.replace_state(root, other_state[root])
        # Do this after the tree replace or it will change the version
        for root, objects in divergent_items.iteritems():
            for object in objects:
                # Mark deletion failed if possible
                other_universe.creation_failed(
                    object, reason='Reached the limit of consecutive '
                                   'DELETE retries',
                    error=errors.OPERATION_CRITICAL)
        return modified

    def replace_state(self, root, tree):
        pass

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
