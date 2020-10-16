"""
Sensor to check Internet ISP link path status via DNS queries.
"""

import logging
from datetime import timedelta, datetime

import dns.resolver
import dns.ipv4
import dns.reversename

import requests
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

# ASUSWRT_CONFIG_FILENAME = "asuswrt.conf"
# HOST_SCRIPT = "/jffs/scripts/asuswrt-status.sh"

ATTR_ISP_IP_UPDATED = 'isp_ip_updated'
ATTR_PRIMARY_ISP_STATUS = 'primary_isp_status'
ATTR_PRIMARY_CONFIGURED_ISP_IP = 'primary_configured_isp_ip'
ATTR_PRIMARY_CURRENT_ISP_IP = 'primary_current_isp_ip'
ATTR_PRIMARY_ISP_IP_UPDATED = 'primary_isp_ip_updated'
ATTR_SECONDARY_ISP_STATUS = 'secondary_isp_status'
ATTR_SECONDARY_CONFIGURED_ISP_IP = 'secondary_configured_isp_ip'
ATTR_SECONDARY_CURRENT_ISP_IP = 'secondary_current_isp_ip'
ATTR_SECONDARY_ISP_IP_UPDATED = 'secondary_isp_ip_updated'
ATTR_VPN_STATUS = 'vpn_status'
ATTR_VPN_NAT_IP = 'vpn_nat_ip'

CONF_PRIMARY_PROBE = 'primary_probe'
CONF_PRIMARY_PROBE_TYPE = 'primary_probe_type'
CONF_PRIMARY_CONFIGURED_ISP_IP = 'primary_configured_isp_ip'
CONF_SECONDARY_PROBE = 'secondary_probe'
CONF_SECONDARY_PROBE_TYPE = 'secondary_probe_type'
CONF_SECONDARY_CONFIGURED_ISP_IP = 'secondary_configured_isp_ip'
CONF_VPN_PROBE = 'vpn_probe'
CONF_VPN_PROBE_TYPE = 'vpn_probe_type'
CONF_VPN_HOSTNAME = 'vpn_hostname'

PROBE_GOOGLE = 'google'
PROBE_OPENDNS = 'opendns'
PROBE_AKAMAI = 'akamai'

DEFAULT_NAME = 'Internet Status'
DEFAULT_PRIMARY_PROBE = 'ns1.google.com'
DEFAULT_PRIMARY_PROBE_TYPE = PROBE_GOOGLE
DEFAULT_SECONDARY_PROBE = 'ns2.google.com'
DEFAULT_SECONDARY_PROBE_TYPE = PROBE_GOOGLE
DEFAULT_VPN_PROBE = 'resolver1.opendns.com'
DEFAULT_VPN_PROBE_TYPE = PROBE_OPENDNS
DEFAULT_VPN_HOSTNAME = ''

ICON = 'mdi:wan'
SCAN_INTERVAL = timedelta(minutes=1)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PRIMARY_PROBE, default=DEFAULT_PRIMARY_PROBE): cv.string,
    vol.Optional(CONF_PRIMARY_PROBE_TYPE, default=DEFAULT_PRIMARY_PROBE_TYPE): cv.string,
    vol.Optional(CONF_PRIMARY_CONFIGURED_ISP_IP, default=""): cv.string,
    vol.Optional(CONF_SECONDARY_PROBE, default=DEFAULT_SECONDARY_PROBE): cv.string,
    vol.Optional(CONF_SECONDARY_PROBE_TYPE, default=DEFAULT_SECONDARY_PROBE_TYPE): cv.string,
    vol.Optional(CONF_SECONDARY_CONFIGURED_ISP_IP, default=""): cv.string,
    vol.Optional(CONF_VPN_PROBE, default=DEFAULT_VPN_PROBE): cv.string,
    vol.Optional(CONF_VPN_PROBE_TYPE, default=DEFAULT_VPN_PROBE_TYPE): cv.string,
    vol.Optional(CONF_VPN_HOSTNAME, default=DEFAULT_VPN_HOSTNAME): cv.string
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the ISP test sensor."""

    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    primary_probe = config.get(CONF_PRIMARY_PROBE)
    primary_probe_type = config.get(CONF_PRIMARY_PROBE_TYPE)
    primary_configured_isp_ip = config.get(CONF_PRIMARY_CONFIGURED_ISP_IP)
    if primary_configured_isp_ip == "":
        primary_configured_isp_ip = None
    secondary_probe = config.get(CONF_SECONDARY_PROBE)
    secondary_probe_type = config.get(CONF_SECONDARY_PROBE_TYPE)
    secondary_configured_isp_ip = config.get(CONF_SECONDARY_CONFIGURED_ISP_IP)
    if secondary_configured_isp_ip == "":
        secondary_configured_isp_ip = None
    vpn_probe = config.get(CONF_VPN_PROBE)
    vpn_probe_type = config.get(CONF_VPN_PROBE_TYPE)
    vpn_hostname = config.get(CONF_VPN_HOSTNAME)

    try:
        sensor = WanCheckSensor(name, host, primary_probe, primary_probe_type, \
                     primary_configured_isp_ip, secondary_probe, \
                     secondary_probe_type, secondary_configured_isp_ip, \
                     vpn_probe, vpn_probe_type, vpn_hostname)
        add_entities([sensor], True)
    except Exception as e:
        _LOGGER.error("Error creating sensor: " + str(e))

class WanCheckSensor(Entity):
    """Implementation of a ISP test sensor."""

    def __init__(self, name, host, primary_probe, primary_probe_type, primary_configured_isp_ip, secondary_probe, secondary_probe_type, secondary_configured_isp_ip, vpn_probe, vpn_probe_type, vpn_hostname):
        """Initialise the ISP test sensor."""

        self._name = name
        self._host = host
        try:
            probe_host = primary_probe
            try:
                dns.ipv4.inet_aton(probe_host)
            except:
                self._primary_probe = str(dns.resolver.query(probe_host)[0])
            else:
                self._primary_probe = probe_host
            self._primary_probe_type = primary_probe_type
            self._primary_configured_isp_ip = primary_configured_isp_ip
            probe_host = secondary_probe
            try:
                dns.ipv4.inet_aton(probe_host)
            except:
                self._secondary_probe = str(dns.resolver.query(probe_host)[0])
            else:
                self._secondary_probe = probe_host
            self._secondary_probe_type = secondary_probe_type
            self._secondary_configured_isp_ip = secondary_configured_isp_ip
            probe_host = vpn_probe
            try:
                dns.ipv4.inet_aton(probe_host)
            except:
                self._vpn_probe = str(dns.resolver.query(probe_host)[0])
            else:
                self._vpn_probe = probe_host
            self._vpn_probe_type = vpn_probe_type
            self._vpn_hostname = vpn_hostname
        except Exception as e:
            raise Exception('Could not resolve ' + probe_host + ': ' + str(e))

        self._isp_status = 'unknown'
        self._primary_isp_status = 'unknown'
        self._primary_current_isp_ip = None
        self._primary_isp_ip_updated = False
        self._secondary_isp_status = 'unknown'
        self._secondary_current_isp_ip = None
        self._secondary_isp_ip_updated = False
        self._vpn_status = 'down'
        self._vpn_nat_ip = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return ICON

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._isp_status

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            ATTR_PRIMARY_ISP_STATUS: self._primary_isp_status,
            ATTR_PRIMARY_CONFIGURED_ISP_IP: self._primary_configured_isp_ip,
            ATTR_PRIMARY_ISP_IP_UPDATED: self._primary_isp_ip_updated,
            ATTR_SECONDARY_ISP_STATUS: self._secondary_isp_status,
            ATTR_SECONDARY_CURRENT_ISP_IP: self._secondary_current_isp_ip,
            ATTR_SECONDARY_ISP_IP_UPDATED: self._secondary_isp_ip_updated,
            ATTR_VPN_STATUS: self._vpn_status
        }
        if self._primary_isp_status == 'up':
            attrs[ATTR_PRIMARY_CURRENT_ISP_IP] = self._primary_current_isp_ip
        if self._secondary_isp_status == 'up':
            attrs[ATTR_SECONDARY_CONFIGURED_ISP_IP] = self._secondary_configured_isp_ip
        if self._vpn_status == 'up':
            attrs[ATTR_VPN_NAT_IP] = self._vpn_nat_ip
        return attrs

    def dns_probe(self, server, probe_type):
        """Obtain self IP address using a probe."""

        resolver = dns.resolver.Resolver()
        resolver.nameservers = [server]
        resolver.timeout = 1.0
        resolver.lifetime = 3.0
        current_ip = None

        try:
            if probe_type == PROBE_GOOGLE:
                ## dig @ns1.google.com TXT o-o.myaddr.l.google.com +short
                for rdata in resolver.query('o-o.myaddr.l.google.com', 'TXT'):
                    txt = rdata.strings[0].decode('utf-8')
                    ## Handle edns response, though this may only provide subnet level IP resolution
                    if txt.startswith('edns0-client-subnet'):
                        current_ip = txt[20:-3]
                    else:
                        current_ip = txt
            elif probe_type == PROBE_OPENDNS:
                ## dig @resolver1.opendns.com ANY myip.opendns.com +short
                for rdata in resolver.query('myip.opendns.com', 'A'):
                    current_ip = rdata.address
            elif probe_type == PROBE_AKAMAI:
                ## dig @ns1-1.akamaitech.net ANY whoami.akamai.net +short
                for rdata in resolver.query('whoami.akamai.net', 'A'):
                    current_ip = rdata.address
            else:
                _LOGGER.warning("unimplemented probe type %s for server %s", probe_type, server)
                pass
        except Exception as e:
            _LOGGER.warning("probe type %s for server %s failed: %s", probe_type, server, str(e))
            pass

        _LOGGER.debug("probe %s for server %s returned IP %s", probe_type, server, current_ip)
        return current_ip

    def update(self):
        """Update the sensor."""

        ## Get public IP address of primary, secondary and VPN links
        self._primary_current_isp_ip = self.dns_probe(self._primary_probe, self._primary_probe_type)
        self._secondary_current_isp_ip = self.dns_probe(self._secondary_probe, self._secondary_probe_type)
        self._vpn_nat_ip = self.dns_probe(self._vpn_probe, self._vpn_probe_type)

        ## Compare reverse DNS map of VPN NAT IP to determine VPN status
        self._vpn_status = 'unknown'
        if self._vpn_hostname:
            if self._vpn_nat_ip and self._vpn_nat_ip != 'unknown':
                rquery = []
                ptr = ''
                try:
                    rquery = dns.resolver.query(dns.reversename.from_address(self._vpn_nat_ip), "PTR")
                    ptr = str(rquery[0])
                    if self._vpn_hostname in ptr:
                        self._vpn_status = 'up'
                    else:
                        self._vpn_status = 'down'
                except Exception as e:
                    _LOGGER.warning("Reverse lookup for %s failed: %s", self._vpn_nat_ip, str(e))
                    pass

        ## Determine link status
        self._isp_status = 'up'
        self._primary_isp_status = 'up'
        self._secondary_isp_status = 'up'
        self._primary_isp_ip_updated = False
        self._secondary_isp_ip_updated = False

        ## Check whether ISP link IP addresses could be retrieved
        # if self._primary_current_isp_ip == 'unknown':
        #     self._isp_status = 'error'
        #     self._primary_isp_status = 'unknown'
        # if self._secondary_current_isp_ip == 'unknown':
        #     self._isp_status = 'error'
        #     self._secondary_isp_status = 'unknown'

        ## Check link failover status
        if self._primary_current_isp_ip == None:
            ## Primary link failed but has not failed over to secondary yet
            self._isp_status = 'degraded (primary down)'
            self._primary_isp_status = 'down'
            if self._secondary_current_isp_ip == None:
                ## Both primary and secondary links have failed
                self._isp_status = 'down'
                self._secondary_isp_status = 'down'
        elif self._secondary_current_isp_ip == None:
            ## Secondary link failed but has not failed over to primary yet
            ## Primary link is up from previous check
            self._isp_status = 'degraded (secondary down)'
            self._secondary_isp_status = 'down'
        elif self._primary_current_isp_ip == self._secondary_current_isp_ip:
            ## One of the links has failed and both paths are using the same link
            self._isp_status = 'failover'
            if self._primary_current_isp_ip == self._secondary_configured_isp_ip:
                self._isp_status = 'failover (primary down)'
                self._primary_isp_status = 'down'
            elif self._secondary_current_isp_ip == self._primary_configured_isp_ip:
                self._isp_status = 'failover (secondary down)'
                self._secondary_isp_status = 'down'
        else:
            if self._primary_current_isp_ip != None and self._primary_current_isp_ip != 'unknown':
                if self._primary_configured_isp_ip == None:
                    self._primary_configured_isp_ip = self._primary_current_isp_ip
                elif self._primary_current_isp_ip != self._primary_configured_isp_ip:
                    self._primary_configured_isp_ip = self._primary_current_isp_ip
                    self._primary_isp_ip_updated = True
            if self._secondary_current_isp_ip != None and self._secondary_current_isp_ip != 'unknown':
                if self._secondary_configured_isp_ip == None:
                    self._secondary_configured_isp_ip = self._secondary_current_isp_ip
                elif self._secondary_current_isp_ip != self._secondary_configured_isp_ip:
                    self._secondary_configured_isp_ip = self._secondary_current_isp_ip
                    self._secondary_isp_ip_updated = True
