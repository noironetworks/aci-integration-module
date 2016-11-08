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

import functools
import time
import uuid

import gevent
from oslo_log import log as logging

AIM_LOCK_PREFIX = 'aim_lock'
OPENSTACK_VMM_TYPE = 'OpenStack'


def log(method):
    """Decorator helping to log method calls."""
    LOG = logging.getLogger(method.__module__)

    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        instance = args[0]
        data = {"class_name": "%s.%s" % (instance.__class__.__module__,
                                         instance.__class__.__name__),
                "method_name": method.__name__,
                "args": args[1:], "kwargs": kwargs}
        LOG.debug('%(class_name)s method %(method_name)s'
                  ' called with arguments %(args)s %(kwargs)s', data)
        return method(*args, **kwargs)
    return wrapper


def generate_uuid():
    return str(uuid.uuid4())


def wait_for_next_cycle(start_time, polling_interval, log, readable_caller='',
                        notify_exceeding_timeout=True):
    # sleep till end of polling interval
    elapsed = time.time() - start_time
    log.debug("%(caller)s loop - completed in %(time).3f. ",
              {'caller': readable_caller, 'time': elapsed})
    if elapsed < polling_interval:
        gevent.sleep(polling_interval - elapsed)
    elif notify_exceeding_timeout:
        log.debug("Loop iteration exceeded interval "
                  "(%(polling_interval)s vs. %(elapsed)s)!",
                  {'polling_interval': polling_interval,
                   'elapsed': elapsed})
        gevent.sleep(0)
    else:
        gevent.sleep(0)
