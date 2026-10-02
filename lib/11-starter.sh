#!/usr/bin/env bash

log 'Installing starter pack publication, private access, and video tools'
starter_root=${KIT_STARTER_ROOT:-}
# A fixed CLI release avoids surprise changes in the client publishing path.
netlify_version=27.10.2
kit_node=${KIT_NODE_BIN:-/home/hermes/.hermes/node/bin/node}
kit_npm_cli=${KIT_NPM_CLI:-/home/hermes/.hermes/node/lib/node_modules/npm/bin/npm-cli.js}
netlify_script="$starter_root/usr/local/lib/node_modules/netlify-cli/bin/run.js"
[[ -x $kit_node && -f $kit_npm_cli ]] || { echo 'Hermes bundled Node and npm are required for Netlify CLI.' >&2; exit 1; }
"$kit_node" --version | awk -F. '{sub(/^v/, "", $1); if ($1 < 22 || ($1 == 22 && $2 < 13)) exit 1}' || { echo 'Netlify CLI needs the kit Node 22.13 or newer.' >&2; exit 1; }
if [[ ! -f $netlify_script || $("$kit_node" "$netlify_script" --version 2>/dev/null || true) != *"$netlify_version"* ]]; then
  rm -f -- "$starter_root/usr/local/bin/netlify"
  # npm package lifecycle scripts call `node` and `npm` themselves. Give those
  # children the bundled toolchain explicitly; the installer uses absolute paths.
  env PATH="$(dirname "$kit_node"):/usr/bin:/bin" "$kit_node" "$kit_npm_cli" install --global --prefix="$starter_root/usr/local" --no-audit --no-fund "netlify-cli@$netlify_version"
fi
# npm's generated executable uses /usr/bin/env node. Pin runtime execution too.
install -d -m 0755 "$starter_root/usr/local/bin"
rm -f -- "$starter_root/usr/local/bin/netlify"
printf '#!/usr/bin/env bash\nexec %q %q "$@"\n' "$kit_node" "$netlify_script" > "$starter_root/usr/local/bin/netlify"
chmod 0755 "$starter_root/usr/local/bin/netlify"
apt-get -y --no-install-recommends install ffmpeg=7:6.1.1-3ubuntu5 gnupg
python3 - "$KIT_RUNTIME_DIR/lib" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from kit_powerup import local_chromium
local_chromium()
PY
if [[ -f /etc/hermes-kit/consents.json ]] && jq -e '.consents[]? | select(.integration == "builder" or .integration == "website")' /etc/hermes-kit/consents.json >/dev/null; then
  python3 - "$KIT_RUNTIME_DIR/lib" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from kit_powerup import install_builder_qa
install_builder_qa()
PY
fi
install -d -m 0755 "$starter_root/usr/share/keyrings" "$starter_root/etc/apt/sources.list.d"
key_tmp=$(mktemp)
curl --fail --silent --show-error --location --retry 6 --retry-all-errors --retry-delay 5 --retry-max-time 300 https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg --output "$key_tmp"
fingerprint=$(gpg --show-keys --with-colons "$key_tmp" | awk -F: '$1 == "fpr" {print $10; exit}')
[[ $fingerprint == 2596A99EAAB33821893C0A79458CA832957F5868 ]] || { rm -f "$key_tmp"; echo 'Tailscale signing key fingerprint differs from the pin.' >&2; exit 1; }
install -m 0644 "$key_tmp" "$starter_root/usr/share/keyrings/tailscale-archive-keyring.gpg"
rm -f "$key_tmp"
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/ubuntu noble main' > "$starter_root/etc/apt/sources.list.d/tailscale.list"
apt-get update
apt-get -y --no-install-recommends install tailscale
install -d -m 0755 "$starter_root/etc/tailscale" "$starter_root/etc/systemd/system/tailscaled.service.d"
if [[ ! -f $starter_root/etc/tailscale/tailscaled.json ]]; then
  printf '{"enabled":false,"locked":false}\n' > "$starter_root/etc/tailscale/tailscaled.json"
  chmod 0600 "$starter_root/etc/tailscale/tailscaled.json"
fi
install -m 0644 /dev/stdin "$starter_root/etc/systemd/system/tailscaled.service.d/10-hermes-kit.conf" <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/sbin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock --config=/etc/tailscale/tailscaled.json
EOF
systemctl daemon-reload
systemctl enable tailscaled.service
for helper in kit-tailscale kit-make-video kit-starter-enable; do
  install -d -m 0755 "$starter_root/usr/local/bin"
  ln -sfn "$KIT_RUNTIME_DIR/bin/$helper" "$starter_root/usr/local/bin/$helper"
done
install -m 0644 /dev/stdin "$starter_root/etc/systemd/system/hermes-kit-starter.service" <<EOF
[Unit]
Description=Client starter Builder bridge
After=network-online.target
[Service]
ExecStart=/usr/bin/python3 $KIT_RUNTIME_DIR/lib/kit_starter_server.py
Restart=on-failure
UMask=0077
PrivateTmp=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
if [[ -f /etc/hermes-kit/consents.json ]] && jq -e '.consents[]? | select(.integration == "builder")' /etc/hermes-kit/consents.json >/dev/null; then
  systemctl enable --now hermes-kit-starter.service
else
  systemctl disable --now hermes-kit-starter.service 2>/dev/null || true
fi
