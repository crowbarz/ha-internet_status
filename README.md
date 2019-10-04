# ha-internet_status

Sensor to check Internet ISP link path status via DNS queries.

Used where a network is connected to the Internet via multiple upstream ISPs
that NAT to different public IP addresses. The sensor asks multiple DNS
resolvers to return the NAT IP used to reach that resolver, and thus determine
which of the egress ISPs were taken to reach that resolver. Using current and
historical data, the sensor can determine whether the upstream ISP links are
available.

Also supports monitoring of an additional VPN link via DNS queries and reverse
DNS mapping the IP address back to a domain to determine if the VPN connection
is up.

Requires routing on the ISP gateway to be set up to route specific DNS resolvers
through specific links by default, optionally failing over to a secondary link
should the primary link not be available.

Requester IP address query services from
[Google](https://developers.google.com/maps/root-ca-faq#how-can-i-determine-the-public-address-of-my-dns),
[Akamai](https://developer.akamai.com/blog/2018/05/10/introducing-new-whoami-tool-dns-resolver-information)
and [OpenDNS](https://www.cyberciti.biz/faq/how-to-find-my-public-ip-address-from-command-line-on-a-linux/)
are supported by this component.