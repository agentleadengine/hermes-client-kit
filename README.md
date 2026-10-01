# Hermes Client Kit

Installs and hardens a Hermes Agent on a client-owned Ubuntu 24.04 server (for example a DigitalOcean droplet), then
keeps it healthy with signed health reports and signed updates.

- The client owns the server, the AI account and the data. Passwords and AI keys are entered by the client on their own
  server and never leave it.
- Health reports carry status only (no chats, memory, files or keys); unknown fields are rejected.
- Install: put a `kit.conf` (see `kit.conf.example`) at `/etc/hermes-kit/kit.conf`, then run `./install.sh` as root, or
  use the cloud-init script your provider gives you. Check with `kit-verify`.

Hermes Agent is an open source project by Nous Research. This kit is not affiliated with Nous Research, OpenAI,
DigitalOcean or Cloudflare.
