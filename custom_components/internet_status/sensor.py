"""Sensor to represent overall internet status."""

import logging

from homeassistant.const import CONF_NAME
from homeassistant.helpers.entity import Entity

from .const import (
    DOMAIN,
    CONF_LINKS,
    CONF_RTT_SENSOR,
    DEF_LINK_NAME,
    DEF_LINK_RTT_SUFFIX,
    DATA_DOMAIN_CONFIG,
    DATA_SENSOR_ENTITY,
    DATA_PRIMARY_LINK_ENTITY,
    DATA_SECONDARY_LINK_ENTITIES,
    DATA_LINK_RTT_ENTITIES,
    ATTR_RTT,
    ATTR_RTT_ARRAY,
)

_LOGGER = logging.getLogger(__name__)

INTERNET_STATUS_ICON = 'mdi:wan'
LINK_RTT_ICON = 'mdi:lan-connect'

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the internet status sensor."""

    if discovery_info is None:
        return

    domain_config = hass.data[DOMAIN][DATA_DOMAIN_CONFIG]
    entities = []

    _LOGGER.info("setting up internet link status sensors")
    name = domain_config.get(CONF_NAME)
    entity_id = "sensor." + DOMAIN
    internet_status_entity = InternetStatusSensor(hass, entity_id, name)
    hass.data[DOMAIN][DATA_SENSOR_ENTITY] = internet_status_entity
    entities.append(internet_status_entity)

    _LOGGER.info("setting up link rtt sensors")
    link_rtt_entities = [ ]
    link_count = 0
    for entity_id, link_config in domain_config[CONF_LINKS].items():
        link_count += 1
        entity_id = "sensor." + entity_id + "_rtt"
        link_rtt_config = link_config.get(CONF_RTT_SENSOR)
        entity = None
        if link_rtt_config is not None:
            if CONF_NAME in link_config:
                name = link_config[CONF_NAME] + DEF_LINK_RTT_SUFFIX
            else:
                name = (DEF_LINK_NAME % link_count) + DEF_LINK_RTT_SUFFIX
            name = link_rtt_config.get(CONF_NAME, name)
            entity = LinkRttSensor(hass, entity_id, name, link_count,
                link_rtt_config)
        link_rtt_entities.append(entity)
    hass.data[DOMAIN][DATA_LINK_RTT_ENTITIES] = link_rtt_entities

    ## Add sensors to platform
    add_entities(entities, True)

class InternetStatusSensor(Entity):
    """Sensor that determines the status of internet access."""

    def __init__(self, hass, entity_id, name):
        """Initialise the internet status sensor."""
        self._data = hass.data[DOMAIN]
        self._unique_id = entity_id
        self._name = name
        self._link_status = None

        self.entity_id = entity_id
        self._updated = False
        _LOGGER.debug("%s()", name)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return INTERNET_STATUS_ICON

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

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    def update(self):
        """Update the sensor."""

        ## Get entities
        link_status = 'up'
        primary_entity = self._data.get(DATA_PRIMARY_LINK_ENTITY)
        secondary_entity = None
        secondary_entities = self._data.get(DATA_SECONDARY_LINK_ENTITIES)
        ## TODO: update to handle any number of secondary entities
        if secondary_entities and len(secondary_entities) > 0:
            secondary_entity = secondary_entities[0]

        ## Wait for both link sensors to be initialised
        if primary_entity is None or secondary_entity is None:
            return

        primary_link_up = primary_entity.link_up
        primary_configured_ip = primary_entity.configured_ip
        primary_current_ip = primary_entity.current_ip
        secondary_link_up = secondary_entity.link_up
        secondary_configured_ip = secondary_entity.configured_ip
        secondary_current_ip = secondary_entity.current_ip

        ## Wait for both link sensors to update
        if primary_link_up is None or secondary_link_up is None:
            return

        ## Check link failover status
        if not primary_link_up:
            ## Primary link failed but has not failed over to secondary yet
            link_status = 'degraded (primary down)'
            if not secondary_link_up:
                ## Both primary and secondary links have failed
                link_status = 'down'
        elif not secondary_link_up:
            ## Secondary link failed but has not failed over to primary yet
            ## Primary link is up from previous check
            link_status = 'degraded (secondary down)'
        elif primary_current_ip == secondary_current_ip:
            ## One of the links has failed and both paths are using the same link
            link_status = 'failover'
            if primary_current_ip == secondary_configured_ip:
                link_status = 'failover (primary down)'
                primary_entity.set_failover()
            elif secondary_current_ip == primary_configured_ip:
                link_status = 'failover (secondary down)'
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
        if self._link_status != link_status:
            self._link_status = link_status
            _LOGGER.info("%s state=%s", self._name, link_status)
            self.schedule_update_ha_state()

        self._updated = True


class LinkRttSensor(Entity):
    """Sensor that tracks rtt to probe server."""

    def __init__(self, hass, entity_id, name, link_count, link_rtt_config):
        """Initialise the internet status sensor."""
        self._data = hass.data[DOMAIN]
        self._unique_id = entity_id
        self._name = name
        self._rtt = None
        self._rtt_array = None

        self.entity_id = entity_id
        self._updated = False
        _LOGGER.debug("%s: entity_id=%s, link_count=%s, rtt_config=%s",
            name, entity_id, link_count, link_rtt_config)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return LINK_RTT_ICON

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._rtt

    @property
    def unit_of_measurement(self):
        """Return the state of the sensor."""
        return "ms"

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            ATTR_RTT: self._rtt,
            ATTR_RTT_ARRAY: self._rtt_array
        }
        return attrs

    @property
    def should_poll(self):
        """Polling not required as link binary_sensors will update sensor."""
        return False

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    def update(self):
        """Update the sensor. Updated by the link binary_sensors"""
        self._updated = True
        return

    def set_rtt(self, rtt, rtt_array):
        """Update rtt data."""
        self._rtt = rtt
        self._rtt_array = rtt_array
        if self._updated:
            self.schedule_update_ha_state()
