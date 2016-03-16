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
class ComparableCollection(object):
    """Defines base ComparableCollection API."""

    @abc.abstractmethod
    def add(self, key, **kwargs):
        """Add a member to the Comparable Collection

        Adding an existing key will result in an update
        :param key: Key of the member
        :param kwargs: Original attributes of the member
        :return: The ComparableCollection reference
        :raises:
        """

    @abc.abstractmethod
    def include(self, iterable):
        """Add multiple members to the Comparable Collection

        Adding an existing key will result in an update
        :param iterable: A list of dictionaries defining the members to be
        added, the 'key' key must be present in all the passed dictionaries or
        a KeyError will be raised
        :return: The ComparableCollection reference
        :raises: KeyError,
        """

    @abc.abstractmethod
    def pop(self, key, default=None):
        """Remove and returns a member

        In hierarchical implementations, a full subtree might be returned.
        :param key: Key of the member to pop
        :param default: value to return in case the member is missing
        :return: the removed member with its related subtree if applies
        :raises:
        """

    @abc.abstractmethod
    def remove(self, key):
        """Remove a member

        Raises KeyError if the member doesn't exist
        :param key: Key of the member to be removed
        :return: The ComparableCollection reference
        :raises: KeyError
        """

    @abc.abstractmethod
    def find(self, key):
        """Find member with given key

        :param key: Key of the member to be found
        :return: None if not found, the member otherwise
        """

    @abc.abstractmethod
    def diff(self, other):
        """Difference

        Calculates the set of operations needed to transform other into self.
        :param other: Another ComparableCollection
        :return: dictionary containing operations {"add":[<keys>],
                                                   "remove":[<keys>]}
        """
