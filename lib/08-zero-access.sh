#!/usr/bin/env bash

log 'Installing zero-access support, access, health, and update controls'
# shellcheck source=lib/sshd-transaction.sh
source "$KIT_DIR/lib/sshd-transaction.sh"
: "${KIT_TIER:=care}"
: "${OPS_SSH_PUBKEY:=}"
: "${SUPPORT_PLATFORM:=none}"
: "${SUPPORT_ALLOWED_USER:=}"
: "${OTLP_HEALTH_ENDPOINT:=}"
[[ $KIT_TIER =~ ^(care|managed|full|ludicrous)$ ]] || { echo 'KIT_TIER must be care, managed, or full.' >&2; exit 1; }
[[ $KIT_TIER == ludicrous ]] && KIT_TIER=full
[[ $SUPPORT_PLATFORM =~ ^(none|photon|telegram|whatsapp|signal|slack)$ ]] || { echo 'SUPPORT_PLATFORM is invalid.' >&2; exit 1; }
if [[ $SUPPORT_PLATFORM != none ]]; then [[ $SUPPORT_ALLOWED_USER =~ ^[A-Za-z0-9._:@+-]{1,128}$ ]] || { echo 'SUPPORT_ALLOWED_USER must be exactly one stable ID.' >&2; exit 1; }; fi
if [[ -n $OTLP_HEALTH_ENDPOINT ]]; then [[ $OTLP_HEALTH_ENDPOINT == https://* ]] || { echo 'OTLP_HEALTH_ENDPOINT must use HTTPS.' >&2; exit 1; }; fi

apt-get -y --no-install-recommends install tlog auditd
install -d -m 0700 /etc/ssh/kit /var/lib/hermes-kit/grants
install -d -m 0755 /etc/ssh/auth_principals
if [[ ! -f /etc/ssh/kit/client-ca ]]; then ssh-keygen -q -t ed25519 -N '' -f /etc/ssh/kit/client-ca; fi
[[ -f /etc/ssh/kit/revoked.krl ]] || ssh-keygen -q -k -f /etc/ssh/kit/revoked.krl
chmod 0600 /etc/ssh/kit/client-ca
chmod 0644 /etc/ssh/kit/client-ca.pub /etc/ssh/kit/revoked.krl
install -d -m 0755 /etc/tlog
install -m 0644 /dev/stdin /etc/tlog/tlog-rec-session.conf <<'EOF'
{
  "notice": "WARNING: this privileged support session is recorded.",
  "log": { "input": true, "output": true, "window": true },
  "writer": "journal",
  "journal": { "priority": "info", "augment": true }
}
EOF
# Care and Managed converge to no full operator access. A Full reinstall preserves
# a still-valid client-approved grant instead of removing its sudo policy and
# recreating access on every install.
if [[ $KIT_TIER == care || $KIT_TIER == managed ]]; then
  # A downgrade removes standing Full Service keys before any service restarts.
  if [[ -f /etc/hermes-kit/full/authorized_keys ]]; then : > /etc/hermes-kit/full/authorized_keys; chmod 0600 /etc/hermes-kit/full/authorized_keys; fi
  rm -f /etc/ssh/kit-full.keys
  for certificate in /var/lib/hermes-kit/grants/*-cert.pub; do
    [[ -f $certificate ]] || continue
    grant_id=${certificate##*/}; grant_id=${grant_id%-cert.pub}
    "$KIT_DIR/bin/kit-revoke-access" "$grant_id" || true
  done
  rm -f /etc/sudoers.d/90-hermes-kit-ops /etc/sudoers.d/90-hermes-kit-hermes-ops
  sshd_file_apply /etc/ssh/sshd_config.d/10-hermes-kit-access.conf
  rm -f /etc/ssh/auth_principals/hermes-ops
  if id -u hermes-ops >/dev/null 2>&1; then loginctl terminate-user hermes-ops || true; userdel --remove hermes-ops; fi
  if [[ $KIT_TIER == care ]]; then
    sshd_file_apply /etc/ssh/sshd_config.d/11-hermes-kit-manager.conf
    rm -f /etc/hermes-kit/manager/authorized_keys /etc/ssh/kit-manager.keys /etc/sudoers.d/91-hermes-kit-manager
    if id -u kit-manager >/dev/null 2>&1; then loginctl terminate-user kit-manager || true; userdel --remove kit-manager; fi
  fi
fi
sshd -t
systemctl reload ssh || systemctl restart ssh.socket

if ! id -u hermes-support >/dev/null 2>&1; then useradd --system --home /var/lib/hermes-support --shell /usr/sbin/nologin hermes-support; fi
install -d -m 0700 -o hermes-support -g hermes-support /var/lib/hermes-support /run/hermes-support
install -d -m 0751 -o root -g root /var/lib/hermes-kit
if [[ ! -f /var/lib/hermes-kit/health.json ]]; then
  printf '%s\n' '{"schema":1,"generated_at":"unknown","status":"unknown"}' | install -o root -g hermes-support -m 0640 /dev/stdin /var/lib/hermes-kit/health.json
fi
# The documented POSIX installer puts the runtime in ~/.hermes/hermes-agent;
# ~/.local/bin/hermes is only a wrapper.  Copy both into a versioned, root-owned
# location and rewrite every absolute source path in the wrapper.
support_source=/home/hermes/.hermes/hermes-agent
[[ -d $support_source && -x /home/hermes/.local/bin/hermes ]] || { echo 'Hermes source runtime is missing.' >&2; exit 1; }
support_revision=$(git -c safe.directory="$support_source" -C "$support_source" rev-parse HEAD)
support_runtime=/opt/hermes-support-runtime/$support_revision
if [[ ! -f $support_runtime/bin/hermes ]]; then
  install -d -m 0755 -o root -g root "$support_runtime/bin"
  cp -a "$support_source/." "$support_runtime/"
  cp -a /home/hermes/.local/bin/hermes "$support_runtime/bin/hermes"
  sed -i "s#/home/hermes/.hermes/hermes-agent#$support_runtime#g" "$support_runtime/bin/hermes"
  chown -R root:root "$support_runtime"
  chmod -R go-w "$support_runtime"
fi
ln -sfn "$support_runtime" /opt/hermes-support-runtime/current
runuser -u hermes-support -- env HOME=/var/lib/hermes-support HERMES_HOME=/var/lib/hermes-support PATH=/opt/hermes-support-runtime/current/bin:/usr/local/bin:/usr/bin:/bin /opt/hermes-support-runtime/current/bin/hermes --version >/dev/null
install -d -m 0700 -o hermes-support -g hermes-support /var/lib/hermes-support/skills/health-report
install -m 0644 -o hermes-support -g hermes-support "$KIT_DIR/support-profile/config.yaml" /var/lib/hermes-support/config.yaml
install -m 0644 -o hermes-support -g hermes-support "$KIT_DIR/support-profile/SOUL.md" /var/lib/hermes-support/SOUL.md
install -m 0640 -o root -g hermes-support "$KIT_DIR/support-profile/skills/health-report/SKILL.template.md" /var/lib/hermes-support/skills/health-report/SKILL.template.md
install -m 0640 -o root -g hermes-support "$KIT_DIR/support-profile/skills/health-report/SKILL.md" /var/lib/hermes-support/skills/health-report/SKILL.md
if [[ $SUPPORT_PLATFORM != none ]]; then
  support_env=/var/lib/hermes-support/.env
  support_env_tmp=$(mktemp /var/lib/hermes-support/.env.XXXXXX)
  { [[ -f $support_env ]] && grep -Ev '^[A-Z_]+_ALLOWED_USERS=' "$support_env" || true; printf '%s_ALLOWED_USERS="%s"\n' "${SUPPORT_PLATFORM^^}" "$SUPPORT_ALLOWED_USER"; } > "$support_env_tmp"
  chown hermes-support:hermes-support "$support_env_tmp"
  chmod 0600 "$support_env_tmp"
  mv "$support_env_tmp" "$support_env"
fi
install -m 0644 /dev/stdin /etc/systemd/system/hermes-support-gateway.service <<'EOF'
[Unit]
Description=Hermes Kit content-free support gateway
After=network-online.target hermes-kit-health.service

[Service]
User=hermes-support
Group=hermes-support
Environment=HERMES_HOME=/var/lib/hermes-support
Environment=HERMES_WRITE_SAFE_ROOT=/run/hermes-support
ExecStartPre=/opt/hermes-support-runtime/current/bin/hermes --version
ExecStart=/opt/hermes-support-runtime/current/bin/hermes gateway run
Restart=on-failure
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
InaccessiblePaths=/home/hermes /etc/hermes
ReadWritePaths=/var/lib/hermes-support /run/hermes-support
BindReadOnlyPaths=/var/lib/hermes-kit/health.json:/var/lib/hermes-support/health.json
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-health.service <<'EOF'
[Unit]
Description=Write content-free Hermes Kit health report

[Service]
Type=oneshot
ExecStart=/usr/local/bin/kit-health
ExecStartPost=/bin/systemctl try-restart hermes-support-gateway.service
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-health.timer <<'EOF'
[Unit]
Description=Refresh Hermes Kit health every five minutes

[Timer]
OnBootSec=2m
OnUnitActiveSec=5m
Persistent=true

[Install]
WantedBy=timers.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-report.service <<'EOF'
[Unit]
Description=Send signed Hermes Kit health report
Wants=network-online.target
After=network-online.target hermes-kit-health.service

[Service]
Type=oneshot
ExecStartPre=/usr/local/bin/kit-health
ExecStart=-/usr/local/bin/kit-report
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-report.timer <<'EOF'
[Unit]
Description=Send signed Hermes Kit health every five minutes

[Timer]
OnBootSec=3m
OnUnitActiveSec=5m
Persistent=true

[Install]
WantedBy=timers.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-report-shutdown.service <<'EOF'
[Unit]
Description=Send final Hermes Kit shutdown report
DefaultDependencies=no
After=network.target network-online.target
Before=shutdown.target
Conflicts=shutdown.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/true
ExecStop=/usr/local/bin/kit-report --shutdown
TimeoutStopSec=40s

[Install]
WantedBy=multi-user.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-grant-cleanup.service <<'EOF'
[Unit]
Description=Terminate expired Hermes Kit support access

[Service]
Type=oneshot
ExecStart=/usr/local/bin/kit-expire-grants
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-grant-cleanup.timer <<'EOF'
[Unit]
Description=Check support grant expiry

[Timer]
OnBootSec=1m
OnUnitActiveSec=15m
Persistent=true

[Install]
WantedBy=timers.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-autoupdate.service <<'EOF'
[Unit]
Description=Pull a verified Hermes Kit release

[Service]
Type=oneshot
ExecStart=/usr/local/bin/kit-autoupdate run
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-autoupdate.timer <<'EOF'
[Unit]
Description=Weekly Hermes Kit client-selected update window

[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
for helper in kit-grant-access kit-revoke-access kit-handover kit-health kit-enroll kit-report kit-downtime kit-expire-grants kit-autoupdate kit-set-support-key kit-manage-grant kit-manage-revoke kit-full-access kit-powerup; do ln -sfn "$KIT_RUNTIME_DIR/bin/$helper" "/usr/local/bin/$helper"; done
ln -sfn "$KIT_RUNTIME_DIR/bin/kit-manage-dispatch" /usr/local/sbin/kit-manage-dispatch
systemctl daemon-reload
systemctl enable --now hermes-kit-health.timer hermes-kit-autoupdate.timer hermes-kit-report-shutdown.service
if [[ -f /var/lib/hermes-kit/report/enrolled-agent-id ]]; then systemctl enable --now hermes-kit-report.timer; fi
systemctl start hermes-kit-health.service
if [[ $SUPPORT_PLATFORM != none ]]; then systemctl enable --now hermes-support-gateway.service; fi
if [[ $KIT_TIER == full && -n $OPS_SSH_PUBKEY ]] && ! compgen -G '/var/lib/hermes-kit/grants/*-cert.pub' >/dev/null; then
  /usr/local/bin/kit-grant-access --public-key <(printf '%s\n' "$OPS_SSH_PUBKEY") --hours 8 --waiver setup-bootstrap --setup --bootstrap
fi
