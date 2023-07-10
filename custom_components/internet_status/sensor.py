"""Internet Status sensor platform."""

from datetime import datetime, timedelta
import logging

from homeassistant.components.sensor import (
    # SensorDeviceClass,
    SensorStateClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    DEF_LINK_RTT_SUFFIX,
    DEF_INTERNET_STATUS_ICON,
    DEF_LINK_RTT_ICON,
    ATTR_RTT,
)
from .coordinator import InternetStatusCoordinator, ProbeDNSLink

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary_sensor platform."""
    coordinator: InternetStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    entities.append(InternetStatusSensor(coordinator))
    for link in coordinator.links_all.values():
        if isinstance(link, ProbeDNSLink) and link.rtt_update_interval is not None:
            entities.append(LinkRttSensor(coordinator, link))

    async_add_entities(entities)


class InternetStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor representing status of Internet access."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: InternetStatusCoordinator):
        """Initialise the internet status sensor."""
        self.coordinator = coordinator
        self._attr_name = None
        self._attr_unique_id = f"{coordinator.entry.entry_id}_sensor"
        self._attr_native_value = None

        super().__init__(coordinator, context=coordinator)

    @property
    def icon(self) -> str:
        """Return the entity icon."""
        return DEF_INTERNET_STATUS_ICON.get(
            self.coordinator.internet_status, DEF_INTERNET_STATUS_ICON[None]
        )

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
        self._attr_native_value = self.coordinator.internet_status
        self.async_write_ha_state()


class LinkRttSensor(CoordinatorEntity, SensorEntity):
    """Sensor that tracks rtt to probe server."""

    _attr_has_entity_name = True
    _attr_icon = DEF_LINK_RTT_ICON
    ## TODO: Duration does not display unit of measurement properly in 2023.6.2
    # _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "ms"

    def __init__(
        self, coordinator: InternetStatusCoordinator, link: ProbeDNSLink
    ) -> None:
        """Initialise the link status binary_sensor."""
        self.coordinator = coordinator
        self.link = link
        self._attr_name = f"{link.name} {DEF_LINK_RTT_SUFFIX}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}:{slugify(link.name)}"

        super().__init__(coordinator, context=link)

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
        current_time = datetime.utcnow()
        if self.link.rtt_next_update <= current_time:
            _LOGGER.debug("updating LinkRttSensor for link %s", self.link.name)
            self._attr_native_value = self.link.rtt
            self._attr_extra_state_attributes = {ATTR_RTT: self.link.rtt_array}
            self.link.rtt_next_update = current_time + timedelta(
                seconds=self.link.rtt_update_interval
            )
            self.async_write_ha_state()
