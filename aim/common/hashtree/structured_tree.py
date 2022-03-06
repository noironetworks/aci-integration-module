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

import collections
import hashlib
import json

from oslo_log import log

from aim.common.hashtree import base
from aim.common.hashtree import exceptions as exc
from aim.common import utils

LOG = log.getLogger(__name__)


class StructuredTreeNode(object):
    # Use lightweight class
    __slots__ = [
        'key',  # iterable that defines hierarchical order
        'partial_hash',  # hash of the attributes originally belonging
                         # to the resource from which this node was generated
        'full_hash',  # hash(partial_hash, children.full_hash)
        'dummy',  # whether or not this node is dummy
        'error',  # When True, skip to compare children
        '_children',  # underlying nodes
        'metadata',  # Additional "user" data dict, not used for
                     # tree comparison
    ]

    def __init__(self, key, partial_hash=None, full_hash=None, dummy=True,
                 metadata=None, error=False):
        self.key = key
        self.partial_hash = partial_hash
        # Same as partial hash by default
        self.full_hash = full_hash or self.partial_hash
        self._children = ChildrenList()
        self.dummy = dummy
        self.metadata = metadata or KeyValueStore()
        if isinstance(self.metadata, dict):
            self.metadata = KeyValueStore().include(
                [KeyValue(k, v) for k, v in list(self.metadata.items())])
        self.error = error

    def __cmp__(self, other):
        return utils.cmp(self.key, getattr(other, 'key', other))

    # In Py3, all objects that implemented __cmp__ must be updated to
    # implement some of the rich methods instead like __eq__, __lt__, etc.
    # Here, __eq__ and __lt__ are sufficient for comparison.
    def __eq__(self, other):
        return self.key == getattr(other, 'key', other)

    def __lt__(self, other):
        return (self.key < getattr(other, 'key', other))

    def set_child(self, key, default=None):
        return self._children.setdefault(key, default)

    def replace_child(self, node):
        return self._children.add(node)

    def remove_child(self, key):
        self._children.remove(key)

    def get_children(self):
        return tuple(self._children)

    def get_child(self, key, default=None):
        return self._children.get(key, default)

    def __str__(self):
        return json.dumps(self.to_dict())

    def to_dict(self):
        root = collections.OrderedDict(
            [('key', self.key), ('partial_hash', self.partial_hash),
             ('full_hash', self.full_hash), ('dummy', self.dummy),
             ('error', self.error),
             ('metadata', self.metadata.to_dict()),
             ('_children', [])])
        for children in self.get_children():
            root['_children'].append(children.to_dict())
        return root


class ChildrenList(base.OrderedList):

    __slots__ = ['_stash']

    def transform_key(self, key):
        return StructuredTreeNode(key)

    def transform_value(self, value):
        return value


class KeyValue(object):

    __slots__ = ['key', 'value']

    def __init__(self, key, value=None):
        self.key = key
        self.value = value

    def __cmp__(self, other):
        return utils.cmp(self.key, other.key)

    # In Py3, all objects that implemented __cmp__ must be updated to
    # implement some of the rich methods instead like __eq__, __lt__, etc.
    # Here, __eq__ and __lt__ are sufficient for comparison.
    def __lt__(self, other):
        return (self.key < other.key)

    def __eq__(self, other):
        return (self.key == other.key)

    def __str__(self):
        return "(%s, %s)" % (self.key, self.value)


class KeyValueStore(base.OrderedList):

    __slots__ = ['_stash']

    def transform_key(self, key):
        return KeyValue(key)

    def transform_value(self, value):
        return value.value

    def to_dict(self):
        return {x.key: x.value for x in self}

    def __cmp__(self, other):
        if isinstance(other, KeyValueStore):
            return super(KeyValueStore, self).__cmp__(other)
        if isinstance(other, dict):
            return super(KeyValueStore, self).__cmp__(
                KeyValueStore().include([KeyValue(k, v) for k, v in
                                         list(other.items())]))
        return False

    # In Py3, all objects that implemented __cmp__ must be updated to
    # implement some of the rich methods instead like __eq__, __lt__, etc.
    # Here, __eq__ and __lt__ are sufficient for comparison.
    def __eq__(self, other):
        if isinstance(other, KeyValueStore):
            return super(KeyValueStore, self).__eq__(other)
        if isinstance(other, dict):
            return super(KeyValueStore, self).__eq__(
                KeyValueStore().include([KeyValue(k, v) for k, v in
                                         list(other.items())]))

    def __str__(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        return '%s(%s)' % (super(KeyValueStore, self).__repr__(), str(self))


class StructuredHashTree(base.ComparableCollection):
    """Structured Hash Tree.

    This hash tree works the best for structured data, as in hierarchically
    organized by key.

    The key of each node is composed of multiple ordered parts which will be
    used to navigate the tree and choose the right place for a added node.
    This allows an easier and more predictable dynamic growth of the tree.

    Usage examples:

    Initialize with or without initial data
    tree = StructuredHashTree()
    tree = StructuredHashTree([{'key': ('tn-tenant', 'bd-bridge1'),
                                'arpEnabled': False},
                               {'key': ('tn-tenant', 'bd-bridge2'),
                                'arpEnabled': True},
                               {'key': ('tn-tenant', 'ctx-context1')}])

    Add a new node
    tree.add(('tn-tenant', 'bd-bridge3'), arpEnabled=False)

    Amend some changes to a previously added node
    tree.add(('tn-tenant', 'bd-bridge3'), arpEnabled=True)

    Remove a node
    try:
        tree.remove(('tn-tenant', 'bd-bridge3'))
    except KeyError:
        pass

    Pop a subtree if present
    tree.pop(('tn-tenant', 'bd-bridge3'))
    """

    __slots__ = ['root', 'root_key', 'has_populated']

    def __init__(self, root=None, root_key=None, has_populated=False):
        """Initialize a Structured Hash Tree.

        Initial data can be passed to initialize the tree
        :param root
        """
        self.root = root
        self.root_key = root_key
        if self.root:
            # Ignore the value passed in the constructor
            self.root_key = self.root.key
        self.has_populated = has_populated

    @property
    def root_full_hash(self):
        if self.root:
            return self.root.full_hash
        elif self.root_key:
            return self._hash(str(self.root_key))
        else:
            return None

    @staticmethod
    def from_string(string, root_key=None, has_populated=False):
        to_dict = utils.json_loads(string)
        return (StructuredHashTree(StructuredHashTree._build_tree(to_dict),
                                   has_populated=has_populated) if
                to_dict else StructuredHashTree(root_key=root_key,
                                                has_populated=has_populated))

    @staticmethod
    def _build_tree(root_dict):
        root = StructuredTreeNode(tuple(root_dict['key']),
                                  root_dict['partial_hash'],
                                  root_dict['full_hash'],
                                  dummy=root_dict['dummy'],
                                  error=root_dict['error'],
                                  metadata=root_dict.get('metadata'))
        for child in root_dict['_children']:
            root._children.add(StructuredHashTree._build_tree(child))
        return root

    def add(self, key, **kwargs):
        if not key:
            # nothing to do
            return self
        has_metadata = '_metadata' in kwargs
        metadata_dict = kwargs.pop('_metadata', {})
        metadata = KeyValueStore().include(
            KeyValue(k, v) for k, v in list((metadata_dict or {}).items()))
        error = kwargs.pop('_error', False)
        # When self.root is node, it gets initialized with a bogus node
        if not self.root:
            self.root = StructuredTreeNode(
                (key[0],), self._hash_attributes(key=(key[0],), _dummy=True))
            self.root_key = self.root.key
            self.has_populated = True
        else:
            # With the first element of the key, verify that this is not an
            # attempt of creating a hydra (tree with multiple roots)
            if (key[0],) != self.root.key:
                raise exc.MultipleRootTreeError(key=key,
                                                root_key=self.root.key)

        node = self.root
        stack = [node]
        partial_key = (key[0],)
        # Traverse the tree and place the node, discard first part of the key
        for part in key[1:]:
            partial_key += (part,)
            # Get child or set it with a placeholder if it doesn't exist
            node = node.set_child(
                partial_key, StructuredTreeNode(
                    partial_key, self._hash_attributes(key=partial_key,
                                                       _dummy=True)))
            stack.append(node)
        # When a node is explicitly added, it is not dummy
        node.dummy = False
        # Node is the last added element at this point
        node.partial_hash = self._hash_attributes(key=key, _dummy=node.dummy,
                                                  **kwargs)
        node.error = error
        if has_metadata:
            if metadata_dict is not None:
                node.metadata.update(metadata)
            else:
                node.metadata = metadata
        # Recalculate full hashes navigating the stack backwards
        self._recalculate_parents_stack(stack)
        return self

    def include(self, iterable):
        """Add multiple nodes to the Tree.

        :param iterable: A list of dictionaries representing each node of the
        newly initialized tree. Each dictionary must contain at least the 'key'
        key.
        :return: self
        """
        cache = []
        try:
            for node in iterable:
                # 'key' is not considered in the Hash calculation
                key = node.pop('key')
                cache.append(key)
                self.add(key, **node)
            return self
        except Exception as e:
            LOG.error("An exception has occurred while adding nodes, "
                      "rolling back partially succeeded ones")
            # Rollback currently inserted objects
            for x in cache:
                self.pop(x)
            raise e

    def pop(self, key, default=None):
        result = default
        current, stack = self._get_node_and_parent_stack(key)
        if current:
            if not stack:
                # Current is root
                self.root = None
                return StructuredHashTree(current)
            # We can remove the node and recalculate the tree
            # Subtree is returned as StructuredTree
            result = StructuredHashTree(current)
            stack[-1].remove_child(current.key)
            # Remove empty nodes in from the stack
            self._clear_stack_from_dummies(stack)
            if stack:
                self._recalculate_parents_stack(stack)
        return result

    def remove(self, key):
        if not self.pop(key):
            raise KeyError

    def clear(self, key):
        # Set the specific node as Dummy
        node, parents = self._get_node_and_parent_stack(key)
        if not node:
            return
        # Make node dummy
        node.dummy = True
        node.partial_hash = self._hash_attributes(key=key, _dummy=node.dummy)
        node.full_hash = None
        parents.append(node)
        # Cleanup parent list if node is a leaf
        self._clear_stack_from_dummies(parents)
        if parents:
            self._recalculate_parents_stack(parents)
        return node

    def find(self, key):
        return self._get_node_and_parent_stack(key)[0]

    def find_by_metadata(self, key, value):
        return self._find_by_metadata(key, value)

    def find_no_metadata(self, key):
        # Find all the nodes without a certain metadata key
        return self._find_by_metadata(key, None, False)

    def _find_by_metadata(self, key, value, present=True):
        # TODO(ivar): this is a linear search on the whole tree, make it more
        # efficient by storing nodes indexed by their metadata
        if not self.root:
            return []
        result = []
        visit = [self.root]
        for curr in visit:
            visit.extend(curr._children)
            try:
                if curr.metadata[key] == value and not curr.dummy and present:
                    result.append(curr.key)
            except KeyError:
                if not present and not curr.dummy:
                    result.append(curr.key)
        return result

    def diff(self, other):
        # Calculates the set of operations needed to transform other into self
        if not self.root:
            return {"add": [], "remove": self._get_subtree_keys(other.root)}
        if not other.root:
            return {"add": self._get_subtree_keys(self.root), "remove": []}
        childrenl = ChildrenList()
        childrenl.add(self.root)
        childrenr = ChildrenList()
        childrenr.add(other.root)
        result = {"add": [], "remove": []}
        self._diff_children(childrenl, childrenr, result)
        return result

    def has_subtree(self):
        return self.root and len(self.root._children) > 0

    def _diff_children(self, selfchildren, otherchildren, result):
        for othernode in otherchildren:
            if selfchildren.index(othernode.key) is None:
                # This subtree needs to be removed
                result['remove'] += self._get_subtree_keys(othernode)
            else:
                # Common child
                selfnode = selfchildren[othernode.key]
                if selfnode.partial_hash != othernode.partial_hash:
                    # Only evaluate differences for non error nodes
                    if not (othernode.error or selfnode.error):
                        if selfnode.dummy:
                            # Needs to be removed on the other tree
                            result['remove'].append(othernode.key)
                        else:
                            # Needs to be modified on the other tree
                            result['add'].append(othernode.key)
                if selfnode.full_hash != othernode.full_hash:
                    # Evaluate all their children
                    self._diff_children(selfnode._children,
                                        othernode._children, result)
        for node in selfchildren:
            if otherchildren.index(node.key) is None:
                # Whole subtree needs to be added
                result['add'] += self._get_subtree_keys(node)
            # Common nodes have already been evaluated in the previous loop

    def _get_subtree_keys(self, root):
        # traverse the tree and returns all its keys
        if not root:
            return []
        result = [root.key] if not (
            root.dummy or root.error) else []
        for node in root.get_children():
            result += self._get_subtree_keys(node)
        return result

    def _recalculate_parents_stack(self, parent_stack):
        # Recalculate full hashes navigating the stack backwards
        for node in parent_stack[::-1]:
            node.full_hash = self._hash(
                ''.join([node.partial_hash or ''] +
                        [x.full_hash for x in node.get_children()]))

    def _hash_attributes(self, **kwargs):
        return self._hash(json.dumps(collections.OrderedDict(
            sorted(list(kwargs.items()), key=lambda t: t[0]))))

    def _hash(self, string):
        # To avoid error in Py3:
        # Unicode-objects must be encoded before hashing
        # We encode the string to bytes
        return hashlib.sha256(string.encode('utf-8')).hexdigest()

    def __str__(self):
        return str(self.root or '{}')

    def __repr__(self):
        return '%s(%s)' % (super(StructuredHashTree, self).__repr__(),
                           str(self))

    def __eq__(self, other):
        if not other or not isinstance(other, StructuredHashTree):
            return False
        # Verify nodes are all equal
        return self._compare_subtrees(self.root, other.root)

    def _compare_subtrees(self, first, second):
        if first != second:
            # Covers case of one being None
            return False
        if not first:
            # Both are None
            return True
        # This also guarantees that Subtrees are identical
        return first.full_hash == second.full_hash

    def _is_node_removable(self, node):
        # A removable node has no children, and dummy
        return node.dummy and not node.get_children()

    def _get_node_and_parent_stack(self, key):
        not_found = None, []
        if not self.root:
            return not_found
        if self.root.key == key:
            return self.root, []
        elif self.root.key == (key[0],):
            parent = self.root
            stack = [parent]
            partial_key = (key[0],)
            for part in key[1:-1]:
                partial_key += (part,)
                parent = parent.get_child(partial_key)
                if not parent:
                    # Not Found
                    return not_found
                stack.append(parent)
            current = parent.get_child(key)
            return current, stack
        return not_found

    def _clear_stack_from_dummies(self, stack):
        for i in range(len(stack) - 1, -1, -1):
            node = stack[i]
            if self._is_node_removable(node):
                # Nodes with no partial hash and no children are
                # considered dummies and should be removed
                if i == 0:
                    # This is the root node
                    self.root = None
                else:
                    # Remove from parent
                    stack[i - 1].remove_child(node.key)
                # A node was removed and can be popped from the stack
                stack.pop()
            else:
                # One single non-dummy node in the stack is enough to
                # guarantee that there are no more
                break
