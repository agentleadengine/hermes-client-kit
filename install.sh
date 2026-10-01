#!/usr/bin/env bash
set -euo pipefail

KIT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE=/var/log/hermes-kit.log
CONFIG_FILE="${KIT_CONFIG:-/etc/hermes-kit/kit.conf}"

if [[ ${EUID} -ne 0 ]]; then
  echo "install.sh must run as root" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 0600 "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

if [[ ! -f "$CONFIG_FILE" ]]; then
  CONFIG_FILE="$KIT_DIR/kit.conf"
fi
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing kit configuration. Copy kit.conf.example to kit.conf or set KIT_CONFIG." >&2
  exit 1
fi

# The intake's cloud-init calls install.sh directly. Arm the first-boot retry
# before any network-dependent install step can fail.
if [[ ${KIT_INSTALL_RETRY_ACTIVE:-} != 1 && ! -e /opt/hermes-kit/current ]]; then
  install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-install-retry.service <<EOF
[Unit]
Description=Install Hermes Client Kit with bounded first-boot retries
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=$KIT_DIR/bin/kit-install-retry
TimeoutStartSec=0
EOF
  install -m 0644 /dev/stdin /etc/systemd/system/hermes-kit-install-retry.timer <<'EOF'
[Unit]
Description=Retry failed Hermes Kit first-boot installation

[Timer]
OnBootSec=10m
OnUnitInactiveSec=10m
Unit=hermes-kit-install-retry.service

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now hermes-kit-install-retry.timer
  systemctl start hermes-kit-install-retry.service
  exit $?
fi

# shellcheck source=lib/common.sh
source "$KIT_DIR/lib/common.sh"
load_kit_config "$CONFIG_FILE"
: "${CLIENT_NAME:=}"
: "${OPS_SSH_PUBKEY:=}"
: "${MODEL_PROVIDER:=opencode-zen}"
: "${MODEL_NAME:=}"
: "${MESSAGING_PLATFORM:=none}"
: "${PHOTON_ALLOWED_USERS:=}"
: "${TELEGRAM_ALLOWED_USERS:=}"
: "${WHATSAPP_ALLOWED_USERS:=}"
: "${SIGNAL_ALLOWED_USERS:=}"
: "${SLACK_ALLOWED_USERS:=}"
: "${MAIL_ALLOWED_SENDERS:=}"
: "${MAIL_ALLOWED_RECIPIENTS:=$MAIL_ALLOWED_SENDERS}"
: "${HERMES_COMMIT:=}"
: "${SEARXNG_IMAGE:=}"
: "${ENABLE_HINDSIGHT:=false}"
: "${HINDSIGHT_LLM_PROVIDER:=}"
: "${HINDSIGHT_LLM_MODEL:=}"
: "${HINDSIGHT_LLM_BASE_URL:=}"
: "${KIT_TIER:=care}"
: "${SUPPORT_PLATFORM:=none}"
: "${SUPPORT_ALLOWED_USER:=}"
: "${OTLP_HEALTH_ENDPOINT:=}"
 : "${AGENT_CARE_REPORT_URL:=}"
 : "${AGENT_CARE_JOB_ID:=}"
 : "${AGENT_CARE_JOB_TOKEN:=}"
validate_no_allow_all_config || { echo 'Allow-all messaging flags are forbidden.' >&2; exit 1; }
if [[ $MESSAGING_PLATFORM == agentmail ]]; then
  validate_explicit_allowlist "$MAIL_ALLOWED_SENDERS" || { echo 'MAIL_ALLOWED_SENDERS must be an explicit non-wildcard list.' >&2; exit 1; }
  validate_explicit_allowlist "$MAIL_ALLOWED_RECIPIENTS" || { echo 'MAIL_ALLOWED_RECIPIENTS must be an explicit non-wildcard list.' >&2; exit 1; }
fi
persist_kit_config "$CONFIG_FILE"

# Keep every installed release available after a temporary update checkout is
# removed. Helpers and units must never point at the caller's working tree.
release_id=$(git -C "$KIT_DIR" rev-parse HEAD 2>/dev/null || sha256sum "$KIT_DIR/install.sh" | awk '{print $1}')
release_id=${release_id:0:64}
KIT_RUNTIME_DIR="/opt/hermes-kit/versions/$release_id"
if [[ $(readlink -f "$KIT_DIR") != "$KIT_RUNTIME_DIR" ]]; then
  install -d -m 0755 /opt/hermes-kit/versions
  if [[ ! -f "$KIT_RUNTIME_DIR/install.sh" ]]; then
    install -d -m 0755 "$KIT_RUNTIME_DIR"
    cp -a "$KIT_DIR/." "$KIT_RUNTIME_DIR/"
  fi
fi
export KIT_RUNTIME_DIR
current_step=initialization
on_error() {
  local status=$?
  printf 'ERROR: Hermes Client Kit failed during %s (exit %s). See %s for details.\n' "$current_step" "$status" "$LOG_FILE" >&2
  exit "$status"
}
trap on_error ERR
for step in "$KIT_DIR"/lib/[0-9][0-9]-*.sh; do
  current_step=$(basename "$step")
  log "Starting $current_step"
  # shellcheck source=/dev/null
  source "$step"
done

write_version "$KIT_DIR"
ln -sfn "$KIT_RUNTIME_DIR" /opt/hermes-kit/current
# Enrollment needs the installed helpers and units from the completed lib steps.
# A temporary HQ failure is retried independently of the installation report.
if [[ -n ${KIT_AGENT_ID:-} && -n ${KIT_ENROLL_CODE:-} && -n ${KIT_HQ_URL:-} ]] || [[ -f /var/lib/hermes-kit/report/enrolled-agent-id ]]; then
  if ! /usr/local/bin/kit-enroll-retry --install; then
    log 'Enrollment setup failed; arming the retry timer without failing installation.'
    systemctl enable --now hermes-kit-enroll.timer || true
  fi
fi
if [[ -x /usr/local/bin/kit-install-report ]]; then
  /usr/local/bin/kit-install-report --installed
fi
echo "Hermes Client Kit installation completed. Run kit-verify."
