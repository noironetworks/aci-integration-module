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


class Status(object):

    def is_build(self):
        """Returns True if the current status is transient."""
        raise

    def is_error(self):
        """Returns True if current status is an error state."""
        raise


class AciStatus(Status):
    """Status of an AIM resource that is mapped to ACI object.

    Following attributes are available:
    * sync_status - Indicates whether ACI object was created/updated
    * sync_message - Informational or error message related to ACI
                     object creation/update
    * health_score - Health score of ACI object as reported by APIC
    * health_level - Level-wise classification of health-score
    * faults - List of AciFault objects as reported by APIC
    """

    # ACI object create/update is pending
    SYNC_PENDING = 0
    # ACI object was created/updated. It may or may not be in healthy state
    SYNCED = 1
    # Create/update of ACI object failed
    SYNC_FAILED = 2

    HEALTH_POOR = "Poor Health Score"
    HEALTH_FAIR = "Fair Health Score"
    HEALTH_GOOD = "Good Health Score"
    HEALTH_EXCELLENT = "Excellent Health Score"

    def __init__(self):
        self.sync_status = self.SYNCED
        self.sync_message = ''
        self.health_score = 100
        self.faults = []

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

    def is_build(self):
        return self.sync_status == self.SYNC_PENDING

    def is_error(self):
        return (self.sync_status == self.SYNC_FAILED or
                self.health_level == self.HEALTH_POOR or
                [f for f in self.faults if f.severity > AciFault.SEV_MINOR])


class AciFault(object):
    """Fault information reported by ACI."""

    LC_UNKNOWN = 0x0
    LC_SOAKING = 0x1
    LC_RETAINING = 0x10
    LC_RAISED = 0x2
    LC_SOAKING_CLEARING = 0x4
    LC_RAISED_CLEARING = 0x8

    SEV_CLEARED = 0
    SEV_INFO = 1
    SEV_WARNING = 2
    SEV_MINOR = 3
    SEV_MAJOR = 4
    SEV_CRITICAL = 5

    def __init__(self, code):
        self.fault_code = code
        self.severity = self.SEV_INFO
        self.lifecycle_status = self.LC_UNKNOWN
        self.cause_code = 0         # unknown
        self.description = ""
        self.last_update_timestamp = None
