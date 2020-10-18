"""Monitor internet link status via DNS queries."""

import logging
import time
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_NAME,
    CONF_SCAN_INTERVAL,
)
from homeassistant.helpers import discovery

from .const import (
    DOMAIN,
    CONF_PRIMARY_LINK,
    CONF_SECONDARY_LINK,
    CONF_VPN_LINK,
    CONF_PROBE_SERVER,
    CONF_PROBE_TYPE,
    CONF_CONFIGURED_IP,
    CONF_TIMEOUT,
    CONF_RETRIES,
    CONF_REVERSE_HOSTNAME,
    DEF_SCAN_INTERVAL,
    DEF_TIMEOUT,
    DEF_RETRIES,
    DEF_NAME,
    DEF_NAME_PRIMARY_LINK,
    DEF_PRIMARY_PROBE,
    DEF_PRIMARY_PROBE_TYPE,
    DEF_NAME_SECONDARY_LINK,
    DEF_SECONDARY_PROBE,
    DEF_SECONDARY_PROBE_TYPE,
    DEF_NAME_VPN,
    DEF_VPN_PROBE,
    DEF_VPN_PROBE_TYPE,
    DATA_DOMAIN_CONFIG,
    )

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_NAME, default=DEF_NAME): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEF_SCAN_INTERVAL): cv.positive_time_period,
        vol.Optional(CONF_TIMEOUT, default=DEF_TIMEOUT): cv.socket_timeout,
        vol.Optional(CONF_RETRIES, default=DEF_RETRIES): cv.positive_int,
        vol.Required(CONF_PRIMARY_LINK): vol.Schema({
            vol.Optional(CONF_NAME, default=DEF_NAME_PRIMARY_LINK): cv.string,
            vol.Optional(CONF_PROBE_SERVER, default=DEF_PRIMARY_PROBE): cv.string,
            vol.Optional(CONF_PROBE_TYPE, default=DEF_PRIMARY_PROBE_TYPE): cv.string,
            vol.Optional(CONF_SCAN_INTERVAL): cv.positive_time_period,
            vol.Optional(CONF_TIMEOUT): cv.socket_timeout,
            vol.Optional(CONF_RETRIES): cv.positive_int,
            vol.Optional(CONF_CONFIGURED_IP): cv.string,
        }),
        vol.Optional(CONF_SECONDARY_LINK): vol.Schema({
            vol.Optional(CONF_NAME, default=DEF_NAME_SECONDARY_LINK): cv.string,
            vol.Optional(CONF_PROBE_SERVER, default=DEF_SECONDARY_PROBE): cv.string,
            vol.Optional(CONF_PROBE_TYPE, default=DEF_SECONDARY_PROBE_TYPE): cv.string,
            vol.Optional(CONF_SCAN_INTERVAL): cv.positive_time_period,
            vol.Optional(CONF_TIMEOUT): cv.socket_timeout,
            vol.Optional(CONF_RETRIES): cv.positive_int,
            vol.Optional(CONF_CONFIGURED_IP): cv.string,
        }),
        vol.Optional(CONF_VPN_LINK): vol.Schema({
            vol.Optional(CONF_NAME, default=DEF_NAME_VPN): cv.string,
            vol.Optional(CONF_PROBE_SERVER, default=DEF_VPN_PROBE): cv.string,
            vol.Optional(CONF_PROBE_TYPE, default=DEF_VPN_PROBE_TYPE): cv.string,
            vol.Optional(CONF_SCAN_INTERVAL): cv.positive_time_period,
            vol.Optional(CONF_TIMEOUT): cv.socket_timeout,
            vol.Optional(CONF_RETRIES): cv.positive_int,
            vol.Optional(CONF_CONFIGURED_IP): cv.string,
            vol.Optional(CONF_REVERSE_HOSTNAME): cv.string,
        }),
    }),
}, extra=vol.ALLOW_EXTRA)

def setup(hass, config):
    """Set up the internet link status component."""
    _LOGGER.debug("setup component: config=%s", config[DOMAIN])
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = { DATA_DOMAIN_CONFIG: config[DOMAIN] }

    ## Setup platforms. Load link sensors first
    discovery.load_platform(hass, "binary_sensor", DOMAIN, {}, config)
    # _LOGGER.debug("sleeping")
    # time.sleep(5)
    discovery.load_platform(hass, "sensor", DOMAIN, {}, config)

    return True
