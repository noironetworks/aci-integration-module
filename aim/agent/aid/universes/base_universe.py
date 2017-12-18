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

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes import errors
from aim import aim_manager
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim import context
from aim import tree_manager


LOG = logging.getLogger(__name__)
CREATE = 'create'
DELETE = 'delete'
CONFIG_UNIVERSE = 0
OPER_UNIVERSE = 1
MONITOR_UNIVERSE = 2
ACTION_RESET = 'reset'
ACTION_PURGE = 'purge'


def fix_session_if_needed(func):
    def wrap(inst, *args, **kwargs):
        try:
            return func(inst, *args, **kwargs)
        except Exception as e:
            inst.context.store.fix_session(e)
            raise e
    return wrap


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
    def initialize(self, store, conf_mgr, multiverse):
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
    def cleanup_state(self, key):
        """Cleanup state entry

        :param key: tenant id
        :return:
        """

    @abc.abstractmethod
    def vote_deletion_candidates(self, other_universe, delete_candidates,
                                 vetoes):
        """Vote deletion candidates

        Decide whether the cleanup process should be initiated for a specific
        candidate.

        :param other_universe
        :param delete_candidates: set that each universe can use to
               vote for tenant deletion.
        :param
        :return:
        """

    @abc.abstractmethod
    def finalize_deletion_candidates(self, other_universe, delete_candidates):
        """Finalize deletion candidates

        After one reconciliation cycle, decide whether the tenant should be
        completely deleted. Universes can only *remove* candidates at this
        point from the list.

        :param other_universe:
        :param delete_candidates:
        :return:
        """

    @abc.abstractmethod
    def update_status_objects(self, my_state, other_universe, other_state,
                              raw_diff, transformed_diff, skip_roots=None):
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

    def initialize(self, store, conf_mgr, multiverse):
        super(HashTreeStoredUniverse, self).initialize(
            store, conf_mgr, multiverse)
        self.multiverse = multiverse
        self.context = context.AimContext(store=store)
        self.manager = aim_manager.AimManager()
        self.conf_manager = conf_mgr
        self._state = {}
        self.failure_log = {}
        self.max_create_retry = self.conf_manager.get_option(
            'max_operation_retry', 'aim')
        # Don't increase retry value if at least retry_cooldown seconds have
        # passed
        self.retry_cooldown = self.conf_manager.get_option(
            'retry_cooldown', 'aim')
        self.reset_retry_limit = 2 * self.max_create_retry
        self.purge_retry_limit = 2 * self.reset_retry_limit
        self.error_handlers = {
            errors.OPERATION_TRANSIENT: self._retry_until_max,
            errors.UNKNOWN: self._retry_until_max,
            errors.OPERATION_CRITICAL: self._surrender_operation,
            errors.SYSTEM_CRITICAL: self._fail_agent,
        }
        self._action_cache = {}
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

    def observe(self):
        pass

    def reconcile(self, other_universe, delete_candidates):
        return self._reconcile(other_universe, delete_candidates)

    def vote_deletion_candidates(self, other_universe, delete_candidates,
                                 vetoes):
        pass

    def finalize_deletion_candidates(self, other_universe, delete_candidates):
        pass

    def _reconcile(self, other_universe, delete_candidates):
        # "self" is always the current state, "other" the desired
        my_state = self.state
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

        if not differences.get(CREATE) and not differences.get(DELETE):
            diff = False
        else:
            LOG.info("Universe differences between %s and %s: %s",
                     self.name, other_universe.name, differences)
            diff = True

        # Get AIM resources at the end to reduce the number of transactions
        result = {CREATE: other_universe.get_resources(differences[CREATE]),
                  DELETE: self.get_resources_for_delete(differences[DELETE])}

        reset, purge = self._track_universe_actions(result)
        LOG.debug('Action cache for %s: %s' % (self.name, self._action_cache))
        # Schedule root reset
        if reset:
            self.reset(reset)
            other_universe.reset(reset)
        stop_sync = set()
        for action, res in purge:
            # It's no use to set error state for resetting roots
            if res.root not in reset:
                if action == CREATE:
                    self.creation_failed(
                        res, reason='Divergence detected on this object.',
                        error=errors.OPERATION_CRITICAL)
                if action == DELETE:
                    self.deletion_failed(
                        res, reason='Divergence detected on this object.',
                        error=errors.OPERATION_CRITICAL)
                stop_sync.add(res.root)
        # Don't synchronize resetting roots or purge objects
        stop_sync |= reset
        if stop_sync:
            for method in CREATE, DELETE:
                differences[method] = [
                    x for x in differences[method] if
                    tree_manager.AimHashTreeMaker._extract_root_rn(x)
                    not in stop_sync]
                result[method] = [
                    x for x in result[method] if
                    self._get_resource_root(method, x) not in stop_sync]

        # Set status objects properly
        self.update_status_objects(my_state, other_universe, other_state,
                                   differences, result, skip_roots=stop_sync)
        other_universe.update_status_objects(other_state, self, my_state,
                                             differences, result,
                                             skip_roots=stop_sync)
        # Reconciliation method for pushing changes
        self.push_resources(result)
        return diff

    def reset(self, tenants):
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
                aci_object.values()[0]['attributes'].update(attr)
                dn = aci_object.values()[0]['attributes']['dn']
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

    def serve(self, tenants):
        pass

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
        return self.error_handlers.get(error, self._noop)(
            aim_object, operation, reason)

    @fix_session_if_needed
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

    @fix_session_if_needed
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

    def _noop(self, *args, **kwargs):
        return

    def _convert_get_resources_result(self, result, monitored_set):
        return result

    def _track_universe_actions(self, actions):
        """Track Universe Actions.

        Keep track of what the universe has been doing in the past few
        iterations. Keeping count of any operation repeated over time and
        decreasing count of actions that are not happening in this iteration.
        :param actions: dictionary in the form {'create': [..], 'delete': [..]}
        :return:
        """
        cache = {}
        curr_time = time.time()
        reset = set()
        purge = []
        for action in [CREATE, DELETE]:
            for res in self._action_items_to_aim_resources(actions, action):
                # Same resource created twice in the same iteration is
                # increased only once
                root = res.root
                new = (cache.setdefault(action, {}).
                       setdefault(root, {}).
                       setdefault(res.hash, {'limit': self.reset_retry_limit,
                                             'res': res, 'retries': 0,
                                             'action': ACTION_RESET,
                                             'last': curr_time}))
                # Retrieve current object situation if any
                curr = self._action_cache.get(action, {}).get(root, {}).get(
                    res.hash, {})
                if curr:
                    new.update(curr)
                    if curr_time - curr['last'] >= self.retry_cooldown:
                        new['retries'] += 1
                        new['last'] = curr_time
                if new['retries'] > new['limit']:
                    if new['action'] == ACTION_RESET:
                        reset.add(root)
                        new['limit'] = self.purge_retry_limit
                        new['action'] = ACTION_PURGE
                    else:
                        new['limit'] += 5
                        purge.append((action, res))
        self._action_cache = cache
        return reset, purge

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
