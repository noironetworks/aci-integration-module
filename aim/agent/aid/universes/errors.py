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


# unknown error
UNKNOWN = 'unknown'
# the operation will never succeed (eg. malformed object)
OPERATION_CRITICAL = 'operation_critical'
# the operation might eventually succeed and it's failing for temporary
# reasons (eg. object parent doesn't exist during creation)
OPERATION_TRANSIENT = 'operation_transient'
# the whole system is broken and cannot be recovered regardless of the
# operation (eg. wrong APIC certificate or credentials)
SYSTEM_CRITICAL = 'system_critical'
# the system is currently broken regardless of the operation, but might
# recover eventually (eg. network partition)
SYSTEM_TRANSIENT = 'system_transient'

SUPPORTED_ERRORS = [UNKNOWN, OPERATION_CRITICAL, OPERATION_TRANSIENT,
                    SYSTEM_CRITICAL, SYSTEM_TRANSIENT]
CRITICAL_ERRORS = [OPERATION_CRITICAL, SYSTEM_CRITICAL]
TRANSIENT_ERRORS = [OPERATION_TRANSIENT, SYSTEM_TRANSIENT]
OPERATION_ERRORS = [OPERATION_CRITICAL, OPERATION_TRANSIENT]
SYSTEM_ERRORS = [SYSTEM_TRANSIENT, SYSTEM_CRITICAL]
