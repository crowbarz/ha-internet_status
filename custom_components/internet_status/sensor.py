"""Sensor to represent overall internet status."""

import logging

from homeassistant.const import CONF_NAME, CONF_ENTITY_ID

from homeassistant.components.sensor import (
    # SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from .const import (
    DOMAIN,
    CONF_LINKS,
    CONF_RTT_SENSOR,
    CONF_UPDATE_RATIO,
    CONF_DEBUG_RTT,
    DEF_LINK_NAME,
    DEF_LINK_RTT_SUFFIX,
    DATA_DOMAIN_CONFIG,
    DATA_SENSOR_ENTITY,
    DATA_PRIMARY_LINK_ENTITY,
    DATA_SECONDARY_LINK_ENTITIES,
    DATA_LINK_RTT_ENTITIES,
    ATTR_RTT,
)

_LOGGER = logging.getLogger(__name__)

INTERNET_STATUS_ICON = "mdi:wan"
LINK_RTT_ICON = "mdi:lan-connect"


def setup_platform(hass, _config, add_entities, discovery_info=None):
    """Set up the internet status sensor."""

    if discovery_info is None:
        return

    domain_config = hass.data[DOMAIN][DATA_DOMAIN_CONFIG]
    entities = []

    _LOGGER.info("setting up internet link status sensor")
    name = domain_config.get(CONF_NAME)
    entity_id = domain_config.get(CONF_ENTITY_ID)
    internet_status_entity = InternetStatusSensor(hass, entity_id, name)
    hass.data[DOMAIN][DATA_SENSOR_ENTITY] = internet_status_entity
    entities.append(internet_status_entity)

    _LOGGER.info("setting up link rtt sensors")
    link_rtt_entities = []
    link_count = 0
    # for entity_id, link_config in domain_config[CONF_LINKS].items():
    for link_config in domain_config[CONF_LINKS]:
        link_count += 1
        # entity_id = "sensor." + entity_id + "_rtt"
        link_rtt_config = link_config.get(CONF_RTT_SENSOR)
        entity_id = link_rtt_config.get(CONF_ENTITY_ID)
        entity = None
        if link_rtt_config is not None:
            if CONF_NAME in link_config:
                name = link_config[CONF_NAME] + DEF_LINK_RTT_SUFFIX
            else:
                name = (DEF_LINK_NAME % link_count) + DEF_LINK_RTT_SUFFIX
            name = link_rtt_config.get(CONF_NAME, name)
            entity = LinkRttSensor(hass, entity_id, name, link_count, link_rtt_config)
        link_rtt_entities.append(entity)
        entities.append(entity)
    hass.data[DOMAIN][DATA_LINK_RTT_ENTITIES] = link_rtt_entities

    ## Add sensors to platform
    _LOGGER.debug("adding sensor entities: %s", str(entities))
    add_entities(entities, True)


class InternetStatusSensor(SensorEntity):
    """Sensor that determines the status of internet access."""

    _attr_icon = INTERNET_STATUS_ICON
    _attr_should_poll = False
    _attr_extra_state_attributes = {}

    def __init__(self, hass, entity_id, name):
        """Initialise the internet status sensor."""
        self._data = hass.data[DOMAIN]
        self._attr_name = name
        self._attr_unique_id = DOMAIN + ":" + name
        self._attr_native_value = None

        if entity_id:
            self.entity_id = entity_id
        self._updated = False
        _LOGGER.debug(
            "%s.__init__(): entity_id=%s",
            name,
            entity_id,
        )

    def update(self):
        """Initial update of the sensor."""
        _LOGGER.debug("%s.update(): initial update", self._attr_name)
        self.set_state()
        self._updated = True
        return

    def set_state(self):
        """Update the sensor state."""
        ## Get entities
        primary_entity = self._data.get(DATA_PRIMARY_LINK_ENTITY)
        secondary_entity = None
        secondary_entities = self._data.get(DATA_SECONDARY_LINK_ENTITIES)
        ## TODO: update to handle any number of secondary entities
        if secondary_entities and len(secondary_entities) > 0:
            secondary_entity = secondary_entities[0]

        ## Wait for both link sensors to be initialised
        if primary_entity is None or secondary_entity is None:
            _LOGGER.debug("link sensors not set up, skipping set_state")
            return

        primary_link_up = primary_entity.link_up
        primary_configured_ip = primary_entity.configured_ip
        primary_current_ip = primary_entity.current_ip
        secondary_link_up = secondary_entity.link_up
        secondary_configured_ip = secondary_entity.configured_ip
        secondary_current_ip = secondary_entity.current_ip

        ## Wait for both link sensors to update
        if primary_link_up is None or secondary_link_up is None:
            _LOGGER.debug("link sensors not updated, skipping set_state")
            return

        ## Check link failover status
        link_status = "up"
        if not primary_link_up:
            ## Primary link failed but has not failed over to secondary yet
            link_status = "degraded (primary down)"
            if not secondary_link_up:
                ## Both primary and secondary links have failed
                link_status = "down"
            elif primary_current_ip == secondary_configured_ip:
                ## Primary failed over to secondary
                link_status = "failover (primary down)"
                # primary_entity.set_failover()
        elif not secondary_link_up:
            ## Primary link is up from previous check
            ## Secondary link has failed but primary link is up
            link_status = "degraded (secondary down)"
        elif primary_current_ip == secondary_current_ip:
            ## One of the links has failed and both paths are using the same
            ## link. This can only occur if configured_ips are not set (links
            ## with configured_ip are down if current_ip != configured_ip)
            link_status = "failover"
            if primary_current_ip == secondary_configured_ip:
                link_status = "failover (primary down)"
                primary_entity.set_failover()
            elif secondary_current_ip == primary_configured_ip:
                link_status = "failover (secondary down)"
                secondary_entity.set_failover()
        else:
            ## Normal, update configured IP if not specified
            primary_entity.clear_failover()
            secondary_entity.clear_failover()
            if primary_current_ip:
                primary_entity.set_configured_ip()
            if secondary_current_ip:
                secondary_entity.set_configured_ip()

        ## Only trigger update if link status has changed
        if self._attr_native_value != link_status:
            self._attr_native_value = link_status
            _LOGGER.info("%s: state=%s", self._attr_name, link_status)
            if self._updated:
                _LOGGER.debug("%s.set_state(): updating HA state", self._attr_name)
                self.schedule_update_ha_state()
            else:
                _LOGGER.debug("%s.set_state(): skipping update", self._attr_name)


class LinkRttSensor(SensorEntity):
    """Sensor that tracks rtt to probe server."""

    _attr_icon = LINK_RTT_ICON
    _attr_native_unit_of_measurement = "ms"
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    ## TODO: no appropriate device class for rtt value
    # _attr_device_class = SensorDeviceClass.DATA_RATE

    def __init__(self, hass, entity_id, name, link_count, link_rtt_config):
        """Initialise the internet status sensor."""
        self._data = hass.data[DOMAIN]
        self._attr_unique_id = DOMAIN + ":" + name
        self._attr_name = name
        self._update_count = None
        self._update_ratio = link_rtt_config[CONF_UPDATE_RATIO]
        self._debug_rtt = link_rtt_config[CONF_DEBUG_RTT]

        if entity_id:
            self.entity_id = entity_id
        self._updated = False
        if self._debug_rtt:
            _LOGGER.debug(
                "%s.__init__(): entity_id=%s, link_count=%d, update_ratio=%d, rtt_config=%s",
                name,
                entity_id,
                link_count,
                self._update_ratio,
                link_rtt_config,
            )

    def update(self):
        """Initial update of the sensor."""
        if self._debug_rtt:
            _LOGGER.debug("%s.update(): initial update", self._attr_name)
        self._updated = True
        return

    def set_rtt(self, rtt, rtt_array):
        """Update rtt data."""
        if self._update_count is None or self._update_count >= self._update_ratio:
            self._update_count = 1
            self._attr_native_value = rtt
            self._attr_extra_state_attributes = {ATTR_RTT: rtt_array}
            if self._debug_rtt:
                _LOGGER.debug(
                    "%s: rtt=%.3f rtt_array=%s", self._attr_name, rtt, rtt_array
                )
            if self._updated:
                if self._debug_rtt:
                    _LOGGER.debug("%s.set_rtt(): updating HA state", self._attr_name)
                self.schedule_update_ha_state()
            else:
                if self._debug_rtt:
                    _LOGGER.debug("%s.set_rtt(): skipping update", self._attr_name)
        else:
            self._update_count += 1
