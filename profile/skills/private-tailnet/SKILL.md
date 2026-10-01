---
name: private-tailnet
description: Explain private access to client tools through the client's Tailscale network.
version: 1.0.0
license: MIT
---
# Private access to tools

The server joins only the client's own Tailscale network. Sam uses `kit-tailscale join` during setup, reading a one-use key from a local prompt. Never ask for that key in chat or send it to any service other than Tailscale. Do not run `tailscale funnel` or open a public port.

Published tools stay on local server ports. `kit-tailscale serve` makes an approved tool reachable only from devices permitted by the client's tailnet. `kit-tailscale preview` gives the client a private address for reviewing their website before publication. If a device cannot reach either address, check whether it is signed in to the client's tailnet and whether the client allows that device. Do not weaken firewall or account rules to make access work.
