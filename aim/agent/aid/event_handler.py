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

import abc
import os
import Queue as queue
import six
import socket
import time
import traceback

from oslo_log import log as logging

from aim.common import utils


LOG = logging.getLogger(__name__)
EVENT_SERVE = 'serve'
EVENT_RECONCILE = 'reconcile'
EVENTS = [EVENT_SERVE, EVENT_RECONCILE]
PAYLOAD_MAX_LEN = 1024
SOCKET_RECONNECT_MAX_WAIT = 10


@six.add_metaclass(abc.ABCMeta)
class EventHandlerBase(object):
    """Event Handler for AID."""

    @abc.abstractmethod
    def initialize(self, conf):
        """Initialize Event Handler

        :param conf
        :return:
        """

    @abc.abstractmethod
    def get_event(self, timeout=None):
        """Get AID event

        Blocking call, which returns AID events when present. A timeout
        can be set.
        :param timeout
        :return:
        """


@six.add_metaclass(abc.ABCMeta)
class SenderBase(object):
    """Sender for AID events."""

    @abc.abstractmethod
    def initialize(self, conf):
        """Initialize Sender

        :param conf
        :return:
        """

    @abc.abstractmethod
    def serve(self):
        """Send a serve event.

        :return:
        """

    @abc.abstractmethod
    def reconcile(self):
        """Send a reconcile event.

        :return:
        """


class EventHandler(EventHandlerBase):

    q = None

    def initialize(self, conf_manager):
        LOG.info("Initialize Event Handler")
        self.recovery_retries = None
        self.conf_manager = conf_manager
        self.listener = self._spawn_listener()
        EventHandler.q = queue.Queue()
        time.sleep(0)
        return self

    def _connect(self):
        self.us_path = self.conf_manager.get_option('unix_socket_path',
                                                    group='aim')
        LOG.info("Connect to socket %s" % self.us_path)
        try:
            os.unlink(self.us_path)
        except OSError:
            if os.path.exists(self.us_path):
                raise
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock_dir = os.path.dirname(self.us_path)
        if not os.path.exists(sock_dir):
            os.makedirs(sock_dir)
        self.sock.bind(self.us_path)

    def _spawn_listener(self):
        return utils.spawn_thread(self._listener)

    def _listener(self):
        # Multiple event notifiers can connect to AID
        while True:
            try:
                self._connect()
                LOG.info("Listening for Events on %s", self.us_path)
                while True:
                    self._recv_loop()
                self.recovery_retries = None
            except Exception as e:
                LOG.debug(traceback.format_exc())
                LOG.error("An error as occurred in the event listener "
                          "thread: %s" % e)
                self.recovery_retries = utils.exponential_backoff(
                    SOCKET_RECONNECT_MAX_WAIT,
                    tentative=self.recovery_retries)
            finally:
                try:
                    self.sock.close()
                except AttributeError:
                    LOG.debug("Socket wasn't initialized before failure")

    def _recv_loop(self):
        event = self.sock.recv(PAYLOAD_MAX_LEN)
        LOG.debug("Received event %s" % event)
        if event.lower() in EVENTS:
            self._put_event(event)

    def get_event(self, timeout=None):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            # Timeout expired
            return None

    @staticmethod
    def serve():
        EventHandler._put_event(EVENT_SERVE)

    @staticmethod
    def reconcile():
        EventHandler._put_event(EVENT_RECONCILE)

    @staticmethod
    def _put_event(event):
        try:
            EventHandler.q.put_nowait(event)
        except queue.Full:
            LOG.warn("Event queue is full, discard %s event" % event)
        except AttributeError:
            LOG.warn("Event queue not initialized, cannot set event")


class EventSender(SenderBase):

    def __init__(self):
        self.recovery_retries = None

    def initialize(self, conf):
        try:
            self.conf_manager = conf
            self.us_path = self.conf_manager.get_option('unix_socket_path',
                                                        group='aim')
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self.sock.connect(self.us_path)
            LOG.info("Connected to %s" % self.us_path)
            self.recovery_retries = None
            return self
        except Exception:
            LOG.error(traceback.format_exc())
            self.recovery_retries = utils.exponential_backoff(
                SOCKET_RECONNECT_MAX_WAIT, tentative=self.recovery_retries)

    def serve(self):
        self._send(EVENT_SERVE)

    def reconcile(self):
        self._send(EVENT_RECONCILE)

    def _send(self, event):
        LOG.debug("Sending %s event" % event)
        try:
            self.sock.send(event)
        except Exception as e:
            LOG.debug(traceback.format_exc())
            LOG.error("An error as occurred in the event sender "
                      "thread: %s" % e.message)
            self.sock.close()
            self.initialize(self.conf_manager)
