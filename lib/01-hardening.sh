#!/usr/bin/env bash

log 'Applying OS hardening'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y upgrade
apt-get -y --no-install-recommends install unattended-upgrades fail2ban ufw openssh-server ca-certificates curl git jq gnupg libatomic1 rsyslog python3-venv build-essential
dpkg-reconfigure -f noninteractive unattended-upgrades

# Operator access is exceptional and certificate-bound.  Do not create an
# unrestricted key-based ops account during provisioning.
rm -f /etc/sudoers.d/90-hermes-kit-ops
if id -u ops >/dev/null 2>&1; then
  loginctl terminate-user ops || true
  userdel --remove ops
fi

if ! id -u "$HERMES_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$HERMES_USER"
fi
gpasswd -d "$HERMES_USER" sudo >/dev/null 2>&1 || true
gpasswd -d "$HERMES_USER" docker >/dev/null 2>&1 || true

install -d -m 0755 /etc/ssh/sshd_config.d
# shellcheck source=lib/sshd-transaction.sh
source "$KIT_DIR/lib/sshd-transaction.sh"
mkdir -p /run/sshd
# Repair the invalid drop-in left by older kit-manage-grant releases before
# validating the rest of the hardening changes.
repairs=() repair_sources=()
for legacy_policy in /etc/ssh/sshd_config.d/10-hermes-kit-access.conf /etc/ssh/sshd_config.d/11-hermes-kit-manager.conf; do
  [[ -f $legacy_policy ]] || continue
  if grep -Eq '^[[:space:]]*PermitUserEnvironment[[:space:]]+' "$legacy_policy"; then
    repaired_policy=$(mktemp)
    sed '/^[[:space:]]*PermitUserEnvironment[[:space:]]/d' "$legacy_policy" > "$repaired_policy"
    repairs+=("$legacy_policy" "$repaired_policy")
    repair_sources+=("$repaired_policy")
  fi
done
if (( ${#repairs[@]} )); then
  if ! sshd_files_apply "${repairs[@]}"; then
    rm -f -- "${repair_sources[@]}"
    exit 1
  fi
  rm -f -- "${repair_sources[@]}"
fi
ssh_policy=$(mktemp)
cat > "$ssh_policy" <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
PermitUserEnvironment no
EOF
if ! sshd_file_apply /etc/ssh/sshd_config.d/00-hermes-kit.conf "$ssh_policy"; then
  rm -f "$ssh_policy"
  exit 1
fi
rm -f "$ssh_policy"
sshd_file_apply /etc/ssh/sshd_config.d/99-hermes-kit.conf
sshd_effective=$(sshd -T)
grep -x 'permitrootlogin no' <<<"$sshd_effective" >/dev/null
grep -x 'passwordauthentication no' <<<"$sshd_effective" >/dev/null
grep -x 'kbdinteractiveauthentication no' <<<"$sshd_effective" >/dev/null
grep -x 'authenticationmethods publickey' <<<"$sshd_effective" >/dev/null
systemctl try-reload-or-restart ssh.service; systemctl restart ssh.socket 2>/dev/null || true

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw --force enable
systemctl enable --now fail2ban
systemctl enable --now rsyslog
install -d -m 0755 /var/lib/hermes-kit
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-access-log.service <<'EOF'
[Unit]
Description=Refresh client-readable Hermes operator access log

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'umask 022; { journalctl --no-pager -u ssh -u sshd -t sudo 2>/dev/null || true; test -f /var/log/auth.log && grep -E "sshd.*Accepted|sudo:" /var/log/auth.log || true; test -f /var/lib/hermes-kit/access-events.log && cat /var/lib/hermes-kit/access-events.log || true; } | sort -u > /var/lib/hermes-kit/access-log.txt'
ExecStartPost=/bin/chown root:root /var/lib/hermes-kit/access-log.txt
ExecStartPost=/bin/chmod 0644 /var/lib/hermes-kit/access-log.txt
EOF
install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-access-log.timer <<'EOF'
[Unit]
Description=Refresh Hermes operator access log every five minutes

[Timer]
OnBootSec=1m
OnUnitActiveSec=5m
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now hermes-kit-access-log.timer
systemctl start hermes-kit-access-log.service

for helper in kit-set-key kit-verify kit-update kit-offboard kit-mailroom-setup kit-agentmail-lists kit-consent kit-lockdown kit-access-log; do
  ln -sfn "$KIT_RUNTIME_DIR/bin/$helper" "/usr/local/bin/$helper"
done
