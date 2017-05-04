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

import ast
import copy
import json
from six import iteritems

from aim.api import types
try:
    from kubernetes import client
    from kubernetes.client import api_client as klient
    from kubernetes.client import rest
    from kubernetes import config as konfig
    from kubernetes import watch

    # K8S client is logging too much, restrict their log level
    rest.logger.setLevel('INFO')
except ImportError:
    pass

from aim.common import utils


K8S_DEFAULT_NAMESPACE = 'default'
K8S_API_VERSION_CORE_V1 = 'v1'
K8S_API_VERSION_EXTENSIONS_V1BETA1 = 'extensions/v1beta1'


class K8sObject(dict):
    # Base class for all Kubernetes objects.
    # Override the follow functions to customize behavior
    # - from_attr() -> update this K8s object from AIM attribute dictionary
    # - to_attr() -> create AIM attribute dictionary from this K8s object
    # - build_selectors() -> build K8s query selectors from given AIM
    #                        attribute filters

    attribute_map = {'name': ('metadata', 'name'),
                     'display_name': ('metadata', 'annotations',
                                      'aim/display_name'),
                     'namespace_name': ('metadata', 'namespace'),
                     'guid': ('metadata', 'uid')}
    namespaced = True
    default_spec = {}

    def _get_aim_id(self):
        if self.namespaced:
            return '%s %s %s' % (self['metadata']['name'],
                                 self['metadata']['namespace'],
                                 self['metadata']['uid'])
        return '%s %s' % (self['metadata']['name'], self['metadata']['uid'])

    def _get_aim_id_selector(self, filters):
        if 'aim_id' in filters:
            parts = filters['aim_id'].split(' ')
            return {'name': parts[0],
                    'namespace': parts[1] if len(parts) > 1 else None}
        return {}

    def __getattr__(self, item):
        if item == 'aim_id':
            return self._get_aim_id()
        elif item in self.attribute_map:
            try:
                d = self
                for a in self.attribute_map[item]:
                    d = d[a]
                return d
            except KeyError:
                pass
        return super(K8sObject, self).__getattr__(item)

    def from_attr(self, resource_klass, attribute_dict):
        self.setdefault('spec', self.default_spec)
        for k, v in attribute_dict.iteritems():
            k8s_attrs = self.attribute_map.get(k)
            if not k8s_attrs:
                continue
            d = self
            for a in k8s_attrs[:-1]:
                d = d.setdefault(a, {})
            d[k8s_attrs[-1]] = v

    def to_attr(self, resource_klass, defaults=None):
        result = {}
        if defaults:
            result.update(defaults)
        for k in resource_klass.attributes():
            try:
                result[k] = getattr(self, k)
            except AttributeError:
                pass
        return result

    def build_selectors(self, aim_klass, filters):
        label_selectors = []
        name = None
        ns = None
        for fltr, value in filters.iteritems():
            k8s_attrs = self.attribute_map.get(fltr)
            if not k8s_attrs:
                continue
            if k8s_attrs == ('metadata', 'name'):
                name = value
            elif k8s_attrs == ('metadata', 'namespace'):
                ns = value
            elif (len(k8s_attrs) == 3 and
                    k8s_attrs[:2] == ('metadata', 'labels')):
                label_selectors.append('%s=%s' % (k8s_attrs[-1], value))
        result = self._get_aim_id_selector(filters)
        if label_selectors:
            result['label_selector'] = '&'.join(label_selectors)
        if name:
            result['name'] = name
        if ns:
            result['namespace'] = ns
        return result

    def _extract_owner_reference(self, ref_type):
        for ref in self['metadata'].get('ownerReferences', []):
            if (ref['kind'] == ref_type.kind and
                    ref['apiVersion'] == ref_type.api_version):
                return ref['name']


class Namespace(K8sObject):
    api_version = K8S_API_VERSION_CORE_V1
    kind = 'Namespace'
    namespaced = False


class Deployment(K8sObject):
    api_version = K8S_API_VERSION_EXTENSIONS_V1BETA1
    kind = 'Deployment'

    attribute_map = copy.copy(K8sObject.attribute_map)
    attribute_map.update({'replicas': ('spec', 'replicas')})

    # These values are needed to make K8s ApiServer happy in unit-test.
    default_spec = {'template':
                    {'spec':
                     {'containers': [{'image': 'dummy', 'name': 'dummy'}]}}}

    def from_attr(self, resource_klass, attribute_dict):
        super(Deployment, self).from_attr(resource_klass, attribute_dict)
        if 'name' in attribute_dict:
            match = self.setdefault('spec', {}).setdefault(
                'selector', {}).setdefault('matchLabels', {})
            if not match:
                match['k8s-app'] = attribute_dict['name']
            t_label = self.setdefault('spec', {}).setdefault(
                'template', {}).setdefault(
                    'metadata', {}).setdefault('labels', {})
            if not t_label:
                t_label['k8s-app'] = attribute_dict['name']


class ReplicaSet(K8sObject):
    api_version = K8S_API_VERSION_EXTENSIONS_V1BETA1
    kind = 'ReplicaSet'

    attribute_map = copy.copy(K8sObject.attribute_map)
    attribute_map.update({'deployment_name': ('metadata', 'annotations',
                                              'aim/deployment_name')})

    # These values are needed to make K8s ApiServer happy in unit-test.
    default_spec = {'template':
                    {'spec':
                     {'containers': [{'image': 'dummy', 'name': 'dummy'}]}}}

    def from_attr(self, resource_klass, attr):
        super(ReplicaSet, self).from_attr(resource_klass, attr)
        if 'deployment_name' in attr:
            # We don't set deployment_name in ownerReferences because we
            # don't have information like uid for the Deployment
            match = self.setdefault('spec', {}).setdefault(
                'selector', {}).setdefault('matchLabels', {})
            if not match:
                match['k8s-app'] = attr['deployment_name']
            t_label = self.setdefault('spec', {}).setdefault(
                'template', {}).setdefault(
                    'metadata', {}).setdefault('labels', {})
            if not t_label:
                t_label['k8s-app'] = attr['deployment_name']

    def to_attr(self, resource_klass, defaults=None):
        result = super(ReplicaSet, self).to_attr(resource_klass,
                                                 defaults=defaults)
        depl = self._extract_owner_reference(Deployment)
        if depl:
            result['deployment_name'] = depl
        elif 'deployment_name' not in result:
            # workaround for older versions of Kubernetes - guess the
            # deployment name from ReplicaSet attributes
            pod_hash = self['metadata'].get('labels',
                                            {}).get('pod-template-hash')
            name = self['metadata']['name']
            if pod_hash and name.endswith(pod_hash):
                result['deployment_name'] = name.replace('-%s' % pod_hash,
                                                         '')
        return result


class Service(K8sObject):
    api_version = K8S_API_VERSION_CORE_V1
    kind = 'Service'

    attribute_map = copy.copy(K8sObject.attribute_map)
    attribute_map.update({'service_type': ('spec', 'type'),
                          'cluster_ip': ('spec', 'clusterIP'),
                          'load_balancer_ip': ('spec', 'loadBalancerIP')})
    service_types = {'ClusterIP': 'clusterIp',
                     'ExternalName': 'externalName',
                     'LoadBalancer': 'loadBalancer',
                     'NodePort': 'nodePort'}

    def _port_to_num(self, port_str):
        try:
            return int(port_str)
        except ValueError:
            # check well-defined string names for ports
            port_str = port_str.lower()
            for p_num, p_name in types.ports.iteritems():
                if p_name == port_str:
                    return int(p_num)
        return port_str

    def from_attr(self, resource_klass, attr):
        # fix service_type
        if 'service_type' in attr:
            for st_k, st_a in self.service_types.iteritems():
                if st_a == attr['service_type']:
                    attr['service_type'] = st_k
        if attr.get('cluster_ip') == '0.0.0.0':
            attr.pop('cluster_ip')
        super(Service, self).from_attr(resource_klass, attr)

        if 'service_ports' in attr:
            ports = []
            for p in attr['service_ports']:
                if not (p.get('port') and p.get('protocol') and
                        p.get('target_port')):
                    continue
                pt = {'port': self._port_to_num(p['port']),
                      'protocol': p['protocol'].upper(),
                      'targetPort': self._port_to_num(p['target_port']),
                      'name': '%s-%s-%s' % (p['port'], p['protocol'],
                                            p['target_port'])}
                if p.get('node_port'):
                    pt['nodePort'] = self._port_to_num(p['node_port'])
                ports.append(pt)
            self.setdefault('spec', {})['ports'] = ports

    def to_attr(self, resource_klass, defaults=None):
        result = super(Service, self).to_attr(resource_klass,
                                              defaults=defaults)
        # fix service_type
        if 'service_type' in result:
            result['service_type'] = (
                self.service_types.get(result['service_type'],
                                       result['service_type']))
        for p in self['spec'].get('ports'):
            pt = {'port': str(p['port']),
                  'protocol': p.get('protocol', 'TCP').lower(),
                  'target_port': str(p.get('targetPort', p['port']))}
            if 'nodePort' in p:
                pt['node_port'] = str(p['nodePort'])
            result.setdefault('service_ports', []).append(pt)
        return result


class Node(K8sObject):
    api_version = K8S_API_VERSION_CORE_V1
    kind = 'Node'
    namespaced = False

    attribute_map = copy.copy(K8sObject.attribute_map)
    attribute_map.update({'host_name': ('metadata', 'labels',
                                        'kubernetes.io/hostname'),
                          'os': ('status', 'nodeInfo', 'osImage'),
                          'kernel_version': ('status', 'nodeInfo',
                                             'kernelVersion')})


class Pod(K8sObject):
    api_version = K8S_API_VERSION_CORE_V1
    kind = 'Pod'

    attribute_map = copy.copy(K8sObject.attribute_map)
    attribute_map.update({'compute_node_name': ('spec', 'nodeName'),
                          'replica_set_name': ('metadata', 'annotations',
                                               'aim/replica_set_name')})

    # These values are needed to make K8s ApiServer happy in unit-test.
    default_spec = {'containers': [{'image': 'dummy', 'name': 'dummy'}]}

    def to_attr(self, resource_klass, defaults=None):
        result = super(Pod, self).to_attr(resource_klass, defaults=defaults)
        repl_set = self._extract_owner_reference(ReplicaSet)
        if repl_set:
            result['replica_set_name'] = repl_set
        if 'compute_node_name' in result:
            result.setdefault('host_name', result['compute_node_name'])
        return result


class AciContainersObject(K8sObject):
    api_version = 'acicontainers.cisco.com/v1'
    kind = 'Aci'

    def __getattr__(self, item):
        try:
            return self['spec'][self['spec']['type']][item]
        except KeyError:
            try:
                if item == 'aim_id':
                    return self._get_aim_id()
                if item in ['id']:
                    return self['metadata']['name']
                if item in ['last_update_timestamp', 'heartbeat_timestamp']:
                    return self['metadata']['creationTimestamp']
                if item in ['version']:
                    return self['metadata']['resourceVersion']
            except KeyError:
                pass
        raise AttributeError

    def __setattr__(self, item, value):
        try:
            self['spec'][self['spec']['type']][item] = value
            return
        except KeyError:
            try:
                if item in ['id']:
                    self['metadata']['name'] = value
                    return
                if item in ['last_update_timestamp', 'heartbeat_timestamp']:
                    self['metadata']['creationTimestamp'] = value
                    return
                if item in ['version']:
                    self['metadata']['resourceVersion'] = value
                    return
            except KeyError:
                pass
        self[item] = value

    def from_attr(self, resource_klass, attribute_dict):
        name = utils.camel_to_snake(resource_klass.__name__)
        self.setdefault('spec', {'type': name, name: {}})
        self.setdefault('metadata', {'labels': {'aim_type': name}})
        labels = self['metadata']['labels']
        attrs = self['spec'][name]
        for k, v in attribute_dict.iteritems():
            if k in resource_klass.identity_attributes:
                labels[k] = utils.sanitize_name(v)
            attrs[k] = v
        if 'name' not in self['metadata']:
            self['metadata']['name'] = self._build_name(name, resource_klass)

    def to_attr(self, resource_klass, defaults=None):
        result = {}
        for k in resource_klass.attributes():
            try:
                result[k] = getattr(self, k)
            except AttributeError:
                pass
        return result

    def build_selectors(self, aim_klass, filters):
        result = 'aim_type=%s' % utils.camel_to_snake(aim_klass.__name__)
        for fltr in filters:
            if fltr in aim_klass.identity_attributes:
                result += ',%s=%s' % (
                    fltr, utils.sanitize_name(filters[fltr]))
        selectors = self._get_aim_id_selector(filters)
        selectors['label_selector'] = result
        return selectors

    def _build_name(self, type, resource_klass):
        components = []
        for attr in sorted(resource_klass.identity_attributes):
            components.append(self['spec'][type][attr])
        return utils.sanitize_name(type, *components)


class AciContainersV1(object):

    query_params = ['pretty', 'field_selector', 'label_selector',
                    'resource_version', 'timeout_seconds', 'watch',
                    'grace_period_seconds', 'orphan_dependents']
    verb_accept_headers = {
        'GET': ['application/json', 'application/yaml',
                'application/vnd.kubernetes.protobuf',
                'application/json;stream=watch',
                'application/vnd.kubernetes.protobuf;stream=watch'],
        'POST': ['application/json', 'application/yaml',
                 'application/vnd.kubernetes.protobuf'],
        'PUT': ['application/json', 'application/yaml',
                'application/vnd.kubernetes.protobuf'],
        'PATCH': ['application/json', 'application/yaml',
                  'application/vnd.kubernetes.protobuf'],
        'DELETE': ['application/json', 'application/yaml',
                   'application/vnd.kubernetes.protobuf']
    }
    verb_content_type = {
        'GET': ['*/*'], 'PUT': ['*/*'], 'POST': ['*/*'], 'DELETE': ['*/*'],
        'PATCH': ['application/json-patch+json',
                  'application/merge-patch+json',
                  'application/strategic-merge-patch+json'],
    }

    def __init__(self, api_client=None, config_file=None):
        config = client.Configuration()
        if api_client:
            self.api_client = api_client
        else:
            if not config.api_client:
                if config_file is not None and config_file != "":
                    konfig.load_kube_config(config_file=config_file)
                else:
                    konfig.load_incluster_config()
                config.api_client = klient.ApiClient()
                # K8S python client doesn't provide any way to configure the
                # client pool size, so we inject the value here
                config.api_client.rest_client.pool_manager.connection_pool_kw[
                    'maxsize'] = 20
            self.api_client = config.api_client
        self._watch = None

    @property
    def watch(self):
        return self._watch

    def get_new_watch(self):
        self._watch = watch.Watch()
        return self.watch

    def stop_watch(self):
        self.watch.stop()

    def _exec_rest_operation(self, k8s_klass, verb, **kwargs):
        kwargs['_return_http_data_only'] = True
        if kwargs.get('callback'):
            return self._exec_rest_operation_with_http_info(k8s_klass, verb,
                                                            **kwargs)
        else:
            (data) = self._exec_rest_operation_with_http_info(k8s_klass, verb,
                                                              **kwargs)
            return data

    def _exec_rest_operation_with_http_info(self, k8s_klass, verb, **kwargs):
        params = locals()
        for key, val in iteritems(params['kwargs']):
            params[key] = val
        del params['kwargs']

        # Path looks like
        # /api(s)?/<api_version>(/namespaces/{namespace})?/<kind>(/{name})?'

        path = '/api'
        if k8s_klass.api_version != K8S_API_VERSION_CORE_V1:
            path += 's'
        path += '/' + k8s_klass.api_version
        path_params = {}
        if getattr(k8s_klass, 'namespaced', True) and params['namespace']:
            path += '/namespaces/{namespace}'
            path_params['namespace'] = params['namespace']
        path += ('/%ss' % k8s_klass.kind.lower())
        # When name is passed, use it as a path parameter
        if 'name' in params:
            path += '/{name}'
            path_params['name'] = params['name']

        resource_path = path.replace('{format}', 'json')
        query_params = {}
        # Set query params for the verb
        for query in self.query_params:
            if query in params:
                query_params[utils.snake_to_lower_camel(query)] = params[query]

        header_params = {
            'Accept': self.api_client.select_header_accept(
                self.verb_accept_headers[verb]),
            'Content-Type': self.api_client.select_header_content_type(
                self.verb_content_type[verb])
        }

        # Authentication setting
        auth_settings = ['BearerToken']
        if verb == 'POST' and 'body' in params:
            params['body']['kind'] = k8s_klass.kind
            params['body']['apiVersion'] = k8s_klass.api_version

        result = self.api_client.call_api(
            resource_path, verb, path_params, query_params, header_params,
            body=params.get('body'), post_params=[], files={},
            response_type='str', auth_settings=auth_settings,
            callback=params.get('callback'), collection_formats={},
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'))
        if result and isinstance(result, str):
            try:
                return json.loads(
                    result.replace(": u'", "'").replace("'", '"'))
            except ValueError:
                try:
                    return ast.literal_eval(result)
                except ValueError:
                    pass

        return result

    def list(self, k8s_klass, namespace, **kwargs):
        # List on base path
        return self._exec_rest_operation(k8s_klass, 'GET', namespace=namespace,
                                         **kwargs)

    def create(self, k8s_klass, namespace, body, **kwargs):
        # Create object
        return self._exec_rest_operation(k8s_klass, 'POST',
                                         namespace=namespace, body=body,
                                         **kwargs)

    def replace(self, k8s_klass, name, namespace, body, **kwargs):
        # Replace existing object
        return self._exec_rest_operation(k8s_klass, 'PUT', namespace=namespace,
                                         body=body, name=name, **kwargs)

    def read(self, k8s_klass, name, namespace, **kwargs):
        # Read existing object
        return self._exec_rest_operation(k8s_klass, 'GET', namespace=namespace,
                                         name=name, **kwargs)

    def patch(self, k8s_klass, name, namespace, body, **kwargs):
        # Modify existing object
        return self._exec_rest_operation(k8s_klass, 'PATCH',
                                         namespace=namespace,
                                         body=body, name=name, **kwargs)

    def delete_collection(self, k8s_klass, namespace, **kwargs):
        # Delete objects given collection filters
        return self._exec_rest_operation(k8s_klass, 'DELETE',
                                         namespace=namespace, **kwargs)

    def delete(self, k8s_klass, name, namespace, body, **kwargs):
        # Delete objects
        return self._exec_rest_operation(k8s_klass, 'DELETE',
                                         namespace=namespace,
                                         name=name, body=body, **kwargs)
