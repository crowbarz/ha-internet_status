"""Constants for the internet_status integration."""

from datetime import timedelta

DOMAIN = 'internet_status'

CONF_PRIMARY_LINK = 'primary_link'
CONF_SECONDARY_LINK = 'secondary_link'
CONF_VPN_LINK = 'vpn_link'
CONF_PROBE_SERVER = 'probe_host'
CONF_PROBE_TYPE = 'probe_type'
CONF_CONFIGURED_IP = 'configured_ip'
CONF_TIMEOUT = 'timeout'
CONF_RETRIES = 'retries'
CONF_REVERSE_HOSTNAME = 'reverse_hostname'

ATTR_CONFIGURED_IP = CONF_CONFIGURED_IP
ATTR_CURRENT_IP = 'current_ip'
ATTR_IP_LAST_UPDATED = 'ip_last_updated'
ATTR_RTT = 'rtt'

PROBE_GOOGLE = 'google'
PROBE_OPENDNS = 'opendns'
PROBE_AKAMAI = 'akamai'

DATA_DOMAIN_CONFIG = "domain_config"
DATA_PARENT_ENTITY = "parent_entity"
DATA_PRIMARY_ENTITY = "primary_entity"
DATA_SECONDARY_ENTITY = "secondary_entity"
DATA_VPN_ENTITY = "vpn_entity"

DEF_SCAN_INTERVAL = timedelta(minutes=1)
DEF_TIMEOUT = 1.0
DEF_RETRIES = 3

DEF_NAME = "Internet Status"
DEF_NAME_PRIMARY_LINK = "Primary Link Status"
DEF_PRIMARY_PROBE = 'ns1.google.com'
DEF_PRIMARY_PROBE_TYPE = PROBE_GOOGLE
DEF_NAME_SECONDARY_LINK = "Secondary Link Status"
DEF_SECONDARY_PROBE = 'ns2.google.com'
DEF_SECONDARY_PROBE_TYPE = PROBE_GOOGLE
DEF_NAME_VPN = "VPN Status"
DEF_VPN_PROBE = 'resolver1.opendns.com'
DEF_VPN_PROBE_TYPE = PROBE_OPENDNS
