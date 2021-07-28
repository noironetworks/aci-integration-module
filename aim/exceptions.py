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


class AimException(Exception):
    """Base AIM Exception.

    Specific exception classes should inherit from this class
    and define property 'message' describing the erroroneous condition.
    The message may be parameterized. Keyword-arguments should be provided
    to the constructor to fill those parameters.
    """
    message = "An unknown exception occurred."

    def __init__(self, **kwargs):
        try:
            super(AimException, self).__init__(self.message % kwargs)
            self.msg = self.message % kwargs
            self.message = self.msg
        except Exception:
            self.msg = self.message
            raise

    def __str__(self):
        return self.msg


class IdentityAttributesMissing(AimException):
    message = "Identity attributes missing for type %(klass)s: %(attr)s."


class UnknownResourceType(AimException):
    message = "Unknown resource type %(type)s."


class AciResourceDefinitionError(AimException):
    message = ("Required class attribute %(attr)s not defined for "
               "resource %(klass)s.")


class InvalidDNForAciResource(AimException):
    message = ("DN %(dn)s is not valid for resource %(cls)s.")


class AciResourceValueError(AimException):
    message = ("Value %(value)s for resource attribute %(attr)s not defined "
               "for resource %(klass)s.")


class ConfigurationUndefined(AimException):
    message = ("Configuration %(conf)s undefined in group %(group)s for host "
               "%(host)s")


class UnsupportedAIMConfig(AimException):
    message = ("Configuration %(conf)s is not supported in AIM mode "
               "for group %(group)s")


class UnsupportedAIMConfigGroup(AimException):
    message = "Configuration group %(group)s is not supported in AIM mode"


class OneHostPerCallbackItemSubscriptionAllowed(AimException):
    message = ("Host %(tentative_host)s can't subcribe to option %(key)s in "
               "group %(group)s with callback %(callback)s, as there's "
               "another host already subscribed for such call: %(curr_hosts)s")


class InvalidMonitoredStateUpdate(AimException):
    message = "Monitored state of object %(object)s cannot be updated"


class InvalidMonitoredObjectDelete(AimException):
    message = ("Monitored object %(object)s cannot be deleted while in "
               "pending state")


class BadTrackingArgument(AimException):
    message = ("Bad argument passed to the tracking function. root %(exp)s "
               "expected, but there are resources for root %(act)s. "
               "All objects: %(res)s")


class DefaultSecurityGroupNameError(AimException):
    message = "Name attribute %(attr)s not allowed for resource %(klass)s."
