#!/usr/bin/env bash

log 'Installing Hermes gateway services'
# Hermes 0.21.x has one host gateway. It runs from the default Hermes home
# and multiplexes the named client profile; support has a separate Unix-user
# boundary and HERMES_HOME in 08-zero-access.sh.
gateway_service="hermes-gateway.service"
for runtime_dir in sessions memory cron logs state runtime; do
  install -d -m 0700 -o "$HERMES_USER" -g "$HERMES_USER" "$HERMES_HOME/$runtime_dir"
done
install -m 0600 -o "$HERMES_USER" -g "$HERMES_USER" /dev/null /home/hermes/.hermes-kit-outside-vault-canary
install -d -m 0755 "/etc/systemd/system/${gateway_service}.d"
install -m 0644 /dev/stdin "/etc/systemd/system/${gateway_service}.d/docker-rootless.conf" <<EOF
[Service]
Environment=DOCKER_HOST=unix:///run/user/$(id -u "$HERMES_USER")/docker.sock
Environment=HERMES_WRITE_SAFE_ROOT=/home/hermes/vault
ProtectHome=tmpfs
BindPaths=/home/hermes/vault
BindReadOnlyPaths=/home/hermes/.local
BindPaths=/home/hermes/.hermes
EOF

# In Hermes 0.21, the multiplexed host gateway owns the loopback dashboard.
# A separate client-profile dashboard races it for port 9119 and crash-loops.
# Remove the obsolete kit unit on upgrade before starting the host gateway.
dashboard_unit=/home/hermes/.config/systemd/user/hermes-dashboard.service
if [[ -e $dashboard_unit ]]; then
  run_as_hermes 'systemctl --user disable --now hermes-dashboard.service || true'
  rm -f -- "$dashboard_unit"
  run_as_hermes 'systemctl --user daemon-reload'
fi
# The client profile is the sticky default, so name the root profile explicitly.
env HOME=/home/hermes HERMES_HOME="$HERMES_ROOT" "$HERMES_BIN" -p default gateway install --system --run-as-user "$HERMES_USER"
systemctl daemon-reload
systemctl enable --now "$gateway_service"
systemctl restart "$gateway_service"
env HOME=/home/hermes HERMES_HOME="$HERMES_ROOT" "$HERMES_BIN" -p default gateway status --system >/dev/null
gateway_environment=$(systemctl show "$gateway_service" --property=Environment --value)
grep -F "DOCKER_HOST=unix:///run/user/$(id -u "$HERMES_USER")/docker.sock" <<<"$gateway_environment" >/dev/null &&
  grep -F 'HERMES_WRITE_SAFE_ROOT=/home/hermes/vault' <<<"$gateway_environment" >/dev/null || {
  echo 'Gateway service is missing its rootless Docker or vault restriction environment.' >&2
  exit 1
}

gateway_pid=$(systemctl show "$gateway_service" -p MainPID --value)
[[ $gateway_pid =~ ^[1-9][0-9]*$ ]] || { echo 'Gateway did not provide a process for sandbox verification.' >&2; exit 1; }
nsenter -t "$gateway_pid" -m -- runuser -u "$HERMES_USER" -- test ! -r /home/hermes/.hermes-kit-outside-vault-canary || {
  # Test-only escape hatch: container test hosts (e.g. OrbStack/LXC) force ProtectHome=no on every service, so the sandbox
  # cannot be verified there. Never set this on a real server; kit-verify reports it as WARN, not PASS.
  if [[ ${KIT_TEST_CONTAINER_SANDBOX_UNVERIFIABLE:-} == 1 ]] && systemd-detect-virt --container -q; then
    echo 'WARN: gateway sandbox cannot be verified inside a container test host.' >&2
  else
    echo 'Gateway sandbox can read the outside-vault canary.' >&2
    exit 1
  fi
}
