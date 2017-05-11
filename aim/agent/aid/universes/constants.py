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


# Keep all the lock names/prefixes here stored in constants for an easier
# lookup of who is using them.

# Access to the k8s watcher tree shared resource
K8S_WATCHER_TREE_LOCK = 'k8s_watcher_trees'
# Prevent AID from observing new state for all roots
AID_OBSERVER_LOCK = 'aid_observer_lock'
# Access ACI tree of a specific root
ACI_TREE_LOCK_NAME_PREFIX = "root_aci_tree_lock-"
# Access to aci backlog
ACI_BACKLOG_LOCK_NAME_PREFIX = "backlog_aci_lock-"
