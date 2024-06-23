<!-- markdownlint-disable MD038 -->

# internet_status

Monitor internet link paths via DNS queries and pings.

This integration will monitor the upstream paths of a network where multiple links (via different ISPs) are used to connect to the internet. It uses certain DNS resolvers, one per link, that support returning the public IP address of the querying host, as seen by the DNS resolver. Each link is expected to use a different public IP address, so links can be monitored by checking for changes to the public IP address. When a link fails, then either the DNS request fails, or the public IP address associated with a different path is returned.

Optionally, the integration can also detect that a link is not up by checking whether the DNS name for the returned public IP address for that link matches a specific suffix.

The integration operates independently of the network's internet gateways. However, for each secondary link, it requires static routes to be configured on the network to route specific DNS resolvers via the link being monitored. See your network gateway's documention for details on how to configure static routes for your particular network: how to configure your network is outside the scope of this integration.

The integration also optionally monitors network links via ping, and can record the average round trip time of the pings at a reduced frequency.

## Installation

This integration can be installed via HACS by adding this repository as a custom repository. See the [HACS documentation](https://hacs.xyz/docs/faq/custom_repositories/) for the procedure.

## Configuration

This integration is configured via the config flow UI. Add the integration at **Settings > Devices & Services > Add Integration**.

After adding the integration, the scan interval, timeout and retries, and the link configuration can be updated by clicking **Configure** on the integration page. Reconfiguring the integration will restart the integration.

### Link configuration

The link configuration is a YAML list, where each item represents a link. One link must be designated as the primary link, and any number of other links can be designated as secondary link. Additional links (such as VPN or internal links) may be specified, though the status of these links will not be used to determine the overall internet connectivity status.

The following properties are supported for link objects:

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | `Link `_n_ | Friendly name for the link entity |
| `link_type` | string | `monitor-only` | Type of the link, valid values are: `primary`, `secondary` and `monitor-only`. Must specify one `primary` and zero or more `secondary` and `monitor-only` links. `monitor-only` links are not used to determine overall internet connectivity status |
| `probe_type` | string | `google` | Type of probe used to query the current IP address of this link, [see the list of probe types below](#supported-probe-types) |
| `probe_target` | filename for `probe_type=file`, hostname or IP address for all other `probe_type`s | required | DNS server name or IP that link IP address queries are sent to. DNS names can be used (resolved with a timeout of `timeout`) but IP addresses are recommended. The `probe_target` must be routed via this link on the internet gateway, although it may fail over to another link in case of failure |
| `scan_interval` | int | integration default | Polling frequency for this link (in seconds), overrides frequency configured at integration level |
| `timeout` | float | integration default | Timeout for DNS queries, overrides timeout configured at integration level |
| `retries` | int | integration default | Number of probes sent to the probe server on each poll, overrides retries configured at integration level |
| `configured_ip` | IP address | | The public IP address expected to be used for this link. See [Configured IP address for links](#configured-ip-address-for-links) for a description of how the configured IP address is used to determine whether a link is up |
| `reverse_hostname` | string | | A link is considered down and failed over if the reverse DNS lookup of the NAT IP address does not contain the value specified in this property |
| `rtt_sensor` | object | | Enables the RTT sensor for this link, see [`rtt_sensor` object](#rtt_sensor-object). |

Using an IP address to specify the probe target (rather than the DNS name) is strongly encouraged to avoid unintended changes. Note that the integration resolves all DNS names specified in the configuration at integration startup only, and will not use any subsequent changes to the name.

**NOTE:** It is most efficient to use scan and update intervals that are multiples of each other. Whilst each link and RTT sensor can be configured with unique scan and update intervals, polls and updates may not always occur at the expected time when the intervals have a greatest common divisor of less than 5 seconds.

## Supported probe types

The following requester IP address query services are supported:

- [Google](https://developers.google.com/maps/root-ca-faq#how-can-i-determine-the-public-address-of-my-dns) (type `google`): use servers `ns[1-4].google.com`
- [OpenDNS](https://www.cyberciti.biz/faq/how-to-find-my-public-ip-address-from-command-line-on-a-linux/) (type `opendns`): use servers `resolver[1-4].opendns.com`
- [Akamai](https://developer.akamai.com/blog/2018/05/10/introducing-new-whoami-tool-dns-resolver-information) (type `akamai`): use any of the servers returned by the command `dig ns akamaitech.net`
- File-based IP address query (type `file`): read current IP address from filename specified in `probe_target`. A daemon script that determines the current IP address for the link can write it to this file.
- Ping-based probes (type `ping`): ping the target host specified in `probe_target`. This sensor is very similar to the [Ping integration](https://www.home-assistant.io/integrations/ping/) with a configurable polling interval and a configurable update frequency for the RTT sensor.

### `rtt_sensor` object

Specifying an `rtt_sensor` object enables the round trip time (RTT) sensor for probe types that return RTT information: `google`, `opendns`, `akamai` and `ping`. This sensor records the RTT for the DNS query or ping to the `probe_target`.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | _link_name_` RTT` | Friendly name for the link RTT entity |
| `update_interval` | int | 300s | The frequency that the RTT entity should update. |

**NOTE:** Every update to each RTT sensors is by default stored in the Home Assistant database update, which can get very large when a low `update_interval` is specified. To minimise the growth of the database, it is recommended that either this sensor is excluded in the [`recorder` integration](https://www.home-assistant.io/integrations/recorder/) or a value of no lower than 300s be configured for `update_interval`.

## Entities

The state of the sensor `sensor.internet_status` shows the overall state of internet connectivity. It can have the following values:

- `up`: All primary and secondary links are up
- `degraded (secondary down)`: The primary link is up, but one or more secondary links are down
- `degraded (primary down)`: The primary link is down, but at least one secondary link remains up. There are no responses received for the DNS request sent via the primary link
- `failover to secondary (primary down)`: The primary link is down, and the DNS requests for the primary link are being rerouted via a secondary link
- `failover to other (primary down)`: The primary link is down, and the DNS requests for the primary link are being rerouted via a link that is not configured in the integration
- `down`: All primary and secondary links have failed

A binary_sensor connectivity entity is created for each link. This entity has state `on` when the link is considered up.

A link is considered failed when any of the following are true:

- the public IP address DNS query for the link fails, or
- the IP address returned by the DNS query for the link matches the configured IP address for a different link, or
- the IP address does not reverse resolve to a hostname with a suffix matching the `reverse_hostname` property, if it is provided for the link

The state of the binary_sensor entity for failed links is `off`. When the public IP address of the link matches the configured IP address for another link, the `link_failover` attribute is also set to `true`.

If an [`rtt_sensor` object](#rtt_sensor-object) is specified for a link, then an additional sensor entity is added for the link. This entity records the average round-trip time for the DNS requests for the public IP address of the link.

## Configured IP address for links

The configured IP address for a link is used to determine whether the link has failed over. It can be specified in the link configuration using the `configured_ip` property, or determined heuristically.

Once all primary and secondary links are up and have unique IP addresses, the integration will automatically set the configured IP address for each link that does not have the `configured_ip` property configured.

Two services are provided to change the configured IP for a link:

### Service `set_configured_ip`

Set the configured IP for a specified link to the current IP address. Useful on links tha use dynamic public IP addresses that can change periodically.

### Service `reset_configured_ip_all`

Reset the configured IP for all links to the IP address specified in the configuration, if present. Re-compute the configured IP addresses for all other links, once all links are up and have unique IP addresses.

## Example link configuration

The example link configuration below uses the Google DNS resolvers to determine the public IP address for each link. RTT sensors are enabled, and update at a reduced frequency. It requires the following routes to be in place on your internet gateway:

- **216.239.32.10** routed via the `Primary ISP` link (primary)
- **216.239.34.10** routed via the `Secondary ISP` link (secondary)
- **216.239.36.10** routed via the `Backup ISP` link (secondary)
- **216.239.38.10** routed via the `VPN` link (monitored)

```yaml
- name: Primary ISP
  link_type: primary
  probe_target: 216.239.32.10
  probe_type: google
  rtt_sensor:
    update_interval: 60
- name: Secondary ISP
  link_type: secondary
  probe_target: 216.239.34.10
  probe_type: google
  rtt_sensor:
    update_interval: 60
- name: Backup ISP
  link_type: secondary
  probe_target: 216.239.36.10
  probe_type: google
  rtt_sensor:
    update_interval: 60
- name: VPN
  scan_interval: 60
  retries: 2
  timeout: 2
  probe_target: 216.239.38.10
  probe_type: google
  reverse_hostname: cable.virginm.net
  rtt_sensor:
    update_interval: 120
```

## Enabling debugging

This component logs messages to the `custom_components.internet_status` namespace. See the [Logger integration documentation](https://www.home-assistant.io/integrations/logger/) for the procedure for enabling logging for this namespace.

## Known issues/limitations

- Reverse DNS queries are attempted with a lifetime of the specified `timeout` and are only tried once, and will cause a link to be marked as failed over if this DNS request fails.
- Reverse DNS queries are performed through the DNS settings configured on the host, and not via the `probe_target`. This is required as the probe servers are generally not recursive DNS servers and are not authoritative for link addresses (unless your upstream's DNS servers emulate one of the supported IP address query services, which is unlikely.)
- The configured IP address of monitor-only links are not set correctly if the link is down or failed over at component startup. The `internet_status.set_configured_ip` service can be used to update the configured IP address for a link to the current IP address, after the link is up again.
