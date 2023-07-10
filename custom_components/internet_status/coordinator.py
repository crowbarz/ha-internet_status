"""Internet Status data update coordinator."""

from abc import ABC
from datetime import datetime, timedelta
from typing import Any
import asyncio
import logging

# import time
import aiofiles
import dns.asyncresolver
import dns.resolver
import dns.rdatatype
import dns.inet
import dns.ipv4
import dns.reversename
import dns.exception

from homeassistant.const import CONF_NAME
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import slugify

from .const import (
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
    ProbeType,
    LinkType,
)

_LOGGER = logging.getLogger(__name__)


class InternetStatusCoordinator(DataUpdateCoordinator):
    """Internet Status coordinator."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, config: list[dict[Any, Any]]
    ) -> None:
        """Initialise Internet Status coordinator."""
        super().__init__(
            hass,
            _LOGGER.getChild("coordinator"),
            # Name of the data. For logging purposes.
            name="InternetStatus",
            ## short initial refresh after all platforms have completed setup
            update_interval=timedelta(seconds=3),
        )
        self.entry = entry
        self.name = entry.title
        self.internet_status = None
        self._update_interval = timedelta(
            seconds=config.get(CONF_SCAN_INTERVAL, DEFAULTS[CONF_SCAN_INTERVAL])
        )
        self.links_all: dict[str, InternetLink] = {}
        self._slugs_all: list[str] = []
        self._primary_link: InternetLink = None
        self._secondary_links: list[InternetLink] = []
        self._monitor_links: list[InternetLink] = []
        self._configured_ip_updated = False
        self._init_links(config)

    def _init_links(self, config: list[dict[Any, Any]]) -> None:
        """Initialise links from config."""
        link_id = 1

        def get_unique_name(name: str) -> str:
            """Generate a unique link name."""
            nonlocal link_id
            if name is None:
                name = f"{DEF_LINK_NAME_PREFIX} {link_id}"
            while name in self.links_all or slugify(name) in self._slugs_all:
                link_id += 1
                name = f"{DEF_LINK_NAME_PREFIX} {link_id}"
            return name

        def get_inherited_attr(attr, link_config) -> Any:
            """Get attribute inherited from main config."""
            return link_config.get(attr, config.get(attr, DEFAULTS[attr]))

        for link_config in config.get(CONF_LINKS, []):
            link_type = LinkType(
                link_config.get(CONF_LINK_TYPE, DEFAULTS[CONF_LINK_TYPE])
            )
            name = get_unique_name(link_config.get(CONF_NAME))
            scan_interval = get_inherited_attr(CONF_SCAN_INTERVAL, link_config)
            reverse_hostname = link_config.get(CONF_REVERSE_HOSTNAME)
            configured_ip = link_config.get(CONF_CONFIGURED_IP)
            timeout = get_inherited_attr(CONF_TIMEOUT, link_config)
            retries = get_inherited_attr(CONF_RETRIES, link_config)

            link = None
            probe_type = None
            if probe_type_raw := link_config.get(CONF_PROBE_TYPE):
                probe_type = ProbeType(probe_type_raw)
            match probe_type:
                case ProbeType.FILE:
                    _LOGGER.debug(
                        "creating link %s: link_type=%s, probe_type=%s, file_path=%s",
                        name,
                        link_type,
                        probe_type,
                        file_path,
                    )
                    file_path = link_config.get(CONF_PROBE_TARGET)
                    link: ProbeFileLink = ProbeFileLink(
                        link_type,
                        name,
                        probe_target=file_path,
                        scan_interval=scan_interval,
                    )
                case ProbeType.GOOGLE | ProbeType.OPENDNS | ProbeType.AKAMAI:
                    if (probe_host := link_config.get(CONF_PROBE_TARGET)) is None:
                        _LOGGER.warning(
                            "no target specified for link %s (probe_type=%s)",
                            name,
                            probe_type,
                        )
                        continue
                    _LOGGER.debug(
                        "creating link %s: link_type=%s, probe_type=%s, probe_host=%s, "
                        "scan_interval=%f, reverse_hostname=%s, configured_ip=%s, "
                        "retries=%d, timeout=%f",
                        name,
                        link_type,
                        probe_type,
                        probe_host,
                        scan_interval,
                        reverse_hostname,
                        configured_ip,
                        retries,
                        timeout,
                    )
                    link: ProbeDNSLink = PROBE_TYPE_CLASS_MAP[probe_type](
                        link_type=link_type,
                        name=name,
                        probe_host=probe_host,
                        scan_interval=scan_interval,
                        reverse_hostname=reverse_hostname,
                        configured_ip=configured_ip,
                        retries=retries,
                        timeout=timeout,
                    )
                    rtt_sensor_conf = None
                    if CONF_RTT_SENSOR in link_config:
                        rtt_sensor_conf = link_config.get(CONF_RTT_SENSOR) or {}
                        rtt_update_interval = rtt_sensor_conf.get(
                            CONF_UPDATE_INTERVAL,
                            DEFAULTS[CONF_RTT_SENSOR][CONF_UPDATE_INTERVAL],
                        )
                        link.enable_rtt(rtt_update_interval)
                ## TODO: case ProbeType.PING:
                case _:
                    _LOGGER.warning(
                        "unknown probe_type %s for link %s", probe_type_raw, name
                    )
                    continue

            if link_type == LinkType.PRIMARY:
                if self._primary_link is not None:
                    _LOGGER.warning(
                        "demoted link %s to secondary as primary link is already defined",
                        name,
                    )
                    link.link_type = LinkType.SECONDARY
                    self._secondary_links.append(link)
                else:
                    self._primary_link = link
            elif link_type == LinkType.SECONDARY:
                self._secondary_links.append(link)
            elif link_type == LinkType.MONITOR_ONLY:
                self._monitor_links.append(link)
            else:
                _LOGGER.warning("unknown link_type %s for link %s", link_type, name)
                continue
            self.links_all[name] = link
            self._slugs_all.append(slugify(name))
            link_id += 1

        if self._primary_link is None:
            raise RuntimeError("no primary link defined")

    async def _async_update_data(self) -> None:
        """Update link statuses and overall Internet status."""
        link: InternetLink
        async with asyncio.TaskGroup() as tgr:
            for link in self.links_all.values():
                tgr.create_task(link.async_update())

        primary_up = (
            self._primary_link.link_up
            and self._primary_link.reverse_hostname is not False
        )
        primary_ip = self._primary_link.current_ip
        secondaries_up = map(lambda x: x.link_up, self._secondary_links)
        secondaries_ip = map(lambda x: x.current_ip, self._secondary_links)

        internet_status = "up"
        if not primary_up:
            ## Primary link failed but has not failed over to secondary yet
            internet_status = "degraded (primary down)"
            if primary_up is False and not any(secondaries_up):
                ## Primary and all secondary links have failed
                internet_status = "down"
            elif primary_ip:
                internet_status = "failover to other (primary down)"
                if primary_ip in secondaries_ip:
                    ## Primary failed over to secondary
                    internet_status = "failover to secondary (primary down)"
        elif not all(secondaries_up):  # primary_up is True
            ## A secondary link has failed but primary link is up
            internet_status = "degraded (secondary down)"
        elif primary_ip in [secondaries_ip]:
            ## The primary link has the same IP as a secondary link, but the
            ## primary link is up. This can only occur if configured_ips have
            ## not been set at the start.
            internet_status = "failover"
        else:  ## Primary and all secondaries are up
            if not self._configured_ip_updated:
                self._configured_ip_updated = True
                self.set_configured_ip()

        if self.internet_status != internet_status:
            _LOGGER.info("internet_status: %s", internet_status)
        self.internet_status = internet_status

        ## Calculate next update time
        current_time = datetime.utcnow()
        next_update = current_time + self._update_interval
        for link in self.links_all.values():
            if link.next_update < next_update:
                next_update = link.next_update
        ## Delay update by 1 seconds to compensate for _schedule_refresh
        ## microsecond randomisation
        self.update_interval = next_update - current_time + timedelta(seconds=1)
        _LOGGER.debug("next update due in %fs", self.update_interval.total_seconds())

    def set_configured_ip(self) -> None:
        """Set configured IP for all links."""
        self._primary_link.set_configured_ip()
        for link in self._secondary_links:
            link.set_configured_ip()

    def clear_configured_ip(self) -> None:
        """Clear configured IP for all links."""
        self._primary_link.clear_configured_ip()
        for link in self._secondary_links:
            link.clear_configured_ip()


class InternetLink(ABC):
    """Internet link object."""

    def __init__(
        self,
        link_type: str,
        name: str,
        probe_target: str,
        scan_interval: float = DEFAULTS[CONF_SCAN_INTERVAL],
        link_up: bool = None,
    ) -> None:
        self.link_type = link_type
        self.name = name
        self.probe_target = probe_target
        self.scan_interval = scan_interval
        self.link_up = link_up
        self.next_update = datetime.utcnow()
        self.reverse_hostname = None
        self.reverse_ok = None
        self.configured_ip = None
        self.configured_ip_set = False
        self.current_ip = None

    def set_configured_ip(self) -> None:
        """Set configured IP for the link."""
        if not self.configured_ip_set:
            if self.current_ip is not None:
                self.configured_ip = self.current_ip
            if self.link_up is None:
                self.link_up = True

    def clear_configured_ip(self) -> None:
        """Clear configured IP for the link."""
        if not self.configured_ip_set:
            self.configured_ip = None
            if self.link_up is None:
                self.link_up = True

    async def async_probe(self) -> bool:
        """Probe Internet link. (stub)"""
        raise RuntimeError("probe not implemented")

    async def async_update(self) -> bool:
        """Update status of link."""
        current_time = datetime.utcnow()
        if self.next_update <= current_time:
            _LOGGER.debug("updating link %s", self.name)
            link_up = await self.async_probe()
            self.next_update = current_time + timedelta(seconds=self.scan_interval)
            if link_up != self.link_up:
                _LOGGER.info("link_status %s: %s", self.name, link_up)
            self.link_up = link_up
            return True
        return False


class ProbeFileLink(InternetLink):
    """Internet link with file probe."""

    async def async_probe(self) -> bool:
        """Probe file for status."""

        async with aiofiles.open(
            self.probe_target, "r", encoding="utf8", errors="surrogateescape"
        ) as fileh:
            current_ip = await fileh.read().rstrip()

        if not dns.inet.is_address(current_ip):
            self.current_ip = None
            return False

        self.current_ip = current_ip
        if self.configured_ip is None:
            self.configured_ip = current_ip
        if self.configured_ip is None or self.current_ip == self.configured_ip:
            return True
        return None


class ProbeDNSLink(InternetLink, ABC):
    """Internet link with DNS probe."""

    probe_type = None

    def __init__(
        self,
        link_type: str,
        name: str,
        probe_host: str,
        scan_interval: float = DEFAULTS[CONF_SCAN_INTERVAL],
        reverse_hostname: str = None,
        link_up: bool = None,
        configured_ip: str = None,
        retries: int = DEFAULTS[CONF_RETRIES],
        timeout: float = DEFAULTS[CONF_TIMEOUT],
    ) -> None:
        super().__init__(
            link_type=link_type,
            name=name,
            probe_target=probe_host,
            scan_interval=scan_interval,
            link_up=link_up,
        )
        self.reverse_hostname = reverse_hostname
        self.configured_ip = configured_ip
        if configured_ip:
            self.configured_ip_set = True  ## Prevent configure_ip from being reset
        self._retries = retries
        self._timeout = timeout
        self.rtt = None
        self.rtt_array = None
        self.rtt_update_interval = None
        self.rtt_next_update = None

        resolver = dns.asyncresolver.Resolver()
        resolver.nameservers = [probe_host]
        resolver.timeout = self._timeout
        resolver.lifetime = self._timeout
        self.resolver = resolver

    def enable_rtt(
        self, update_interval: int = DEFAULTS[CONF_RTT_SENSOR][CONF_UPDATE_INTERVAL]
    ) -> None:
        """Enable RTT reporting."""
        self.rtt_update_interval = update_interval
        self.rtt_next_update = datetime.utcnow()

    async def async_send_dns_probe(self):
        """Send DNS probe. (stub)"""
        raise RuntimeError("send_dns_probe not implemented")

    async def async_probe(self) -> bool:
        """Send DNS probes and update rtt."""
        probe_host = self.probe_target
        current_ip = None
        self.rtt_array = []
        for count in range(self._retries, 0, -1):
            start_time = datetime.utcnow()
            try:
                probe_ip = await self.async_send_dns_probe()
            except dns.exception.DNSException as exc:
                _LOGGER.debug(
                    "failed: probe_type=%s, probe_host=%s: %s",
                    self.probe_type,
                    probe_host,
                    exc,
                )
                continue

            if probe_ip is not None:
                current_ip = probe_ip
                rtt = round(
                    (datetime.utcnow() - start_time) / timedelta(milliseconds=1), 3
                )
                self.rtt_array.append(rtt)
                _LOGGER.debug(
                    "success: probe_type=%s, probe_host=%s, current_ip=%s, rtt=%fs",
                    self.probe_type,
                    probe_host,
                    current_ip,
                    rtt,
                )
            if count > 1 and rtt < self._timeout * 1000:
                await asyncio.sleep(self._timeout - rtt / 1000)
        if self.rtt_array:
            self.rtt = round(sum(self.rtt_array) / len(self.rtt_array), 3)
            _LOGGER.debug("average rtt: %fs", self.rtt)
        else:
            self.rtt = None

        self.current_ip = current_ip
        if current_ip is None:
            return False
        if self.configured_ip is None or current_ip == self.configured_ip:
            return True
        return None

    async def check_dns_reverse_lookup(self):
        """Reverse DNS lookup current IP and match with reverse hostname."""
        reverse_hostname = self.reverse_hostname
        current_ip = self.current_ip
        # timeout = self._timeout
        try:
            answer = await dns.asyncresolver.resolve_address(current_ip)
            ptr_data = str(answer[0])
            if reverse_hostname in ptr_data:
                _LOGGER.debug(
                    "success: reverse lookup: %s in %s", reverse_hostname, ptr_data
                )
                return True
            _LOGGER.debug(
                "failed: reverse lookup: %s not in %s", reverse_hostname, ptr_data
            )
            return False
        except dns.exception.DNSException as exc:
            _LOGGER.warning("reverse lookup for %s failed: %s", current_ip, str(exc))
            return False

    async def async_update(self) -> bool:
        """Update status of DNS link."""
        if not (link_updated := await super().async_update()):
            return link_updated
        if self.link_up and self.reverse_hostname is not None:
            self.reverse_ok = await self.check_dns_reverse_lookup()
        return True


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
