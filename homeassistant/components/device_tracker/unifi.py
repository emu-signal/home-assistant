"""
homeassistant.components.device_tracker.unifi
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Device tracker platform that supports scanning a Unifi controller
for device presence.

Configuration:

To use the Unifi tracker you will need to add something like the following
to your config/configuration.yaml

device_tracker:
    platform: unifi
    # the unifi controller sets its own hostname to 'unifi' by default
    host: unifi
    username: YOUR_ADMIN_USERNAME
    password: YOUR_ADMIN_PASSWORD
    # which major version of the controller you use
    version: v4

Variables:

host
*Required
The hostname or IP address of your controller

username
*Required
The username of a user with administrative privileges

password
*Required
The password for your given admin account.

version
*Optional, default=v2
The major version of the UniFi controller you are running (v2, v3, v4 supported)
"""
import logging
from datetime import timedelta
from time import time
import threading

from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers import validate_config
from homeassistant.util import Throttle
from homeassistant.components.device_tracker import DOMAIN

# Return cached results if last scan was less then this time ago
MIN_TIME_BETWEEN_SCANS = timedelta(seconds=5)

_LOGGER = logging.getLogger(__name__)


def get_scanner(hass, config):
    """ Validates config and returns a UniFi scanner. """
    if not validate_config(config,
            {DOMAIN: [CONF_HOST, CONF_USERNAME, CONF_PASSWORD, "version"]},
            _LOGGER):
        return None

    info = config[DOMAIN]

    scanner = UniFiDeviceScanner(
            info[CONF_HOST], info[CONF_USERNAME], info[CONF_PASSWORD], info["version"])

    return scanner if scanner.success_init else None

class UniFiDeviceScanner(object):
    """ This class queries a UniFi wireless router using the HTTP(S) API. """

    success_init = False

    # TODO Support port, site_id
    def __init__(self, host, username, password, version='v4'):
        self.last_results = []

        try:
            # Pylint does not play nice if not every folders has an __init__.py
            # pylint: disable=no-name-in-module, import-error
            from homeassistant.external.unifi.unifi.controller import Controller, APIError
        except ImportError:
            _LOGGER.exception(
                ("Failed to import unifi. "
                 "Did you maybe not run `git submodule init` "
                 "and `git submodule update`?"))

            self.success_init = False

            return

        try:
            self._controller = Controller(host, username, password, version=version)
            self.success_init = True
        except APIError:
            _LOGGER.exception(
                    ("Failed to connect to UniFi controller"
                     "Did you set the configuration correctly?"))

        self.lock = threading.Lock()

        if self.success_init:
            self._update_info()
        else:
            _LOGGER.error("Failed to Login")

    def scan_devices(self):
        """ Scans for devices, strips out those which are offline
            list containing found device ids. """
        self._update_info()

        return (device['mac'] for device in self.last_results
                if device['last_seen'] > time() - 10 )

    def get_device_name(self, mac):
        """ Returns the name of the given device or None if we don't know. """
        try:
            return next(device['name'] for device in self.last_results
                        if device['mac'] == mac)
        except StopIteration:
            return None

    @Throttle(MIN_TIME_BETWEEN_SCANS)
    def _update_info(self):
        """ Retrieves latest information from the UniFi router.
            Returns boolean if scanning successful. """
        if not self.success_init:
            return

        with self.lock:
            _LOGGER.debug("Scanning")
            self.last_results = self._controller.get_clients() or []
