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

import collections
import copy
import json
import Queue
import time
import traceback

from acitoolkit import acitoolkit
from apicapi import apic_client
from apicapi import exceptions as apic_exc
import gevent
from oslo_log import log as logging

from aim.agent.aid.universes.aci import converter
from aim.agent.aid.universes import base_universe
from aim.common.hashtree import structured_tree
from aim.db import tree_model
from aim import exceptions

LOG = logging.getLogger(__name__)
TENANT_KEY = 'fvTenant'
FAULT_KEY = 'faultInst'
TAG_KEY = 'tagInst'
STATUS_FIELD = 'status'
SEVERITY_FIELD = 'severity'
CHILDREN_FIELD = 'children'
CHILDREN_LIST = set(converter.resource_map.keys() + ['fvTenant', 'tagInst'])
OPERATIONAL_LIST = [FAULT_KEY]


# Dictionary with all the needed RS objects of a given APIC object type.
# Key is the APIC type, value is a list of DN suffixes that the manager needs
# to retrieve. For example, a value of ['rsctx'] for a fvBD means that the
# manager will do a GET on uni/tn-tname/BD-bdname/rsctx in order to complete
# the event list. A functor can be passed instead of a simple suffix list
# for more general cases.
def parent_dn(resource):
    dn = resource['attributes']['dn']
    return dn[:dn.rfind('/')]


def bd_dn(resource):
    return 'fvBD', parent_dn(resource)

RS_FILL_DICT = {'fvBD': [('fvRsCtx', 'rsctx')],
                'fvRsCtx': [bd_dn]}


class WebSocketSessionLoginFailed(exceptions.AimException):
    message = ("Web socket session failed to login for tenant %(tn_name)s "
               "with error %(code)s: %(text)s")


class WebSocketSubscriptionFailed(exceptions.AimException):
    message = ("Web socket session failed to subscribe for tenant %(tn_name)s "
               "with error %(code)s: %(text)s")


class Tenant(acitoolkit.Tenant):

    def __init__(self, *args, **kwargs):
        self.filtered_children = kwargs.pop('filtered_children', [])
        super(Tenant, self).__init__(*args, **kwargs)

    def _get_instance_subscription_urls(self):
        url = ('/api/mo/uni/tn-{}.json?query-target=subtree&'
               'rsp-prop-include=config-only&rsp-subtree-include=faults&'
               'subscription=yes'.format(self.name))
        if self.filtered_children:
            url += '&target-subtree-class=' + ','.join(self.filtered_children)
        return [url]

    def instance_subscribe(self, session):
        # Have it publicly available
        resp = self._instance_subscribe(session)
        if resp.ok:
            return json.loads(resp.text)['imdata']
        else:
            raise WebSocketSubscriptionFailed(tn_name=self.name,
                                              code=resp.status_code,
                                              text=resp.text)

    def instance_unsubscribe(self, session):
        urls = self._get_instance_subscription_urls()
        LOG.debug("Subscription urls: %s", urls)
        for url in urls:
            session.unsubscribe(url)

    def instance_get_event_data(self, session):
        # Replace _instance_get_event to avoid object creation, we just need
        # the sheer data
        urls = self._get_instance_subscription_urls()
        for url in urls:
            # Aggregate similar events
            result = []
            while session.has_events(url):
                event = session.get_event(url)['imdata'][0]
                event_klass = event.keys()[0]
                event_dn = event[event_klass]['attributes']['dn']
                for partial in result:
                    if (event_klass == partial.keys()[0] and
                            event_dn == partial[event_klass][
                                'attributes']['dn']):
                        partial.update(event)
                        break
                else:
                    result.append(event)
            return result

    def instance_has_event(self, session):
        return self._instance_has_events(session)


class AciTenantManager(gevent.Greenlet):

    def __init__(self, tenant_name, apic_config, apic_session, *args,
                 **kwargs):
        super(AciTenantManager, self).__init__(*args, **kwargs)
        LOG.info("Init manager for tenant %s" % tenant_name)
        self.apic_config = apic_config
        # Each tenant has its own sessions
        self.aci_session = apic_session
        self.dn_manager = apic_client.DNManager()
        self.tenant_name = tenant_name
        children_mos = set()
        for mo in CHILDREN_LIST:
            if mo in apic_client.ManagedObjectClass.supported_mos:
                children_mos.add(apic_client.ManagedObjectClass(mo).klass_name)
            else:
                children_mos.add(mo)
        self.tenant = Tenant(self.tenant_name, filtered_children=children_mos)
        self._state = structured_tree.StructuredHashTree()
        self._operational_state = structured_tree.StructuredHashTree()
        self.health_state = False
        self.polling_yield = 1
        self.to_aim_converter = converter.AciToAimModelConverter()
        self.to_aci_converter = converter.AimToAciModelConverter()
        self.object_backlog = Queue.Queue()
        self.tree_maker = tree_model.AimHashTreeMaker()
        # TODO(ivar): retrieve apic_system_id
        self.tag_name = 'openstack_aid'
        self.tag_set = set()
        # Warm bit to avoid rushed synchronization before receiving the first
        # batch of APIC events
        self._warm = False

    def is_dead(self):
        # Wrapping the greenlet property for easier testing
        return self.dead

    def is_warm(self):
        return self._warm

    # These methods are dangerous if run concurrently with _event_to_tree.
    # However, serialization/deserialization of the in-memory tree should not
    # cause I/O operation, therefore they can't be context switched.
    def get_state_copy(self):
        return structured_tree.StructuredHashTree.from_string(
            str(self._state), root_key=self._state.root_key)

    def get_operational_state_copy(self):
        return structured_tree.StructuredHashTree.from_string(
            str(self._operational_state),
            root_key=self._operational_state.root_key)

    def _run(self):
        LOG.debug("Starting main loop for tenant %s" % self.tenant_name)
        try:
            while True:
                self._main_loop()
        except gevent.GreenletExit:
            try:
                self.tenant.instance_unsubscribe(self.ws_session)
                # TODO(ivar): unsubscribe from all the DB options
            except Exception as e:
                LOG.error("An exception has occurred while exiting thread "
                          "for tenant %s: %s" % (self.tenant_name,
                                                 e.message))
            finally:
                # We need to make sure that this thread dies upon
                # GreenletExit
                return

    def _main_loop(self):
        try:
            # tenant subscription is redone upon exception
            LOG.debug("Starting event loop for tenant %s" % self.tenant_name)
            self._subscribe_tenant()
            count = 3
            last_time = 0
            epsilon = 0.5
            while True:
                start = time.time()
                self._event_loop()
                if count == 0:
                    LOG.debug("Setting tenant %s to warm state" %
                              self.tenant_name)
                    self._warm = True
                    count -= 1
                elif count > 0:
                    count -= 1
                curr_time = time.time() - start
                if abs(curr_time - last_time) > epsilon:
                    # Only log significant differences
                    LOG.debug("Event loop for tenant %s completed in %s "
                              "seconds" % (self.tenant_name,
                                           time.time() - start))
                    last_time = curr_time
                if not last_time:
                    last_time = curr_time
        except gevent.GreenletExit:
            raise
        except Exception as e:
            LOG.error("An exception has occurred in thread serving tenant "
                      "%s, error: %s" % (self.tenant_name, e.message))
            LOG.debug(traceback.format_exc())

    def _event_loop(self):
        start_time = time.time()
        # Push the backlog at the very start of the event loop, so that
        # all the events we generate here are likely caught in this iteration.
        self._push_aim_resources()
        if self.tenant.instance_has_event(self.ws_session):
            LOG.debug("Event for tenant %s in warm state %s" %
                      (self.tenant_name, self._warm))
            # Continuously check for events
            events = self.tenant.instance_get_event_data(
                self.ws_session)
            for event in events:
                if (event.keys()[0] == TENANT_KEY and not
                        event[TENANT_KEY]['attributes'].get(STATUS_FIELD)):
                    LOG.info("Resetting Tree %s" % self.tenant_name)
                    # This is a full resync, tree needs to be reset
                    self._state = structured_tree.StructuredHashTree()
                    self._operational_state = (
                        structured_tree.StructuredHashTree())
                    break
            LOG.debug("received events: %s", events)
            # Make events list flat
            self._flat_events(events)
            # Manage Tags
            events = self._filter_ownership(events)
            LOG.debug("Filtered events: %s", events)
            # Pull incomplete objects
            self._fill_events(events)
            LOG.debug("Filled events: %s", events)
            self._event_to_tree(events)
        # yield for other threads
        gevent.sleep(max(0, self.polling_yield - (time.time() -
                                                  start_time)))

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
        # TODO(ivar): improve performance by squashing similar events
        self.object_backlog.put(resources)

    def _push_aim_resources(self):
        while not self.object_backlog.empty():
            request = self.object_backlog.get()
            LOG.debug("Requests: %s" % request)
            for method, aim_objects in request.iteritems():
                # Method will be either "create" or "delete"
                for aim_object in aim_objects:
                    # get MO from ACI client, identify it via its DN parts and
                    # push the new body
                    LOG.debug('%s AIM object %s in APIC' %
                              (method, aim_object))
                    if method == base_universe.DELETE:
                        to_push = [copy.deepcopy(aim_object)]
                    else:
                        to_push = self.to_aci_converter.convert([aim_object])
                    # Set TAGs before pushing the request
                    tags = []
                    if method == base_universe.CREATE:
                        # No need to deal with tags on deletion
                        for obj in to_push:
                            dn = obj.values()[0]['attributes']['dn']
                            dn += '/tag-%s' % self.tag_name
                            tags.append({"tagInst__%s" % obj.keys()[0]:
                                         {"attributes": {"dn": dn}}})
                    LOG.debug("Pushing %s into APIC: %s" %
                              (method, to_push + tags))
                    # Multiple objects could result from a conversion, push
                    # them in a single transaction
                    MO = apic_client.ManagedObjectClass
                    decompose = apic_client.DNManager().aci_decompose_dn_guess
                    try:
                        with self.aci_session.transaction() as trs:
                            for obj in to_push + tags:
                                attr = obj.values()[0]['attributes']
                                mo, parents_rns = decompose(attr.pop('dn'),
                                                            obj.keys()[0])
                                # exclude RNs that are fixed
                                rns = [mr[1] for mr in parents_rns
                                       if (mr[0] not in MO.supported_mos or
                                           MO(mr[0]).rn_param_count)]
                                getattr(getattr(self.aci_session, mo),
                                        method)(
                                            *rns, transaction=trs, **attr)
                    except apic_exc.ApicResponseNotOk:
                        # TODO(ivar): Either creation or deletion failed.
                        # Look at the reason and update the AIM status
                        # accordingly.
                        try:
                            printable = aim_object.__dict__
                        except AttributeError:
                            printable = aim_object
                        LOG.error("An error as occurred during %s for "
                                  "object %s" % (method, printable))
                        LOG.debug(traceback.format_exc())

    def _subscribe_tenant(self):
        # REVISIT(ivar): acitoolkit is missing some features like certificate
        # identification and multi controller support. In order to alleviate
        # this, we can at least simulate the multi controller here with the
        # following hacky code (which we can limiting to this method for now).
        # A decision should be taken whether we want to add features to
        # acitoolkit to at least support certificate identification, or if
        # we want to implement the WS interface in APICAPI altogether
        protocol = 'https' if self.apic_config.get_option(
            'apic_use_ssl', group='apic') else 'http'
        if not getattr(self, 'ws_urls', None):
            self.ws_urls = collections.deque(
                ['%s://%s' % (protocol, host) for host in
                 self.apic_config.get_option('apic_hosts', group='apic')])
        self.ws_urls.rotate(-1)
        self.ws_session = acitoolkit.Session(
            self.ws_urls[0], self.apic_config.get_option(
                'apic_username', group='apic'),
            self.apic_config.get_option('apic_password', group='apic'),
            verify_ssl=self.apic_config.get_option(
                'verify_ssl_certificate', group='apic'))
        self.health_state = False
        resp = self.ws_session.login()
        if not resp.ok:
            raise WebSocketSessionLoginFailed(tn_name=self.tenant_name,
                                              code=resp.status_code,
                                              text=resp.text)
        current = time.time()
        self.tenant.instance_subscribe(self.ws_session)
        LOG.info('Subscription to tenant %s took %s seconds' % (
            self.tenant_name, time.time() - current))
        self.health_state = True

    def _event_to_tree(self, events):
        """Parse the event and push it into the tree

        This method requires translation between ACI and AIM model in order
        to  honor the Universe contract.
        :param events: an ACI event in the form of a list of objects
        :return:
        """
        config_tree = {'create': [], 'delete': []}
        operational_tree = {'create': [], 'delete': []}
        trees = {True: operational_tree, False: config_tree}
        states = {id(operational_tree): self._operational_state,
                  id(config_tree): self._state}
        for event in events:
            aci_resource = event.values()[0]
            if self._is_deleting(event):
                trees[event.keys()[0] == FAULT_KEY]['delete'].append(event)
                # Pop deleted object from the TAG list
                dn = aci_resource['attributes']['dn']
                self.tag_set.discard(dn)
            else:
                trees[event.keys()[0] == FAULT_KEY]['create'].append(event)

        # Convert objects
        for tree in trees.values():
            state = states[id(tree)]
            tree['create'] = self.to_aim_converter.convert(tree['create'])
            tree['delete'] = self.to_aim_converter.convert(tree['delete'])

            self.tree_maker.update(state, tree['create'])
            self.tree_maker.delete(state, tree['delete'])
            if state is self._state:
                # Delete also from Operational tree for branch cleanup
                self.tree_maker.delete(self._operational_state, tree['delete'])

            LOG.debug("New tree for tenant %s: %s" % (self.tenant_name,
                                                      str(state)))

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
        visited = set()
        dns = {x.values()[0]['attributes']['dn'] for x in events}
        start = time.time()
        for event in events:
            resource = event.values()[0]
            res_type = event.keys()[0]
            status = resource['attributes'].get(STATUS_FIELD)
            if (status == converter.MODIFIED_STATUS or
                    res_type in OPERATIONAL_LIST):
                try:
                    # Remove from extra dns if there
                    # 'dn' attribute is guaranteed to be there
                    dn = resource['attributes']['dn']
                    if dn in visited:
                        continue
                    # See if there's any extra object to be retrieved
                    for filler in RS_FILL_DICT.get(res_type, []):
                        t, id = ((filler[0], dn + '/' + filler[1])
                                 if not callable(filler) else filler(resource))
                        if id not in dns:
                            # Avoid duplicate lookups
                            events.append(
                                {t: {'attributes': {'dn': id,
                                                    'status': status}}})
                    visited.add(dn)
                    kargs = {'rsp_prop_include': 'config-only'}
                    # Operational state need full configuration
                    if event.keys()[0] in OPERATIONAL_LIST:
                        kargs.pop('rsp_prop_include')
                    # TODO(ivar): the 'mo/' suffix should be added by APICAPI
                    data = self.aci_session.get_data('mo/' + dn, **kargs)
                    resource['attributes'].update(
                        data[0].values()[0]['attributes'])
                    # Status not needed unless deleted
                    resource['attributes'].pop('status')
                except apic_exc.ApicResponseNotOk as e:
                    # Object might have been deleted
                    if str(e.err_code) == '404':
                        LOG.debug("Resource %s not found", dn)
                        resource['attributes'][STATUS_FIELD] = (
                            converter.DELETED_STATUS)
                    else:
                        LOG.error(e.message)
                        raise
        LOG.debug('Filling procedure took %s for tenant %s' %
                  (time.time() - start, self.tenant.name))

    def _flat_events(self, events):
        # If there are children objects, put them at the top level
        for event in events:
            if event.values()[0].get(CHILDREN_FIELD):
                # Rebuild the DN
                children = event.values()[0].pop(CHILDREN_FIELD)
                for child in children:
                    attrs = child.values()[0]['attributes']
                    name_or_code = attrs.get('name', attrs.get('code'))
                    # Set DN of this object the the parent DN plus
                    # the proper prefix followed by the name or code (in case
                    # of faultInst)
                    attrs['dn'] = (
                        event.values()[0]['attributes']['dn'] + '/' +
                        apic_client.ManagedObjectClass.mos_to_prefix[
                            child.keys()[0]] + (('-' + name_or_code)
                                                if name_or_code else ''))
                events.extend(children)

    def _filter_ownership(self, events):
        result = []
        for event in events:
            if event.keys()[0] == TAG_KEY:
                decomposed = event.values()[0]['attributes']['dn'].split('/')
                if decomposed[-1] == 'tag-' + self.tag_name:
                    if self._is_deleting(event):
                        self.tag_set.discard('/'.join(decomposed[:-1]))
                    else:
                        self.tag_set.add('/'.join(decomposed[:-1]))
            else:
                result.append(event)
        return [x for x in result if self._is_owned(x) or self._is_deleting(x)]

    def _is_owned(self, aci_object):
        dn = aci_object.values()[0]['attributes']['dn']
        if aci_object.keys()[0] in apic_client.MULTI_PARENT:
            decomposed = dn.split('/')
            # Check for parent ownership
            return '/'.join(decomposed[:-1]) in self.tag_set
        else:
            return dn in self.tag_set

    def _is_deleting(self, aci_object):
        attrs = aci_object.values()[0]['attributes']
        status = attrs.get(STATUS_FIELD, attrs.get(SEVERITY_FIELD))
        return status in [converter.DELETED_STATUS, converter.CLEARED_SEVERITY]
