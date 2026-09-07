# Security and deployment boundaries

GNOME Web Display controls an already logged-in desktop. Treat access to its
password, browser session, or host account as access to that desktop. This release
has automated tests, not an independent security audit.

## Intended use

Use it on your own GNOME Wayland host with devices and people you trust. It is not
a multi-tenant remote-desktop service. Everyone who signs in has the same ability
to view and control the virtual monitor, select host audio sources, and affect the
shared desktop. Pausing **Control** is a local UI convenience, not a read-only role.
Keep confidential windows off the shared monitor and inspect the audio source.

The default web listener is HTTP on `0.0.0.0:8090`. HTTP does **not** protect the
password, session cookie, keyboard input, or signaling from network observers or
modification. Use a trusted certificate with native HTTPS, or a correctly configured
HTTPS reverse proxy / encrypted VPN. WebRTC media encryption does not secure an
HTTP login. Do not put this default setup directly on the public Internet.

## Network trust

The launcher publishes the MediaMTX RTSP and HTTP listeners to `127.0.0.1:8554`
and `127.0.0.1:8889`. It requires **Docker Engine 28.0.0 or newer** because older
versions have a documented localhost-publishing exposure to other LAN hosts.
This check applies to the daemon/server, including when invoked through sudo, not
just the CLI. See [Docker's port-publishing documentation][docker-ports].

Local processes and other containers on the same Docker bridge can still reach
MediaMTX. They are inside the trust boundary. MediaMTX's internal endpoints do not
use this application's password; do not expose them to untrusted clients or attach
untrusted containers to that bridge. Custom Docker direct-routing or firewall
settings can change exposure and must be reviewed separately.

UDP `8189` is published for WebRTC media. Docker creates NAT/publishing firewall
rules. The project does not run UFW/iptables commands, change router forwarding,
or silently tune the kernel. Validate actual reachability from another device;
a local bind check is not a network security assessment.

## Application protections

The application uses a password chosen at startup or supplied in a private file;
there is no bundled default password. Tokens are independent per sign-in, kept in
memory, expire after the configured lifetime, and are removed by sign-out. Cookies
are HttpOnly and SameSite=Strict; Secure is set for native HTTPS or an explicitly
configured HTTPS public origin. Restarting the process invalidates all sessions.

Login attempts are limited per direct network peer. By default, eight attempts in
one minute are allowed. The limiter is bounded and in-memory; it is not protection
against distributed denial of service. Behind a reverse proxy, clients share the
proxy's peer bucket. Forwarded address/protocol headers are not trusted implicitly.

State-changing requests and input WebSocket connections require the expected
Origin. The stream proxy only serves the configured reader/WHEP paths and strips
application credentials before forwarding to MediaMTX. Input messages have size,
rate, shape, and value checks. Tracked keys/buttons are released on disconnect,
blur, pause, and sign-out where the transport/session can deliver cleanup.

The app limits stored sessions to 32, simultaneous input sockets to 16, individual
WebSocket messages to 8 KiB, and HTTP request bodies to 64 KiB. These limits are
not a comprehensive resource-exhaustion defense. Avoid unattended deployment to
untrusted networks.

## Important revocation limitation

Signing out revokes the application's cookie and closes its input WebSockets.
The normal UI removes the embedded player. This does **not** guarantee immediate
termination of a previously established WebRTC peer maintained by a modified or
malicious client: media sessions are not cryptographically bound to the web cookie.
Stop the host application / its MediaMTX container to terminate all media access.
A strict per-user media revocation design requires additional MediaMTX session
authorization/control integration and is not implemented here.

## Local secrets, logs, and privileges

A password file must be owned by the launching user, with no group/other access.
`VSCREEN_PASSWORD` and the process's in-memory password can be visible to sufficiently
privileged local processes. This is not a password vault. Never commit passwords,
TLS private keys, session cookies, or real `.env` / `config.toml` files.

Normal launching must not use sudo: Mutter and PipeWire belong to the logged-in
user. Installation and Docker operations can request explicit administrator consent.
The installer does not add users to the root-equivalent Docker group. APT may change
packages or start services as part of its transaction; review it before approving.
The installer does not automatically change Docker repositories to perform an upgrade.

The Docker image receives no home-directory mount or password. It receives the
read-only MediaMTX configuration and advertised host address, with all Linux
capabilities dropped and `no-new-privileges`. This is defense in depth, not a claim
that arbitrary configured container images are safe. Only use an image you trust.

GStreamer logs may contain local device names and operational details. The app
disables aiohttp request access logging, but reverse proxies and Docker can have
their own logs. Inspect and redact logs before sharing them.

## Reporting and maintenance

No maintainer contact or support SLA was supplied with the original archive.
Before publishing, the repository owner should enable private vulnerability
reporting and provide a contact in this file. Do not open a public issue containing
credentials, private screenshots, or a working exploit against a live deployment.
Keep Python, the distribution, Docker, browsers, and the pinned MediaMTX image
maintained; test protocol compatibility before changing the image version.

[docker-ports]: https://docs.docker.com/engine/network/port-publishing/
