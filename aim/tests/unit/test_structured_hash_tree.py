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

import copy

from aim import aim_manager
from aim.api import resource
from aim.common.hashtree import exceptions as exc
from aim.common.hashtree import structured_tree as tree
from aim.tests import base
from aim import tree_manager


class TestStructuredNode(base.BaseTestCase):

    def setUp(self):
        super(TestStructuredNode, self).setUp()

    def test_initialize(self):
        node = tree.StructuredTreeNode(('key',), 'partial_hash',
                                       metadata={'foo': True})
        self.assertEqual(('key',), node.key)
        self.assertEqual('partial_hash', node.partial_hash)
        self.assertEqual('partial_hash', node.full_hash)
        self.assertTrue(isinstance(node._children, tree.ChildrenList))
        self.assertTrue(isinstance(node.get_children(), tuple))
        self.assertEqual({'foo': True}, node.metadata)
        self.assertEqual(
            ('{"key": ["key"], "partial_hash": "partial_hash", '
             '"full_hash": "partial_hash", "dummy": true, "error": false, '
             '"_children": [], "metadata": {"foo": true}}'),
            str(node))

    def test_set_child(self):
        # Test with default
        node = tree.StructuredTreeNode(('keyA',), 'partial_hashA')
        child = node.set_child(('keyA', 'keyB'))
        self.assertEqual(1, len(node.get_children()))
        self.assertTrue(isinstance(node.get_children()[0],
                                   tree.StructuredTreeNode))
        self.assertIs(child, node.get_children()[0])
        self.assertEqual(('keyA', 'keyB'), child.key)
        self.assertIsNone(child.partial_hash)

        # Test passing node
        child = node.set_child(('keyA', 'keyC'),
                               tree.StructuredTreeNode(('keyA', 'keyC'),
                                                       'partial_hashAC'))
        self.assertEqual(2, len(node.get_children()))
        self.assertEqual(('keyA', 'keyC'), child.key)
        self.assertEqual('partial_hashAC', child.partial_hash)

    def test_set_child_existing(self):
        node = tree.StructuredTreeNode(('keyA',), 'partial_hashA')
        child = node.set_child(('keyA', 'keyB'),
                               tree.StructuredTreeNode(('keyA', 'keyB'),
                                                       'partial_hashAB'))
        # Set again
        child_new = node.set_child(
            ('keyA', 'keyB'), tree.StructuredTreeNode(('keyA', 'keyB'),
                                                      'something_else'))
        self.assertIs(child, child_new)
        self.assertEqual('partial_hashAB', child_new.partial_hash)

    def test_replace_child(self):
        node = tree.StructuredTreeNode(('keyA',), 'partial_hashA')
        child = node.set_child(('keyA', 'keyB'),
                               tree.StructuredTreeNode(('keyA', 'keyB'),
                                                       'partial_hashAB'))
        # Replace
        child_new = node.replace_child(
            tree.StructuredTreeNode(('keyA', 'keyB'), 'something_else'))
        self.assertIsNot(child, child_new)
        self.assertEqual('something_else', child_new.partial_hash)

    def test_remove_child(self):
        node = tree.StructuredTreeNode(('keyA',), 'partial_hashA')
        # Nothing happens
        node.remove_child(('keyA', 'keyB'))
        # Add some children and then delete them
        node.replace_child(tree.StructuredTreeNode(('keyA', 'keyB'),
                                                   'partial_hashAB'))
        node.replace_child(tree.StructuredTreeNode(('keyA', 'keyC'),
                                                   'partial_hashAC'))
        node.replace_child(tree.StructuredTreeNode(('keyA', 'keyZ'),
                                                   'partial_hashAZ'))
        self.assertEqual(3, len(node._children))
        node.remove_child(('keyA', 'keyC'))
        # Verify the right one was removed
        self.assertEqual(
            (tree.StructuredTreeNode(('keyA', 'keyB')),
             tree.StructuredTreeNode(('keyA', 'keyZ'))), node.get_children())

    def test_get_child(self):
        node = tree.StructuredTreeNode(('keyA',), 'partial_hashA')
        node.replace_child(tree.StructuredTreeNode(('keyA', 'keyB'),
                                                   'partial_hashAB'))
        node.replace_child(tree.StructuredTreeNode(('keyA', 'keyC'),
                                                   'partial_hashAC'))
        node.replace_child(tree.StructuredTreeNode(('keyA', 'keyZ'),
                                                   'partial_hashAZ'))
        # Doesn't exist
        self.assertIsNone(node.get_child(('keyA', 'keyY')))
        # Returns Default on non existing
        self.assertEqual('nope',
                         node.get_child(('keyA', 'keyY'), default='nope'))
        # Found!
        self.assertEqual(tree.StructuredTreeNode(('keyA', 'keyC')),
                         node.get_child(('keyA', 'keyC')))
        # Adding Default doesn't change the result
        self.assertEqual(tree.StructuredTreeNode(('keyA', 'keyC')),
                         node.get_child(('keyA', 'keyC'), default='nope'))


class TestChildrenList(base.BaseTestCase):

    def setUp(self):
        super(TestChildrenList, self).setUp()

    def test_sorted_add(self):
        children = tree.ChildrenList()
        # Append some
        children.add(tree.StructuredTreeNode(('keyA', 'keyB')))
        self.assertEqual(0, children.index(('keyA', 'keyB')))
        children.add(tree.StructuredTreeNode(('keyA', 'keyC')))
        self.assertEqual(1, children.index(('keyA', 'keyC')))
        children.add(tree.StructuredTreeNode(('keyA', 'keyZ')))
        self.assertEqual(2, children.index(('keyA', 'keyZ')))
        # Insert in the middle
        children.add(tree.StructuredTreeNode(('keyA', 'keyD')))
        self.assertEqual(2, children.index(('keyA', 'keyD')))
        self.assertEqual(3, children.index(('keyA', 'keyZ')))
        # Insert in front
        children.add(tree.StructuredTreeNode(('keyA', 'key')))
        self.assertEqual(0, children.index(('keyA', 'key')))
        # Verify whole list
        self.assertEqual([tree.StructuredTreeNode(('keyA', 'key')),
                          tree.StructuredTreeNode(('keyA', 'keyB')),
                          tree.StructuredTreeNode(('keyA', 'keyC')),
                          tree.StructuredTreeNode(('keyA', 'keyD')),
                          tree.StructuredTreeNode(('keyA', 'keyZ'))],
                         children._stash)

    def test_index_not_found(self):
        children = tree.ChildrenList()
        # non existing elem
        self.assertIsNone(children.index('test'))

    def test_getitem(self):
        children = tree.ChildrenList()
        children.add(tree.StructuredTreeNode(('keyA', 'keyB')))
        children.add(tree.StructuredTreeNode(('keyA', 'keyC')))
        # Not found
        raised = False
        try:
            children[('keyA', 'keyD')]
        except KeyError:
            raised = True
        self.assertTrue(raised)
        self.assertEqual(children[('keyA', 'keyB')],
                         tree.StructuredTreeNode(('keyA', 'keyB')))

    def test_compare(self):
        # Same nodes, same list
        children1 = tree.ChildrenList()
        children1.add(tree.StructuredTreeNode(('keyA', 'keyB')))
        children1.add(tree.StructuredTreeNode(('keyA', 'keyC')))

        children2 = tree.ChildrenList()
        children2.add(tree.StructuredTreeNode(('keyA', 'keyC')))
        children2.add(tree.StructuredTreeNode(('keyA', 'keyB')))

        self.assertEqual(children1, children2)
        self.assertEqual(str(children1), str(children2))

        children2.add(tree.StructuredTreeNode(('keyA', 'keyD')))
        self.assertNotEqual(children1, children2)


class TestStructuredHashTree(base.BaseTestCase):

    def setUp(self):
        super(TestStructuredHashTree, self).setUp()

    def _tree_deep_check(self, root1, root2):
        if not root1 and not root2:
            return True
        if not root1:
            return False
        if not root2:
            return False
        if any(bool(getattr(root1, x) != getattr(root2, x))
               for x in root1.__slots__ if x != '_children'):
            return False
        if len(root1.get_children()) != len(root2.get_children()):
            return False
        if any(not self._tree_deep_check(root1.get_children()[x],
                                         root2.get_children()[x])
               for x in xrange(len(root1.get_children()))):
            return False
        return True

    def test_initialize(self):
        data = tree.StructuredHashTree()
        self.assertIsNone(data.root)
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')}])
        self.assertIsNotNone(data.root)
        self.assertEqual(('keyA',), data.root.key)

    def test_str(self):
        data = tree.StructuredHashTree()
        self.assertEqual("{}", str(data))
        data.add(('keyA', 'keyB', 'keyC'), **{})
        self.assertEqual(str(data.root), str(data))

    def test_add(self):
        # Add on empty root
        data = tree.StructuredHashTree()
        data.add(('keyA', 'keyB', 'keyC'), **{})
        self.assertEqual(('keyA',), data.root.key)
        full_hash_gramp1 = data.root.full_hash
        self.assertEqual(1, len(data.root.get_children()))
        self.assertEqual(('keyA', 'keyB'), data.root.get_children()[0].key)
        full_hash_father1 = data.find(('keyA', 'keyB')).full_hash
        self.assertEqual(1, len(data.root.get_children()[0].get_children()))
        self.assertEqual(('keyA', 'keyB', 'keyC'),
                         data.root.get_children()[0].get_children()[0].key)
        full_hash_first_child1 = data.find(('keyA', 'keyB', 'keyC')).full_hash
        # No extra children added
        self.assertEqual(
            0,
            len(data.root.get_children()[0].get_children()[0].get_children()))
        # Adding extra node will change full hashes
        data.add(('keyA', 'keyB', 'keyCA'), **{})
        full_hash_second_child1 = data.find(('keyA', 'keyB',
                                             'keyCA')).full_hash
        # This new node changed its parents' hash
        full_hash_gramp2 = data.root.full_hash
        full_hash_father2 = data.find(('keyA', 'keyB')).full_hash
        full_hash_first_child2 = data.find(('keyA', 'keyB', 'keyC')).full_hash
        # Gramps hash is different
        self.assertNotEqual(full_hash_gramp1, full_hash_gramp2)
        # Father hash is different
        self.assertNotEqual(full_hash_father1, full_hash_father2)
        # First child hash is untouched
        self.assertEqual(full_hash_first_child1, full_hash_first_child2)

        # Adding already existing Node replaces it
        data.add(('keyA', 'keyB', 'keyCA'), **{'new_attr': 'new_value'})
        full_hash_second_child2 = data.find(('keyA', 'keyB',
                                             'keyCA')).full_hash
        # Second child hash changed
        self.assertNotEqual(full_hash_second_child1, full_hash_second_child2)
        # Gramps hash is different
        self.assertNotEqual(full_hash_gramp2, data.root.full_hash)
        # Father hash is different
        self.assertNotEqual(full_hash_father2,
                            data.find(('keyA', 'keyB')).full_hash)
        # First child hash is untouched
        self.assertEqual(full_hash_first_child2,
                         data.find(('keyA', 'keyB', 'keyC')).full_hash)

    def test_add_none_key(self):
        data = tree.StructuredHashTree()
        retured = data.add(None)
        # Nothing happened
        self.assertEqual(data, retured)

    def test_add_multiple_heads(self):
        data = tree.StructuredHashTree().add(('keyA', 'keyB'))
        self.assertRaises(exc.MultipleRootTreeError, data.add, ('keyA1',
                                                                'keyB'))

    def test_add_with_metadata(self):
        t = tree.StructuredHashTree()

        # new node with no metadata
        node = t.add(('keyA', 'keyA')).find(('keyA', 'keyA'))
        self.assertIsNotNone(node)
        self.assertEqual({}, node.metadata)

        # new node with metadata
        t.add(('keyA', 'keyB'), _metadata={"foo": 1})
        node = t.find(('keyA', 'keyB'))
        self.assertIsNotNone(node)
        self.assertEqual({'foo': 1}, node.metadata)
        self.assertEqual({}, t.root.metadata)

        # existing node, no metadata change
        node = t.add(('keyA', 'keyB')).find(('keyA', 'keyB'))
        self.assertIsNotNone(node)
        self.assertEqual({'foo': 1}, node.metadata)

        # existing node, metadata change
        t.add(('keyA', 'keyB'), _metadata={"bar": 2})
        node = t.find(('keyA', 'keyB'))
        self.assertIsNotNone(node)
        self.assertEqual({'bar': 2}, node.metadata)

        # existing node, unset metadata
        t.add(('keyA', 'keyB'), _metadata=None)
        node = t.find(('keyA', 'keyB'))
        self.assertIsNotNone(node)
        self.assertEqual({}, node.metadata)

    def test_include_with_metadata(self):
        t = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB'), '_metadata': {"foo": 1}},
             {'key': ('keyA', 'keyC'), '_metadata': {"bar": 2}},
             {'key': ('keyA', 'keyC', 'keyD')}])
        node = t.find(('keyA', 'keyB'))
        self.assertIsNotNone(node)
        self.assertEqual({'foo': 1}, node.metadata)

        node = t.find(('keyA', 'keyC'))
        self.assertIsNotNone(node)
        self.assertEqual({'bar': 2}, node.metadata)

        node = t.find(('keyA', 'keyC', 'keyD'))
        self.assertIsNotNone(node)
        self.assertEqual({}, node.metadata)

        # change the metadata values
        t.include(
            [{'key': ('keyA', 'keyB'), '_metadata': None},
             {'key': ('keyA', 'keyC'), '_metadata': {"bar": 2}},
             {'key': ('keyA', 'keyC', 'keyD'), '_metadata': {"baz": 3}}])
        node = t.find(('keyA', 'keyB'))
        self.assertIsNotNone(node)
        self.assertEqual({}, node.metadata)

        node = t.find(('keyA', 'keyC'))
        self.assertIsNotNone(node)
        self.assertEqual({'bar': 2}, node.metadata)

        node = t.find(('keyA', 'keyC', 'keyD'))
        self.assertIsNotNone(node)
        self.assertEqual({"baz": 3}, node.metadata)

    def test_include_rolled_back(self):
        # Cause an exception during include and verify that nothing changed
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        data_copy = copy.deepcopy(data)
        self.assertRaises(
            exc.MultipleRootTreeError, data.include,
            [{'key': ('keyA', 'keyF')}, {'key': ('keyA', 'keyG')},
             {'key': ('keyA1', 'keyC', 'keyD')}])
        # Verify everything is rolled back
        self.assertEqual(data, data_copy)

    def test_pop(self):
        data = tree.StructuredHashTree()
        self.assertIsNone(data.pop(('keyA',)))
        data.add(('keyA', 'keyB'))
        data_copy = copy.deepcopy(data)

        data2 = data.pop(('keyA',))

        self.assertIsNone(data.root)
        self.assertEqual(data_copy, data2)

        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])

        # Key not found
        self.assertIsNone(data.pop(('keyA', 'keyF', 'keyE')))

    def test_pop_dummies(self):
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC', 'keyD')}])
        # Removing keyD, keyC will also be removed
        data.pop(('keyA', 'keyC', 'keyD'))
        expected = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}])
        self.assertEqual(expected, data)

        # Popping keyB will now also pop the root
        data.pop(('keyA', 'keyB'))
        self.assertIsNone(data.root)

    def test_clear(self):
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA',)}, {'key': ('keyA', 'keyB')},
             {'key': ('keyA', 'keyB', 'keyC')}])
        data_copy = tree.StructuredHashTree().from_string(str(data))
        data.clear(('keyA', 'keyB', 'keyNO'))
        self.assertEqual(data_copy, data)
        self.assertEqual(1, len(data.root.get_children()))
        self.assertFalse(data.root.get_children()[0].dummy)
        data.clear(('keyA', 'keyB'))
        self.assertTrue(data.root.get_children()[0].dummy)
        self.assertNotEqual(data_copy, data)
        data.clear(('keyA', 'keyB', 'keyC'))
        # Dummies removed
        self.assertEqual(0, len(data.root.get_children()))

    def test_find(self):
        data = tree.StructuredHashTree()
        # root None
        self.assertIsNone(data.find(('KeyA',)))
        data.add(('KeyA',))
        # root is Key
        self.assertEqual(data.root, data.find(('KeyA',)))
        # Not found
        self.assertIsNone(data.find(('KeyA', 'KeyB')))
        # Multi Head reserach
        self.assertIsNone(data.find(('KeyZ', 'KeyB')))

    def test_compare_trees(self):
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        # Data equals itself
        self.assertTrue(data == data)

        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        # They are the same
        self.assertTrue(data == data2)
        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD'), 'attr': 'some_attr'}])
        # Hash will change
        self.assertTrue(data != data2)

        # Replace that node and converge the situation
        data2.add(('keyA', 'keyC', 'keyD'), **{})
        self.assertTrue(data == data2)

        # data3 is completely different
        data3 = tree.StructuredHashTree().include(
            [{'key': ('keyA1', 'keyB')}, {'key': ('keyA1', 'keyC')},
             {'key': ('keyA1', 'keyC', 'keyD')}])
        self.assertFalse(data == data3)
        self.assertFalse(data == None)
        self.assertFalse(data == 'notatree')

        # compare with metadata
        data4 = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB'), '_metadata': {'a': 1}},
             {'key': ('keyA', 'keyC'), '_metadata': {'b': 1}},
             {'key': ('keyA', 'keyC', 'keyD')}])
        self.assertTrue(data4 == data)
        node = data4.find(('keyA', 'keyB'))
        self.assertEqual(1, node.metadata['a'])

    def test_remove(self):
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')}])
        self.assertNotEqual(data.root.full_hash, data2.root.full_hash)
        data.remove(('keyA', 'keyC', 'keyD'))
        self.assertEqual(data2, data)

        # Raises on NotFound
        self.assertRaises(KeyError, data.remove, ('keyA', 'keyC', 'keyZ'))
        # Nothing happened
        self.assertEqual(data2, data)

    def test_diff(self):
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')}])

        # data has no difference with itself
        self.assertEqual({"add": [], "remove": []}, data.diff(data))

        # To obtain data from data2, ('keyA', 'keyC', 'keyD') needs to be added
        self.assertEqual({"add": [('keyA', 'keyC', 'keyD')], "remove": []},
                         data.diff(data2))

        # To obtain data2 from data1, ('keyA', 'keyC', 'keyD') needs to be
        # removed
        self.assertEqual({"add": [], "remove": [('keyA', 'keyC', 'keyD')]},
                         data2.diff(data))

        data2.add(('keyA', 'keyC', 'keyF'), **{})
        data2.add(('keyA',), **{'attr': 'somevalue'})

        # To obtain data from data2:
        # add ('keyA', 'keyC', 'keyD')
        # remove ('keyA', 'keyC', 'keyF')
        # modify ('keyA', )

        self.assertEqual({"add": [('keyA',), ('keyA', 'keyC', 'keyD')],
                          "remove": [('keyA', 'keyC', 'keyF')]},
                         data.diff(data2))

        # Opposite for going from data to data2
        self.assertEqual({"add": [('keyA',), ('keyA', 'keyC', 'keyF')],
                          "remove": [('keyA', 'keyC', 'keyD')]},
                         data2.diff(data))

        # Data3 is a completely different tree
        data3 = tree.StructuredHashTree().include(
            [{'key': ('keyA1', 'keyB')}, {'key': ('keyA1', 'keyC')},
             {'key': ('keyA1', 'keyC', 'keyD')}])

        # The whole tree needs to be modified for going from data3 to data
        self.assertEqual({"add": [('keyA', 'keyB'),
                                  ('keyA', 'keyC'), ('keyA', 'keyC', 'keyD')],
                          "remove": [('keyA1', 'keyB'),
                                     ('keyA1', 'keyC'),
                                     ('keyA1', 'keyC', 'keyD')]},
                         data.diff(data3))

    def test_from_string(self):
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB'), '_metadata': {'a': 20}},
             {'key': ('keyA', 'keyC'), '_metadata': {'b': False}},
             {'key': ('keyA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree.from_string(str(data))
        self.assertTrue(data is not data2)
        self.assertEqual(data, data2)
        self.assertTrue(self._tree_deep_check(data.root, data2.root))

    def test_list_keys(self):
        data = tree.StructuredHashTree().include(
            [{'key': (['keyA', ], ['keyB', 'keykeyB'])},
             {'key': (['keyA', ], ['keyC', 'keykeyC'])},
             {'key': (['keyA', ], ['keyC', 'keykeyC'], ['keyD', ])}])
        data2 = tree.StructuredHashTree.from_string(str(data))
        self.assertTrue(data is not data2)
        self.assertEqual(data, data2)
        self.assertTrue(self._tree_deep_check(data.root, data2.root))

    def test_error_nodes(self):

        data = tree.StructuredHashTree().include(
            [{'key': ('keyA',)},
             {'key': ('keyA', 'keyC'), '_error': True},
             {'key': ('keyA', 'keyB')},
             {'key': ('keyA', 'keyC', 'keyD')}])

        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA',)},
             {'key': ('keyA', 'keyC'), 'foo': 'bar'},
             {'key': ('keyA', 'keyB')},
             {'key': ('keyA', 'keyC', 'keyD')}])

        # The diff will be empty since the only different node is in error
        # state
        self.assertEqual({"add": [], "remove": []}, data.diff(data2))
        self.assertEqual({"add": [], "remove": []}, data2.diff(data))

        # Remove the error state to get the difference
        data.add(('keyA', 'keyC'))
        self.assertEqual({"add": [('keyA', 'keyC')], "remove": []},
                         data.diff(data2))
        self.assertEqual({"add": [('keyA', 'keyC')], "remove": []},
                         data2.diff(data))

        # Set error state again, but change child
        data.add(('keyA', 'keyC'), _error=True)
        data.add(('keyA', 'keyC', 'keyD'), foo='bar')
        # Child difference will be noticed
        self.assertEqual({"add": [('keyA', 'keyC', 'keyD')], "remove": []},
                         data.diff(data2))
        self.assertEqual({"add": [('keyA', 'keyC', 'keyD')], "remove": []},
                         data2.diff(data))
        # Same goes for extra subtree
        data.add(('keyA', 'keyC', 'keyE'))
        self.assertEqual({"add": [('keyA', 'keyC', 'keyD'),
                                  ('keyA', 'keyC', 'keyE')],
                          "remove": []},
                         data.diff(data2))
        self.assertEqual({"add": [('keyA', 'keyC', 'keyD')],
                          "remove": [('keyA', 'keyC', 'keyE')]},
                         data2.diff(data))


class TestHashTreeExceptions(base.BaseTestCase):

    def setUp(self):
        super(TestHashTreeExceptions, self).setUp()

    def test_base_exception(self):
        # Base message
        ex = exc.HashTreeException()
        self.assertEqual(ex.message, str(ex))

        # Exception in message parsing
        self.assertRaises(KeyError, exc.MultipleRootTreeError, randomkey=None)


class TestHashTreeManager(base.TestAimDBBase):

    def setUp(self):
        super(TestHashTreeManager, self).setUp()
        self.mgr = tree_manager.TreeManager(tree.StructuredHashTree)

    def test_update(self):
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        self.mgr.update(self.ctx, data)

        data2 = self.mgr.find(self.ctx, root_rn=['keyA'])[0]
        self.assertEqual(data, data2)

        # Change an existing tree
        data.add(('keyA', 'keyF'), test='test')
        self.mgr.update(self.ctx, data)
        data3 = self.mgr.find(self.ctx, root_rn=['keyA'])[0]
        self.assertEqual(data, data3)
        self.assertNotEqual(data, data2)

        # Empty the tree completely
        data3.remove(('keyA',))
        self.assertEqual(('keyA',), data3.root_key)
        self.mgr.update(self.ctx, data3)
        data4 = self.mgr.find(self.ctx, root_rn=['keyA'])[0]
        # Verify this is an empty tree
        self.assertIsNone(data4.root)
        self.assertEqual(data3.root_key, data4.root_key)

    def test_update_bulk(self):
        data1 = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA1', 'keyB')}, {'key': ('keyA1', 'keyC')},
             {'key': ('keyA1', 'keyC', 'keyD')}])

        self.mgr.update_bulk(self.ctx, [data1, data2])
        found = {'keyA': None, 'keyA1': None}
        result = self.mgr.find(self.ctx, root_rn=['keyA', 'keyA1'])
        found[result[0].root.key[0]] = result[0]
        found[result[1].root.key[0]] = result[1]
        self.assertEqual(data1, found['keyA'])
        self.assertEqual(data2, found['keyA1'])

        # Change an existing tree
        data1.add(('keyA', 'keyF'), test='test')
        self.mgr.update_bulk(self.ctx, [data1, data2])
        found2 = {'keyA': None, 'keyA1': None}
        result = self.mgr.find(self.ctx, root_rn=['keyA', 'keyA1'])
        found2[result[0].root.key[0]] = result[0]
        found2[result[1].root.key[0]] = result[1]

        self.assertEqual(data1, found2['keyA'])
        self.assertNotEqual(data1, found['keyA'])
        self.assertEqual(data2, found['keyA1'])
        self.assertEqual(data2, found2['keyA1'])

    def test_deleted(self):
        data = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        self.mgr.update(self.ctx, data)
        self.mgr.delete(self.ctx, data)
        self.assertEqual([], self.mgr.find(self.ctx, root_rn=['keyA']))

    def test_deleted_bulk(self):
        data1 = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA1', 'keyB')}, {'key': ('keyA1', 'keyC')},
             {'key': ('keyA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('keyA2', 'keyB')}, {'key': ('keyA2', 'keyC')},
             {'key': ('keyA2', 'keyC', 'keyD')}])

        self.mgr.update_bulk(self.ctx, [data1, data2, data3])
        self.mgr.delete_bulk(self.ctx, [data1, data2])
        self.assertEqual([], self.mgr.find(self.ctx,
                                           root_rn=['keyA', 'keyA1']))
        # data3 still persists
        self.assertEqual([data3], self.mgr.find(self.ctx, root_rn=['keyA2']))

    def test_find_changed(self):
        data1 = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA1', 'keyB')}, {'key': ('keyA1', 'keyC')},
             {'key': ('keyA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('keyA2', 'keyB')}, {'key': ('keyA2', 'keyC')},
             {'key': ('keyA2', 'keyC', 'keyD')}])

        self.mgr.update_bulk(self.ctx, [data1, data2, data3])
        data1.add(('keyA',), test='test')
        changed = self.mgr.find_changed(
            self.ctx, {data1.root.key[0]: data1.root.full_hash,
                       data2.root.key[0]: data2.root.full_hash,
                       data3.root.key[0]: data3.root.full_hash})
        self.assertEqual(1, len(changed))
        self.assertEqual(data1.root.key, changed.values()[0].root.key)

    def test_get_tenants(self):
        data1 = tree.StructuredHashTree().include(
            [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
             {'key': ('keyA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('keyA1', 'keyB')}, {'key': ('keyA1', 'keyC')},
             {'key': ('keyA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('keyA2', 'keyB')}, {'key': ('keyA2', 'keyC')},
             {'key': ('keyA2', 'keyC', 'keyD')}])

        self.mgr.update_bulk(self.ctx, [data1, data2, data3])
        tenants = self.mgr.get_roots(self.ctx)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']), set(tenants))

    def test_single_session_multi_objects(self):
        with self.ctx.store.begin(subtransactions=True):
            data = tree.StructuredHashTree().include(
                [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
                 {'key': ('keyA', 'keyC', 'keyD')}])
            self.mgr.update(self.ctx, data)
            agent = resource.Agent(id='test', agent_type='aid', host='host3',
                                   binary_file='binary', hash_trees=['keyA'],
                                   version='1.0')
            agent = aim_manager.AimManager().create(self.ctx, agent)

        # Creation worked
        self.assertEqual('test', agent.id)
        data2 = self.mgr.find(self.ctx, root_rn=['keyA'])[0]
        self.assertEqual(['keyA'], agent.hash_trees)
        self.assertEqual(data, data2)

    def test_agents_to_trees_association(self):
        # N, M association
        with self.ctx.store.begin(subtransactions=True):
            data = tree.StructuredHashTree().include(
                [{'key': ('keyA', 'keyB')}, {'key': ('keyA', 'keyC')},
                 {'key': ('keyA', 'keyC', 'keyD')}])
            data2 = tree.StructuredHashTree().include(
                [{'key': ('keyA1', 'keyB')}, {'key': ('keyA1', 'keyC')},
                 {'key': ('keyA1', 'keyC', 'keyD')}])
            data3 = tree.StructuredHashTree().include(
                [{'key': ('keyA2', 'keyB')}, {'key': ('keyA2', 'keyC')},
                 {'key': ('keyA2', 'keyC', 'keyD')}])
            self.mgr.update_bulk(self.ctx, [data, data2, data3])
            agent1 = resource.Agent(agent_type='aid', host='host',
                                    binary_file='binary',
                                    hash_trees=['keyA', 'keyA1', 'keyA2'],
                                    version='1.0')
            agent2 = resource.Agent(agent_type='aid', host='host2',
                                    binary_file='binary',
                                    hash_trees=['keyA', 'keyA2'],
                                    version='1.0')
            agent1 = aim_manager.AimManager().create(self.ctx, agent1)
            agent2 = aim_manager.AimManager().create(self.ctx, agent2)
        self.assertEqual(set(['keyA', 'keyA1', 'keyA2']),
                         set(agent1.hash_trees))
        self.assertEqual(set(['keyA', 'keyA2']), set(agent2.hash_trees))
        # Empty agent2
        agent2 = aim_manager.AimManager().update(self.ctx, agent2,
                                                 hash_trees=[])
        # Delete a tree
        self.ctx.store.expunge_all()
        self.mgr.delete(self.ctx, data)
        if self.ctx.store.supports_foreign_keys:
            agent1 = aim_manager.AimManager().get(self.ctx, agent1)
            self.assertEqual(set(['keyA1', 'keyA2']), set(agent1.hash_trees))
            self.assertEqual(set(), set(agent2.hash_trees))
            # Add rogue key
            self.assertRaises(
                exc.HashTreeNotFound, aim_manager.AimManager().update,
                self.ctx, agent1, hash_trees=['notakey'])
            # Verify agent1 was rolled back properly
            agent1 = aim_manager.AimManager().get(self.get_new_context(),
                                                  agent1)
            self.assertEqual(set(['keyA1', 'keyA2']), set(agent1.hash_trees))


class TestAimHashTreeMaker(base.TestAimDBBase):

    def setUp(self):
        super(TestAimHashTreeMaker, self).setUp()
        self.maker = tree_manager.AimHashTreeMaker()

    def test_get_root_key(self):
        bd = self._get_example_aim_bd(tenant_name='t1', name='bd1')
        self.assertEqual('tn-t1', self.maker.get_root_key(bd))

        bd.tenant_name = 't2'
        self.assertEqual('tn-t2', self.maker.get_root_key(bd))

        class InvalidResource(resource.AciResourceBase):
            _aci_mo_name = 'fvFoo'
            _tree_parent = resource.BridgeDomain
            identity_attributes = []
            other_attributes = []

            def __init__(self):
                super(InvalidResource, self).__init__({})

        self.assertIsNone(self.maker.get_root_key(InvalidResource()))

    def test_update(self):
        htree = tree.StructuredHashTree()
        exp_tree = tree.StructuredHashTree()

        bd = self._get_example_aim_bd(tenant_name='t1', name='bd1')
        subnet = resource.Subnet(tenant_name='t1', bd_name='bd1',
                                 gw_ip_mask='10.0.0.1/24')

        fvBD_attr = {'arpFlood': 'no',
                     'epMoveDetectMode': '',
                     'limitIpLearnToSubnets': 'no',
                     'ipLearning': 'yes',
                     'unicastRoute': 'yes',
                     'unkMacUcastAct': 'proxy',
                     'nameAlias': ''}
        fvRsCtx_attr = {'tnFvCtxName': 'default'}
        fvSubnet_attr = {'scope': 'public',
                         'nameAlias': ''}

        self.maker.update(htree, [bd, subnet])

        bd_key = ('fvTenant|t1', 'fvBD|bd1')
        rsctx_key = ('fvTenant|t1', 'fvBD|bd1', 'fvRsCtx|rsctx')
        subnet_key = ('fvTenant|t1', 'fvBD|bd1', 'fvSubnet|10.0.0.1/24')

        exp_tree.add(bd_key, **fvBD_attr)
        exp_tree.add(rsctx_key, **fvRsCtx_attr)
        exp_tree.add(subnet_key, **fvSubnet_attr)
        self.assertEqual(exp_tree, htree)
        self.assertEqual({}, htree.find(bd_key).metadata)
        self.assertEqual({'related': True},
                         htree.find(rsctx_key).metadata)
        self.assertEqual({}, htree.find(subnet_key).metadata)

        bd.name = 'bd2'
        subnet.bd_name = 'bd2'
        self.maker.update(htree, [bd, subnet])

        bd_key = ('fvTenant|t1', 'fvBD|bd2')
        rsctx_key = ('fvTenant|t1', 'fvBD|bd2', 'fvRsCtx|rsctx')
        subnet_key = ('fvTenant|t1', 'fvBD|bd2', 'fvSubnet|10.0.0.1/24')
        exp_tree.add(bd_key, **fvBD_attr)
        exp_tree.add(rsctx_key, **fvRsCtx_attr)
        exp_tree.add(subnet_key, **fvSubnet_attr)
        self.assertEqual(exp_tree, htree)

        fvBD_attr['unkMacUcastAct'] = 'flood'
        fvRsCtx_attr = {'tnFvCtxName': 'shared'}
        bd.l2_unknown_unicast_mode = 'flood'
        bd.vrf_name = 'shared'
        self.maker.update(htree, [bd])

        exp_tree = exp_tree.add(('fvTenant|t1', 'fvBD|bd2'), **fvBD_attr)
        exp_tree.add(('fvTenant|t1', 'fvBD|bd2', 'fvRsCtx|rsctx'),
                     **fvRsCtx_attr)
        self.assertEqual(exp_tree, htree)
        self.assertEqual(exp_tree, htree)
        self.assertEqual({}, htree.find(bd_key).metadata)
        self.assertEqual({'related': True},
                         htree.find(rsctx_key).metadata)
        self.assertEqual({}, htree.find(subnet_key).metadata)

    def test_update_1(self):
        htree = tree.StructuredHashTree()
        exp_tree = tree.StructuredHashTree()

        subj = resource.ContractSubject(tenant_name='t1', contract_name='c1',
                                        name='s1', in_filters=['i1'],
                                        out_filters=['o1'], bi_filters=['f1'])
        self.maker.update(htree, [subj])

        exp_tree = exp_tree.add(('fvTenant|t1', 'vzBrCP|c1', 'vzSubj|s1'),
                                nameAlias='')
        exp_tree = exp_tree.add(
            ('fvTenant|t1', 'vzBrCP|c1', 'vzSubj|s1',
             'vzInTerm|intmnl', 'vzRsFiltAtt|i1'),
            tnVzFilterName='i1')
        exp_tree = exp_tree.add(
            ('fvTenant|t1', 'vzBrCP|c1', 'vzSubj|s1',
             'vzOutTerm|outtmnl', 'vzRsFiltAtt|o1'),
            tnVzFilterName='o1')
        exp_tree = exp_tree.add(
            ('fvTenant|t1', 'vzBrCP|c1', 'vzSubj|s1', 'vzRsSubjFiltAtt|f1'),
            tnVzFilterName='f1')
        exp_tree = exp_tree.add(
            ('fvTenant|t1', 'vzBrCP|c1', 'vzSubj|s1',
             'vzRsSubjGraphAtt|rsSubjGraphAtt'),
            tnVnsAbsGraphName='')
        exp_tree = exp_tree.add(
            ('fvTenant|t1', 'vzBrCP|c1', 'vzSubj|s1',
             'vzInTerm|intmnl', 'vzRsInTermGraphAtt|rsInTermGraphAtt'),
            tnVnsAbsGraphName='')
        exp_tree = exp_tree.add(
            ('fvTenant|t1', 'vzBrCP|c1', 'vzSubj|s1',
             'vzOutTerm|outtmnl', 'vzRsOutTermGraphAtt|rsOutTermGraphAtt'),
            tnVnsAbsGraphName='')
        self.assertEqual(exp_tree, htree)

    def test_delete(self):
        bd1 = self._get_example_aim_bd(tenant_name='t1', name='bd1')
        bd2 = self._get_example_aim_bd(tenant_name='t1', name='bd2')

        htree = tree.StructuredHashTree()
        self.maker.update(htree, [bd1, bd2])

        self.maker.delete(htree, [bd1])

        fvBD_attr = {'arpFlood': 'no',
                     'epMoveDetectMode': '',
                     'limitIpLearnToSubnets': 'no',
                     'ipLearning': 'yes',
                     'unicastRoute': 'yes',
                     'unkMacUcastAct': 'proxy',
                     'nameAlias': ''}
        fvRsCtx_attr = {'tnFvCtxName': 'default'}

        exp_tree = tree.StructuredHashTree()
        exp_tree = exp_tree.add(('fvTenant|t1', 'fvBD|bd2'), **fvBD_attr)
        exp_tree = exp_tree.add(('fvTenant|t1', 'fvBD|bd2', 'fvRsCtx|rsctx'),
                                **fvRsCtx_attr)
        self.assertEqual(exp_tree, htree)

        self.maker.delete(htree, [bd2])
        self.assertFalse(htree.has_subtree())
