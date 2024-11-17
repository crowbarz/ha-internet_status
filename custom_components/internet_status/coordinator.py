"""Internet Status data update coordinator."""

from abc import ABC
from datetime import datetime, timedelta, UTC
from typing import Any
import asyncio
import logging
import math

# import time
import aiofiles
import dns.asyncresolver
import dns.resolver
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns.inet
import dns.ipv4
import dns.reversename
import dns.exception

from icmplib import NameLookupError, async_ping

from homeassistant.const import CONF_NAME
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    CONF_LINKS,
    CONF_SCAN_INTERVAL,
    CONF_RETRIES,
    CONF_TIMEOUT,
    CONF_PROBE_TARGET,
    CONF_PROBE_TYPE,
    CONF_LINK_TYPE,
    CONF_CONFIGURED_IP,
    CONF_REVERSE_HOSTNAME,
    CONF_RTT_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULTS,
    DEF_LINK_NAME_PREFIX,
    MIN_UPDATE_INTERVAL,
    ProbeType,
    LinkType,
)

_LOGGER = logging.getLogger(__name__)


class InternetLinks:
    """Configured Internet links."""

    def __init__(self, config: dict[str, Any]):
        """Create links from config."""
        self.links_all: dict[str, InternetLink] = {}
        self.slugs_all: list[str] = []
        self.primary_link: InternetLink = None
        self.secondary_links: list[InternetLink] = []
        self.monitor_links: list[InternetLink] = []

        link_id = 1

        def get_unique_name(name: str) -> str:
            """Generate a unique link name."""
            nonlocal link_id
            if name is None:
                name = f"{DEF_LINK_NAME_PREFIX} {link_id}"
            while name in self.links_all or slugify(name) in self.slugs_all:
                link_id += 1
                name = f"{DEF_LINK_NAME_PREFIX} {link_id}"
            return name

        def inherit_attrs(link_config: dict[str, Any]) -> None:
            """Propagate inherited link attributes from main config."""

            for attr in [CONF_SCAN_INTERVAL, CONF_TIMEOUT, CONF_RETRIES]:
                if attr not in link_config:
                    link_config[attr] = config.get(attr, DEFAULTS[attr])

        link_config: dict[str, Any]
        for link_config in config.get(CONF_LINKS, []):
            link_type = LinkType(
                link_config.get(CONF_LINK_TYPE, DEFAULTS[CONF_LINK_TYPE])
            )
            name = get_unique_name(link_config.get(CONF_NAME))
            inherit_attrs(link_config)

            link = None
            probe_type = None
            if probe_type_raw := link_config.get(CONF_PROBE_TYPE):
                try:
                    probe_type = ProbeType(probe_type_raw)
                except ValueError:
                    pass
            match probe_type:
                case ProbeType.FILE:
                    link = ProbeFileLink(name, link_type, link_config=link_config)
                case ProbeType.GOOGLE | ProbeType.OPENDNS | ProbeType.AKAMAI:
                    link = PROBE_TYPE_CLASS_MAP[probe_type](
                        name, link_type, link_config=link_config
                    )
                case ProbeType.PING:
                    link = ProbePingLink(name, link_type, link_config=link_config)
                case _:
                    _LOGGER.warning(
                        "unknown probe_type %s for link %s", probe_type_raw, name
                    )
                    continue

            if link_type == LinkType.PRIMARY:
                if self.primary_link is not None:
                    _LOGGER.warning(
                        "demoted link %s to secondary as primary link is already defined",
                        name,
                    )
                    link.link_type = LinkType.SECONDARY
                    self.secondary_links.append(link)
                else:
                    self.primary_link = link
            elif link_type == LinkType.SECONDARY:
                self.secondary_links.append(link)
            elif link_type == LinkType.MONITOR_ONLY:
                self.monitor_links.append(link)
            else:
                _LOGGER.warning("unknown link_type %s for link %s", link_type, name)
                continue
            self.links_all[name] = link
            self.slugs_all.append(slugify(name))
            link_id += 1

        if self.primary_link is None:
            raise RuntimeError("no primary link defined")


class InternetStatusCoordinator(DataUpdateCoordinator):
    """Internet Status coordinator."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, links: InternetLinks
    ) -> None:
        """Initialise Internet Status coordinator."""
        self.entry = entry
        self.links = links
        self.internet_status = None
        self._configured_ip_updated = False
        self._full_update = True
        link_scan_intervals = [
            link.scan_interval for link in self.links.links_all.values()
        ]
        link_rtt_update_intervals = [
            link.rtt_update_interval
            for link in self.links.links_all.values()
            if getattr(link, "rtt_update_interval", None)
        ]
        update_interval = max(
            math.gcd(*link_scan_intervals, *link_rtt_update_intervals),
            MIN_UPDATE_INTERVAL,
        )
        _LOGGER.debug("setting update interval to %d", update_interval)
        super().__init__(
            hass,
            _LOGGER.getChild("coordinator"),
            # Name of the data. For logging purposes.
            name="InternetStatus",
            update_interval=timedelta(seconds=update_interval),
            update_method=self.async_update_link_status,
        )

    async def async_refresh_full(self) -> None:
        """Perform a full refresh."""
        _LOGGER.debug("forcing full update")
        self._full_update = True
        await self.async_refresh()

    async def async_update_link_status(self) -> None:
        """Update link statuses and overall Internet status."""
        link: InternetLink
        async with asyncio.TaskGroup() as tgr:
            for link in self.links.links_all.values():
                tgr.create_task(link.async_update(self._full_update))
        self._full_update = False

        ## Update link failover status
        main_links = [self.links.primary_link] + self.links.secondary_links
        link_failover_any = False
        while main_links:
            link = main_links.pop(0)
            main_link_ips = {
                (l.configured_ip or l.current_ip): l.name
                for l in main_links
                if l.configured_ip or l.current_ip
            }
            link_failover = False
            if link.current_ip:
                link_failover = link.current_ip in main_link_ips.keys()
                if link_failover:
                    link_failover_any = True
                    link.link_up = None  ## for links with no configured IP set
            if link.link_failover != link_failover:
                if link_failover:
                    _LOGGER.info(
                        "%s: failed over to link %s",
                        link.name,
                        main_link_ips[link.current_ip],
                    )
                elif link.link_failover is not None:
                    _LOGGER.info("%s: link failover cleared", link.name)
                link.link_failover = link_failover

        ## Determine internet status
        primary_link = self.links.primary_link
        primary_up = primary_link.link_up
        secondaries_up = [link.link_up for link in self.links.secondary_links]
        internet_status = "up"

        if not primary_up or primary_link.link_failover:
            ## Primary link failed but has not failed over to secondary yet
            internet_status = "degraded (primary down)"
            if primary_up is False and not any(secondaries_up):
                ## Primary and all secondary links have failed
                internet_status = "down"
            elif primary_link.link_failover:
                ## Primary failed over to secondary
                internet_status = "failover to secondary (primary down)"
            else:
                internet_status = "failover to other link (primary down)"
        elif not all(secondaries_up):  # primary_up is True
            ## A secondary link has failed but primary link is up
            internet_status = "degraded (secondary down)"
        else:  ## Primary and all secondaries are up
            if not link_failover_any and not self._configured_ip_updated:
                self.set_configured_ip()

        if self.internet_status != internet_status:
            _LOGGER.info("internet_status: %s", internet_status)
        self.internet_status = internet_status

    def set_configured_ip(self) -> None:
        """Set configured IP for links that do not have a configured IP."""
        for link in self.links.links_all.values():
            if link.configured_ip is None and link.current_ip:
                link.set_configured_ip()
        self._configured_ip_updated = True

    def reset_configured_ip(self) -> None:
        """Reset configured IP for all links."""
        self._configured_ip_updated = False
        for link in self.links.links_all.values():
            link.reset_configured_ip()


class InternetLink(ABC):
    """
    Internet link object.

    link_up: False = IP address cannot be determined for the link
             True = link is up and has the expected IP address
             None = link is up but does not have the expected IP address
    link_failover: None = link failover is not checked for this link
                   False = link is not failed over
                   True = current IP address for link is the configured IP of another link
    """

    def __init__(
        self, name: str, link_type: LinkType, link_config: dict[str, Any]
    ) -> None:
        self.name = name
        self.link_type = link_type
        self.link_config = link_config
        self.probe_target: str = link_config[CONF_PROBE_TARGET]
        self.scan_interval: float = link_config[CONF_SCAN_INTERVAL]
        self.configured_ip: str | None = link_config.get(CONF_CONFIGURED_IP)
        self._config_configured_ip = self.configured_ip
        self.link_failover: bool | None = None
        self.link_up: bool | None = None
        self.current_ip: str | None = None
        self.reverse_hostname: str | None = None
        self._reverse_ok: bool | None = None  ## TODO: review needed?
        self._next_update = datetime.now(UTC)
        _LOGGER.debug(
            "creating link %s(%s): link_type=%s, probe_target=%s, "
            "scan_interval=%s, configured_ip=%s",
            name,
            self.__class__.__name__,
            link_type,
            self.probe_target,
            self.scan_interval,
            self.configured_ip,
        )

    def set_configured_ip(self) -> None:
        """Set configured IP for the link."""
        if self.current_ip is not None:
            _LOGGER.debug(
                "%s: updating configured IP from: %s to: %s",
                self.name,
                self.configured_ip,
                self.current_ip,
            )
            self.configured_ip = self.current_ip
            if self.link_up is None:
                self.link_up = True
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="set_configured_ip_unknown_current_ip",
            )

    def reset_configured_ip(self) -> None:
        """Reset configured IP for the link."""
        self.configured_ip = self._config_configured_ip
        self.link_up = bool(self.current_ip)

    async def async_probe(self) -> bool | None:
        """Probe Internet link. (stub)"""
        raise RuntimeError("probe not implemented")

    async def async_update(self, full_update: bool = False) -> bool:
        """Update status of link."""
        current_time = datetime.now(UTC)
        if full_update or self._next_update <= current_time:
            _LOGGER.debug("%s: probing link", self.name)
            self._next_update = current_time + timedelta(seconds=self.scan_interval)
            current_ip = self.current_ip
            link_up = await self.async_probe()
            if self.link_failover and current_ip == self.current_ip:
                ## Link previously marked as failed over and IP has not changed
                link_up = None
            if link_up != self.link_up:
                _LOGGER.info("%s: link_status: %s", self.name, link_up)
            self.link_up = link_up
            return True
        next_update_in = self._next_update - current_time
        _LOGGER.debug("%s: skipping, next update in: %s", self.name, next_update_in)
        return False


class ProbeFileLink(InternetLink):
    """Internet link with file probe."""

    async def async_probe(self) -> bool | None:
        """Probe file for status."""

        async with aiofiles.open(
            self.probe_target, "r", encoding="utf8", errors="surrogateescape"
        ) as fileh:
            current_ip = (await fileh.read()).rstrip()

        if not dns.inet.is_address(current_ip):
            self.current_ip = None
            return False

        self.current_ip = current_ip
        if self.configured_ip is None or self.current_ip == self.configured_ip:
            return True
        return None


class ProbeDNSLink(InternetLink, ABC):
    """Internet link with DNS probe."""

    probe_type = None

    def __init__(
        self,
        name: str,
        link_type: LinkType,
        link_config: dict[str, Any],
    ) -> None:
        super().__init__(name, link_type, link_config)
        self.reverse_hostname: str | None = link_config.get(CONF_REVERSE_HOSTNAME)
        self._timeout: float = link_config[CONF_TIMEOUT]
        self._retries: int = link_config[CONF_RETRIES]
        self._reverse_hostname_error: bool = False
        self.rtt: float | None = None
        self.rtt_array: list[float] | None = None
        self.rtt_update_interval: float | None = None
        self.rtt_next_update: datetime | None = None

        ## Create resolver for public IP address DNS query
        resolver = dns.asyncresolver.Resolver()
        resolver.nameservers = [self.probe_target]
        resolver.timeout = self._timeout
        self.resolver = resolver

        _LOGGER.debug(
            "creating link %s(%s): reverse_hostname=%s, retries=%d, timeout=%f",
            name,
            self.__class__.__name__,
            self.reverse_hostname,
            self._retries,
            self._timeout,
        )

        ## Enable RTT sensor
        if CONF_RTT_SENSOR in link_config:
            rtt_sensor_config: dict[str, Any] = link_config[CONF_RTT_SENSOR] or {}
            self.rtt_update_interval = rtt_sensor_config.get(
                CONF_UPDATE_INTERVAL, DEFAULTS[CONF_RTT_SENSOR][CONF_UPDATE_INTERVAL]
            )
            self.rtt_next_update = datetime.now(UTC)

    async def async_send_dns_probe(self):
        """Send DNS probe. (stub)"""
        raise RuntimeError("send_dns_probe not implemented")

    async def async_probe(self) -> bool | None:
        """Send DNS probes and update rtt."""
        probe_host = self.probe_target
        current_ip = None
        self.rtt_array = []
        for count in range(self._retries, 0, -1):
            start_time = datetime.now(UTC)
            try:
                probe_ip = await self.async_send_dns_probe()
            except dns.exception.DNSException as exc:
                _LOGGER.debug(
                    "%s: probe %d failed: probe_type=%s, probe_host=%s: %s",
                    self.name,
                    count,
                    self.__class__.__name__,
                    probe_host,
                    exc,
                )
                continue

            if probe_ip is not None:
                current_ip = probe_ip
                rtt = round(
                    (datetime.now(UTC) - start_time) / timedelta(milliseconds=1), 3
                )
                self.rtt_array.append(rtt)
                _LOGGER.debug(
                    "%s: probe %d success: probe_type=%s, probe_host=%s, "
                    "current_ip=%s, rtt=%fs",
                    self.name,
                    count,
                    self.__class__.__name__,
                    probe_host,
                    current_ip,
                    rtt,
                )
            if count > 1 and rtt < self._timeout * 1000:
                await asyncio.sleep(self._timeout - rtt / 1000)
        if self.rtt_array:
            self.rtt = round(sum(self.rtt_array) / len(self.rtt_array), 3)
            _LOGGER.debug("%s: average rtt=%fs", self.name, self.rtt)
        else:
            self.rtt = None

        self.current_ip = current_ip
        if current_ip is None:
            return False
        if self.configured_ip and current_ip != self.configured_ip:
            return None
        if self.reverse_hostname:
            return True if await self.check_dns_reverse_lookup() else None
        return True

    async def check_dns_reverse_lookup(self):
        """Reverse DNS lookup current IP and match with reverse hostname."""
        reverse_hostname = self.reverse_hostname
        current_ip = self.current_ip
        # timeout = self._timeout
        try:
            answer = await dns.asyncresolver.resolve_address(current_ip)
            self._reverse_hostname_error = False
            ptr_data = str(answer[0])
            if reverse_hostname in ptr_data:
                _LOGGER.debug(
                    "%s: reverse lookup success: %s in %s",
                    self.name,
                    reverse_hostname,
                    ptr_data,
                )
                return True
            _LOGGER.debug(
                "%s: reverse lookup failed: %s not in %s",
                self.name,
                reverse_hostname,
                ptr_data,
            )
            return False
        except dns.exception.DNSException as exc:
            if not self._reverse_hostname_error:
                _LOGGER.warning(
                    "%s: reverse lookup for %s failed: %s",
                    self.name,
                    current_ip,
                    str(exc),
                )
                self._reverse_hostname_error = True
            return False


class ProbeGoogleDNSLink(ProbeDNSLink):
    """Internet link with Google DNS probe."""

    probe_type = "google"

    async def async_send_dns_probe(self) -> str:
        """Probe public IP address using Google DNS."""
        current_ip = None
        ## dig @ns1.google.com TXT o-o.myaddr.l.google.com +short
        for rdata in await self.resolver.resolve(
            "o-o.myaddr.l.google.com", dns.rdatatype.TXT
        ):
            txt = rdata.strings[0].decode("utf-8")
            ## Handle edns response, though this may only provide subnet level IP resolution
            if txt.startswith("edns0-client-subnet"):
                current_ip = txt[20:-3]
            else:
                current_ip = txt
        return current_ip


class ProbeOpenDNSLink(ProbeDNSLink):
    """Internet link with OpenDNS probe."""

    probe_type = "opendns"

    async def async_send_dns_probe(self) -> str:
        """Obtain public IP address using a probe."""
        current_ip = None
        ## dig @resolver1.opendns.com ANY myip.opendns.com +short
        for rdata in await self.resolver.resolve("myip.opendns.com", dns.rdatatype.A):
            current_ip = rdata.address
            break
        return current_ip


class ProbeAkamaiDNSLink(ProbeDNSLink):
    """Internet link with Akamai DNS probe."""

    probe_type = "akamai"

    async def async_send_dns_probe(self) -> str:
        """Probe public IP address using Akamai DNS."""
        current_ip = None
        ## dig @ns1-1.akamaitech.net ANY whoami.akamai.net +short
        for rdata in await self.resolver.resolve("whoami.akamai.net", dns.rdatatype.A):
            current_ip = rdata.address
            break
        return current_ip


PROBE_TYPE_CLASS_MAP: dict[ProbeType, InternetLink] = {
    ProbeType.GOOGLE: ProbeGoogleDNSLink,
    ProbeType.OPENDNS: ProbeOpenDNSLink,
    ProbeType.AKAMAI: ProbeAkamaiDNSLink,
}


class ProbePingLink(InternetLink):
    """Internet link with Ping probe."""

    def __init__(
        self,
        name: str,
        link_type: LinkType,
        link_config: dict[str, Any],
    ) -> None:
        super().__init__(name, link_type, link_config)
        self._timeout: float = link_config[CONF_TIMEOUT]
        self._retries: int = link_config[CONF_RETRIES]
        self.rtt: float | None = None
        self.rtt_array: list[float] | None = None
        self.rtt_update_interval: float | None = None
        self.rtt_next_update: datetime | None = None

        _LOGGER.debug(
            "creating link %s(%s): retries=%d, timeout=%f",
            name,
            self.__class__.__name__,
            self._retries,
            self._timeout,
        )

        ## Enable RTT sensor
        if CONF_RTT_SENSOR in link_config:
            rtt_sensor_config: dict[str, Any] = link_config[CONF_RTT_SENSOR] or {}
            self.rtt_update_interval = rtt_sensor_config.get(
                CONF_UPDATE_INTERVAL, DEFAULTS[CONF_RTT_SENSOR][CONF_UPDATE_INTERVAL]
            )
            self.rtt_next_update = datetime.now(UTC)

    async def async_probe(self) -> bool | None:
        """Send ping probes and update rtt."""
        probe_host = self.probe_target
        self.current_ip = None
        self.rtt = None
        self.rtt_array = []
        try:
            data = await async_ping(
                self.probe_target, count=self._retries, timeout=self._timeout
            )
            if data.is_alive:
                self.current_ip = data.address
                self.rtt = data.max_rtt
                self.rtt_array = data.rtts
                _LOGGER.debug(
                    "%s: probe success: probe_host=%s, average rtt=%fs",
                    self.name,
                    probe_host,
                    self.rtt,
                )
            else:
                _LOGGER.debug(
                    "%s: probe failed: probe_host=%s: no response",
                    self.name,
                    probe_host,
                )

        except NameLookupError as exc:
            _LOGGER.debug(
                "%s: probe failed: probe_host=%s: %s",
                self.name,
                probe_host,
                exc,
            )

        return bool(self.current_ip)
