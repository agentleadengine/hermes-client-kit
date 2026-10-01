#!/usr/bin/env bash

log 'Installing token-gated activation and support page'
apt-get -y --no-install-recommends install caddy
install -d -m 0700 /var/lib/agent-care/activation /var/lib/agent-care/support /var/lib/agent-care/home
ln -sfn "$KIT_RUNTIME_DIR/bin/kit-activation" /usr/local/bin/kit-activation
ln -sfn "$KIT_RUNTIME_DIR/bin/kit-install-report" /usr/local/bin/kit-install-report
install -m 0755 "$KIT_DIR/activation/activation-service.py" /usr/local/lib/hermes-kit-activation-service.py
install -m 0644 "$KIT_DIR/activation/Caddyfile" /etc/caddy/Caddyfile
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-activation.service <<'EOF'
[Unit]
Description=Hermes Kit private activation and support page
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/lib/hermes-kit-activation-service.py
Restart=on-failure
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/agent-care /var/lib/hermes-kit /run

[Install]
WantedBy=multi-user.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-activation-expiry.service <<'EOF'
[Service]
Type=oneshot
ExecStart=/usr/local/bin/kit-activation expire
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-activation-expiry.timer <<'EOF'
[Timer]
OnBootSec=5m
OnUnitActiveSec=5m
Persistent=true
[Install]
WantedBy=timers.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-support-expiry.service <<'EOF'
[Service]
Type=oneshot
ExecStart=/usr/local/bin/kit-activation revoke-support
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-support-expiry.timer <<'EOF'
[Timer]
OnBootSec=24h
Persistent=true
[Install]
WantedBy=timers.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-install-report.service <<'EOF'
[Service]
Type=oneshot
ExecStart=/usr/local/bin/kit-install-report
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-install-report.timer <<'EOF'
[Timer]
OnBootSec=5m
OnUnitActiveSec=5m
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl disable --now caddy hermes-kit-activation.service hermes-kit-activation-expiry.timer hermes-kit-support-expiry.timer hermes-kit-install-report.timer 2>/dev/null || true
