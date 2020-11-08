"""Binary sensor to check internet link status via DNS queries."""

import logging
from datetime import timedelta, datetime
import time
import dns.resolver
import dns.ipv4
import dns.reversename
import dns.exception

from homeassistant.const import CONF_NAME, CONF_ENTITY_ID, CONF_SCAN_INTERVAL
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
    CONF_DEBUG_PROBE,
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

UPDATE_THROTTLE = timedelta(seconds=1)
PARALLEL_UPDATES = 0
LINK_STATUS_ICON = "mdi:wan"


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the link status sensors."""

    if discovery_info is None:
        return

    domain_config = hass.data[DOMAIN][DATA_DOMAIN_CONFIG]
    entities = []

    _LOGGER.info("setting up internet link status binary sensors")
    link_entities = []
    secondary_entities = []
    link_count = 0
    try:
        # for entity_id, link_config in domain_config[CONF_LINKS].items():
        for link_config in domain_config[CONF_LINKS]:
            link_count += 1
            # entity_id = "binary_sensor." + entity_id + "_status"
            entity_id = link_config.get(CONF_ENTITY_ID)
            name = link_config.get(
                CONF_NAME, (DEF_LINK_NAME % link_count) + DEF_LINK_NAME_SUFFIX
            )
            link_type = link_config.get(CONF_LINK_TYPE)
            server_count = (link_count - 1) % 4 + 1
            probe_server = link_config.get(
                CONF_PROBE_SERVER, DEF_LINK_PROBE_SERVER % server_count
            )
            probe_type = link_config.get(CONF_PROBE_TYPE, DEF_LINK_PROBE_TYPE)
            scan_interval = link_config.get(
                CONF_SCAN_INTERVAL, domain_config.get(CONF_SCAN_INTERVAL)
            )
            timeout = link_config.get(CONF_TIMEOUT, domain_config.get(CONF_TIMEOUT))
            retries = link_config.get(CONF_RETRIES, domain_config.get(CONF_RETRIES))
            if (
                link_type == LINK_TYPE_PRIMARY
                and DATA_PRIMARY_LINK_ENTITY in hass.data[DOMAIN]
            ):
                _LOGGER.warning(
                    "only one primary link allowed, %s changed to %s %s",
                    name,
                    CONF_LINK_TYPE,
                    LINK_TYPE_SECONDARY,
                )
                link_type = LINK_TYPE_SECONDARY

            entity = LinkStatusBinarySensor(
                hass,
                entity_id,
                name,
                link_count,
                link_type,
                probe_server,
                probe_type,
                timeout,
                retries,
                link_config,
            )

            ## Schedule this entity to update every scan_interval
            track_time_interval(hass, entity.update_entity_states, scan_interval)

            link_entities.append(entity)
            if entity:
                entities.append(entity)
                if link_type == LINK_TYPE_PRIMARY:
                    hass.data[DOMAIN][DATA_PRIMARY_LINK_ENTITY] = entity
                elif link_type == LINK_TYPE_SECONDARY:
                    secondary_entities.append(entity)
        hass.data[DOMAIN][DATA_SECONDARY_LINK_ENTITIES] = secondary_entities
        hass.data[DOMAIN][DATA_LINK_ENTITIES] = link_entities
        _LOGGER.debug("adding binary sensor entities: %s", str(entities))
        add_entities(entities, True)
        if DATA_PRIMARY_LINK_ENTITY not in hass.data[DOMAIN]:
            _LOGGER.warning(
                "no primary link specified, internet link sensor will not be updated"
            )
    except RuntimeError as exc:
        _LOGGER.error("error creating binary sensors: %s", exc)


class LinkStatusBinarySensor(BinarySensorEntity):
    """Sensor to check the status of an internet link."""

    def __init__(
        self,
        hass,
        entity_id,
        name,
        link_count,
        link_type,
        probe_server,
        probe_type,
        timeout,
        retries,
        probe_config,
    ):
        """Initialise the link check sensor."""
        self._data = hass.data[DOMAIN]
        self._name = name
        self._unique_id = DOMAIN + ":" + name
        self._link_type = link_type
        self._link_count = link_count
        self._probe_type = probe_type
        self._timeout = timeout
        self._retries = retries
        self._reverse_hostname = probe_config.get(CONF_REVERSE_HOSTNAME)
        self._debug_probe = probe_config.get(CONF_DEBUG_PROBE)

        if entity_id:
            self.entity_id = entity_id
        self._updated = False
        self.configured_ip = probe_config.get(CONF_CONFIGURED_IP)
        self.current_ip = None
        self.link_up = None
        self.link_failover = False
        self._ip_last_updated = None

        probe_host = None
        _LOGGER.debug(
            "%s(%x).__init__(): entity_id=%s, link_count=%d, link_type=%s, probe_server=%s, probe_type=%s, timeout=%s, retries=%s, reverse_hostname=%s, configured_ip=%s",
            name,
            id(self),
            entity_id,
            link_count,
            link_type,
            probe_server,
            probe_type,
            timeout,
            retries,
            self._reverse_hostname,
            self.configured_ip,
        )
        try:
            ## Attempt to parse as IP address
            dns.ipv4.inet_aton(probe_server)
            probe_host = probe_server
        except dns.exception.DNSException:
            pass

        if probe_host is None:
            ## Attempt to resolve as DNS name
            try:
                probe_host = str(dns.resolver.query(probe_server, lifetime=timeout)[0])
            except dns.exception.DNSException as exc:
                raise RuntimeError(
                    "could not resolve %s: %s" % (probe_server, exc)
                ) from exc

        self._probe_host = probe_host

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
        return self.link_up and not self.link_failover

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_CONNECTIVITY

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        ip_last_updated = self._ip_last_updated
        attrs = {
            ATTR_CONFIGURED_IP: self.configured_ip,
            ATTR_CURRENT_IP: self.current_ip,
            ATTR_LINK_FAILOVER: self.link_failover,
        }
        if ip_last_updated is not None:
            attrs[ATTR_IP_LAST_UPDATED] = datetime.fromtimestamp(
                ip_last_updated
            ).replace(microsecond=0)
        return attrs

    @property
    def should_poll(self):
        """Polling not required as we set up our own poller."""
        return False

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    def dns_probe(self, resolver):
        """Obtain public IP address using a probe."""
        probe_host = self._probe_host
        probe_type = self._probe_type
        current_ip = None

        try:
            if probe_type == PROBE_TYPE_GOOGLE:
                ## dig @ns1.google.com TXT o-o.myaddr.l.google.com +short
                for rdata in resolver.query("o-o.myaddr.l.google.com", "TXT"):
                    txt = rdata.strings[0].decode("utf-8")
                    ## Handle edns response, though this may only provide subnet level IP resolution
                    if txt.startswith("edns0-client-subnet"):
                        current_ip = txt[20:-3]
                    else:
                        current_ip = txt
            elif probe_type == PROBE_TYPE_OPENDNS:
                ## dig @resolver1.opendns.com ANY myip.opendns.com +short
                for rdata in resolver.query("myip.opendns.com", "A"):
                    current_ip = rdata.address
            elif probe_type == PROBE_TYPE_AKAMAI:
                ## dig @ns1-1.akamaitech.net ANY whoami.akamai.net +short
                for rdata in resolver.query("whoami.akamai.net", "A"):
                    current_ip = rdata.address
            else:
                _LOGGER.error(
                    "unimplemented probe type %s for server %s", probe_type, probe_host
                )
        except dns.exception.DNSException as exc:
            _LOGGER.debug(
                "failed: probe type %s for server %s: %s", probe_type, probe_host, exc
            )
            return None

        if self._debug_probe:
            _LOGGER.debug(
                "success: probe %s for server %s returned IP %s",
                probe_type,
                probe_host,
                current_ip,
            )
        return current_ip

    def dns_reverse_lookup_check(self):
        """Reverse DNS lookup current IP and match with reverse hostname."""
        current_ip = self.current_ip
        reverse_hostname = self._reverse_hostname
        timeout = self._timeout
        rquery = []
        ptr = ""
        try:
            rquery = dns.resolver.query(
                dns.reversename.from_address(current_ip), "PTR", lifetime=timeout
            )
            ptr = str(rquery[0])
            if reverse_hostname in ptr:
                _LOGGER.debug(
                    "success: reverse lookup: %s in %s", reverse_hostname, ptr
                )
                return True
            else:
                _LOGGER.debug(
                    "failed: reverse lookup: %s not in %s", reverse_hostname, ptr
                )
                return False
        except dns.exception.DNSException as exc:
            _LOGGER.warning("reverse lookup for %s failed: %s", current_ip, str(exc))
            return None

    def update_entity_states(self, now):
        """Update triggered by track_time_interval."""
        self.update()

    @Throttle(UPDATE_THROTTLE)
    def update(self):
        """Update the link status sensor."""
        name = self._name
        probe_host = self._probe_host
        retries = self._retries
        reverse_hostname = self._reverse_hostname
        timeout = self._timeout

        if not self._updated:
            _LOGGER.debug("%s(%x).update(): initial update", name, id(self))

        resolver = dns.resolver.Resolver()
        resolver.nameservers = [probe_host]
        resolver.timeout = timeout
        resolver.lifetime = timeout

        rtt_array = []
        current_ip = None
        link_up = True

        for count in range(retries):
            start_time = time.time()
            probe_ip = self.dns_probe(resolver)
            if probe_ip is not None:
                current_ip = probe_ip
                rtt = round((time.time() - start_time) * 1000, 3)
                rtt_array.append(rtt)
                if count < retries - 1 and rtt < timeout * 1000:
                    time.sleep(timeout - rtt / 1000)

        ## Calculate and update rtt sensor if sensors are set up
        rtt = round(sum(rtt_array) / len(rtt_array), 3) if rtt_array else None
        rtt_entities = self._data.get(DATA_LINK_RTT_ENTITIES)
        if rtt_entities:
            rtt_entity = rtt_entities[self._link_count - 1]
            if rtt_entity:
                rtt_entity.set_rtt(rtt, rtt_array)

        ## Check whether IP address has changed
        if self.current_ip != current_ip:
            self.current_ip = current_ip
            if current_ip is not None:
                ## Link is up
                self._ip_last_updated = time.time()
                if reverse_hostname:
                    ## Perform reverse DNS matching
                    link_up = self.dns_reverse_lookup_check()
                    _LOGGER.debug(
                        "%s reverse_check=%s, current_ip=%s", name, link_up, current_ip
                    )
                    if link_up:
                        if self.configured_ip is None:
                            _LOGGER.info(
                                "%s up (configured IP set), current_ip=%s",
                                name,
                                current_ip,
                            )
                            self.configured_ip = current_ip
                        elif self.configured_ip != current_ip:
                            _LOGGER.info(
                                "%s up (IP address changed), current_ip=%s",
                                name,
                                current_ip,
                            )
                        else:
                            _LOGGER.info(
                                "%s up (reverse check ok), current_ip=%s",
                                name,
                                current_ip,
                            )
                    else:
                        _LOGGER.info(
                            "%s down (reverse check failed), current_ip=%s",
                            name,
                            current_ip,
                        )
                elif self.link_failover:
                    _LOGGER.info("%s up (failover), current_ip=%s", name, current_ip)
                else:
                    _LOGGER.info("%s up, current_ip=%s", name, current_ip)
            else:
                _LOGGER.info(
                    "%s down, unable to reach server %s after %d retries",
                    name,
                    probe_host,
                    retries,
                )
                link_up = False
        # else: ## IP address has not changed, link is up
        if link_up is False:
            self.link_failover = False
        if self.link_up == link_up:
            return  ## link status unchanged

        ## Link status has changed
        self.link_up = link_up
        if self._link_type == LINK_TYPE_MONITOR_ONLY:
            ## Update configured_ip for monitor-only links where not manually
            ## configured or where not set via reverse_hostname
            ## NOTE: does not work if probe_server has active backup route
            ##       when component is started as it sets wrong configured_ip
            if link_up and self.configured_ip is None:
                self.configured_ip = self.current_ip
        else:
            ## Update parent entity for primary and secondary links
            sensor_entity = self._data.get(DATA_SENSOR_ENTITY)
            if sensor_entity:
                sensor_entity.set_state()

        ## Avoid calling self.schedule_update_ha_state during initial update
        self._updated = True

    def set_failover(self):
        """Set link to failed over state."""
        if self.link_up or not self.link_failover:
            self.link_up = False
            self.link_failover = True
            if self._updated:
                _LOGGER.debug(
                    "%s(%x).set_failover(): updating HA state", self._name, id(self)
                )
                self.schedule_update_ha_state()
            else:
                _LOGGER.debug(
                    "%s(%x).set_failover(): skipping update", self._name, id(self)
                )

    def clear_failover(self):
        """Clear link failover state."""
        if self.link_failover:
            self.link_failover = False
            if self._updated:
                _LOGGER.debug(
                    "%s(%x).clear_failover(): updating HA state", self._name, id(self)
                )
                self.schedule_update_ha_state()
            else:
                _LOGGER.debug(
                    "%s(%x).clear_failover(): skipping update", self._name, id(self)
                )

    def set_configured_ip(self):
        """Set this link's configured IP."""
        configured_ip = self.configured_ip
        current_ip = self.current_ip
        if configured_ip != current_ip:
            _LOGGER.info(
                "%s up (configured IP set), current_ip=%s",
                self._name,
                current_ip,
            )
            self.configured_ip = current_ip
            if configured_ip is not None:
                self._ip_last_updated = time.time()
            if self._updated:
                _LOGGER.debug(
                    "%s(%x).set_configured_ip(): updating HA state",
                    self._name,
                    id(self),
                )
                self.schedule_update_ha_state()
            else:
                _LOGGER.debug(
                    "%s(%x).set_configured_ip(): skipping update", self._name, id(self)
                )
