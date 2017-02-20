from six import iteritems

from kubernetes import client, config, watch
from kubernetes.client import api_client as klient


class RbacAuthorizationV1alpha1Api(object):

    def __init__(self, api_client=None):
        config = client.Configuration()
        if api_client:
            self.api_client = api_client
        else:
            if not config.api_client:
                config.api_client = klient.ApiClient()
            self.api_client = config.api_client

    def list_namespaced_role_binding(self, namespace, **kwargs):
        kwargs['_return_http_data_only'] = True
        if kwargs.get('callback'):
            return self.list_namespaced_role_binding_with_http_info(
                namespace, **kwargs)
        else:
            (data) = self.list_namespaced_role_binding_with_http_info(
                namespace, **kwargs)
            return data

    def list_namespaced_role_binding_with_http_info(self, namespace, **kwargs):
        all_params = ['namespace', 'pretty', 'field_selector',
                      'label_selector', 'resource_version', 'timeout_seconds',
                      'watch', 'callback', '_return_http_data_only',
                      '_preload_content', '_request_timeout']

        params = locals()
        for key, val in iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_namespaced_role_binding" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'namespace' is set
        if ('namespace' not in params) or (params['namespace'] is None):
            raise ValueError("Missing the required parameter `namespace` when "
                             "calling `list_namespaced_role_binding`")


        collection_formats = {}

        resource_path = ('/apis/rbac.authorization.k8s.io/v1alpha1/namespaces/'
                         '{namespace}/rolebindings'.replace('{format}',
                                                            'json'))
        path_params = {}
        if 'namespace' in params:
            path_params['namespace'] = params['namespace']

        query_params = {}
        if 'pretty' in params:
            query_params['pretty'] = params['pretty']
        if 'field_selector' in params:
            query_params['fieldSelector'] = params['field_selector']
        if 'label_selector' in params:
            query_params['labelSelector'] = params['label_selector']
        if 'resource_version' in params:
            query_params['resourceVersion'] = params['resource_version']
        if 'timeout_seconds' in params:
            query_params['timeoutSeconds'] = params['timeout_seconds']
        if 'watch' in params:
            query_params['watch'] = params['watch']

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json', 'application/yaml',
             'application/vnd.kubernetes.protobuf',
             'application/json;stream=watch',
             'application/vnd.kubernetes.protobuf;stream=watch'])

        # HTTP header `Content-Type`
        header_params['Content-Type'] = (
            self.api_client.select_header_content_type(['*/*']))

        # Authentication setting
        auth_settings = ['BearerToken']

        return self.api_client.call_api(
            resource_path, 'GET', path_params, query_params, header_params,
            body=body_params, post_params=form_params, files=local_var_files,
            response_type='V1alpha1RoleBindingList',
            auth_settings=auth_settings, callback=params.get('callback'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)


# Configs can be set in Configuration class directly or using helper utility
config.load_kube_config()

v1 = RbacAuthorizationV1alpha1Api()
w = watch.Watch()
for event in w.stream(v1.list_namespaced_role_binding, namespace='default'):
    print("Event: %s %s" % (event['type'], event['object'].metadata.name))