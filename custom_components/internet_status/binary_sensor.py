"""Binary sensor to check internet link status via DNS queries."""

import logging
from datetime import timedelta, datetime
import time
import dns.resolver
import dns.ipv4
import dns.reversename
import dns.exception

from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    DEVICE_CLASS_CONNECTIVITY,
)
from homeassistant.helpers.event import track_time_interval
from homeassistant.util import Throttle

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
    ATTR_CONFIGURED_IP,
    ATTR_CURRENT_IP,
    ATTR_IP_LAST_UPDATED,
    ATTR_RTT,
    PROBE_GOOGLE,
    PROBE_OPENDNS,
    PROBE_AKAMAI,
    DATA_DOMAIN_CONFIG,
    DATA_PARENT_ENTITY,
    DATA_PRIMARY_ENTITY,
    DATA_SECONDARY_ENTITY,
    DATA_VPN_ENTITY,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_THROTTLE = timedelta(seconds=10)
SCAN_INTERVAL = timedelta(minutes=1)
PARALLEL_UPDATES = 0
ICON = 'mdi:wan'

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the link status sensors."""

    if discovery_info is None:
        return

    domain_config = hass.data[DOMAIN][DATA_DOMAIN_CONFIG]

    _LOGGER.debug("setting up internet link status binary sensors")
    scan_interval = domain_config.get(CONF_SCAN_INTERVAL)
    timeout = domain_config.get(CONF_TIMEOUT)
    retries = domain_config.get(CONF_RETRIES)
    config_primary = domain_config.get(CONF_PRIMARY_LINK)
    config_secondary = domain_config.get(CONF_SECONDARY_LINK)
    config_vpn = domain_config.get(CONF_VPN_LINK)
    primary_entity = None
    secondary_entity = None
    vpn_entity = None
    entities = []

    try:
        primary_entity = LinkStatusBinarySensor(hass, CONF_PRIMARY_LINK,
            scan_interval, timeout, retries, config_primary)
        hass.data[DOMAIN][DATA_PRIMARY_ENTITY] = primary_entity
        entities.append(primary_entity)
        if config_secondary:
            secondary_entity = LinkStatusBinarySensor(hass, CONF_SECONDARY_LINK,
                scan_interval, timeout, retries, config_secondary)
            hass.data[DOMAIN][DATA_SECONDARY_ENTITY] = secondary_entity
            entities.append(secondary_entity)
        if config_vpn:
            vpn_entity = LinkStatusBinarySensor(hass, CONF_VPN_LINK,
                scan_interval, timeout, retries, config_vpn)
            hass.data[DOMAIN][DATA_VPN_ENTITY] = vpn_entity
            entities.append(vpn_entity)
        add_entities(entities, True)

    except RuntimeError as exc:
        _LOGGER.error("Error creating binary sensors: %s", exc)

class LinkStatusBinarySensor(BinarySensorEntity):
    """Sensor to check the status of an internet link."""

    def __init__(self, hass, link_type, scan_interval, timeout, retries, probe_config):
        """Initialise the link check sensor."""
        scan_interval = probe_config.get(CONF_SCAN_INTERVAL, scan_interval)
        timeout = probe_config.get(CONF_TIMEOUT, timeout)
        retries = probe_config.get(CONF_RETRIES, retries)

        self._name = probe_config.get(CONF_NAME)
        self._data = hass.data[DOMAIN]
        self._link_type = link_type
        self._probe_server = probe_config.get(CONF_PROBE_SERVER)
        self._probe_type = probe_config.get(CONF_PROBE_TYPE)
        self._reverse_hostname = probe_config.get(CONF_REVERSE_HOSTNAME)
        self._scan_interval = scan_interval
        self._timeout = timeout
        self._retries = retries

        self.parent_entity = None
        self.configured_ip = probe_config.get(CONF_CONFIGURED_IP)
        self.current_ip = None
        self.link_up = None
        self.link_failover = False
        self.rtt = None
        self.ip_last_updated = None

        probe_host = probe_config.get(CONF_PROBE_SERVER)
        probe = None
        _LOGGER.debug("%s(scan_interval=%s, timeout=%s, retries=%s, probe_server=%s, probe_type=%s, reverse_hostname=%s, configured_ip=%s, probe_config=%s)",
            self._name, scan_interval, timeout, retries, self._probe_server,
            self._probe_type, self._reverse_hostname, self.configured_ip,
            probe_config)
        try:
            ## Attempt to parse as IP address
            dns.ipv4.inet_aton(probe_host)
            probe = probe_host
        except dns.exception.DNSException:
            pass

        if probe is None:
            ## Attempt to resolve as DNS name
            try:
                probe = str(dns.resolver.query(probe_host)[0])
            except dns.exception.DNSException as exc:
                raise RuntimeError('could not resolve %s: %s' % probe_host, exc) from exc

        ## Schedule this entity to update every scan_interval
        track_time_interval(hass, self._update_entity_states, scan_interval)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return ICON

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.link_up

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_CONNECTIVITY

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        ip_last_updated = self.ip_last_updated
        attrs = {
            ATTR_CONFIGURED_IP: self.configured_ip,
            ATTR_CURRENT_IP: self.current_ip,
            ATTR_RTT: self.rtt,
        }
        if ip_last_updated is not None:
            attrs[ATTR_IP_LAST_UPDATED] = datetime.fromtimestamp(ip_last_updated).replace(microsecond=0)
        return attrs

    @property
    def should_poll(self):
        """Polling not required as we set up our own poller."""
        return False

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
        except dns.exception.DNSException as exc:
            _LOGGER.warning("probe type %s for server %s failed: %s", probe_type, probe_server, exc)
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
        except dns.exception.DNSException as exc:
            _LOGGER.warning("reverse lookup for %s failed: %s", current_ip, str(exc))
            return None

    def _update_entity_states(self, now):
        """Update triggered by track_time_interval."""
        self.update()

    @Throttle(UPDATE_THROTTLE)
    def update(self):
        """Update the sensor."""
        probe_server = self._probe_server
        retries = self._retries
        reverse_hostname = self._reverse_hostname
        timeout = self._timeout

        resolver = dns.resolver.Resolver()
        resolver.nameservers = [ probe_server ]
        resolver.timeout = timeout
        resolver.lifetime = timeout

        rtt_array = [ ]
        current_ip = None
        link_up = True

        for count in range(retries):
            start_time = time.time()
            probe_ip = self.dns_probe(resolver)
            if probe_ip is not None:
                current_ip = probe_ip
                rtt = round((time.time()-start_time)*1000, 3)
                rtt_array.append(rtt)
                if count < retries-1 and rtt < timeout*1000:
                    time.sleep(timeout-rtt/1000)
        if self.current_ip != current_ip:
            _LOGGER.info("%s current_ip=%s", self._name, current_ip)
            self.current_ip = current_ip
            if current_ip is not None:
                self.ip_last_updated = time.time()
        rtt = round(sum(rtt_array)/len(rtt_array), 3) if rtt_array else None
        self.rtt = rtt
        _LOGGER.debug("%s rtt=%.3f rtt_array=%s", self._name, rtt, rtt_array)
        if current_ip is None:
            _LOGGER.warning("%s unable to reach server %s after %d retries",
                self._name, probe_server, retries)
            link_up = False
            self.link_failover = False

        if current_ip and reverse_hostname:
            ## Perform reverse DNS matching
            link_up = self.dns_reverse_lookup_check()

        if not self.link_failover:
            if self.link_up != link_up:
                ## Update link status if not failed over
                self.link_up = link_up
            else:
                ## No link status change, don't update parent
                return

        ## self.link_up and self.configured_ip are set/updated by
        ## parent entity for non-VPN links
        parent_entity = self._data[DATA_PARENT_ENTITY]
        link_type = self._link_type
        if parent_entity and (link_type == CONF_PRIMARY_LINK or link_type == CONF_SECONDARY_LINK):
            parent_entity.update()
