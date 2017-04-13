# Copyright (c) 2017 Cisco Systems
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

import click
import time

from aim.agent.aid import event_handler
from aim.agent.aid.universes.k8s import k8s_watcher
from aim import aim_store
from aim.db import api
from aim.tools.cli.groups import aimcli


@aimcli.aim.group(name='k8swatcher')
@click.pass_context
def k8swatcher(ctx):
    store = api.get_store(expire_on_commit=True)
    if not isinstance(store, aim_store.K8sStore):
        msg = ('Incorrect AIM store type. Expected %s, '
               'found %s' % (aim_store.K8sStore.__name__,
                             type(store).__name__))
        raise click.UsageError(msg)


@k8swatcher.command(name='run')
@click.pass_context
def run(ctx):
    event_handler.EventHandler().initialize(None)
    w = k8s_watcher.K8sWatcher()
    w.run()
    while True:
        time.sleep(5)
