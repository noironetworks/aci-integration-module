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

import bisect
from hashlib import md5
from oslo_serialization import base64 as b64


class Star:
    __slots__ = ['h4sh', 'node']

    def __init__(self, h4sh, node=None):
        self.h4sh = h4sh
        self.node = node

    def __cmp__(self, other):
        return self.h4sh.__cmp__(other.h4sh)

    def __eq__(self, other):
        return self.h4sh == other.h4sh

    def __lt__(self, other):
        return self.h4sh < other.h4sh

    def __str__(self):
        return str(self.node)


class ConsistentHashRing(object):
    """Consistent Hash Ring

    Consistent hashing implementation that spreads nodes of a cluster into
    a ring, and assigns Keys based on the position of the ring they end into
    given a specific hash function.
    This implementation uses md5 hash algorithm and supports configurable
    vnodes number (the higher the better distributed) and Key replicas (eg.
    Same key can be served by multiple nodes in the cluster).

    This is NOT a key-value storage! The main and only purpose of this class is
    to calculate consistent key allocation into a node cluster.

    This class is not thread safe, but guarantees is results to be reproducible
    by different instances given the same configuration.
    """

    def __init__(self, nodes=None, vnodes=40, replicas=1, default_weight=1):
        """ConsistentHashRing initialization.

        :param nodes: Initial node set, the expected format is a dictionary
        with the node ID as key and its weight as value. Weight can be set to
        None to use the default value.
        :param vnodes: Number of stars for each node constellation, the bigger
        the constellations the more evenly distributed the keys will be.
        Default value is evolving based on experimental knowledge.
        :param replicas: Number of nodes that each given key has to cover for
        high availability. This number is obviously limited by the total number
        of nodes in the cluster.
        :param default_weight: Weight value to be used for nodes when not
        specified.
        :return:
        """
        self._nodes = {}
        self._ring = []
        self._vnodes = vnodes
        self._replicas = replicas
        self._default_weight = default_weight
        self.add_nodes(nodes or {})

    def _hashi(self, node, weight):
        """Hash iterator for a given node

        :return:
        """
        weight = weight if weight is not None else self._default_weight
        vnodes = self._vnodes * weight
        for x in range(vnodes):
            yield self._hash(str(node) + str(x))

    def _hash(self, key):
        return int(md5(b64.encode_as_bytes(key)).hexdigest(), 16)

    def add_node(self, node, weight=None):
        """Add a node to the ring

        :param node: node unique identifier
        :param weight:
        :return:
        """
        self.add_nodes({node: weight})

    def add_nodes(self, nodes):
        """Add multiple nodes to the ring

        :param nodes: The expected format is a dictionary
        with the node ID as key and its weight as value. Weight can be set to
        None to use the default value.
        :return:
        """

        # Remove nodes already in the ring, this could be a weight update
        # operation
        self.remove_nodes(set(self._nodes.keys()) & set(nodes.keys()))
        for node, weight in list(nodes.items()):
            for h4sh in self._hashi(node, weight):
                bisect.insort(self._ring, Star(h4sh, node))
        self._nodes.update(nodes)

    def remove_node(self, node):
        """Remove a single node from the ring

        :param node:
        :return:
        """
        self.remove_nodes([node])

    def remove_nodes(self, nodes):
        """Remove a set of nodes from the ring

        :param nodes:
        :return:
        """
        for node in nodes:
            if node not in self._nodes:
                continue
            weight = self._nodes.pop(node, None)
            for x in self._hashi(node, weight):
                try:
                    self._ring.remove(Star(x))
                except ValueError:
                    pass

    def assign_key(self, key):
        """Assign a key to the ring

        :param key: identifier
        :return: list of nodes that serve this key
        """
        index = bisect.bisect(self._ring, Star(self._hash(key)))
        if index == len(self._ring):
            index = 0
        result = [self._ring[index].node]
        # Replicate across the ring in anti clockwise motion
        for x in range(len(self._ring)):
            if len(result) == self._replicas:
                # We have enough candidates
                break
            if self._ring[index - x].node not in result:
                result.append(self._ring[index - x].node)
        return result

    def __len__(self):
        return len(self._nodes)
