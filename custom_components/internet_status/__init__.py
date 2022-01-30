"""Monitor internet link status via DNS queries."""

import logging
import voluptuous as vol
from threading import Event

import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_NAME,
    CONF_ENTITY_ID,
    CONF_SCAN_INTERVAL,
)
from homeassistant.helpers import discovery

from .const import (
    DOMAIN,
    CONF_LINKS,
    CONF_LINK_TYPE,
    CONF_PROBE_SERVER,
    CONF_PROBE_TYPE,
    CONF_CONFIGURED_IP,
    CONF_TIMEOUT,
    CONF_RETRIES,
    CONF_REVERSE_HOSTNAME,
    CONF_RTT_SENSOR,
    CONF_UPDATE_RATIO,
    CONF_DEBUG_PROBE,
    CONF_DEBUG_RTT,
    DEF_SCAN_INTERVAL,
    DEF_TIMEOUT,
    DEF_RETRIES,
    DEF_UPDATE_RATIO,
    DEF_LINK_TYPE,
    DEF_NAME,
    DEF_DEBUG_PROBE,
    DEF_DEBUG_RTT,
    DATA_DOMAIN_CONFIG,
)

_LOGGER = logging.getLogger(__name__)

RTT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ENTITY_ID): vol.All(cv.entity_domain("sensor"), cv.entity_id),
        vol.Optional(CONF_UPDATE_RATIO, default=DEF_UPDATE_RATIO): cv.positive_int,
        vol.Optional(CONF_DEBUG_RTT, default=DEF_DEBUG_RTT): cv.boolean,
    }
)

LINK_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_LINK_TYPE, default=DEF_LINK_TYPE): cv.string,
        vol.Optional(CONF_ENTITY_ID): vol.All(
            cv.entity_domain("binary_sensor"), cv.entity_id
        ),
        vol.Optional(CONF_PROBE_SERVER): cv.string,
        vol.Optional(CONF_PROBE_TYPE): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL): cv.positive_time_period,
        vol.Optional(CONF_TIMEOUT): cv.socket_timeout,
        vol.Optional(CONF_RETRIES): cv.positive_int,
        vol.Optional(CONF_CONFIGURED_IP): cv.string,
        vol.Optional(CONF_REVERSE_HOSTNAME): cv.string,
        vol.Optional(CONF_RTT_SENSOR): RTT_SCHEMA,
        vol.Optional(CONF_DEBUG_PROBE, default=DEF_DEBUG_PROBE): cv.boolean,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_NAME, default=DEF_NAME): cv.string,
                vol.Optional(CONF_ENTITY_ID): vol.All(
                    cv.entity_domain("sensor"), cv.entity_id
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEF_SCAN_INTERVAL
                ): cv.positive_time_period,
                vol.Optional(CONF_TIMEOUT, default=DEF_TIMEOUT): cv.socket_timeout,
                vol.Optional(CONF_RETRIES, default=DEF_RETRIES): cv.positive_int,
                vol.Required(CONF_LINKS): vol.All(cv.ensure_list, [LINK_SCHEMA]),
                # vol.Required(CONF_LINKS): cv.schema_with_slug_keys(LINK_SCHEMA),
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass, config):
    """Set up the internet link status component."""
    _LOGGER.debug("setup component: config=%s", config[DOMAIN])
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {
            DATA_DOMAIN_CONFIG: config[DOMAIN],
        }

    ## Setup platforms. Load link sensors first
    discovery.load_platform(hass, "binary_sensor", DOMAIN, {}, config)
    discovery.load_platform(hass, "sensor", DOMAIN, {}, config)

    return True
