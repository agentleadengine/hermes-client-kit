#!/usr/bin/env bash

log 'Installing plan access and client power-up controls'
for helper in kit-manage-grant kit-manage-revoke kit-full-access kit-powerup kit-logins-site kit-schedule kit-website kit-tools-setup kit-tools-configure kit-tools-image kit-tools-connect kit-tools-certs kit-tools-stage kit-tools-publish kit-tools-rollback kit-tools-db-restore kit-tools-import kit-tools-backup kit-tools-backup-key kit-tools-rebuild; do
  ln -sfn "$KIT_RUNTIME_DIR/bin/$helper" "/usr/local/bin/$helper"
done
ln -sfn "$KIT_RUNTIME_DIR/bin/kit-manage-dispatch" /usr/local/sbin/kit-manage-dispatch
install -m 0755 "$KIT_DIR/lib/website-preview.py" /usr/local/lib/hermes-kit-website-preview.py
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-website-preview.service <<'EOF'
[Unit]
Description=Loopback-only client website preview
[Service]
User=hermes
Group=hermes
ExecStart=/usr/bin/python3 /usr/local/lib/hermes-kit-website-preview.py
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
[Install]
WantedBy=multi-user.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-tools-backup.service <<'EOF'
[Unit]
Description=Encrypt and copy client tool snapshots
[Service]
Type=oneshot
ExecStart=/usr/local/bin/kit-tools-backup
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-tools-backup.timer <<'EOF'
[Unit]
Description=Nightly client tool backups
[Timer]
OnCalendar=*-*-* 02:15:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-tools-certs.service <<'EOF'
[Unit]
Description=Refresh client Cloudflare Access signing keys
[Service]
Type=oneshot
ExecStart=/usr/local/bin/kit-tools-certs
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-tools-certs.timer <<'EOF'
[Unit]
Description=Keep client tool origin signing keys fresh
[Timer]
OnBootSec=10m
OnUnitActiveSec=1h
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
if [[ $KIT_TIER == managed && -s /etc/hermes-kit/manager/authorized_keys ]]; then
  python3 - "$KIT_RUNTIME_DIR/lib" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from kit_access import setup_manager
setup_manager()
PY
fi
# Distribution updates replace config.yaml. Reapply only previously consented
# power-ups; the consent ledger is the authority for optional relaxations.
python3 - "$KIT_RUNTIME_DIR/lib" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from kit_powerup import apply_policy, consents, install_logins
enabled = {entry.get("integration") for entry in consents().get("consents", [])}
if "logins" in enabled:
    install_logins()
apply_policy(enabled)
PY
if [[ -f /etc/hermes-kit/consents.json ]] && jq -e '.consents[]? | select(.integration == "builder")' /etc/hermes-kit/consents.json >/dev/null; then
  systemctl enable --now hermes-kit-tools-backup.timer
else
  systemctl disable --now hermes-kit-tools-backup.timer 2>/dev/null || true
fi
