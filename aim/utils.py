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
import re

from aim.api import resource
from aim.db import models
from aim import exceptions


class WrongStoreType(exceptions.AimException):
    message = "Store feature missing for this optimizer call: %(features)s."


def sanitize_display_name(display_name):
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', display_name[:59])


def requires(requirements):
    def wrap(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            diff = set(requirements) - set(args[0].store.features)
            if diff:
                raise WrongStoreType(features=requirements)
            else:
                return func(*args, **kwargs)
        return inner
    return wrap


@requires(['sql'])
def get_epg_by_host_names(context, host_names):
    session = context.store.db_session
    with session.begin(subtransactions=True):
        result = []
        for epg_db in session.query(models.EndpointGroup).join(
                models.EndpointGroup.static_paths).filter(
                models.EndpointGroupStaticPath.host.in_(host_names)).all():
            result.append(context.store.make_resource(resource.EndpointGroup,
                                                      epg_db))
    return result
