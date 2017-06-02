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

from requests import exceptions as request_exc

from apicapi import exceptions as apicapi_exc
from oslo_log import log as logging

from aim.agent.aid.universes import errors

LOG = logging.getLogger(__name__)


class APICErrorHandler(object):
    """APIC Error Handler.

    For each error type returned during a write operation in APIC, including
    errors caused by temporary network partition, categorize each failure
    into a defined superset of a few enumerations that can be used by the
    caller to decide which action is the best to be taken after such failure.

    """

    APIC_OBJECT_CRITICAL = set([122, 121, 120, 106, 801, 104])
    APIC_OBJECT_TRANSIENT = set([100, 102])

    def analyze_request_exception(self, e):
        if isinstance(e, request_exc.Timeout):
            LOG.warn("APIC didn't respond and the request timed out.")
            return errors.SYSTEM_TRANSIENT
        elif isinstance(e, request_exc.ConnectionError):
            return errors.SYSTEM_TRANSIENT
        elif isinstance(e, request_exc.URLRequired):
            return errors.OPERATION_CRITICAL
        elif isinstance(e, request_exc.InvalidURL):
            return errors.OPERATION_CRITICAL
        elif isinstance(e, request_exc.RequestException):
            LOG.warn("A generic request exception occurred: %s", e.message)
            return errors.OPERATION_TRANSIENT
        else:
            LOG.warn("An unknown error occurred: %s", e.message)
            return errors.UNKNOWN

    def analyze_apic_error(self, error_status, error_code):
        if error_status == 400:
            if error_code in self.APIC_OBJECT_CRITICAL:
                return errors.OPERATION_CRITICAL
            if error_code in self.APIC_OBJECT_TRANSIENT:
                return errors.OPERATION_TRANSIENT
            else:
                LOG.warn("Unmanaged error code %s from APIC", error_code)
                return errors.UNKNOWN
        elif error_status == 403:
            LOG.warn("Forbidden operation, re-login required.")
            return errors.SYSTEM_TRANSIENT
        elif error_status >= 500:
            LOG.warn("Server error, APIC might recover by itself.")
            return errors.SYSTEM_TRANSIENT
        else:
            LOG.warn("Unknown status code %s from APIC", error_status)
            return errors.UNKNOWN


class APICAPIErrorHandler(APICErrorHandler):
    """Error handling for the APICAPI library."""

    def __init__(self):
        self.apicapi_error_handlers = {
            # Most commonly returned exception by APICAPI when the network
            # is properly working but the operation cannot be completed.
            apicapi_exc.ApicResponseNotOk: (self._handle_apic_error, ""),
            apicapi_exc.ApicResponseNoCookie: (
                self._return_system_critical,
                "During a login operation, APIC returned properly but for "
                "some reason the login Cookie is missing. Needs manual "
                "intervention"),
            # APICAPI wraps Timeout errors into ApicHostNoResponse exceptions.
            # These are usually considerate system transient.
            apicapi_exc.ApicHostNoResponse: (
                self._return_system_transient,
                "APIC didn't respond and the request timed out."),
            # The transaction is not built properly, this operation will never
            # succeed
            apicapi_exc.ApicInvalidTransactionMultipleRoot: (
                self._return_operation_critical,
                "The transaction is not built properly, this operation "
                "will never succeed"),
            apicapi_exc.ApicManagedObjectNotSupported: (
                self._return_operation_critical,
                "The requested APIC object is not supported by the APICPI "
                "client, this operation will never succeed."
                "(apicapi upgrade might be required"),
            apicapi_exc.ApicSessionNotLoggedIn: (
                self._return_system_transient,
                "The APICAPI client is not logged in."
            )
        }

    def analyze_exception(self, e):
        """Analyze an apic_client exception from the APICAPI module.

        :param e:
        :return: the proper error type enumeration
        """
        err_func, msg = self.apicapi_error_handlers.get(
            type(e), (self.analyze_request_exception, ''))
        err_type = err_func(e)
        if msg:
            if err_type in errors.CRITICAL_ERRORS:
                LOG.error(msg)
            else:
                LOG.warn(msg)
        return err_type

    def _handle_apic_error(self, e):
        try:
            status = int(e.err_status)
        except ValueError:
            status = 0

        try:
            code = int(e.err_code)
        except ValueError:
            code = 0

        return self.analyze_apic_error(status, code)

    def _return_system_critical(self, e):
        return errors.SYSTEM_CRITICAL

    def _return_system_transient(self, e):
        return errors.SYSTEM_TRANSIENT

    def _return_operation_critical(self, e):
        return errors.OPERATION_CRITICAL
