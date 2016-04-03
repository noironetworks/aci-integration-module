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
        except Exception:
            self.msg = self.message
            raise

    def __str__(self):
        return self.msg


class IdentityAttributesMissing(AimException):
    message = "Identity attributes missing: %(attr)s."


class UnknownResourceType(AimException):
    message = "Unknown resource type %(type)s."


class AciResourceDefinitionError(AimException):
    message = ("Required class attribute %(attr)s not defined for "
               "resource %(klass)s")
