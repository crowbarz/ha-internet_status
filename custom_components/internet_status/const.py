"""Constants for the internet_status integration."""

from enum import StrEnum

from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL

DOMAIN = "internet_status"
VERSION = "0.7.2"

CONF_TIMEOUT = "timeout"
CONF_RETRIES = "retries"
CONF_LINKS = "links"
CONF_LINK_TYPE = "link_type"
CONF_PROBE_TARGET = "probe_target"
CONF_PROBE_TYPE = "probe_type"
CONF_REVERSE_HOSTNAME = "reverse_hostname"
CONF_CONFIGURED_IP = "configured_ip"
CONF_RTT_SENSOR = "rtt_sensor"
CONF_UPDATE_INTERVAL = "update_interval"

SERVICE_SET_CONFIGURED_IP = "set_configured_ip"


class LinkType(StrEnum):
    """Defined link types."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    MONITOR_ONLY = "monitor_only"


class ProbeType(StrEnum):
    """Defined probe types."""

    GOOGLE = "google"
    OPENDNS = "opendns"
    AKAMAI = "akamai"
    PING = "ping"
    FILE = "file"


DEFAULTS = {
    CONF_SCAN_INTERVAL: 30,
    CONF_TIMEOUT: 1.0,
    CONF_RETRIES: 3,
    CONF_LINK_TYPE: LinkType.MONITOR_ONLY,
    CONF_NAME: "Internet Status",
    # CONF_PROBE_SERVER: "ns%d.google.com",
    CONF_PROBE_TYPE: ProbeType.GOOGLE,
    CONF_RTT_SENSOR: {
        CONF_UPDATE_INTERVAL: 300,
    },
}
DEF_LINK_NAME_PREFIX = "Link "
DEF_LINK_RTT_SUFFIX = " RTT"

MIN_UPDATE_INTERVAL = 5

DEF_INTERNET_STATUS_ICON = {
    "up": "mdi:lan-connect",
    "down": "mdi:lan-disconnect",
    None: "mdi:lan-pending",
}

DEF_LINK_ICON = {
    True: "mdi:check-network-outline",
    False: "mdi:close-network-outline",
    None: "mdi:help-network-outline",
}

DEF_LINK_RTT_ICON = "mdi:web-clock"


ATTR_CONFIGURED_IP = CONF_CONFIGURED_IP
ATTR_CURRENT_IP = "current_ip"
ATTR_IP_LAST_UPDATED = "ip_last_updated"
ATTR_LINK_FAILOVER = "link_failover"
ATTR_RTT = "rtt"

DATA_DOMAIN_CONFIG = "domain_config"
DATA_SENSOR_ENTITY = "sensor_entity"
DATA_PRIMARY_LINK_ENTITY = "primary_link_entity"
DATA_SECONDARY_LINK_ENTITIES = "secondary_link_entities"
## index of link_entities correlates with index of link_rtt_entities
DATA_LINK_ENTITIES = "link_entities"
DATA_LINK_RTT_ENTITIES = "link_rtt_entities"
