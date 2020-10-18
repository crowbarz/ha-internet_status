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
    CONF_PROBE_SERVER,
    CONF_PROBE_TYPE,
    CONF_LINKS,
    CONF_LINK_TYPE,
    CONF_CONFIGURED_IP,
    CONF_TIMEOUT,
    CONF_RETRIES,
    CONF_REVERSE_HOSTNAME,
    DEF_LINK_NAME,
    DEF_LINK_NAME_SUFFIX,
    DEF_LINK_PROBE_SERVER,
    DEF_LINK_PROBE_TYPE,
    ATTR_CONFIGURED_IP,
    ATTR_CURRENT_IP,
    ATTR_IP_LAST_UPDATED,
    ATTR_LINK_FAILOVER,
    LINK_TYPE_PRIMARY,
    LINK_TYPE_SECONDARY,
    LINK_TYPE_MONITOR_ONLY,
    PROBE_TYPE_GOOGLE,
    PROBE_TYPE_OPENDNS,
    PROBE_TYPE_AKAMAI,
    DATA_DOMAIN_CONFIG,
    DATA_SENSOR_ENTITY,
    DATA_PRIMARY_LINK_ENTITY,
    DATA_SECONDARY_LINK_ENTITIES,
    DATA_LINK_ENTITIES,
    DATA_LINK_RTT_ENTITIES,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_THROTTLE = timedelta(seconds=10)
SCAN_INTERVAL = timedelta(minutes=1)
PARALLEL_UPDATES = 0
LINK_STATUS_ICON = 'mdi:wan'

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the link status sensors."""

    if discovery_info is None:
        return

    domain_config = hass.data[DOMAIN][DATA_DOMAIN_CONFIG]

    _LOGGER.debug("setting up internet link status binary sensors")
    link_entities = []
    secondary_entities = []
    link_count = 0
    try:
        for link_config in domain_config[CONF_LINKS]:
            link_count += 1
            name = link_config.get(CONF_NAME,
                (DEF_LINK_NAME % link_count) + DEF_LINK_NAME_SUFFIX)
            link_type = link_config.get(CONF_LINK_TYPE)
            server_count = (link_count-1)%4+1
            probe_server = link_config.get(CONF_PROBE_SERVER, DEF_LINK_PROBE_SERVER % server_count)
            probe_type = link_config.get(CONF_PROBE_TYPE, DEF_LINK_PROBE_TYPE)
            scan_interval = link_config.get(CONF_SCAN_INTERVAL,
                domain_config.get(CONF_SCAN_INTERVAL))
            timeout = link_config.get(CONF_TIMEOUT,
                domain_config.get(CONF_TIMEOUT))
            retries = link_config.get(CONF_RETRIES,
                domain_config.get(CONF_RETRIES))
            if link_type == LINK_TYPE_PRIMARY and DATA_PRIMARY_LINK_ENTITY in hass.data[DOMAIN]:
                _LOGGER.warning("only one primary link allowed, %s changed to %s %s",
                    name, CONF_LINK_TYPE, LINK_TYPE_SECONDARY)
                link_type = LINK_TYPE_SECONDARY

            entity = LinkStatusBinarySensor(hass, name, link_count, link_type,
                probe_server, probe_type, scan_interval, timeout, retries,
                link_config)
            link_entities.append(entity)
            if link_type == LINK_TYPE_PRIMARY:
                hass.data[DOMAIN][DATA_PRIMARY_LINK_ENTITY] = entity
            elif link_type == LINK_TYPE_SECONDARY:
                secondary_entities.append(entity)
        hass.data[DOMAIN][DATA_SECONDARY_LINK_ENTITIES] = secondary_entities
        hass.data[DOMAIN][DATA_LINK_ENTITIES] = link_entities
        add_entities(link_entities, True)
        if DATA_PRIMARY_LINK_ENTITY not in hass.data[DOMAIN]:
            _LOGGER.warning("no primary link specified, internet link sensor will not be updated")

    except RuntimeError as exc:
        _LOGGER.error("Error creating binary sensors: %s", exc)

class LinkStatusBinarySensor(BinarySensorEntity):
    """Sensor to check the status of an internet link."""

    def __init__(self, hass, name, link_count, link_type, probe_server,
                 probe_type, scan_interval, timeout, retries, probe_config):
        """Initialise the link check sensor."""
        self._data = hass.data[DOMAIN]
        self._name = name
        self._link_type = link_type
        self._link_count = link_count
        self._probe_type = probe_type
        self._scan_interval = scan_interval
        self._timeout = timeout
        self._retries = retries
        self._reverse_hostname = probe_config.get(CONF_REVERSE_HOSTNAME)

        self.configured_ip = probe_config.get(CONF_CONFIGURED_IP)
        self.sensor_entity = None
        self.current_ip = None
        self.link_up = None
        self.link_failover = False
        self.rtt = None
        self.rtt_array = None
        self.ip_last_updated = None

        probe_host = None
        _LOGGER.debug("%s: link_count=%d, link_type=%s, probe_server=%s, probe_type=%s, scan_interval=%s, timeout=%s, retries=%s, reverse_hostname=%s, configured_ip=%s, probe_config=%s",
            name, link_count, link_type, probe_server, probe_type, scan_interval,
            timeout, retries, self._reverse_hostname, self.configured_ip,
            probe_config)
        try:
            ## Attempt to parse as IP address
            dns.ipv4.inet_aton(probe_server)
            probe_host = probe_server
        except dns.exception.DNSException:
            pass

        if probe_host is None:
            ## Attempt to resolve as DNS name
            try:
                probe_host = str(dns.resolver.query(probe_server)[0])
            except dns.exception.DNSException as exc:
                raise RuntimeError('could not resolve %s: %s' % (probe_server, exc)) from exc

        self._probe_host = probe_host

        ## Schedule this entity to update every scan_interval
        track_time_interval(hass, self._update_entity_states, scan_interval)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return LINK_STATUS_ICON

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
            ATTR_LINK_FAILOVER: self.link_failover,
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
        probe_host = self._probe_host
        probe_type = self._probe_type
        current_ip = None

        try:
            if probe_type == PROBE_TYPE_GOOGLE:
                ## dig @ns1.google.com TXT o-o.myaddr.l.google.com +short
                for rdata in resolver.query('o-o.myaddr.l.google.com', 'TXT'):
                    txt = rdata.strings[0].decode('utf-8')
                    ## Handle edns response, though this may only provide subnet level IP resolution
                    if txt.startswith('edns0-client-subnet'):
                        current_ip = txt[20:-3]
                    else:
                        current_ip = txt
            elif probe_type == PROBE_TYPE_OPENDNS:
                ## dig @resolver1.opendns.com ANY myip.opendns.com +short
                for rdata in resolver.query('myip.opendns.com', 'A'):
                    current_ip = rdata.address
            elif probe_type == PROBE_TYPE_AKAMAI:
                ## dig @ns1-1.akamaitech.net ANY whoami.akamai.net +short
                for rdata in resolver.query('whoami.akamai.net', 'A'):
                    current_ip = rdata.address
            else:
                _LOGGER.error("unimplemented probe type %s for server %s", probe_type, probe_host)
        except dns.exception.DNSException as exc:
            _LOGGER.debug("failed: probe type %s for server %s: %s", probe_type, probe_host, exc)
            return None

        _LOGGER.debug("probe %s for server %s returned IP %s", probe_type, probe_host, current_ip)
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
        name = self._name
        probe_host = self._probe_host
        retries = self._retries
        reverse_hostname = self._reverse_hostname
        timeout = self._timeout

        resolver = dns.resolver.Resolver()
        resolver.nameservers = [ probe_host ]
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
            _LOGGER.info("%s up, current_ip=%s", self._name, current_ip)
            self.current_ip = current_ip
            if current_ip is not None:
                self.ip_last_updated = time.time()

        ## Calculate rtt and update rtt sensor
        rtt = round(sum(rtt_array)/len(rtt_array), 3) if rtt_array else None
        rtt_entities = self._data[DATA_LINK_RTT_ENTITIES]
        if rtt_entities:
            rtt_entity = rtt_entities[self._link_count-1]
            if rtt_entity:
                rtt_entity.set_rtt(rtt, rtt_array)
                _LOGGER.debug("%s rtt=%.3f rtt_array=%s", name, rtt, rtt_array)
        if current_ip is None:
            if self.link_up == True:
                _LOGGER.info("%s down, unable to reach server %s after %d retries",
                    name, probe_host, retries)
            else:
                _LOGGER.debug("%s down, unable to reach server %s after %d retries",
                    name, probe_host, retries)

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
        sensor_entity = self._data[DATA_SENSOR_ENTITY]
        link_type = self._link_type
        if sensor_entity and link_type != LINK_TYPE_MONITOR_ONLY:
            sensor_entity.update()

    def set_failover(self):
        """Set link to failed over state."""
        if self.link_up or not self.link_failover:
            self.link_up = False
            self.link_failover = True
            if self.entity_id:
                self.schedule_update_ha_state()

    def clear_failover(self):
        """Clear link failover state."""
        if self.link_failover:
            self.link_failover = False
            if self.entity_id:
                self.schedule_update_ha_state()

    def set_configured_ip(self):
        """Set this link's configured IP."""
        configured_ip = self.configured_ip
        current_ip = self.current_ip
        if configured_ip != current_ip:
            self.configured_ip = current_ip
            if configured_ip is not None:
                self.ip_last_updated = time.time()
            if self.entity_id:
                self.schedule_update_ha_state()
