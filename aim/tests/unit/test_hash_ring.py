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

import uuid

from aim.common import hashring
from aim.tests import base


class TestHashRing(base.BaseTestCase):

    def setUp(self):
        super(TestHashRing, self).setUp()

    def _count_replicas(self, ring, key):
        x = 0
        for star in ring._ring:
            if star.node == key:
                x += 1
        return x

    def test_init(self):
        ring = hashring.ConsistentHashRing(
            dict((str(x), None) for x in range(10)))
        self.assertEqual(10, len(ring))

    def test_proportional_weight(self):
        ring = hashring.ConsistentHashRing({'a': 1, 'b': 2, 'c': 3})
        a_count = self._count_replicas(ring, 'a')
        b_count = self._count_replicas(ring, 'b')
        c_count = self._count_replicas(ring, 'c')

        self.assertEqual(a_count * 2, b_count)
        self.assertEqual(a_count * 3, c_count)

    def test_replicas(self):
        # One one, only one replica regardless
        ring = hashring.ConsistentHashRing({'a': None})
        allocation = ring.assign_key('somekey')
        self.assertEqual(allocation, ['a'])

        # Add a node and recheck the allocation
        ring.add_node('b', None)
        allocation = ring.assign_key('somekey')
        self.assertEqual(set(allocation), set(['a', 'b']))

        # Add another node, result is always 2
        ring.add_node('c', None)
        allocation = ring.assign_key('somekey')
        self.assertEqual(2, len(allocation))

    def test_consistency(self):
        # Create many rings with all the same cluster, and verify that
        # they get the same result for different keys
        cluster = dict([(str(x), None) for x in range(100)])

        # 10 rings
        rings = [hashring.ConsistentHashRing(cluster) for x in range(10)]
        # They are all different instances with the same configuration,
        # keys must be assigned in the same way
        # Hash 100 keys
        for x in range(100):
            key = str(uuid.uuid4())
            result = set(tuple(y.assign_key(key)) for y in rings)
            self.assertEqual(1, len(result))
            self.assertEqual(2, len(result.pop()))

        # Remove one key from all the rings and the result is the same
        for ring in rings:
            ring.remove_node('9')

        # Still consistently hashed
        for x in range(100):
            key = str(uuid.uuid4())
            result = set(tuple(y.assign_key(key)) for y in rings)
            self.assertEqual(1, len(result))
            self.assertEqual(2, len(result.pop()))

    def test_remove_non_existing_node(self):
        ring = hashring.ConsistentHashRing({'a': None})
        ring.remove_node('b')
        # Nothing happened
        self.assertEqual(1, len(ring))

    def test_update_weight(self):
        ring = hashring.ConsistentHashRing({'a': 1, 'b': 2, 'c': 3})
        a_count = self._count_replicas(ring, 'a')

        ring.add_node('a', 6)
        a_count2 = self._count_replicas(ring, 'a')
        self.assertEqual(6, a_count2 / a_count)
