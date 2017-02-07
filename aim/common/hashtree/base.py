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
import bisect
import six


@six.add_metaclass(abc.ABCMeta)
class ComparableCollection(object):
    """Defines base ComparableCollection API."""
    __slots__ = ()

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


@six.add_metaclass(abc.ABCMeta)
class OrderedList(object):
    """Ordered List.

    A useful support structure for comparable objects, it is a collection
    of nodes that is kept ordered for tree repeatability. Fast access to
    a node takes log(n) time because of the use of bisection, while keeping
    the data structure small without the use of hash tables.
    """

    __slots__ = ['_stash']

    def __init__(self):
        self._stash = []

    def __iter__(self):
        return self._stash.__iter__()

    @abc.abstractmethod
    def transform_key(self, key):
        """Transform key

        Wrap or transform key into a comparable form.
        :return: Comparable key
        """

    def include(self, items):
        for item in items:
            self.add(item)
        return self

    def add(self, item):
        i = self.index(item.key)
        if i is not None:
            # Already present, replace
            self._stash[i] = item
        else:
            bisect.insort(self._stash, item)
        return item

    def remove(self, key):
        i = self.index(key)
        if i is not None:
            self._stash.pop(i)

    def __getitem__(self, item):
        i = self.index(item)
        if i is not None:
            return self._stash[i]
        raise KeyError

    def index(self, key):
        i = bisect.bisect_left(self._stash, self.transform_key(key))
        if i != len(self._stash) and self._stash[i].key == key:
            return i
        return None

    def setdefault(self, key, default=None):
        """Return item with specified Key.

        add with default value if not present
        """
        current = self.get(key)
        if not current:
            # Not present, set
            current = default or self.transform_key(key)
            self.add(current)
        return current

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __str__(self):
        return "[" + ",".join("%s" % x for x in self._stash) + "]"

    def __len__(self):
        return len(self._stash)

    def __cmp__(self, other):
        return cmp(self._stash, other._stash)

    def __nonzero__(self):
        return len(self) != 0
