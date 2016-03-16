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


@six.add_metaclass(abc.ABCMeta)
class BaseObserver(object):
    """Observer Base Class

    An Observer is a component of the AID (ACI Inconsistency Detector) that
    observes and stores any change to the system state.
    The observed state could either be the Desired or the Operational one.
    Each state is grouped by AIM tenant and should be stored in a format that
    is easily comparable with a state of the same type.
    Any type of observer can choose the favourit storage data structure as
    long as observer inheriting from the same Class are able to compare their
    observed states.
    """

    @abc.abstractmethod
    def initialize(self, db_handler):
        """Observer initialization method.

        This method will be called before any other.

        :param db_handler: handler to the AIM DB, can be used to retrieve state
        or useful configuration options.
        :returns: self
        """

    @abc.abstractmethod
    def compare(self, tenant_id, other_state):
        """State comparison method.

        When an observer's compare method is called, the stored state is
        treated as the desired final state, therefore the returned difference
        will be what's needed in order to make other_state equal to the
        stored_state.

        :param tenant_id: ID of the tenant for which the state comparison is
                          happening.
        :param other_state: state to be compared with
        # TODO(ivar): add return format
        :returns: difference between the stored state and other state.
        """


class HashTreeObvserver(BaseObserver):
    """Observer storing state in the form of a Hash Tree."""

    def initialize(self, db_handler):
        super(HashTreeObvserver, self).initialize(db_handler)
        self.db = db_handler
        return self
