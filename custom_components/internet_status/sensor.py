"""Sensor to check internet link status via DNS queries."""

import logging
from datetime import timedelta, datetime
import time
import dns.resolver
import dns.ipv4
import dns.reversename
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

CONF_PRIMARY_LINK = 'primary_link'
CONF_SECONDARY_LINK = 'secondary_link'
CONF_VPN = 'vpn'
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

DEF_TIMEOUT = 1.0
DEF_RETRIES = 3
DEF_UPDATE_THROTTLE = timedelta(seconds=10)

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

ICON = 'mdi:wan'
SCAN_INTERVAL = timedelta(minutes=1)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEF_NAME): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEF_TIMEOUT): cv.socket_timeout,
    vol.Optional(CONF_RETRIES, default=DEF_RETRIES): cv.positive_int,
    vol.Required(CONF_PRIMARY_LINK): vol.Schema({
        vol.Optional(CONF_NAME, default=DEF_NAME_PRIMARY_LINK): cv.string,
        vol.Optional(CONF_PROBE_SERVER, default=DEF_PRIMARY_PROBE): cv.string,
        vol.Optional(CONF_PROBE_TYPE, default=DEF_PRIMARY_PROBE_TYPE): cv.string,
        vol.Optional(CONF_CONFIGURED_IP): cv.string,
        vol.Optional(CONF_TIMEOUT): cv.socket_timeout,
        vol.Optional(CONF_RETRIES): cv.positive_int,
    }),
    vol.Optional(CONF_SECONDARY_LINK): vol.Schema({
        vol.Optional(CONF_NAME, default=DEF_NAME_SECONDARY_LINK): cv.string,
        vol.Optional(CONF_PROBE_SERVER, default=DEF_SECONDARY_PROBE): cv.string,
        vol.Optional(CONF_PROBE_TYPE, default=DEF_SECONDARY_PROBE_TYPE): cv.string,
        vol.Optional(CONF_CONFIGURED_IP): cv.string,
        vol.Optional(CONF_TIMEOUT): cv.socket_timeout,
        vol.Optional(CONF_RETRIES): cv.positive_int,
    }),
    vol.Optional(CONF_VPN): vol.Schema({
        vol.Optional(CONF_NAME, default=DEF_NAME_VPN): cv.string,
        vol.Optional(CONF_PROBE_SERVER, default=DEF_VPN_PROBE): cv.string,
        vol.Optional(CONF_PROBE_TYPE, default=DEF_VPN_PROBE_TYPE): cv.string,
        vol.Optional(CONF_CONFIGURED_IP): cv.string,
        vol.Optional(CONF_REVERSE_HOSTNAME): cv.string,
        vol.Optional(CONF_TIMEOUT): cv.socket_timeout,
        vol.Optional(CONF_RETRIES): cv.positive_int,
    }),
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the internet link status sensor."""

    name = config.get(CONF_NAME)
    timeout = config.get(CONF_TIMEOUT)
    retries = config.get(CONF_RETRIES)
    config_primary = config.get(CONF_PRIMARY_LINK)
    config_secondary = config.get(CONF_SECONDARY_LINK)
    config_vpn = config.get(CONF_VPN)
    primary_entity = None
    secondary_entity = None
    vpn_entity = None
    entities = []

    try:
        primary_entity = LinkStatusSensor(timeout, retries, config_primary)
        entities.append(primary_entity)
        if config_secondary:
            secondary_entity = LinkStatusSensor(timeout, retries, config_secondary)
            entities.append(secondary_entity)
        if config_vpn:
            vpn_entity = LinkStatusSensor(timeout, retries, config_vpn)
            entities.append(vpn_entity)
        internet_status_entity = InternetStatusSensor(name, timeout, retries, \
            primary_entity, secondary_entity, vpn_entity)
        entities.append(internet_status_entity)
        add_entities(entities, True)
    except Exception as e:
        _LOGGER.error("Error creating sensors: %s", str(e))

class LinkStatusSensor(Entity):
    """Sensor to check the status of an internet link."""

    def __init__(self, timeout, retries, probe_config):
        """Initialise the link check sensor."""
        self._name = probe_config.get(CONF_NAME)
        self._probe_server = probe_config.get(CONF_PROBE_SERVER)
        self._probe_type = probe_config.get(CONF_PROBE_TYPE)
        self._reverse_hostname = probe_config.get(CONF_REVERSE_HOSTNAME)
        self._timeout = timeout
        self._retries = retries
        self._rtt = None

        self.parent_sensor = None
        self.configured_ip = probe_config.get(CONF_CONFIGURED_IP)
        self.current_ip = None
        self.link_up = None
        self.ip_last_updated = None

        probe_host = probe_config.get(CONF_PROBE_SERVER)
        probe = None
        try:
            ## Attempt to parse as IP address
            dns.ipv4.inet_aton(probe_host)
            probe = probe_host
        except dns.exception:
            pass

        if probe is None:
            ## Attempt to resolve as DNS name
            try:
                probe = str(dns.resolver.query(probe_host)[0])
            except dns.exception as e:
                raise Exception('Could not resolve %s: %s' % probe_host, str(e))

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
        return self.link_up

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        ip_last_updated = self.ip_last_updated
        attrs = {
            ATTR_CONFIGURED_IP: self.configured_ip,
            ATTR_CURRENT_IP: self.current_ip,
            ATTR_RTT: self._rtt,
        }
        if ip_last_updated is not None:
            attrs[ATTR_IP_LAST_UPDATED] = datetime.fromtimestamp(ip_last_updated).replace(microsecond=0)
        return attrs

    def dns_probe(self, resolver):
        """Obtain public IP address using a probe."""
        probe_server = self._probe_server
        probe_type = self._probe_type
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
                _LOGGER.error("unimplemented probe type %s for server %s", probe_type, probe_server)
        except dns.exception as e:
            _LOGGER.warning("probe type %s for server %s failed: %s", probe_type, probe_server, str(e))
            return None

        _LOGGER.debug("probe %s for server %s returned IP %s", probe_type, probe_server, current_ip)
        return current_ip

    def dns_reverse_lookup_check(self):
        """Reverse DNS lookup current IP and match with reverse hostname."""
        current_ip = self.current_ip
        rquery = []
        ptr = ''
        try:
            rquery = dns.resolver.query(dns.reversename.from_address(current_ip), "PTR")
            ptr = str(rquery[0])
            if self._reverse_hostname in ptr:
                return True
            else:
                return False
        except dns.exception as e:
            _LOGGER.warning("Reverse lookup for %s failed: %s", current_ip, str(e))
            return None

    @Throttle(DEF_UPDATE_THROTTLE)
    def update(self):
        """Update the sensor."""
        probe_server = self._probe_server
        retries = self._retries
        reverse_hostname = self._reverse_hostname

        resolver = dns.resolver.Resolver()
        resolver.nameservers = [ probe_server ]
        resolver.timeout = self._timeout
        resolver.lifetime = self._timeout

        rtt = None
        current_ip = None

        for _ in range(retries):
            start_time = time.time()
            current_ip = self.dns_probe(resolver)
            if current_ip is not None:
                rtt = round((time.time()-start_time)*1000, 3)
                break
        if self.current_ip != current_ip:
            self.ip_last_updated = time.time()
            self.current_ip = current_ip
        self._rtt = rtt
        if current_ip is None:
            _LOGGER.warning("unable to reach server %s after %d retries", probe_server, retries)
            self.link_up = False
            return False

        if self.current_ip and reverse_hostname:
            self.link_up = self.dns_reverse_lookup_check()
        else:
            self.link_up = True

        ## self.link_up and self.configured_ip are set/updated by
        ## parent sensor for non-VPN links
        if self.parent_sensor:
            self.parent_sensor.update()

class InternetStatusSensor(Entity):
    """Sensor that determines the status of access to the internet."""

    def __init__(self, name, timeout, retries, primary_entity, secondary_entity, vpn_entity):
        """Initialise the internet status sensor."""
        self._name = name
        self._timeout = timeout
        self._retries = retries
        self._primary_entity = primary_entity
        self._secondary_entity = secondary_entity
        self._vpn_entity = vpn_entity
        self._link_status = None

        if primary_entity:
            primary_entity.parent_sensor = self
        if secondary_entity:
            secondary_entity.parent_sensor = self
        if vpn_entity:
            vpn_entity.parent_sensor = self

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
        return self._link_status

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attrs = {
        }
        return attrs

    @property
    def should_poll(self):
        """Polling not required as link sensors will trigger update."""
        return False

    def update(self):
        """Update the sensor."""

        ## Determine link status
        self._link_status = 'up'
        primary_entity = self._primary_entity
        secondary_entity = self._secondary_entity

        primary_link_up = primary_entity.link_up
        primary_configured_ip = primary_entity.configured_ip
        primary_current_ip = primary_entity.current_ip
        secondary_link_up = secondary_entity.link_up
        secondary_configured_ip = secondary_entity.configured_ip
        secondary_current_ip = secondary_entity.current_ip

        _LOGGER.debug("internet_status update: link_status: %s/%s/%s %s/%s/%s",
            primary_link_up, primary_configured_ip, primary_current_ip,
            secondary_link_up, secondary_configured_ip, secondary_current_ip)

        if primary_link_up is None or secondary_link_up is None:
            self._link_status = "error"
            self.schedule_update_ha_state()
            return False

        ## Check link failover status
        if not primary_link_up:
            ## Primary link failed but has not failed over to secondary yet
            self._link_status = 'degraded (primary down)'
            if not secondary_link_up:
                ## Both primary and secondary links have failed
                self._link_status = 'down'
        elif not secondary_link_up:
            ## Secondary link failed but has not failed over to primary yet
            ## Primary link is up from previous check
            self._link_status = 'degraded (secondary down)'
        elif primary_current_ip == secondary_current_ip:
            ## One of the links has failed and both paths are using the same link
            self._link_status = 'failover'
            if primary_current_ip == secondary_configured_ip:
                self._link_status = 'failover (primary down)'
                primary_entity.link_up = False
            elif secondary_current_ip == primary_configured_ip:
                self._link_status = 'failover (secondary down)'
                secondary_entity.link_up = False
        else:
            if primary_current_ip:
                if primary_configured_ip is None:
                    primary_entity.configured_ip = primary_current_ip
                elif primary_current_ip != primary_configured_ip:
                    primary_entity.configured_ip = primary_current_ip
                    primary_entity.ip_last_updated = time.time()
            if secondary_current_ip:
                if secondary_configured_ip is None:
                    secondary_entity.configured_ip = secondary_current_ip
                elif secondary_current_ip != secondary_configured_ip:
                    secondary_entity.configured_ip = secondary_current_ip
                    secondary_entity.ip_last_updated = time.time()
        self.schedule_update_ha_state()
