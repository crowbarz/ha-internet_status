"""Internet Status binary_sensor platform."""

import logging
import voluptuous as vol

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    DEF_LINK_ICON,
    ATTR_CONFIGURED_IP,
    ATTR_CURRENT_IP,
    ATTR_LINK_FAILOVER,
    SERVICE_SET_CONFIGURED_IP,
)
from .coordinator import InternetStatusCoordinator, InternetLink

_LOGGER = logging.getLogger(__name__)


INTERNET_STATUS_SET_CONFIGURED_IP_SCHEMA = {vol.Required("entity_id"): cv.entity_id}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary_sensor platform."""
    coordinator: InternetStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for link in coordinator.links.links_all.values():
        entities.append(LinkStatusBinarySensor(coordinator, link))
    async_add_entities(entities, update_before_add=True)

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_CONFIGURED_IP,
        INTERNET_STATUS_SET_CONFIGURED_IP_SCHEMA,
        LinkStatusBinarySensor.async_set_configured_ip,
    )


class LinkStatusBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor representing status of an Internet link."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: InternetStatusCoordinator, link: InternetLink
    ) -> None:
        """Initialise the link status binary_sensor."""
        self.coordinator = coordinator
        self.link = link
        self._attr_name = link.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}:{slugify(link.name)}"

        super().__init__(coordinator, context=link)

    @property
    def icon(self) -> str:
        """Return the entity icon."""
        return DEF_LINK_ICON.get(self.link.link_up, DEF_LINK_ICON[None])

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.entry.title,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = bool(self.link.link_up)
        self._attr_available = self.link.link_up is not False
        self._attr_extra_state_attributes = {
            ATTR_CONFIGURED_IP: self.link.configured_ip,
            ATTR_CURRENT_IP: self.link.current_ip,
            ATTR_LINK_FAILOVER: self.link.link_failover,
        }
        self.async_write_ha_state()

    async def async_set_configured_ip(self, _service_call: ServiceCall) -> None:
        """Update the configured IP for link."""
        _LOGGER.debug("set_configured_ip(%s)", self.link.name)
        self.link.set_configured_ip()
        await self.coordinator.async_refresh_full()
