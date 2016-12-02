*****************************
End-to-End object integration
*****************************

The scope of this document is to help developers follow the right steps for integrating new resources in the AIM model.
More specifically we will cover:

* How to add a resource to the DB layer;
* How to add a resource to the API layer;
* How to correlate the two;
* How to make AID aware of these new resources, so that they get synchronized;
* Extra: How to modify apicapi accordingly for simple cases.

For each step, a few words will be spent on how to write the proper UTs :-)

DB Layer
========

The first step in adding an AIM object is to create its persistent form through the sqlalchemy ORM interface. For each
new table the developer will have to create the proper python class representation and migration script.

In order to add a new table to the AIM model, look at the following file:

*aim/db/models.py*

And add a new table following the example as below:
::

    class VRF(model_base.Base, model_base.HasAimId,
              model_base.HasName, model_base.HasDisplayName,
              model_base.HasTenantName,
              model_base.AttributeMixin, model_base.IsMonitored):
        """DB model for BridgeDomain."""

        __tablename__ = 'aim_vrfs'
        __table_args__ = (uniq_column(__tablename__, 'tenant_name', 'name') +
                          to_tuple(model_base.Base.__table_args__))

        policy_enforcement_pref = sa.Column(sa.String(16))

Note that:

* The table name has to start with the suffix "aim_";
* The table class must derive from "model_base.Base";
* Most of the common basic attributes can be added to the table via Mixin pattern (see the example above);
* Using "__table_args__", unique constraints and foreign keys can be specified.

Sometimes, a table can have a 1:N relationship with another that needs to be represented as a list in the API. One
example on how to handle this is the following:
::

    class BridgeDomain(model_base.Base, model_base.HasAimId,
                       model_base.HasName, model_base.HasDisplayName,
                       model_base.HasTenantName,
                       model_base.AttributeMixin, model_base.IsMonitored):
        """DB model for BridgeDomain."""

        __tablename__ = 'aim_bridge_domains'
        __table_args__ = (uniq_column(__tablename__, 'tenant_name', 'name') +
                          to_tuple(model_base.Base.__table_args__))

        vrf_name = model_base.name_column()
        enable_arp_flood = sa.Column(sa.Boolean)
        enable_routing = sa.Column(sa.Boolean)
        limit_ip_learn_to_subnets = sa.Column(sa.Boolean)
        l2_unknown_unicast_mode = sa.Column(sa.String(16))
        ep_move_detect_mode = sa.Column(sa.String(16))

        l3outs = orm.relationship(BridgeDomainL3Out,
                                  backref='bd',
                                  cascade='all, delete-orphan',
                                  lazy='joined')

        def from_attr(self, session, res_attr):
            if 'l3out_names' in res_attr:
                l3out_names = []
                for l in (res_attr.pop('l3out_names', []) or []):
                    l3out_names.append(BridgeDomainL3Out(name=l))
                self.l3outs = l3out_names
            # map remaining attributes to model
            super(BridgeDomain, self).from_attr(session, res_attr)

        def to_attr(self, session):
            res_attr = super(BridgeDomain, self).to_attr(session)
            for l in res_attr.pop('l3outs', []):
                res_attr.setdefault('l3out_names', []).append(l.name)
            return res_attr

* "orm.relationship" defined the relationship with the normalization table;
* "from_attr" and "to_attr" are overridden to manage these special cases, making sure that the obtained resources
  contain the proper list of names/ids.

For each new or modified table, a migration script needs to be added. It should be at most one per commit. Look at
*aim/db/migration/alembic_migrations/versions/40855b7eb958_create_bridgedomain_table.py* as an
example on how to create a migration script.

Note that:

* orm relationships are not specified in the migration scripts, as the don't represent actual DB columns.

Testing
-------

DB tests are done End-to-End with the corresponding API resources through the aim_manager layer, which will be covered
later.

Resource Layer
==============

Adding a new resource to the AIM API is pretty straight forward. Based on what has been created in the DB layer, add
the proper resources to *aim/api/resource.py*. An example follows:
::

    class BridgeDomain(AciResourceBase):
        """Resource representing a BridgeDomain in ACI.

        Identity attributes are RNs for ACI tenant and bridge-domain.
        """

        identity_attributes = ['tenant_name', 'name']
        other_attributes = ['display_name',
                            'vrf_name',
                            'enable_arp_flood',
                            'enable_routing',
                            'limit_ip_learn_to_subnets',
                            'l2_unknown_unicast_mode',
                            'ep_move_detect_mode',
                            'l3out_names',
                            'monitored']

        _aci_mo_name = 'fvBD'
        _tree_parent = Tenant

        def __init__(self, **kwargs):
            super(BridgeDomain, self).__init__({'display_name': '',
                                                'vrf_name': '',
                                                'enable_arp_flood': False,
                                                'enable_routing': True,
                                                'limit_ip_learn_to_subnets': False,
                                                'l2_unknown_unicast_mode': 'proxy',
                                                'ep_move_detect_mode': '',
                                                'l3out_names': [],
                                                'monitored': False},
                                               **kwargs)


Note that:

* "_aci_mo_name" defines the main ACI object this class represents. If more than on ACI object is represented by this
  class, use the root one;
* "_tree_parent" is the logical parent in the AIM API;
* default values can be set in the constructor as per above example.


Testing
-------

Resource tests are done End-to-End with the corresponding DB objects through the aim_manager layer, which will be
covered later.


Correlate DB and API
====================

Correlating DB and API objects is needed to tell the AIM manager persist the API members. This is done simply by adding
an entry to *aim.aim_manager.AimManager._db_model_map*. Model validation can be added here if strictly needed, but right
we don't have a formal validation framework.

Testing
-------

End-to-End testing for the API<->DB layer through the aim_manager is done in *aim/tests/unit/test_aim_manager.py*. All
that's to be done to add a minimal set of tests is creating a class as follows:
::
    class TestExternalNetwork(TestAciResourceOpsBase, base.TestAimDBBase):
        resource_class = resource.ExternalNetwork
        prereq_objects = [
            resource.L3Outside(tenant_name='tenant1', name='l3out1')]
        test_identity_attributes = {'tenant_name': 'tenant1',
                                    'l3out_name': 'l3out1'}
        test_required_attributes = {'tenant_name': 'tenant1',
                                    'l3out_name': 'l3out1',
                                    'name': 'net1',
                                    'nat_epg_dn': 'uni/tn-1/ap-a1/epg-g1',
                                    'provided_contract_names': ['k', 'p1', 'p2'],
                                    'consumed_contract_names': ['c1', 'c2', 'k']}
        test_search_attributes = {'name': 'net1'}
        test_update_attributes = {'provided_contract_names': ['c2', 'k'],
                                  'consumed_contract_names': []}
        test_dn = 'uni/tn-tenant1/out-l3out1/instP-net1'

Note that:

* "test_search_attributes" is the set of attributes on which a search will be attempted. It has to be a subset of the
"test_required_attributes"


APICAPI
=======

For every new class that needs to be created on APIC, make sure that the apicapi client supports it. Go to
*apicapi/apic_client.py* and add an entry into ManagedObjectClass.supported_mos, where the key is the APIC class and the
value is a ManagedObjectName where the parent class is specified together with the RN format.
