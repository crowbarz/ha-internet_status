"""Sensor to represent overall internet status."""

import logging
import time

from homeassistant.const import CONF_NAME
from homeassistant.helpers.entity import Entity

from .const import (
    DOMAIN,
    DATA_DOMAIN_CONFIG,
    DATA_PARENT_ENTITY,
    DATA_PRIMARY_ENTITY,
    DATA_SECONDARY_ENTITY,
)

_LOGGER = logging.getLogger(__name__)

ICON = 'mdi:wan'

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the internet status sensor."""

    if discovery_info is None:
        return

    domain_config = hass.data[DOMAIN][DATA_DOMAIN_CONFIG]

    _LOGGER.debug("setting up internet link status sensors")
    name = domain_config.get(CONF_NAME)

    internet_status_entity = InternetStatusSensor(name, hass)
    hass.data[DOMAIN][DATA_PARENT_ENTITY] = internet_status_entity
    add_entities([internet_status_entity])

class InternetStatusSensor(Entity):
    """Sensor that determines the status of internet access."""

    def __init__(self, name, hass):
        """Initialise the internet status sensor."""
        self._name = name
        self._data = hass.data[DOMAIN]
        self._link_status = None
        _LOGGER.debug("%s()", name)

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
        link_status = 'up'
        primary_entity = self._data.get(DATA_PRIMARY_ENTITY)
        secondary_entity = self._data.get(DATA_SECONDARY_ENTITY)

        ## Wait for both link sensors to be initialised
        ## TODO: handle case where no secondary is specified
        if primary_entity is None or secondary_entity is None:
            return

        ## Register self as parent of link sensors
        if primary_entity and primary_entity.parent_entity is None:
            primary_entity.parent_entity = self
        if secondary_entity and secondary_entity.parent_entity is None:
            secondary_entity.parent_entity = self
        ## No need to update parent on VPN entity update

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
                primary_entity.link_up = False
                primary_entity.link_failover = True
            elif secondary_current_ip == primary_configured_ip:
                link_status = 'failover (secondary down)'
                secondary_entity.link_up = False
                secondary_entity.link_failover = True
        else:
            ## Normal, update configured IP if not specified
            primary_entity.link_failover = False
            secondary_entity.link_failover = False
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

        ## Only trigger update
        if self._link_status != link_status:
            self._link_status = link_status
            _LOGGER.info("%s state=%s", self._name, link_status)
            self.schedule_update_ha_state()
