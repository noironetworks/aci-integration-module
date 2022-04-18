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
from six.moves import queue as Queue
import time
import traceback

from acitoolkit import acitoolkit
from apicapi import apic_client
from apicapi import exceptions as apic_exc
from oslo_log import log as logging

from aim.agent.aid import event_handler
from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes.aci import error
from aim.agent.aid.universes import base_universe
from aim.agent.aid.universes import constants as lcon
from aim.common.hashtree import structured_tree
from aim.common import utils
from aim import tree_manager

LOG = logging.getLogger(__name__)
TENANT_KEY = 'fvTenant'
FAULT_KEY = 'faultInst'
TAG_KEY = 'tagInst'
STATUS_FIELD = 'status'
SEVERITY_FIELD = 'severity'
CHILDREN_FIELD = 'children'
CHILDREN_LIST = set(list(converter.resource_map.keys()) + ['fvTenant',
                                                           'tagInst'])
# TODO(ivar): get right children from APICAPI client
TOPOLOGY_CHILDREN_LIST = ['fabricPod', 'opflexODev', 'fabricTopology']
CHILDREN_MOS_UNI = None
CHILDREN_MOS_TOPOLOGY = None
SUPPORTS_ANNOTATIONS = None
RESET_INTERVAL = 3600
DEFAULT_WS_TO = '60'
BASELINE_WS_TO = '900'


class ScheduledReset(Exception):
    pass


def get_children_mos(apic_session, root):
    root_type = 'uni'
    try:
        root_type = apic_client.DNManager().get_rn_base(root)
    except KeyError:
        pass
    global CHILDREN_MOS_UNI
    global CHILDREN_MOS_TOPOLOGY
    if root_type in ['uni']:
        if CHILDREN_MOS_UNI is None:
            CHILDREN_MOS_UNI = set()
            for mo in CHILDREN_LIST:
                if mo in apic_client.ManagedObjectClass.supported_mos:
                    mo_name = apic_client.ManagedObjectClass(mo).klass_name
                else:
                    mo_name = mo
                try:
                    # Verify class support
                    apic_session.GET('/mo/uni/tn-common.json?'
                                     'target-subtree-class=%s' % mo_name)
                except apic_exc.ApicResponseNotOk as e:
                    if int(e.err_status) == 400 and int(e.err_code) == 12:
                        continue
                    raise e
                CHILDREN_MOS_UNI.add(mo_name)
        return CHILDREN_MOS_UNI
    elif root_type in ['topology']:
        if CHILDREN_MOS_TOPOLOGY is None:
            CHILDREN_MOS_TOPOLOGY = set()
            for mo in TOPOLOGY_CHILDREN_LIST:
                if mo in apic_client.ManagedObjectClass.supported_mos:
                    mo_name = apic_client.ManagedObjectClass(mo).klass_name
                else:
                    mo_name = mo
                try:
                    apic_session.GET('/node/class/%s.json?' % mo_name)
                except apic_exc.ApicResponseNotOk as e:
                    if int(e.err_status) == 400 and int(e.err_code) == 12:
                        continue
                    raise e
                CHILDREN_MOS_TOPOLOGY.add(mo_name)
        return CHILDREN_MOS_TOPOLOGY


def supports_annotations(apic_session):
    global SUPPORTS_ANNOTATIONS
    if SUPPORTS_ANNOTATIONS is None:
        tn = apic_session.GET('/mo/uni/tn-common.json')
        SUPPORTS_ANNOTATIONS = 'annotation' in tn[0]['fvTenant']['attributes']
    return SUPPORTS_ANNOTATIONS


OPERATIONAL_LIST = [FAULT_KEY]
TENANT_FAILURE_MAX_WAIT = 60
ACI_TYPES_NOT_CONVERT_IF_MONITOR = {}
ACI_TYPES_SKIP_ON_MANAGES = {}
for typ in converter.resource_map:
    if "__" not in typ:
        for resource in converter.resource_map[typ]:
            if resource.get('convert_monitored') is False:
                ACI_TYPES_NOT_CONVERT_IF_MONITOR.setdefault(
                    typ, []).append(resource['resource']._aci_mo_name)
            if resource.get('skip_for_managed') is True:
                ACI_TYPES_SKIP_ON_MANAGES.setdefault(
                    typ, []).append(resource['resource']._aci_mo_name)


class Root(acitoolkit.BaseACIObject):

    def __init__(self, *args, **kwargs):
        self.filtered_children = kwargs.pop('filtered_children', [])
        rn = kwargs.pop('rn')
        ws_subscription_to = kwargs.pop('ws_subscription_to')
        super(Root, self).__init__(*args, **kwargs)
        try:
            rn_base = apic_client.DNManager().get_rn_base(rn)
            if rn.startswith(rn_base):
                self.dn = rn
            else:
                self.dn = rn_base + '/' + rn
        except KeyError:
            self.dn = apic_client.DN_BASE + 'rn'
        self.type = apic_client.ManagedObjectClass.prefix_to_mos[
            rn.split('-')[0]]
        self.urls = self._get_instance_subscription_urls(
            ws_subscription_to=ws_subscription_to)

    def _get_instance_subscription_urls(self,
                                        ws_subscription_to=BASELINE_WS_TO):
        if not self.dn.startswith('topology'):
            url = ('/api/node/mo/{}.json?query-target=subtree&'
                   'rsp-prop-include=config-only&rsp-subtree-include=faults&'
                   'subscription=yes'.format(self.dn))
            if ws_subscription_to != '0':
                url += '&refresh-timeout={}'.format(ws_subscription_to)
            # TODO(amitbose) temporary workaround for ACI bug,
            # remove when ACI is fixed
            url = url.replace('&rsp-prop-include=config-only', '')
            # End work-around
            if self.filtered_children:
                url += '&target-subtree-class=' + ','.join(
                    self.filtered_children)
            return [url]
        else:
            urls = []
            for child in self.filtered_children:
                url = ('/api/node/class/{}.json?subscription=yes&'
                       'rsp-subtree-include=faults'.format(child))
                if ws_subscription_to != '0':
                    url += '&refresh-timeout={}'.format(ws_subscription_to)
                urls.append(url)
            return urls


class OwnershipManager(object):

    def __init__(self, apic_session, apic_config, aim_system_id):
        self.use_annotation = supports_annotations(apic_session)
        self.aim_system_id = aim_system_id or apic_config.get_option(
            'aim_system_id', 'aim')
        if self.use_annotation:
            self.annotation_key = apic_config.get_option(
                'annotation_prefix', 'aim') + self.aim_system_id
        self.tag_key = self.aim_system_id
        self.owned_by_tag = set()
        self.owned_by_annotation = set()
        self.failure_log = {}

    @property
    def owned_set(self):
        return self.owned_by_tag | self.owned_by_annotation

    def set_ownership_key(self, to_push):
        """Set ownership key

        When pushing objects to APIC, push annotations when supported, TAG
        only otherwise.
        :param to_push:
        :return:
        """
        result = to_push
        if self.use_annotation:
            for obj in to_push:
                list(obj.values())[0]['attributes']['annotation'] = (
                    self.annotation_key)
        else:
            tags = []
            for obj in to_push:
                if not list(obj.keys())[0].startswith(TAG_KEY):
                    dn = list(obj.values())[0]['attributes']['dn']
                    dn += '/tag-%s' % self.tag_key
                    tags.append({"%s__%s" % (TAG_KEY, list(obj.keys())[0]):
                                 {"attributes": {"dn": dn}}})
            result.extend(tags)
        return result

    def set_ownership_change(self, to_push):
        to_update = []
        if self.use_annotation:
            for obj in to_push:
                if list(obj.keys())[0].startswith(TAG_KEY):
                    dn = list(obj.values())[0]['attributes']['dn']
                    if dn.endswith('/tag-%s' % self.tag_key):
                        dec = apic_client.DNManager().aci_decompose_dn_guess(
                            dn, list(obj.keys())[0])
                        parent_dec = dec[1][:-1]
                        parent_dn = apic_client.DNManager().build(parent_dec)
                        parent_type = parent_dec[-1][0]
                        to_update.append(
                            {parent_type: {'attributes': {'dn': parent_dn,
                                                          'annotation': ''}}})
        return to_push, to_update

    def filter_ownership(self, events):
        managed = []
        if self.use_annotation:
            for event in events:
                attrs = list(event.values())[0]['attributes']
                if AciTenantManager.is_deleting(event):
                    self.owned_by_annotation.discard(attrs['dn'])
                elif attrs.get('annotation') == self.annotation_key:
                    self.owned_by_annotation.add(attrs['dn'])
                elif 'annotation' in attrs:
                    # Has a different annotation
                    self.owned_by_annotation.discard(attrs['dn'])
                if list(event.keys())[0] != TAG_KEY:
                    managed.append(event)
        # Tags might still be in the system, use them with annotations to
        # discern ownership
        for event in events:
            if list(event.keys())[0] == TAG_KEY:
                decomposed = list(event.values())[0][
                    'attributes']['dn'].split('/')
                if decomposed[-1] == 'tag-' + self.tag_key:
                    parent_dn = '/'.join(decomposed[:-1])
                    if AciTenantManager.is_deleting(event):
                        self.owned_by_tag.discard(parent_dn)
                    else:
                        self.owned_by_tag.add(parent_dn)
            else:
                managed.append(event)
        for event in managed:
            if AciTenantManager.is_deleting(event):
                self.owned_by_tag.discard(
                    list(event.values())[0]['attributes']['dn'])
        return managed

    def is_owned(self, aci_object, check_parent=True):
        # An RS whose parent is owned is an owned object.
        dn = list(aci_object.values())[0]['attributes']['dn']
        type = list(aci_object.keys())[0]
        if type in apic_client.MULTI_PARENT:
            decomposed = dn.split('/')
            # Check for parent ownership
            return self.is_owned_dn('/'.join(decomposed[:-1]))
        else:
            owned = self.is_owned_dn(dn)
            if not owned and AciTenantManager.is_child_object(
                    type) and check_parent:
                # Check for parent ownership
                try:
                    decomposed = (
                        apic_client.DNManager().aci_decompose_dn_guess(
                            dn, type))
                except apic_client.DNManager.InvalidNameFormat:
                    LOG.debug("Type %s with DN %s is not supported." %
                              (type, dn))
                    return False
                # Check for parent ownership
                return self.is_owned_dn(apic_client.DNManager().build(
                    decomposed[1][:-1]))
            else:
                return owned

    def is_owned_dn(self, dn):
        return (dn in self.owned_by_annotation) or (dn in self.owned_by_tag)

    def reset_ownership(self):
        self.owned_by_annotation = set()
        self.owned_by_tag = set()


class AciTenantManager(utils.AIMThread):

    def __init__(self, tenant_name, apic_config, apic_session, ws_context,
                 creation_succeeded=None, creation_failed=None,
                 aim_system_id=None, get_resources=None, *args, **kwargs):
        super(AciTenantManager, self).__init__(*args, **kwargs)
        LOG.info("Init manager for tenant %s" % tenant_name)
        self.get_resources = get_resources
        self.apic_config = apic_config
        # Each tenant has its own sessions
        self.aci_session = apic_session
        self.dn_manager = apic_client.DNManager()
        self.tenant_name = tenant_name
        children_mos = get_children_mos(self.aci_session, self.tenant_name)
        ws_subscription_to = self.apic_config.get_option(
            'websocket_subscription_timeout', 'aim') or BASELINE_WS_TO
        if int(ws_subscription_to) < int(DEFAULT_WS_TO):
            ws_subscription_to = DEFAULT_WS_TO
        self.ws_subscription_to = ws_subscription_to
        self.tenant = Root(self.tenant_name, filtered_children=children_mos,
                           rn=self.tenant_name,
                           ws_subscription_to=self.ws_subscription_to)
        self._state = structured_tree.StructuredHashTree()
        self._operational_state = structured_tree.StructuredHashTree()
        self._monitored_state = structured_tree.StructuredHashTree()
        self.polling_yield = self.apic_config.get_option(
            'aci_tenant_polling_yield', 'aim')
        self.to_aim_converter = converter.AciToAimModelConverter()
        self.to_aci_converter = converter.AimToAciModelConverter()
        self._reset_object_backlog()
        self.tree_builder = tree_manager.HashTreeBuilder(None)
        self.failure_log = {}

        def noop(*args, **kwargs):
            pass
        self.creation_succeeded = creation_succeeded or noop
        self.creation_failed = creation_failed or noop
        # Warm bit to avoid rushed synchronization before receiving the first
        # batch of APIC events
        self._warm = False
        self.ws_context = ws_context
        self.recovery_retries = None
        self.max_retries = 5
        self.error_handler = error.APICAPIErrorHandler()
        # For testing purposes
        self.num_loop_runs = float('inf')
        self.ownership_mgr = OwnershipManager(apic_session, apic_config,
                                              aim_system_id)
        # Initialize tenant tree

    def _reset_object_backlog(self):
        self.object_backlog = Queue.Queue()

    def kill(self, *args, **kwargs):
        try:
            self._unsubscribe_tenant(kill=True)
        except Exception as e:
            LOG.warn("Failed to unsubscribe tenant during kill "
                     "procedure: %s %s" % (self.tenant_name, str(e)))
        finally:
            super(AciTenantManager, self).kill(*args, **kwargs)

    def is_dead(self):
        # Wrapping the greenlet property for easier testing
        return self.dead

    def is_warm(self):
        return self._warm

    def get_state_copy(self):
        return structured_tree.StructuredHashTree.from_string(
            str(self._state), root_key=self._state.root_key,
            has_populated=self._state.has_populated)

    def get_operational_state_copy(self):
        return structured_tree.StructuredHashTree.from_string(
            str(self._operational_state),
            root_key=self._operational_state.root_key)

    def get_monitored_state_copy(self):
        return structured_tree.StructuredHashTree.from_string(
            str(self._monitored_state),
            root_key=self._monitored_state.root_key)

    def run(self):
        LOG.debug("Starting main loop for tenant %s" % self.tenant_name)
        try:
            while not self._stop:
                self._main_loop()
        except Exception as e:
            LOG.error(traceback.format_exc())
            LOG.error("Exiting thread for tenant %s: %s" %
                      (self.tenant_name, str(e)))
            try:
                self._unsubscribe_tenant()
            except Exception as e:
                LOG.error("An exception has occurred while exiting thread "
                          "for tenant %s: %s" % (self.tenant_name,
                                                 str(e)))
            finally:
                # We need to make sure that this thread dies upon
                # GreenletExit
                return

    def _main_loop(self):
        try:
            # tenant subscription is redone upon exception
            self._subscribe_tenant()
            LOG.debug("Starting event loop for tenant %s" % self.tenant_name)
            last_time = 0
            epsilon = 0.5
            while not self._stop and self.num_loop_runs > 0:
                start = time.time()
                if start > self.scheduled_reset:
                    raise ScheduledReset()
                if start > self.refresh_time:
                    self.ws_context.refresh_subscriptions(
                        urls=self.tenant.urls)
                    self.refresh_time = self._schedule_websocket_refresh()
                self._event_loop()
                curr_time = time.time() - start
                if abs(curr_time - last_time) > epsilon:
                    # Only log significant differences
                    LOG.debug("Event loop for tenant %s completed in %s "
                              "seconds" % (self.tenant_name,
                                           time.time() - start))
                    last_time = curr_time
                if not last_time:
                    last_time = curr_time
                # Successfull run
                self.num_loop_runs -= 1
                self.recovery_retries = None
        except ScheduledReset:
            LOG.info("Scheduled tree reset for root %s" % self.tenant_name)
            try:
                self._unsubscribe_tenant()
            except Exception:
                pass
        except Exception as e:
            LOG.error("An exception has occurred in thread serving tenant "
                      "%s, error: %s" % (self.tenant_name, str(e)))
            LOG.error(traceback.format_exc())
            try:
                self._unsubscribe_tenant()
            except Exception:
                pass
            self.recovery_retries = utils.exponential_backoff(
                TENANT_FAILURE_MAX_WAIT, tentative=self.recovery_retries)
            if self.recovery_retries.get() >= self.max_retries:
                LOG.error("Exceeded max recovery retries for tenant %s. "
                          "Destroying the manager." %
                          self.tenant_name)
                self.kill()

    def _event_loop(self):
        start_time = time.time()
        # Push the backlog at right before the event loop, so that
        # all the events we generate here are likely caught in this
        # iteration.
        self._push_aim_resources()
        if self.ws_context.has_event(self.tenant.urls):
            with utils.get_rlock(lcon.ACI_TREE_LOCK_NAME_PREFIX +
                                 self.tenant_name):
                events = self.ws_context.get_event_data(self.tenant.urls)
                for event in events:
                    # REVISIT(ivar): remove vmmDomP once websocket ACI bug is
                    # fixed
                    if (list(event.keys())[0] in [self.tenant.type,
                                                  'vmmDomP'] and not
                            event[list(event.keys())[0]]['attributes'].get(
                                STATUS_FIELD)):
                        LOG.info("Resetting Tree %s" % self.tenant_name)
                        # REVISIT(ivar): on subscription to VMMPolicy objects,
                        # aci doesn't return the root object itself because of
                        # a bug. Let's craft a fake root to work around this
                        # problem
                        if self.tenant_name.startswith('vmmp-'):
                            LOG.debug('Faking vmmProvP %s' % self.tenant_name)
                            events.append({'vmmProvP': {
                                'attributes': {'dn': self.tenant.dn}}})
                        # This is a full resync, trees need to be reset
                        self._state = structured_tree.StructuredHashTree()
                        self._operational_state = (
                            structured_tree.StructuredHashTree())
                        self._monitored_state = (
                            structured_tree.StructuredHashTree())
                        self.tag_set = set()
                        break
                # REVISIT(ivar): there's already a debug log in acitoolkit
                # listing all the events received one by one. The following
                # would be more compact, we need to choose which to keep.
                # LOG.debug("received events for root %s: %s" %
                #           (self.tenant_name, events))
                # Make events list flat
                self.flat_events(events)
                # Pull incomplete objects
                events = self._fill_events(events)
                # Manage Tags
                events = self.ownership_mgr.filter_ownership(events)
                self._event_to_tree(events)
        time.sleep(max(0, self.polling_yield - (time.time() - start_time)))

    def push_aim_resources(self, resources):
        """Given a map of AIM resources for this tenant, push them into APIC

        Stash the objects to be eventually pushed. Given the nature of the
        system we don't really care if we lose one or two messages, or
        even all of them, or if we mess the order, or get involved in
        a catastrophic meteor impact, we should always be able to get
        back in sync.

        :param resources: a dictionary with "create" and "delete" resources
        :return:
        """
        try:
            with utils.get_rlock(lcon.ACI_BACKLOG_LOCK_NAME_PREFIX +
                                 self.tenant_name, blocking=False):
                backlock = Queue.Queue()
                while not self.object_backlog.empty():
                    requests = self.object_backlog.get()
                    # check if there's an event to squash
                    for op in ['create', 'delete']:
                        for i, req in enumerate(requests.get(op, [])):
                            for j, new in enumerate(resources.get(op, [])):
                                if op is 'create':
                                    req_dn = req.dn
                                    new_dn = new.dn
                                else:
                                    # Delete items are in ACI format
                                    req_dn = list(req.values())[0][
                                        'attributes']['dn']
                                    new_dn = list(new.values())[0][
                                        'attributes']['dn']
                                if req_dn == new_dn:
                                    # Replace old with new
                                    requests[op][i] = new
                                    break
                            else:
                                # No colliding item found
                                continue
                            # new can be removed from resources
                            resources[op].pop(j)
                    backlock.put(requests)
                if any(resources.values()):
                    backlock.put(resources)
                self.object_backlog = backlock
        except utils.LockNotAcquired:
            # If changes need to be pushed, AID will do it on the next
            # iteration
            pass

    def _post_with_transaction(self, to_push, modified=False):
        if not to_push:
            return
        dn_mgr = apic_client.DNManager()
        decompose = dn_mgr.aci_decompose_dn_guess
        with self.aci_session.transaction(
                top_send=True) as trs:
            for obj in to_push:
                attr = list(obj.values())[0]['attributes']
                if modified:
                    attr['status'] = converter.MODIFIED_STATUS
                mo, parents_rns = decompose(
                    attr.pop('dn'), list(obj.keys())[0])
                rns = dn_mgr.filter_rns(parents_rns)
                getattr(self.aci_session, mo).create(*rns, transaction=trs,
                                                     **attr)

    def _push_aim_resources(self):
        dn_mgr = apic_client.DNManager()
        decompose = dn_mgr.aci_decompose_dn_guess
        with utils.get_rlock(lcon.ACI_BACKLOG_LOCK_NAME_PREFIX +
                             self.tenant_name):
            while not self.object_backlog.empty():
                request = self.object_backlog.get()
                for method, aim_objects in list(request.items()):
                    # Method will be either "create" or "delete"
                    # sort the aim_objects based on DN first for DELETE method
                    sorted_aim_objs = aim_objects
                    if method == base_universe.DELETE:
                        sorted_aim_objs = sorted(
                            aim_objects,
                            key=lambda x: list(
                                x.values())[0]['attributes']['dn'])
                    potential_parent_dn = ' '
                    for aim_object in sorted_aim_objs:
                        # get MO from ACI client, identify it via its DN parts
                        # and push the new body
                        if method == base_universe.DELETE:
                            # If a parent is also being deleted then we don't
                            # have to send those children requests to APIC
                            dn = list(aim_object.values())[
                                0]['attributes']['dn']
                            res_type = list(aim_object.keys())[0]
                            decomposed = decompose(dn, res_type)
                            parent_dn = dn_mgr.build(decomposed[1][:-1])
                            if parent_dn.startswith(potential_parent_dn):
                                continue
                            else:
                                potential_parent_dn = dn
                            to_push = [copy.deepcopy(aim_object)]
                        else:
                            if getattr(aim_object, 'monitored', False):
                                # When pushing to APIC, treat monitored
                                # objects as pre-existing
                                aim_object.monitored = False
                                aim_object.pre_existing = True
                            to_push = self.to_aci_converter.convert(
                                [aim_object])
                        LOG.debug('%s AIM object %s in APIC' % (
                                  method, repr(aim_object)))
                        try:
                            if method == base_universe.CREATE:
                                # Set ownership before pushing the request
                                to_push = self.ownership_mgr.set_ownership_key(
                                    to_push)
                                LOG.debug("POSTING into APIC: %s" % to_push)
                                self._post_with_transaction(to_push)
                                self.creation_succeeded(aim_object)
                            else:
                                to_delete, to_update = (
                                    self.ownership_mgr.set_ownership_change(
                                        to_push))
                                LOG.debug("DELETING from APIC: %s" % to_delete)
                                for obj in to_delete:
                                    attr = list(obj.values())[0]['attributes']
                                    self.aci_session.DELETE(
                                        '/mo/%s.json' % attr.pop('dn'))
                                LOG.debug("UPDATING in APIC: %s" % to_update)
                                # Update object ownership
                                self._post_with_transaction(to_update,
                                                            modified=True)
                                if to_update:
                                    self.creation_succeeded(aim_object)
                        except Exception as e:
                            LOG.debug(traceback.format_exc())
                            LOG.error("An error has occurred during %s for "
                                      "object %s: %s" % (method, aim_object,
                                                         str(e)))
                            if method == base_universe.CREATE:
                                err_type = (
                                    self.error_handler.analyze_exception(e))
                                # REVISIT(ivar): for now, treat UNKNOWN errors
                                # the same way as OPERATION_TRANSIENT.
                                # Investigate a way to understand when such
                                # errors might require agent restart.
                                self.creation_failed(aim_object, str(e),
                                                     err_type)

    def _unsubscribe_tenant(self, kill=False):
        LOG.info("Unsubscribing tenant websocket %s" % self.tenant_name)
        self._warm = False
        urls = self.tenant.urls
        if kill:
            # Make sure this thread cannot use websocket anymore
            self.tenant.urls = self.ws_context.EMPTY_URLS
        self.ws_context.unsubscribe(urls)
        self._reset_object_backlog()

    def _subscribe_tenant(self):
        self.ws_context.subscribe(self.tenant.urls)
        self.scheduled_reset = utils.schedule_next_event(RESET_INTERVAL, 0.2)
        self._event_loop()
        self._warm = True
        self.refresh_time = self._schedule_websocket_refresh()

    def _schedule_websocket_refresh(self):
        return utils.get_time() + int(self.ws_subscription_to) / 2

    def _event_to_tree(self, events):
        """Parse the event and push it into the tree

        This method requires translation between ACI and AIM model in order
        to  honor the Universe contract.
        :param events: an ACI event in the form of a list of objects
        :return:
        """
        removed, updated = [], []
        removing_dns = set()
        filtered_events = []
        # Set the owned events
        for event in events:
            # Exclude some events from monitored objects.
            # Some RS objects can be set from AIM even for monitored
            # objects, therefore we need to exclude events regarding those
            # RS objects when we don't own them. One example is fvRsProv on
            # external networks
            type = list(event.keys())[0]
            if type in ACI_TYPES_NOT_CONVERT_IF_MONITOR:
                # Check that the object is indeed correct looking at the
                # parent
                if self._check_parent_type(
                        event,
                        ACI_TYPES_NOT_CONVERT_IF_MONITOR[type]):
                    if not self.ownership_mgr.is_owned(event):
                        # For an RS object like fvRsProv we check the
                        # parent ownership as well.
                        continue
            # Exclude from conversion those list RS objects that we want
            # allow to be manually configured in ACI
            if type in ACI_TYPES_SKIP_ON_MANAGES:
                if self._check_parent_type(
                        event, ACI_TYPES_SKIP_ON_MANAGES[type]):
                    # Check whether the event is owned, and whether its
                    # parent is.
                    if (not self.ownership_mgr.is_owned(
                            event, check_parent=False) and
                            self.ownership_mgr.is_owned(event)):
                        continue
            if self.is_child_object(type) and self.is_deleting(event):
                # Can be excluded, we expect parent objects
                continue

            if self.is_deleting(event):
                dn = list(event.values())[0]['attributes']['dn']
                removing_dns.add(dn)
            filtered_events.append(event)
        for event in self.to_aim_converter.convert(filtered_events):
            if not self.ownership_mgr.is_owned_dn(event.dn):
                event.monitored = True
            if event.dn in removing_dns:
                LOG.info('ACI event: REMOVED %s' % event)
                removed.append(event)
            else:
                LOG.info('ACI event: ADDED %s' % event)
                updated.append(event)
        upd_trees, upd_op_trees, upd_mon_trees = self.tree_builder.build(
            [], updated, removed,
            {self.tree_builder.CONFIG: {self.tenant_name: self._state},
             self.tree_builder.MONITOR:
                 {self.tenant_name: self._monitored_state},
             self.tree_builder.OPER:
                 {self.tenant_name: self._operational_state}})

        # Send events on update
        modified = False
        for upd, tree, readable in [
                (upd_trees, self._state, "configuration"),
                (upd_op_trees, self._operational_state, "operational"),
                (upd_mon_trees, self._monitored_state, "monitored")]:
            if upd:
                modified = True
                LOG.debug("New %s tree for tenant %s: %s" %
                          (readable, self.tenant_name, tree))
        if modified:
            event_handler.EventHandler.reconcile()

    def _fill_events(self, events):
        """Gets incomplete objects from APIC if needed

        - Objects with no status field are already completed
        - Objects with status "created" are already completed
        - Objects with status "deleted" do not exist on APIC anymore
        - Objects with status "modified" need to be retrieved fully via REST

        Whenever an object is missing on retrieval, status will be set to
        "deleted".
        Some objects might be incomplete without their RSs, this method
        will take care of retrieving them.
        :param events: List of events to retrieve
        :return:
        """
        result = self.retrieve_aci_objects(events)
        return result

    def _get_full_state(self):
        return [{self.tenant_name: x} for x in
                [self._state, self._monitored_state, self._operational_state]]

    def retrieve_aci_objects(self, events):
        result = {}

        for event in events:
            resource = list(event.values())[0]
            res_type = list(event.keys())[0]
            status = (resource['attributes'].get(STATUS_FIELD) or '').lower()
            raw_dn = resource['attributes'].get('dn')
            if self.is_child_object(res_type) and res_type != FAULT_KEY:
                # We need to make sure to retrieve the parent object as well
                try:
                    decomposed = (
                        apic_client.DNManager().aci_decompose_dn_guess(
                            raw_dn, res_type))
                    parent_dn = apic_client.DNManager().build(
                        decomposed[1][:-1])
                    if parent_dn not in result:
                        events.append(
                            {decomposed[1][-2][0]:
                             {'attributes': {
                                 'dn': parent_dn,
                                 'status': converter.MODIFIED_STATUS,
                                 '_avoid_print_not_found': True}}})
                except (apic_client.DNManager.InvalidNameFormat, KeyError):
                    LOG.debug("Object with DN %s is not supported." % raw_dn)
                    continue
            if res_type == FAULT_KEY:
                # Make sure we support the parent object
                try:
                    apic_client.DNManager().aci_decompose_dn_guess(raw_dn,
                                                                   res_type)
                    utils.retrieve_fault_parent(raw_dn, converter.resource_map)
                except (apic_client.DNManager.InvalidNameFormat, KeyError):
                    LOG.debug("Fault with DN %s is not supported." % raw_dn)
                    continue
            if res_type == TAG_KEY:
                # Add to the result and go ahead to the next object
                result[raw_dn] = event
                continue
            if status == converter.DELETED_STATUS:
                # Add to the result but keep evaluating
                result[raw_dn] = event
            if status == converter.MODIFIED_STATUS:
                event_attrs = copy.deepcopy(list(
                    event.values())[0]['attributes'])
                event_attrs.pop(STATUS_FIELD)
                apnf = event_attrs.pop('_avoid_print_not_found', False)
                if raw_dn in result:
                    # Update with changes
                    list(result[raw_dn].values())[0]['attributes'].update(
                        event_attrs)
                key = tree_manager.AimHashTreeMaker._dn_to_key(res_type,
                                                               raw_dn)
                data = []
                if key:
                    # Search within the TenantManager state, which is the most
                    # up to date.
                    data = self.get_resources(
                        [key], desired_state=self._get_full_state())
                if not data and not apnf:
                    LOG.debug("Resource %s not found or not supported", raw_dn)
                for item in data:
                    dn = list(item.values())[0]['attributes']['dn']
                    if dn not in result:
                        result[dn] = item
                        if dn == raw_dn:
                            list(result[raw_dn].values())[
                                0]['attributes'].update(event_attrs)
            if not status or status == converter.CREATED_STATUS:
                result[raw_dn] = event
        LOG.debug("Result for retrieving ACI resources: %s\n %s" %
                  (events, result))
        return list(result.values())

    @staticmethod
    def flat_events(events):
        # If there are children objects, put them at the top level
        for event in events:
            if list(event.values())[0].get(CHILDREN_FIELD):
                # Rebuild the DN
                children = list(event.values())[0].pop(CHILDREN_FIELD)
                valid_children = []
                for child in children:
                    attrs = list(child.values())[0]['attributes']
                    rn = attrs.get('rn')
                    name_or_code = attrs.get('name', attrs.get('code'))
                    # Set DN of this object the the parent DN plus
                    # the proper prefix followed by the name or code (in case
                    # of faultInst)
                    try:
                        prefix = apic_client.ManagedObjectClass.mos_to_prefix[
                            list(child.keys())[0]]
                    except KeyError:
                        # We don't manage this object type
                        LOG.debug("Unmanaged object type: %s" % list(
                            child.keys())[0])
                        continue

                    attrs['dn'] = (
                        list(event.values())[0]['attributes']['dn'] + '/' +
                        (rn or (prefix + (('-' + name_or_code)
                                          if name_or_code else ''))))
                    valid_children.append(child)
                events.extend(valid_children)

    def _check_parent_type(self, aci_object, parent_types):
        dn = list(aci_object.values())[0]['attributes']['dn']
        type = list(aci_object.keys())[0]
        try:
            decomposed = (
                apic_client.DNManager().aci_decompose_dn_guess(
                    dn, type))
        except apic_client.DNManager.InvalidNameFormat:
            LOG.debug("Type %s with DN %s is not supported." %
                      (type, dn))
            return False
        if len(decomposed[1]) <= 1:
            return False
        return decomposed[1][-2][0] in parent_types

    @staticmethod
    def is_deleting(aci_object):
        attrs = list(aci_object.values())[0]['attributes']
        status = attrs.get(STATUS_FIELD, attrs.get(SEVERITY_FIELD))
        return status in [converter.DELETED_STATUS, converter.CLEARED_SEVERITY]

    @staticmethod
    def is_child_object(type):
        if type == TAG_KEY:
            return True
        aim_res = converter.resource_map.get(type, [])
        return aim_res and type not in [x['resource']._aci_mo_name
                                        for x in aim_res]
