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

from oslo_utils import importutils

from aim.api import resource

resource_paths = ('aim.api.resource',)


class OperationalResource(object):
    pass


class AciStatus(resource.ResourceBase, OperationalResource):
    """Status of an AIM resource that is mapped to ACI object.

    Following attributes are available:
    * sync_status - Indicates whether ACI object was created/updated
    * sync_message - Informational or error message related to ACI
                     object creation/update
    * health_score - Health score of ACI object as reported by APIC
    * health_level - Level-wise classification of health-score
    * faults - List of AciFault objects as reported by APIC
    """

    identity_attributes = ['resource_type', 'resource_id']
    other_attributes = ['sync_status',
                        'sync_message',
                        'health_score',
                        'faults']
    db_attributes = ['id']

    # ACI object create/update is pending
    SYNC_PENDING = 'sync_pending'
    # ACI object was created/updated. It may or may not be in healthy state
    SYNCED = 'synced'
    # Create/update of ACI object failed
    SYNC_FAILED = 'sync_failed'

    HEALTH_POOR = "Poor Health Score"
    HEALTH_FAIR = "Fair Health Score"
    HEALTH_GOOD = "Good Health Score"
    HEALTH_EXCELLENT = "Excellent Health Score"

    def __init__(self, **kwargs):
        super(AciStatus, self).__init__({'resource_type': None,
                                         'resource_id': None,
                                         'sync_status': self.SYNC_PENDING,
                                         'sync_message': '',
                                         'health_score': 100,
                                         'faults': []}, **kwargs)
        self._parent_class = None

    @property
    def health_level(self):
        if self.health_score > 90:
            return self.HEALTH_EXCELLENT
        elif self.health_score > 75:
            return self.HEALTH_GOOD
        elif self.health_score > 50:
            return self.HEALTH_FAIR
        else:
            return self.HEALTH_POOR

    @property
    def parent_class(self):
        if not self._parent_class:
            for path in resource_paths:
                try:
                    self._parent_class = importutils.import_class(
                        path + '.%s' % self.resource_type)
                except ImportError:
                    continue
        return self._parent_class

    def is_build(self):
        return self.sync_status == self.SYNC_PENDING

    def is_error(self):
        return (self.sync_status == self.SYNC_FAILED or
                self.health_level == self.HEALTH_POOR or
                [f for f in self.faults if f.is_error()])


class AciFault(resource.ResourceBase, OperationalResource):
    """Fault information reported by ACI."""

    LC_UNKNOWN = 0x0
    LC_SOAKING = 0x1
    LC_RETAINING = 0x10
    LC_RAISED = 0x2
    LC_SOAKING_CLEARING = 0x4
    LC_RAISED_CLEARING = 0x8

    SEV_CLEARED = 'cleared'
    SEV_INFO = 'info'
    SEV_WARNING = 'warning'
    SEV_MINOR = 'minor'
    SEV_MAJOR = 'major'
    SEV_CRITICAL = 'critical'

    _aci_mo_name = 'faultInst'
    identity_attributes = ['fault_code', 'external_identifier']
    other_attributes = ['severity',
                        'status_id',
                        'cause',
                        'description']
    db_attributes = ['last_update_timestamp']

    def __init__(self, **kwargs):
        super(AciFault, self).__init__(
            {'severity': self.SEV_INFO, 'lifecycle_status': self.LC_UNKNOWN,
             'cause': '', 'description': "",
             'last_update_timestamp': None}, **kwargs)

    def is_error(self):
        return self.severity in [self.SEV_MAJOR, self.SEV_CRITICAL]

    @property
    def dn(self):
        return self.external_identifier
