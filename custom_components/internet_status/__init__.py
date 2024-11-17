"""Monitor internet link status via DNS queries."""

from __future__ import annotations

import logging

import dns.rdata
import dns.rdataclass
import dns.rdatatype

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import InternetStatusCoordinator, InternetLinks

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up internet_status from a config entry."""

    def setup_links():
        """Set up Internet links synchronously via executor job."""
        ## https://github.com/rthalley/dnspython/issues/1083
        ## https://github.com/rthalley/dnspython/pull/1095
        for rdtype in dns.rdatatype.RdataType:
            if not dns.rdatatype.is_metatype(rdtype) or rdtype == dns.rdatatype.OPT:
                dns.rdata.get_rdata_class(dns.rdataclass.IN, rdtype)

        return InternetLinks(entry.options)

    hass.data.setdefault(DOMAIN, {})
    links = await hass.async_add_executor_job(setup_links)
    coordinator = InternetStatusCoordinator(hass, entry, links)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle options update."""
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_reset_configured_ips_all(_service_call: ServiceCall) -> None:
        """Reset the configured IP for all links."""
        _LOGGER.debug("reset_configured_ips_all()")
        coordinator.reset_configured_ip()
        await coordinator.async_refresh_full()

    hass.services.async_register(
        DOMAIN, "reset_configured_ips_all", async_reset_configured_ips_all
    )

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
