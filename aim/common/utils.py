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

import base64
from collections import OrderedDict
from contextlib import contextmanager
import functools
import hashlib
import json
import os
import oslo_serialization
import random
import re
import six
import threading
import time
import traceback
import uuid
import weakref

from apicapi import apic_client
from oslo_config import cfg
from oslo_log import log as logging


LOG = logging.getLogger(__name__)
AIM_LOCK_PREFIX = 'aim_lock'
OPENSTACK_VMM_TYPE = 'OpenStack'
VMWARE_VMM_TYPE = 'VMware'
KNOWN_VMM_TYPES = {'openstack': OPENSTACK_VMM_TYPE}
ACI_FAULT = 'faultInst'


def log(method):
    """Decorator helping to log method calls."""
    _LOG = logging.getLogger(method.__module__)

    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        instance = args[0]
        data = {"class_name": "%s.%s" % (instance.__class__.__module__,
                                         instance.__class__.__name__),
                "method_name": method.__name__,
                "args": args[1:], "kwargs": kwargs}
        _LOG.debug('%(class_name)s method %(method_name)s'
                   ' called with arguments %(args)s %(kwargs)s', data)
        return method(*args, **kwargs)
    return wrapper


# created a common function for tackling issues of sorting a list of dict
# or list of string for Py3 support
def deep_sort(obj):
    if isinstance(obj, dict):
        obj = OrderedDict(sorted(obj.items()))
        for k, v in list(obj.items()):
            if isinstance(v, dict) or isinstance(v, list):
                obj[k] = deep_sort(v)

    if isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, dict) or isinstance(v, list):
                obj[i] = deep_sort(v)
        obj = sorted(obj, key=lambda x: json.dumps(x))

    return obj


def is_equal(obj1, obj2):
    sorted_obj1 = deep_sort(obj1)
    sorted_obj2 = deep_sort(obj2)
    return sorted_obj1 == sorted_obj2


# In Py3, keyword 'cmp' is undefined
def cmp(obj1, obj2):
    _cmp = lambda x, y: (x > y) - (x < y)
    return _cmp(obj1, obj2)


def generate_uuid():
    return str(uuid.uuid4())


def sleep(time_in_seconds):
    time.sleep(time_in_seconds)


def wait_for_next_cycle(start_time, polling_interval, log, readable_caller='',
                        notify_exceeding_timeout=True):
    # sleep till end of polling interval
    elapsed = get_time() - start_time
    log.debug("%(caller)s loop - completed in %(time).3f. ",
              {'caller': readable_caller, 'time': elapsed})
    if elapsed < polling_interval:
        sleep(polling_interval - elapsed)
    elif notify_exceeding_timeout:
        log.debug("Loop iteration exceeded interval "
                  "(%(polling_interval)s vs. %(elapsed)s)!",
                  {'polling_interval': polling_interval,
                   'elapsed': elapsed})
        sleep(0)
    else:
        sleep(0)


class Counter(object):

    def __init__(self, num=0):
        self.num = num

    def get(self):
        return self.num

    def increment(self):
        self.num += 1


def get_backoff_time(max_time, tentative_number):
    try:
        return min(random.random() * (2 ** tentative_number),  # nosec
                   max_time)
    except OverflowError:
        return max_time


def exponential_backoff(max_time, tentative=None):
    tentative = tentative or Counter()
    sleep_time_secs = get_backoff_time(max_time, tentative.get())
    LOG.debug('Sleeping for %s seconds' % sleep_time_secs)
    sleep(sleep_time_secs)
    tentative.increment()
    return tentative


def perform_harakiri(log, message=None):
    log.error("AAAAARGH!")
    if message:
        log.error(message)
    if cfg.CONF.aim.recovery_restart:
        os._exit(1)


def stob(s):
    if s.lower() in ['true', 'yes', 't', 'y', '1']:
        return True
    if s.lower() in ['false', 'no', 'f', 'n', '0']:
        return False
    return None


def camel_to_snake(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def snake_to_lower_camel(name):
    split = name.split('_')
    return split[0] + ''.join(word.capitalize() for word in split[1:])


def sanitize_name(type, *args):
    # Updated due to PY3 error
    # TypeError: Unicode-objects must be encoded before hashing
    h = hashlib.sha256()
    h.update(type.encode('utf-8'))
    h.update('\x00'.encode('utf-8'))
    for component in args:
        h.update(component.encode('utf-8'))
        h.update('\x00'.encode('utf-8'))
    return (base64.b32encode(h.digest()).decode('utf-8').rstrip('=').lower())


class ThreadExit(Exception):
    pass


class StopLoop(Exception):
    pass


def retry_loop(max_wait, max_retries, name, fail=False, return_=False):
    def wrap(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            recovery_retries = None
            while True:
                try:
                    res = func(*args, **kwargs)
                    if return_:
                        return res
                    recovery_retries = None
                except StopLoop:
                    return
                except ThreadExit as e:
                    raise e
                except Exception as e:
                    LOG.error(traceback.format_exc())
                    recovery_retries = exponential_backoff(
                        max_wait, tentative=recovery_retries)
                    if recovery_retries.get() >= max_retries:
                        LOG.error("Exceeded max recovery retries for %s", name)
                        if fail:
                            perform_harakiri(LOG, str(e))
                        raise e
        return inner
    return wrap


class FakeContext(object):

    def __init__(self, store=None):
        if store:
            self.store = store


def decompose_dn(mo_type, dn):
    try:
        return apic_client.DNManager().aci_decompose_dn_guess(dn, mo_type)[1]
    except (apic_client.DNManager.InvalidNameFormat, KeyError,
            apic_client.cexc.ApicManagedObjectNotSupported, IndexError):
        log_ = LOG.warning
        if mo_type == 'faultDelegate':
            log_ = LOG.debug
        log_("Failed to transform DN %s to key for type %s" % (dn, mo_type))
        return


def retrieve_fault_parent(fault_dn, resource_map):
    # external is the DN of the ACI resource
    dn_mgr = apic_client.DNManager()
    mos_rns = dn_mgr.aci_decompose_with_type(fault_dn, ACI_FAULT)[:-1]
    rns = dn_mgr.filter_rns(mos_rns)
    conv_info = None
    step = -1
    while conv_info is None or len(conv_info) > 1:
        aci_klass = mos_rns[step][0]
        conv_info = resource_map[aci_klass]
        step -= 1
    conv_info = conv_info[0]
    klasses = [conv_info['resource']]
    if conv_info.get('alt_resource'):
        klasses.append(conv_info['alt_resource'])
    parents = []
    for klass in klasses:
        a_obj = klass(**{y: rns[x]
                         for x, y in enumerate(klass.identity_attributes)})
        parents.append(a_obj)
    return parents


class ThreadKillTimeout(Exception):
    message = "Thread kill timed out"


class AIMThread(object):
    KILL_TIMEOUT = 10

    def __init__(self, *args, **kwargs):
        self._thread = None
        self._stop = False

    def start(self):
        self._thread = spawn_thread(self.run)
        return self

    def run(self):
        pass

    def kill(self, wait=False, timeout=KILL_TIMEOUT):
        if self._thread:
            self._stop = True
            if wait:
                tentative = None
                curr_time = get_time()
                while not self.dead and curr_time + timeout < get_time():
                    exponential_backoff(timeout / 3, tentative)
                if not self.dead:
                    raise

    @property
    def dead(self):
        if self._thread:
            return not self._thread.is_alive()


def spawn_thread(target, *args, **kwargs):
    thd = threading.Thread(target=target, args=args, kwargs=kwargs)
    thd.daemon = True
    thd.start()
    return thd


# Key/Values will be garbage collected once al references are lost
all_locks = weakref.WeakValueDictionary()
_master_lock = threading.Lock()


class LockNotAcquired(Exception):
    pass


def generate_rlock(lock_name):
    with _master_lock:
        return all_locks.setdefault(lock_name, threading.RLock())


@contextmanager
def get_rlock(lock_name, blocking=True):
    lock = generate_rlock(lock_name)
    if not lock.acquire(blocking):
        raise LockNotAcquired()
    try:
        yield lock
    finally:
        lock.release()


def rlock(lock_name):
    def wrap(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            # setdefault is atomic
            lock = generate_rlock(lock_name)
            # Too much output if we log this. However, it would be really
            # useful to have a debug mode that show us which lock is held
            # by which thread/method
            try:
                lock.acquire()
                return func(*args, **kwargs)
            finally:
                lock.release()
        return inner
    return wrap


def _byteify(data, ignore_dicts=False):
    if isinstance(data, six.text_type):
        return data.encode('utf-8')
    if isinstance(data, list):
        return [_byteify(item, ignore_dicts=True) for item in data]
    if isinstance(data, dict) and not ignore_dicts:
        return {
            _byteify(key, ignore_dicts=True): _byteify(value,
                                                       ignore_dicts=True)
            for key, value in list(data.items())
        }
    return data


def json_loads(json_text):
    # The ultimate aim of using _byteify is to convert unicode data to
    # bytes (or else it will dump the data into unicode format, since
    # data is in unicode format).
    # We are converting into bytes because in Py2, string and bytes are
    # same in Py2.
    # While we don't need to convert it into bytes for Py3, because string
    # and unicode are same in Py3. So no need for conversion in PY3 case.
    if six.PY3:
        return oslo_serialization.jsonutils.loads(json_text)
    return _byteify(
        oslo_serialization.jsonutils.loads(json_text, object_hook=_byteify),
        ignore_dicts=True)


def json_dumps(dict):
    return oslo_serialization.jsonutils.dump_as_bytes(dict)


def schedule_next_event(interval, deviation):
    return get_time() + interval + random.randrange(  # nosec
        int(-interval * deviation), int(interval * deviation))


def get_time():
    return time.time()
