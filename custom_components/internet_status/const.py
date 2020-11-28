"""Constants for the internet_status integration."""

from datetime import timedelta

DOMAIN = "internet_status"

CONF_LINKS = "links"
CONF_LINK_TYPE = "link_type"
CONF_PROBE_SERVER = "probe_server"
CONF_PROBE_TYPE = "probe_type"
CONF_CONFIGURED_IP = "configured_ip"
CONF_TIMEOUT = "timeout"
CONF_RETRIES = "retries"
CONF_REVERSE_HOSTNAME = "reverse_hostname"
CONF_RTT_SENSOR = "rtt_sensor"
CONF_UPDATE_RATIO = "update_ratio"
CONF_DEBUG_PROBE = "debug_probe"
CONF_DEBUG_RTT = "debug_rtt"

LINK_TYPE_PRIMARY = "primary"
LINK_TYPE_SECONDARY = "secondary"
LINK_TYPE_MONITOR_ONLY = "monitor_only"

PROBE_TYPE_GOOGLE = "google"
PROBE_TYPE_OPENDNS = "opendns"
PROBE_TYPE_AKAMAI = "akamai"
PROBE_TYPE_FILE = "file"

DEF_SCAN_INTERVAL = timedelta(seconds=30)
DEF_TIMEOUT = 1.0
DEF_RETRIES = 3
DEF_UPDATE_RATIO = 10
DEF_LINK_TYPE = LINK_TYPE_MONITOR_ONLY
DEF_NAME = "Internet Status"
DEF_LINK_NAME = "Link %d"
DEF_LINK_NAME_SUFFIX = " Status"
DEF_LINK_RTT_SUFFIX = " Round Trip Time"
DEF_LINK_PROBE_SERVER = "ns%d.google.com"
DEF_LINK_PROBE_TYPE = PROBE_TYPE_GOOGLE
DEF_DEBUG_PROBE = False
DEF_DEBUG_RTT = False

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
