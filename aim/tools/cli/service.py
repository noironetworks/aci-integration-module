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

from aim.agent.aid.event_services import polling
from aim.agent.aid.event_services import rpc_service
from aim.agent.aid import service
from aim.tools.cli import debug_shell
from aim.tools.cli import shell


def aid():
    service.main()


def aimctl():
    shell.run()


def aimdebug():
    debug_shell.run()


def event_polling():
    polling.main()


def rpc():
    rpc_service.main()
