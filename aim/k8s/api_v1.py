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
import json
from six import iteritems

from kubernetes import client
from kubernetes.client import api_client as klient
from kubernetes import config as konfig

from aim.common import utils


K8S_DEFAULT_NAMESPACE = 'default'


class AciContainersObject(dict):

    def __getattr__(self, item):
        try:
            return self['spec'][self['spec']['type']][item]
        except KeyError:
            try:
                if item in ['aim_id', 'id']:
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
                if item in ['aim_id', 'id']:
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
    base_path = '/apis/acicontainers.cisco.com/v1/namespaces/{namespace}/acis'

    def __init__(self, api_client=None):
        config = client.Configuration()
        if api_client:
            self.api_client = api_client
        else:
            if not config.api_client:
                konfig.load_kube_config()
                config.api_client = klient.ApiClient()
            self.api_client = config.api_client

    def _exec_rest_operation(self, verb, **kwargs):
        kwargs['_return_http_data_only'] = True
        if kwargs.get('callback'):
            return self._exec_rest_operation_with_http_info(verb, **kwargs)
        else:
            (data) = self._exec_rest_operation_with_http_info(verb, **kwargs)
            return data

    def _exec_rest_operation_with_http_info(self, verb, **kwargs):
        params = locals()
        for key, val in iteritems(params['kwargs']):
            params[key] = val
        del params['kwargs']

        path = self.base_path
        path_params = {'namespace': params['namespace']}
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

        result = self.api_client.call_api(
            resource_path, verb, path_params, query_params, header_params,
            body=params.get('body'), post_params=[], files={},
            response_type='str', auth_settings=auth_settings,
            callback=params.get('callback'), collection_formats={},
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'))
        if result:
            try:
                return json.loads(result.replace("u'", "'").replace("'", '"'))
            except ValueError:
                try:
                    return ast.literal_eval(result)
                except ValueError:
                    pass
        return result

    def list_namespaced_aci(self, namespace, **kwargs):
        # List on base path
        return self._exec_rest_operation('GET', namespace=namespace, **kwargs)

    @utils.log
    def create_namespaced_aci(self, namespace, body, **kwargs):
        # Create ACI object
        return self._exec_rest_operation('POST', namespace=namespace,
                                         body=body, **kwargs)

    @utils.log
    def replace_namespaced_aci(self, name, namespace, body, **kwargs):
        # Replace existing ACI object
        return self._exec_rest_operation('PUT', namespace=namespace, body=body,
                                         name=name, **kwargs)

    def read_namespaced_aci(self, name, namespace, **kwargs):
        # Read existing ACI object
        return self._exec_rest_operation('GET', namespace=namespace, name=name,
                                         **kwargs)

    @utils.log
    def patch_namespaced_aci(self, name, namespace, body, **kwargs):
        # Modify existing ACI object
        return self._exec_rest_operation('PATCH', namespace=namespace,
                                         body=body, name=name, **kwargs)

    @utils.log
    def delete_collection_namespaced_aci(self, namespace, **kwargs):
        # Delete ACI objects given collection filters
        return self._exec_rest_operation('DELETE', namespace=namespace,
                                         **kwargs)

    @utils.log
    def delete_namespaced_aci(self, name, namespace, body, **kwargs):
        # Delete ACI objects
        return self._exec_rest_operation('DELETE', namespace=namespace,
                                         name=name, body=body, **kwargs)


#   from kubernetes import config, watch
#   config.load_kube_config()
#
#   v1 = AciContainersV1()
#   v1.create_namespaced_aci(
#       'default', {'spec': {'type': 'vrf',
#                            'vrf': {'tenant_name': 'common',
#                                    'name': 'test5'}},
#                   'metadata': {'name': 'vrf-common-test5',
#                                'labels': {'tenant_name': 'common',
#                                           'type': 'vrf',
#                                           'name': 'test5'}}})
#   w = watch.Watch()
#   for event in w.stream(v1.list_namespaced_aci, namespace='default'):
#       print("Event: %s %s" % (event['type'], event['object']))
