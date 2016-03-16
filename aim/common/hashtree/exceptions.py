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


class HashTreeException(Exception):
    """Base Hash Tree Exception."""
    message = "An unknown exception occurred."

    def __init__(self, **kwargs):
        try:
            super(HashTreeException, self).__init__(self.message % kwargs)
            self.msg = self.message % kwargs
        except Exception:
            self.msg = self.message
            raise

    def __str__(self):
        return self.msg


class StructuredHashTreeException(HashTreeException):
    pass


class MultipleRootTreeError(StructuredHashTreeException):
    message = ("Node with key %(key)s cannot be inserted in tree since "
               "it's not nested in root %(root_key)s")


class HashTreeNotFound(StructuredHashTreeException):
    message = "Hash Tree not found for tenans %(tenant_rn)s"
