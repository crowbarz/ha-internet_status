<!-- markdownlint-disable MD038 -->
# internet_status

Monitor internet link paths via DNS queries.

This component will monitor the paths of an internet connected network with multiple upstream links which NAT to different public IP addresses. The sensor sends queries to DNS resolvers on the internet that supporting requester IP address queries to determine the NAT IP that is used to reach that resolver, and thus determine the upstream link that was taken to reach that resolver. It also detects failover scenarios where the reverse DNS of the NAT IP does not contain a keyword (typically an ISP name), or the NAT IP of a primary or secondary path changes to the NAT IP of a different path.

The component operates independently of the network's internet gateway, but does require static routes to be configured on the gateway to route the DNS resolvers via a specific link. (How to configure static routes is outside the scope of this document/component.)

## Configuration

One link must be designated as the primary link, and currently one link must be designated the secondary link. Additional links (such as VPN links) may be specified, however the status of these links will not be used to determine the overall internet connectivity status.

Configure this component via a top-level `internet_status` section in `configuration.yaml`:

### `internet_status` object

| Name | Type | Default | Description
| ---- | ---- | ------- | -----------
| `name` | string | `Internet Status` | friendly name for the internet status sensor
| `entity_id` | string | derived from name | optional entity ID for the internet status sensor. Must begin with `sensor.`. Note: `entity_id` will only be used during the initial setup of the internet status sensor, change it in **Configuration** > **Entities** afterwards.
| `scan_interval` | [scan_interval](https://www.home-assistant.io/docs/configuration/platform_options/) | 30 sec | default polling frequency for all links. `scan_interval` should be set to a value that is greater than `timeout` x `retries` to prevent polling timeouts exceeding the polling interval.
| `timeout` | float | 1 sec | default timeout for DNS queries for all links
| `retries` | int | 3 | default number of probes sent to the probe server on each poll.
| `links` | list | **Required** | a list of [link objects](#link-objects) representing the links to be monitored.

### `link` objects

The following properties are supported for link objects:

| Name | Type | Default | Description
| ---- | ---- | ------- | -----------
| `name` | string | `Link `_n_` Status` | friendly name for the link binary sensor
| `entity_id` | string | derived from name | optional entity ID for the link binary sensor. Must begin with `binary_sensor.`. Note: `entity_id` will only be used during the initial setup of the link binary sensor, change it in **Configuration** > **Entities** afterwards.
| `link_type` | string | `monitor-only` | type of the link, valid values are: `primary`, `secondary` and `monitor-only`. Must specify one `primary` and one `secondary` link, but supports any number of `monitor-only` links.
| `probe_server` | hostname or IP address | `ns`_n_`.google.com` | IP address query server that link probes are sent to, names supported (resolved with a timeout of `timeout`) but IP addresses are recommended. _n_ is determined by the number of the link and cycles from 1-4. The `probe_server` must be routed via this link on the internet gateway, although it may fail over to another link in case of failure.
| `probe_type` | string | `google` | type of IP address query server, [see below](#supported-ip-address-query-services).
| `scan_interval` | [scan_interval](https://www.home-assistant.io/docs/configuration/platform_options/) | global default | polling frequency for this link, overrides global default
| `timeout` | float | global default | timeout for DNS queries, overrides global default
| `retries` | int | global default | number of probes sent to the probe server on each poll, overrides global default
| `configured_ip` | IP address |  | the NAT IP address expected to be used for this link
| `reverse_hostname` | string | | link is considered up if the reverse DNS lookup of the NAT IP address contains `reverse_hostname`
| `rtt_sensor` | object | | enables the RTT sensor for this link, [see below](#rtt_sensor-object). Specify an empty object (`{}`) to enable the RTT sensor with all default settings.
| `debug_probe` | bool | `false` | enables additional debug logging for each DNS probe. See [Enabling debugging](#enabling-debugging) for details.

`configured_ip` will be determined heuristically from the first NAT IP address detected on the link if it is considered up, if it is not specified in the configuration and `reverse_hostname` is not specified. (A successful reverse hostname lookup will set `configured_ip` to the returned IP address.)

Using the IP address of the server rather than the DNS name is strongly encouraged to avoid issues if/when the DNS record for the server is changed, as well as ensure that the probe address matches the routing configuration (which is usually configured using IP addresses rather than DNS names.)

### `rtt_sensor` object

Specifying an `rtt_sensor` object enables the round trip time (RTT) sensor. This sensor records the RTT to the `probe_server`

| Name | Type | Default | Description
| ---- | ---- | ------- | -----------
| `name` | string | `Link `_n_` Round Trip Time` | friendly name for the link. If the underlying link has a friendly name defined, then the default for this attribute is the link name with ` Round Trip Time` appended.
| `entity_id` | string | derived from name | optional entity ID for the link RTT sensor. Must begin with `sensor.`.  Note: `entity_id` will only be used during the initial setup of the link RTT sensor, change it in **Configuration** > **Entities** afterwards.
| `update_ratio` | int | 10 | Ratio of RTT sensor updates to link polls, ie. the RTT sensor is only updated every `update_ratio` polls. The default values for `scan_interval` and `update_ratio` results in the RTT sensor updating every 3 x 10 = 300 seconds. Increasing the ratio reduces the number of events generated by the RTT sensor and recorded in the Home Assistant database.
| `debug_rtt` | bool | `false` | enables additional debug logging for RTT sensor updates. See [Enabling debugging](#enabling-debugging) for details.

## Entities

* `sensor.internet_status`: Indicates the status of the internet as determined by this component. The state may be:
  * `up`: both primary and secondary links are up
  * `degraded (primary down)`: the secondary link is up, but the primary link is down
  * `degraded (secondary down)`: the primary link is up, but the secondary link is down
  * `failover`: a failover has occurred (one link is down), but the component cannot determine which link has failed. This occurs if the NAT IP does not match either of the link's `configured_ip`.
  * `failover (primary down)`: the primary link NAT is the IP expected on the secondary link
  * `failover (secondary down)`: the secondary link NAT is the IP expected on the primary link
  * `down`: both primary and secondary links are down
* `binary_sensor.`_`link_id`_`_status`: the status of the link as determined by the reachability to the `probe_server` and the returned IP address.
* `sensor.`_`link_id`_`_rtt`: the RTT to the `probe_server`. The value includes any processing time incurred on the server. Individual RTT values for the most recent probe are available as a list in attribute `rtt`.

## Example configuration

The example configuration below requires the following routes to be in place on your internet gateway:

* **216.239.34.10** routed via the `isp_primary` link
* **216.239.36.10** routed via the `isp_secondary` link
* **216.239.38.10** routed via the `vpn` link

```yaml
# Example configuration.yaml entry:
internet_status:
  scan_interval: 30
  links:
    isp_primary:
      name: Primary ISP
      link_type: primary
      probe_server: 216.239.34.10
      probe_type: google
      reverse_hostname: isp1name
      rtt_sensor:
        name: Override RTT sensor name
    isp_secondary:
      name: Secondary ISP
      link_type: secondary
      probe_server: 216.239.36.10
      probe_type: google
      reverse_hostname: isp2name
      rtt_sensor: {}
    vpn:
      name: VPN
      probe_server: 216.239.38.10
      probe_type: google
      reverse_hostname: vpnhostname
      # no rtt_sensor enabled
```

## Supported IP address query services

The following requester IP address query services are supported:

* [Google](https://developers.google.com/maps/root-ca-faq#how-can-i-determine-the-public-address-of-my-dns) (type `google`): use servers `ns[1-4].google.com`
* [OpenDNS](https://www.cyberciti.biz/faq/how-to-find-my-public-ip-address-from-command-line-on-a-linux/) (type `opendns`): use servers `resolver[1-4].opendns.com`
* [Akamai](https://developer.akamai.com/blog/2018/05/10/introducing-new-whoami-tool-dns-resolver-information) (type `akamai`): use any of the servers returned by the command `dig ns akamaitech.net`

## Enabling debugging

This component logs messages to the `custom_components.internet_status` namespace. See the [Logger integration documentation](https://www.home-assistant.io/integrations/logger/) for the procedure for enabling logging for this namespace.

The [`debug_probe`](#link-objects) and [`debug_rtt`](#rtt_sensor-object) options can be set to enable additional debugging messages for DNS probes and RTT updates. These debug options generate significant additional logging, so are turned off by default.

## Known issues

* Reverse DNS queries are attempted with a lifetime of the specified `timeout` and are only tried once, and will cause a link to be marked down if this DNS request fails.
* Reverse DNS queries are performed through the DNS settings configured on the host, and not via the `probe_server`. This is required as the probe servers are generally not recursive DNS servers and are not authoritative for link addresses (unless your upstream's DNS servers emulate one of the supported IP address query services, which is unlikely.)
* Every link poll will send `retries` probes to the server and update the RTT sensor. The `scan_interval` for the RTT sensor cannot be configured separately from the link status sensor. If you need to poll RTT at a different frequency to the availability, use a [`ping` sensor](https://www.home-assistant.io/integrations/ping/#binary-sensor) instead.
* The sensor `entity_id` is always `sensor.internet_status` and cannot be changed.
* A secondary link must be specified, the internet status sensor does not update if no secondary link is specified.
* Only the first configured secondary path is currently supported. Additional secondary paths are not monitored correctly.
* The configured IP address of monitor-only links are not set correctly if the link is down at component startup. The workaround is to specify the expected configured IP address in the configuration.
