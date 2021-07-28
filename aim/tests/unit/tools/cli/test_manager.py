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

import ast
import mock
import six


from aim import aim_manager
from aim.api import infra
from aim.api import resource
from aim.common import utils
from aim.tests.unit import test_aim_manager
from aim.tests.unit.tools.cli import test_shell as base
from aim.tools.cli.commands import manager as climanager


def _get_output_bytes(result):
    if hasattr(result, 'output_bytes'):
        if six.PY3:
            return result.output_bytes.decode('utf-8')
        return result.output_bytes
    else:
        if six.PY3:
            return result.stdout_bytes.decode('utf-8')
        return result.stdout_bytes


class TestManager(base.TestShell):

    def setUp(self):
        super(TestManager, self).setUp()
        self.mgr = aim_manager.AimManager()

    def test_load_domains(self):
        # create a VMM and PhysDom first
        pre_phys = resource.PhysicalDomain(name='pre-phys')
        pre_vmm = resource.VMMDomain(type='OpenStack', name='pre-vmm')
        ap = resource.ApplicationProfile(tenant_name='tn1', name='ap')
        pre_epg1 = resource.EndpointGroup(
            tenant_name='tn1', app_profile_name='ap', name='epg1')
        pre_epg2 = resource.EndpointGroup(
            tenant_name='tn1', app_profile_name='ap', name='epg2')
        self.mgr.create(self.ctx, resource.Tenant(name='tn1'))
        self.mgr.create(self.ctx, ap)
        self.mgr.create(self.ctx, pre_phys)
        self.mgr.create(self.ctx, pre_vmm)
        self.mgr.create(self.ctx, pre_epg2)
        self.mgr.create(self.ctx, pre_epg1)
        self.run_command('manager load-domains --no-mappings')
        # Verify pre-existing domains are still there
        self.assertIsNotNone(self.mgr.get(self.ctx, pre_phys))
        self.assertIsNotNone(self.mgr.get(self.ctx, pre_vmm))
        # Also the Domains defined in the config files exist
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.PhysicalDomain(name='phys')))
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.PhysicalDomain(name='phys2')))
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.VMMDomain(type='OpenStack',
                                                      name='ostack')))
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.VMMDomain(type='OpenStack',
                                                      name='ostack2')))
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.VMMDomain(type='VMware',
                                                      name='vmware')))
        self.assertIsNotNone(
            self.mgr.get(self.ctx, resource.VMMDomain(type='VMware',
                                                      name='vmware2')))
        # EPGs are still empty
        pre_epg1 = self.mgr.get(self.ctx, pre_epg1)
        pre_epg2 = self.mgr.get(self.ctx, pre_epg2)

        self.assertEqual([], pre_epg1.vmm_domains)
        self.assertEqual([], pre_epg1.physical_domains)
        self.assertEqual([], pre_epg2.vmm_domains)
        self.assertEqual([], pre_epg2.physical_domains)

        # Delete one of them, and use the replace flag
        self.mgr.delete(self.ctx, resource.VMMDomain(type='OpenStack',
                                                     name='ostack2'))
        self.run_command('manager load-domains --replace --no-mappings')

        # Now only 2 Domains each exist
        self.assertEqual(4, len(self.mgr.find(self.ctx, resource.VMMDomain)))
        self.assertEqual(2, len(self.mgr.find(self.ctx,
                                              resource.PhysicalDomain)))

        # EPGs are still empty
        pre_epg1 = self.mgr.get(self.ctx, pre_epg1)
        pre_epg2 = self.mgr.get(self.ctx, pre_epg2)

        self.assertEqual([], pre_epg1.vmm_domains)
        self.assertEqual([], pre_epg1.physical_domains)
        self.assertEqual([], pre_epg2.vmm_domains)
        self.assertEqual([], pre_epg2.physical_domains)

        # now update the current environment
        cmd = 'manager load-domains --replace --enforce --no-mappings'
        self.run_command(cmd)
        pre_epg1 = self.mgr.get(self.ctx, pre_epg1)
        pre_epg2 = self.mgr.get(self.ctx, pre_epg2)

        def get_vmm(type, name):
            return {'type': type, 'name': name}

        def get_phys(name):
            return {'name': name}

        self.assertEqual(utils.deep_sort([get_vmm('OpenStack', 'ostack'),
                                          get_vmm('OpenStack', 'ostack2'),
                                          get_vmm('VMware', 'vmware'),
                                          get_vmm('VMware', 'vmware2')]),
                         utils.deep_sort(pre_epg1.vmm_domains))
        self.assertEqual(utils.deep_sort([get_phys('phys'),
                                          get_phys('phys2')]),
                         utils.deep_sort(pre_epg1.physical_domains))
        self.assertEqual(utils.deep_sort([get_vmm('OpenStack', 'ostack'),
                                          get_vmm('OpenStack', 'ostack2'),
                                          get_vmm('VMware', 'vmware'),
                                          get_vmm('VMware', 'vmware2')]),
                         utils.deep_sort(pre_epg2.vmm_domains))
        self.assertEqual(utils.deep_sort([get_phys('phys'),
                                          get_phys('phys2')]),
                         utils.deep_sort(pre_epg2.physical_domains))

        # re-run the command, but populate the  domain mappings
        self.run_command('manager load-domains --replace --enforce')

        pre_epg1 = self.mgr.get(self.ctx, pre_epg1)
        pre_epg2 = self.mgr.get(self.ctx, pre_epg2)

        def get_vmm(type, name):
            return {'type': type, 'name': name}

        def get_phys(name):
            return {'name': name}

        # The load-domains should creat host domain mappings with
        # wildcard entries for every entry in the configuration file
        existing_mappings = [{'domain_type': 'PhysDom',
                              'host_name': '*',
                              'domain_name': 'phys'},
                             {'domain_type': 'PhysDom',
                              'host_name': '*',
                              'domain_name': 'phys2'},
                             {'domain_type': 'OpenStack',
                              'host_name': '*',
                              'domain_name': 'ostack'},
                             {'domain_type': 'OpenStack',
                              'host_name': '*',
                              'domain_name': 'ostack'},
                             {'domain_type': 'VMware',
                              'host_name': '*',
                              'domain_name': 'vmware'},
                             {'domain_type': 'VMware',
                              'host_name': '*',
                              'domain_name': 'vmware2'}]
        for mapping in existing_mappings:
            mapping = infra.HostDomainMappingV2(
                host_name=mapping['host_name'],
                domain_name=mapping['domain_name'],
                domain_type=mapping['domain_type'])
            try:
                self.assertIsNotNone(self.mgr.get(self.ctx, mapping))
            except Exception:
                self.assertFalse(True)

        self.assertEqual(utils.deep_sort(
                         [get_vmm('OpenStack', 'ostack'),
                          get_vmm('OpenStack', 'ostack2'),
                          get_vmm('VMware', 'vmware'),
                          get_vmm('VMware', 'vmware2')]),
                         utils.deep_sort(pre_epg1.vmm_domains))
        self.assertEqual(utils.deep_sort([get_phys('phys'),
                                          get_phys('phys2')]),
                         utils.deep_sort(pre_epg1.physical_domains))
        self.assertEqual(utils.deep_sort([get_vmm('OpenStack', 'ostack'),
                                          get_vmm('OpenStack', 'ostack2'),
                                          get_vmm('VMware', 'vmware'),
                                          get_vmm('VMware', 'vmware2')]),
                         utils.deep_sort(pre_epg2.vmm_domains))
        self.assertEqual(utils.deep_sort([get_phys('phys'),
                                          get_phys('phys2')]),
                         utils.deep_sort(pre_epg2.physical_domains))

        # re-run the command, with host-specific domain mappings populated.
        # This should cause an exception
        self.mgr.create(self.ctx, infra.HostDomainMappingV2(
            host_name='host1',
            domain_name='ostack10',
            domain_type='OpenStack'))
        self.run_command('manager load-domains --enforce', raises=True)

    def test_load_mappings(self):
        # The load-domains command invokes load-mappings,
        # so we don't use it to create hte domains -- we
        # have to create them manually

        cfg_mappings = [{'host_name': '*',
                         'domain_name': 'phys',
                         'domain_type': 'PhysDom'},
                        {'host_name': '*',
                         'domain_name': 'phys2',
                         'domain_type': 'PhysDom'},
                        {'host_name': '*',
                         'domain_name': 'ostack',
                         'domain_type': 'OpenStack'},
                        {'host_name': '*',
                         'domain_name': 'ostack2',
                         'domain_type': 'OpenStack'},
                        {'host_name': '*',
                         'domain_name': 'vmware',
                         'domain_type': 'VMware'},
                        {'host_name': '*',
                         'domain_name': 'vmware2',
                         'domain_type': 'VMware'}]
        for mapping in cfg_mappings:
            if mapping['domain_type'] is 'PhysDom':
                domain = resource.PhysicalDomain(name=mapping['domain_name'])
            else:
                domain = resource.VMMDomain(type=mapping['domain_type'],
                                            name=mapping['domain_name'])
            self.mgr.create(self.ctx, domain)

        # Run the load-mappings command, which populates
        # the HostDomainMappingV2 table using the domain
        # objects found in AIM
        self.run_command('manager load-mappings')

        mappings = self.mgr.find(self.ctx, infra.HostDomainMappingV2)
        db_mappings = [infra.HostDomainMappingV2(
                       host_name=mapping['host_name'],
                       domain_type=mapping['domain_type'],
                       domain_name=mapping['domain_name'])
                       for mapping in cfg_mappings]
        self.assertEqual(sorted(db_mappings, key=lambda x: x.domain_name),
                         sorted(mappings, key=lambda x: x.domain_name))

    def _test_load_mappings_preexisting_mappings(self, replace=False):
        # The load-domains command invokes load-mappings,
        # so we don't use it to create hte domains -- we
        # have to create them manually

        cfg_mappings = [{'domain_type': 'PhysDom',
                         'host_name': '*',
                         'domain_name': 'phys'},
                        {'domain_type': 'PhysDom',
                         'host_name': '*',
                         'domain_name': 'phys2'},
                        {'domain_type': 'OpenStack',
                         'host_name': '*',
                         'domain_name': 'ostack'},
                        {'domain_type': 'OpenStack',
                         'host_name': '*',
                         'domain_name': 'ostack2'},
                        {'domain_type': 'VMware',
                         'host_name': '*',
                         'domain_name': 'vmware'},
                        {'domain_type': 'VMware',
                         'host_name': '*',
                         'domain_name': 'vmware2'}]
        existing_mappings = [{'domain_type': 'PhysDom',
                              'host_name': '*',
                              'domain_name': 'phys3'},
                             {'domain_type': 'PhysDom',
                              'host_name': 'vm1',
                              'domain_name': 'phys4'},
                             {'domain_type': 'OpenStack',
                              'host_name': '*',
                              'domain_name': 'ostack3'},
                             {'domain_type': 'OpenStack',
                              'host_name': 'vm2',
                              'domain_name': 'ostack4'},
                             {'domain_type': 'VMware',
                              'host_name': '*',
                              'domain_name': 'vmware3'},
                             {'domain_type': 'VMware',
                              'host_name': 'vm3',
                              'domain_name': 'vmware4'}]
        for mapping in cfg_mappings:
            if mapping['domain_type'] is 'PhysDom':
                domain = resource.PhysicalDomain(name=mapping['domain_name'],
                                                 monitored=True)
            else:
                domain = resource.VMMDomain(type=mapping['domain_type'],
                                            name=mapping['domain_name'],
                                            monitored=True)
            self.mgr.create(self.ctx, domain)
        # Create some existing mappings, both host-specific
        # and wildcarded
        for mapping in existing_mappings:
            mapping_obj = infra.HostDomainMappingV2(
                host_name=mapping['host_name'],
                domain_name=mapping['domain_name'],
                domain_type=mapping['domain_type'])
            self.mgr.create(self.ctx, mapping_obj)
        mappings = self.mgr.find(self.ctx, infra.HostDomainMappingV2)

        # Run the load-mappings command, which populates
        # the HostDomainMappingV2 table using the contents
        # of the configuration file
        cmd = 'manager load-mappings'
        if replace:
            cmd += ' --replace'
        self.run_command(cmd)

        mappings = self.mgr.find(self.ctx, infra.HostDomainMappingV2)
        if replace:
            all_mappings = cfg_mappings
        else:
            all_mappings = existing_mappings + cfg_mappings
        db_mappings = [infra.HostDomainMappingV2(
                       host_name=mapping['host_name'],
                       domain_type=mapping['domain_type'],
                       domain_name=mapping['domain_name'])
                       for mapping in all_mappings]
        self.assertEqual(sorted(db_mappings, key=lambda x: x.domain_name),
                         sorted(mappings, key=lambda x: x.domain_name))

    def test_load_mappings_preexisting_mappings(self):
        self._test_load_mappings_preexisting_mappings()

    def test_load_mappings_preexisting_mappings_replace(self):
        self._test_load_mappings_preexisting_mappings(replace=True)

    def _parse_sync_find_output(self, result):
        res = _get_output_bytes(result).split('\n')[1:-1]
        output = []
        for token in res:
            output.append(tuple(filter(None, token.split(' '))))
        return output

    def test_sync_state_find(self):
        # Create 2 APs and 2 BDs for each state
        tn = self.mgr.create(self.ctx, resource.Tenant(name='tn1'))
        self.mgr.set_resource_sync_synced(self.ctx, tn)
        expected = {'error': set(), 'synced': set(), 'pending': set()}
        expected['synced'].add(('tenant', 'tn1'))
        for state, f in [('error', self.mgr.set_resource_sync_error),
                         ('synced', self.mgr.set_resource_sync_synced),
                         ('pending', self.mgr.set_resource_sync_pending)]:
            for i in range(2):
                name = '%s_%s' % (state, i)
                for res, nice in [(resource.VRF, 'vrf'),
                                  (resource.BridgeDomain, 'bridge-domain')]:
                    item = self.mgr.create(self.ctx, res(tenant_name='tn1',
                                                         name=name))
                    f(self.ctx, item)
                    expected[state].add((nice, 'tn1,%s' % name))

        for state in ['error', 'synced', 'pending']:
            result = self.run_command(
                'manager sync-state-find -p -s %s' % state)
            parsed = self._parse_sync_find_output(result)
            if state is 'synced':
                self.assertEqual(5, len(parsed))
            else:
                self.assertEqual(4, len(parsed))
            self.assertEqual(expected[state], set(parsed))

    def test_sync_state_recover(self):
        # Create 2 APs and 2 BDs for each state
        tn = self.mgr.create(self.ctx, resource.Tenant(name='tn1'))
        self.mgr.set_resource_sync_synced(self.ctx, tn)
        items = []
        for i in range(2):
            name = 'error_%s' % i
            for res in [resource.VRF, resource.BridgeDomain]:
                item = self.mgr.create(self.ctx, res(tenant_name='tn1',
                                                     name=name))
                self.mgr.set_resource_sync_error(self.ctx, item)
                items.append(item)

        with mock.patch('aim.aim_manager.AimManager.update') as up:
            self.run_command('manager sync-state-recover')
            # Items are updated
            self.assertEqual(4, up.call_count)

    def test_tag_list_command(self):
        apic_manager_object = mock.Mock()

        def get_mgr():
            return apic_manager_object

        mo_dict = {'tagInst': {'attributes':
                   {'dn': 'uni/tn-tn1/tag-openstack_aid'}}}
        apic_manager_object.apic.list_mo = mock.Mock(
            return_value=[mo_dict])
        apic_manager_object.apic.transaction = mock.MagicMock()

        with mock.patch('aim.tools.cli.commands.infra.get_apic_manager',
                        side_effect=get_mgr):
            with mock.patch('click.echo') as ce:
                self.run_command('infra tag-list -t openstack_aid')
        ce.called_once_with('uni/tn-tn1/tag-openstack_aid')

    def test_tag_delete_command(self):
        apic_manager_object = mock.Mock()

        def get_mgr():
            return apic_manager_object
        apic_manager_object.apic.DELETE = mock.Mock()
        apic_manager_object.apic.transaction = mock.MagicMock()
        # First try and delete the tenant, which should fail
        with mock.patch('aim.tools.cli.commands.infra.get_apic_manager',
                        side_effect=get_mgr):
            with mock.patch('click.echo') as ce:
                self.run_command('infra tag-delete --dn uni/tn-tn1')
        ce.called_once_with("uni/tn-tn1 object isn't a tag -- ignoring")
        apic_manager_object.apic.transaction.assert_not_called()

        # Now actually delete a tag
        with mock.patch('aim.tools.cli.commands.infra.get_apic_manager',
                        side_effect=get_mgr):
            with mock.patch('click.echo') as ce:
                self.run_command(
                    'infra tag-delete --dn uni/tn-tn1/tag-openstack_aid')
        ce.called_once_with("uni/tn-tn1/tag-openstack_aid deleted")
        apic_manager_object.apic.DELETE.assert_called_with(
            '/mo/uni/tn-tn1/tag-openstack_aid.json')


class TestManagerResourceOpsBase(object):
    test_default_values = {}
    test_dn = None
    prereq_objects = None

    def setUp(self):
        super(TestManagerResourceOpsBase, self).setUp()
        self._mgr = aim_manager.AimManager()
        self._mgr._update_listeners = []

    def _run_manager_command(self, res_command, command, attributes,
                             klass=None):
        klass = klass or self.resource_class

        def transform_list(k, li):
            attr_type = klass.other_attributes.get(k)
            is_list_of_dicts = (
                attr_type and
                attr_type.get("type") == "array" and
                attr_type.get("items", {}).get("type") == "object")
            if k == 'static_paths' or is_list_of_dicts:
                return "'%s'" % ' '.join(
                    [','.join(x) for x in
                     [['%s=%s' % (key, v) for key, v in y.items()]
                      for y in li]])
            elif isinstance(li, list):
                return ','.join(li) if li else "''"
            return li if li not in ['', None] else "''"
        identity = [attributes[k] for k in
                    klass.identity_attributes]
        other = ['--%s %s' % (k, transform_list(k, v))
                 for k, v in attributes.items()
                 if k in klass.other_attributes]
        return self.run_command(
            'manager ' + res_command + '-%s ' % command + ' '.join(
                identity + other) + ' -p')

    def _parse(self, res, klass=None):
        output_bytes = _get_output_bytes(res)
        if not output_bytes:
            return None
        res = [' '.join(x.split()) for x in output_bytes.split('\n')][1:]
        res = [[x[:x.find(' ')], x[x.find(' ') + 1:]] for x in res if x]
        if ['Property', 'Value'] in res:
            # Remove additional tables
            # TODO(ivar): test expected faults
            res = res[:res.index(['Property', 'Value'])]
        res_dict = {}
        klass = klass or self.resource_class
        klass_attributes = klass.attributes
        for item in res:
            if len(item) == 2 and item[0] in klass_attributes():
                attr_type = klass.other_attributes.get(item[0])
                is_boolean = (attr_type and
                              attr_type.get("type") == "boolean")
                loaded = None
                try:
                    # Try to load lists
                    loaded = ast.literal_eval(item[1])
                    if isinstance(loaded, list):
                        res_dict[item[0]] = loaded
                        continue
                except (SyntaxError, ValueError):
                    pass
                if is_boolean:
                    res_dict[item[0]] = utils.stob(item[1])
                elif attr_type:
                    if attr_type.get("type") == "string":
                        res_dict[item[0]] = item[1]
                    else:
                        res_dict[item[0]] = loaded
                else:
                    res_dict[item[0]] = item[1]
        return klass(**res_dict)

    def create(self, res_command, attributes, klass=None):
        res = self._run_manager_command(res_command, 'create', attributes,
                                        klass=klass)
        return self._parse(res, klass=klass)

    def delete(self, res_command, attributes):
        return self._run_manager_command(res_command, 'delete', attributes)

    def update(self, res_command, attributes):
        res = self._run_manager_command(res_command, 'update', attributes)
        return self._parse(res)

    def find(self, res_command, attributes):
        return self._run_manager_command(res_command, 'find', attributes)

    def list(self, res_command, attributes):
        return self._run_manager_command(res_command, 'list', attributes)

    def get(self, res_command, attributes):
        res = self._run_manager_command(res_command, 'get', attributes)
        return self._parse(res)

    def show(self, res_command, attributes):
        res = self._run_manager_command(res_command, 'show', attributes)
        return self._parse(res)

    def describe(self, res_command):
        return self._run_manager_command(res_command, 'describe', {})

    def _test_resource_ops(self, resource, test_identity_attributes,
                           test_required_attributes, test_search_attributes,
                           test_update_attributes,
                           test_default_values,
                           test_dn, res_command):
        """Test basic operations for resources

        :param resource: resource type, eg: BridgeDomain
        :param test_identity_attributes: dictionary with test identity values
        eg: {'tenant_rn': 'foo', 'rn': 'bar'}
        :param test_required_attributes: dictionary with attributes required
        by the DB for successful object creation.
        :param test_search_attributes: dictionary with test search attributes,
        needs to be one/more of the resource's other_attributes suitable for
        search. eg: {'vrf_rn': 'shared'}
        :param test_update_attributes: some attributes already present in
        one of the previously specified ones that hold a different value.
        :param test_default_values: dictionary of default values to verify
        after object has been created
        :param test_dn: expected DN of created resource, if any.
        :return:
        """
        # Run the following only if ID attributes are also required
        if not (set(test_identity_attributes.keys()) -
                set(test_required_attributes.keys())):
            self.run_command('manager ' + res_command + '-create', raises=True)
            self.run_command('manager ' + res_command + '-update', raises=True)
            self.run_command('manager ' + res_command + '-delete', raises=True)
            self.run_command('manager ' + res_command + '-get', raises=True)
            self.run_command('manager ' + res_command + '-show', raises=True)

        creation_attributes = {}
        creation_attributes.update(test_required_attributes),
        creation_attributes.update(test_identity_attributes)

        # Verify successful creation
        r1 = self.create(res_command, creation_attributes)
        if 'name' in creation_attributes:
            creation_attributes['name'] = r1.name
        for k, v in creation_attributes.items():
            self.assertTrue(utils.is_equal(
                            v, test_aim_manager.getattr_canonical(r1, k)))

        if 'name' in test_identity_attributes:
            test_identity_attributes['name'] = r1.name
        id_attr_val = {k: v for k, v in test_identity_attributes.items()
                       if k in r1.identity_attributes}
        # Verify get
        r1 = self.get(res_command, id_attr_val)
        if 'name' in creation_attributes:
            creation_attributes['name'] = r1.name
        for k, v in creation_attributes.items():
            self.assertTrue(utils.is_equal(
                            v, test_aim_manager.getattr_canonical(r1, k)))

        # Verify show
        r1 = self.show(res_command, id_attr_val)
        for k, v in creation_attributes.items():
            self.assertTrue(utils.is_equal(
                            v, test_aim_manager.getattr_canonical(r1, k)))

        # Test update
        updates = {}
        updates.update(id_attr_val)
        updates.update(test_update_attributes)
        r1 = self.update(res_command, updates)
        for k, v in test_update_attributes.items():
            self.assertTrue(utils.is_equal(
                            v, test_aim_manager.getattr_canonical(r1, k)))

        # Test delete
        self.delete(res_command, id_attr_val)
        self.assertIsNone(self.get(res_command, id_attr_val))
        self.assertIsNone(self.show(res_command, id_attr_val))

    def _create_prerequisite_objects(self):
        for obj in (self.prereq_objects or []):
            self.create(climanager.convert(type(obj).__name__), obj.__dict__,
                        klass=type(obj))

    def test_lifecycle(self):
        self._create_prerequisite_objects()
        self._test_resource_ops(
            self.resource_class,
            self.test_identity_attributes,
            self.test_required_attributes,
            self.test_search_attributes,
            self.test_update_attributes,
            self.test_default_values,
            self.test_dn, self.res_command)


class TestBridgeDomain(test_aim_manager.TestBridgeDomainMixin,
                       TestManagerResourceOpsBase, base.TestShell):
    pass


class TestNetflowVMMExporterPol(
        test_aim_manager.TestNetflowVMMExporterPolMixin,
        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestVmmVswitchPolicyGroup(
        test_aim_manager.TestVmmVswitchPolicyGroupMixin,
        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestVmmRelationToExporterPol(
        test_aim_manager.TestVmmRelationToExporterPolMixin,
        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestSubnet(test_aim_manager.TestSubnetMixin, TestManagerResourceOpsBase,
                 base.TestShell):
    pass


class TestVRF(test_aim_manager.TestVRFMixin, TestManagerResourceOpsBase,
              base.TestShell):
    pass


class TestApplicationProfile(test_aim_manager.TestApplicationProfileMixin,
                             TestManagerResourceOpsBase,
                             base.TestShell):
    pass


class TestEndpointGroup(test_aim_manager.TestEndpointGroupMixin,
                        TestManagerResourceOpsBase,
                        base.TestShell):
    pass


class TestFilter(test_aim_manager.TestFilterMixin, TestManagerResourceOpsBase,
                 base.TestShell):
    pass


class TestFilterEntry(test_aim_manager.TestFilterEntryMixin,
                      TestManagerResourceOpsBase,
                      base.TestShell):
    pass


class TestContract(test_aim_manager.TestContractMixin,
                   TestManagerResourceOpsBase,
                   base.TestShell):
    pass


class TestOutOfBandContract(test_aim_manager.TestOutOfBandContractMixin,
                            TestManagerResourceOpsBase,
                            base.TestShell):
    pass


class TestContractSubject(test_aim_manager.TestContractSubjectMixin,
                          TestManagerResourceOpsBase,
                          base.TestShell):
    pass


class TestOutOfBandContractSubject(
        test_aim_manager.TestOutOfBandContractSubjectMixin,
        TestManagerResourceOpsBase,
        base.TestShell):
    pass


class TestEndpoint(test_aim_manager.TestEndpointMixin,
                   TestManagerResourceOpsBase,
                   base.TestShell):
    pass


class TestVMMDomain(test_aim_manager.TestVMMDomainMixin,
                    TestManagerResourceOpsBase,
                    base.TestShell):
    pass


class TestPhysicalDomain(test_aim_manager.TestPhysicalDomainMixin,
                         TestManagerResourceOpsBase,
                         base.TestShell):
    pass


class TestL3Outside(test_aim_manager.TestL3OutsideMixin,
                    TestManagerResourceOpsBase,
                    base.TestShell):
    pass


class TestL3OutNodeProfile(test_aim_manager.TestL3OutNodeProfileMixin,
                           TestManagerResourceOpsBase,
                           base.TestShell):
    pass


class TestL3OutNode(test_aim_manager.TestL3OutNodeMixin,
                    TestManagerResourceOpsBase,
                    base.TestShell):
    pass


class TestL3OutStaticRoute(test_aim_manager.TestL3OutStaticRouteMixin,
                           TestManagerResourceOpsBase,
                           base.TestShell):
    pass


class TestL3OutInterfaceProfile(
        test_aim_manager.TestL3OutInterfaceProfileMixin,
        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestL3OutInterface(test_aim_manager.TestL3OutInterfaceMixin,
                         TestManagerResourceOpsBase,
                         base.TestShell):
    pass


class TestExternalNetwork(test_aim_manager.TestExternalNetworkMixin,
                          TestManagerResourceOpsBase,
                          base.TestShell):
    pass


class TestExternalSubnet(test_aim_manager.TestExternalSubnetMixin,
                         TestManagerResourceOpsBase,
                         base.TestShell):
    pass


class TestHostLink(test_aim_manager.TestHostLinkMixin,
                   TestManagerResourceOpsBase, base.TestShell):
    pass


class TestHostDomainMapping(test_aim_manager.TestHostDomainMappingMixin,
                            TestManagerResourceOpsBase, base.TestShell):
    pass


class TestHostDomainMappingV2(test_aim_manager.TestHostDomainMappingV2Mixin,
                              TestManagerResourceOpsBase, base.TestShell):
    pass


class TestHostLinkNetworkLabel(test_aim_manager.TestHostLinkNetworkLabelMixin,
                               TestManagerResourceOpsBase, base.TestShell):
    pass


class TestSecurityGroup(test_aim_manager.TestSecurityGroupMixin,
                        TestManagerResourceOpsBase,
                        base.TestShell):
    pass


class TestSecurityGroupSubject(test_aim_manager.TestSecurityGroupSubjectMixin,
                               TestManagerResourceOpsBase, base.TestShell):
    pass


class TestSecurityGroupRule(test_aim_manager.TestSecurityGroupRuleMixin,
                            TestManagerResourceOpsBase, base.TestShell):
    pass


class TestSystemSecurityGroup(test_aim_manager.TestSystemSecurityGroupMixin,
                              TestManagerResourceOpsBase,
                              base.TestShell):
    pass


class TestSystemSecurityGroupSubject(
        test_aim_manager.TestSystemSecurityGroupSubjectMixin,
        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestSystemSecurityGroupRule(
        test_aim_manager.TestSystemSecurityGroupRuleMixin,
        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestDeviceCluster(test_aim_manager.TestDeviceClusterMixin,
                        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestDeviceClusterInterface(
    test_aim_manager.TestDeviceClusterInterfaceMixin,
    TestManagerResourceOpsBase, base.TestShell):
        pass


class TestConcreteDevice(test_aim_manager.TestConcreteDeviceMixin,
                         TestManagerResourceOpsBase, base.TestShell):
    pass


class TestConcreteDeviceInterface(
    test_aim_manager.TestConcreteDeviceInterfaceMixin,
    TestManagerResourceOpsBase, base.TestShell):
        pass


class TestServiceGraph(test_aim_manager.TestServiceGraphMixin,
                       TestManagerResourceOpsBase, base.TestShell):
    pass


class TestServiceGraphNode(test_aim_manager.TestServiceGraphNodeMixin,
                           TestManagerResourceOpsBase, base.TestShell):
    pass


class TestServiceGraphConnection(
    test_aim_manager.TestServiceGraphConnectionMixin,
    TestManagerResourceOpsBase, base.TestShell):
        pass


class TestServiceRedirectPolicy(
        test_aim_manager.TestServiceRedirectPolicyMixin,
        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestDeviceClusterContext(test_aim_manager.TestDeviceClusterContextMixin,
                               TestManagerResourceOpsBase, base.TestShell):
    pass


class TestDeviceClusterInterfaceContext(
    test_aim_manager.TestDeviceClusterInterfaceContextMixin,
    TestManagerResourceOpsBase, base.TestShell):
        pass


class TestBgpPeerP(test_aim_manager.TestBgpPeerPMixin,
                   base.TestShell):
        pass


class TestServiceRedirectMonitoringPolicy(
        test_aim_manager.TestServiceRedirectMonitoringPolicyMixin,
        base.TestShell):
    pass


class TestServiceRedirectHealthGroup(
        test_aim_manager.TestServiceRedirectHealthGroupMixin, base.TestShell):
    pass


class TestQosRequirement(
        test_aim_manager.TestQosRequirementMixin,
        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestQosDppPol(
        test_aim_manager.TestQosDppPolMixin,
        TestManagerResourceOpsBase, base.TestShell):
    pass


class TestSpanVsourceGroup(test_aim_manager.TestSpanVsourceGroupMixin,
                           TestManagerResourceOpsBase,
                           base.TestShell):
    pass


class TestSpanVsource(test_aim_manager.TestSpanVsourceMixin,
                      TestManagerResourceOpsBase,
                      base.TestShell):
    pass


class TestSpanVdestGroup(test_aim_manager.TestSpanVdestGroupMixin,
                         TestManagerResourceOpsBase,
                         base.TestShell):
    pass


class TestSpanVdest(test_aim_manager.TestSpanVdestMixin,
                    TestManagerResourceOpsBase,
                    base.TestShell):
    pass


class TestSpanVepgSummary(test_aim_manager.TestSpanVepgSummaryMixin,
                          TestManagerResourceOpsBase,
                          base.TestShell):
    pass


class TestInfraAccBundleGroup(test_aim_manager.TestInfraAccBundleGroupMixin,
                              TestManagerResourceOpsBase,
                              base.TestShell):
    pass


class TestInfraAccPortGroup(test_aim_manager.TestInfraAccPortGroupMixin,
                            TestManagerResourceOpsBase,
                            base.TestShell):
    pass


class TestSpanSpanlbl(test_aim_manager.TestSpanSpanlblMixin,
                      TestManagerResourceOpsBase,
                      base.TestShell):
    pass
