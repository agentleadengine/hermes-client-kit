#!/usr/bin/env bash

HERMES_USER=hermes
# shellcheck source=lib/hermes-path.conf
source "$(dirname -- "${BASH_SOURCE[0]}")/hermes-path.conf"
export HERMES_BIN
HERMES_ROOT=/home/hermes/.hermes
HERMES_PROFILE_NAME=client
HERMES_HOME="$HERMES_ROOT/profiles/$HERMES_PROFILE_NAME"
export HERMES_PROFILE_NAME

log() { printf '[hermes-kit] %s\n' "$*"; }

load_kit_config() {
  # Cloud-init supplies this non-secret file. Do not source it: unknown values
  # are data, not shell code, and AGENT_CARE_* fields are intentionally forward
  # compatible with the intake application.
  local config_file=$1 line key value
  [[ -r $config_file ]] || { echo "Missing kit configuration: $config_file" >&2; return 1; }
  while IFS= read -r line || [[ -n $line ]]; do
    [[ -z ${line//[[:space:]]/} || $line =~ ^[[:space:]]*# ]] && continue
    [[ $line =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]] || { echo 'kit.conf contains an invalid assignment.' >&2; return 1; }
    key=${BASH_REMATCH[1]}; value=${BASH_REMATCH[2]}
    if [[ $value == \"*\" && ${#value} -ge 2 ]]; then value=${value:1:${#value}-2}; elif [[ $value == \'*\' && ${#value} -ge 2 ]]; then value=${value:1:${#value}-2}; fi
    [[ $value != *$'\n'* && $value != *$'\r'* ]] || return 1
    case $key in
      CLIENT_NAME|OPS_SSH_PUBKEY|MODEL_PROVIDER|MODEL_NAME|MESSAGING_PLATFORM|PHOTON_ALLOWED_USERS|TELEGRAM_ALLOWED_USERS|WHATSAPP_ALLOWED_USERS|SIGNAL_ALLOWED_USERS|SLACK_ALLOWED_USERS|MAIL_ALLOWED_SENDERS|MAIL_ALLOWED_RECIPIENTS|MAILROOM_NOTIFY_PLATFORM|HERMES_COMMIT|SEARXNG_IMAGE|ENABLE_HINDSIGHT|HINDSIGHT_LLM_PROVIDER|HINDSIGHT_LLM_MODEL|HINDSIGHT_LLM_BASE_URL|KIT_TIER|KIT_AGENT_ID|KIT_ENROLL_CODE|KIT_HQ_URL|KIT_CHANNEL|SUPPORT_PLATFORM|SUPPORT_ALLOWED_USER|OTLP_HEALTH_ENDPOINT|KIT_GIT_REF|KIT_UPDATE_REPO|KIT_RELEASE_ALLOWED_SIGNER|KIT_RELEASE_MANIFEST_URL|KIT_RELEASE_SIGNER_ID|AGENT_CARE_REPORT_URL|AGENT_CARE_JOB_ID|AGENT_CARE_JOB_TOKEN|AGENT_CARE_REQUESTED_PLATFORM)
        printf -v "$key" '%s' "$value"
        ;;
      *) ;;
    esac
  done < "$config_file"
}

forbid_allow_all_key() {
  local key=$1
  [[ $key != GATEWAY_ALLOW_ALL_USERS && $key != *_ALLOW_ALL_USERS ]]
}

validate_explicit_allowlist() {
  local value=$1 entry compact
  [[ -n ${value//[[:space:]]/} && $value != *'*'* ]] || return 1
  IFS=',' read -r -a entries <<<"$value"
  for entry in "${entries[@]}"; do
    compact=${entry//[[:space:]]/}
    [[ -n $compact && $compact != *'*'* ]] || return 1
  done
}

validate_no_allow_all_values() {
  # Read assignments from a dotenv file or process environment.  Values such as
  # " yes " are enabled too, so normalize whitespace as well as case.
  local key value normalized
  while IFS=$'\t' read -r key value; do
    [[ $key == GATEWAY_ALLOW_ALL_USERS || $key == *_ALLOW_ALL_USERS || $key == *_ALLOW_ALL ]] || continue
    normalized=$(printf '%s' "$value" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
    [[ $normalized != true && $normalized != 1 && $normalized != yes && $normalized != on ]] || return 1
  done
}

validate_no_allow_all_config() {
  local key value
  while IFS= read -r key; do
    value=${!key-}
    printf '%s\t%s\n' "$key" "$value"
  done < <(compgen -A variable) | validate_no_allow_all_values
}

installed_hermes_revision() {
  # The official installer places a launcher inside its checked-out source
  # tree. Walk up from that real launcher and ask git for the checked-out
  # revision. A requested-SHA marker is deliberately never consulted here.
  local hermes_bin candidate
  # Documented source-install location first: the ~/.local/bin launcher is a wrapper script, not a link into the checkout.
  if [[ -d $HERMES_ROOT/hermes-agent/.git ]]; then
    run_as_hermes_root "git -C '$HERMES_ROOT/hermes-agent' rev-parse HEAD" 2>/dev/null
    return
  fi
  hermes_bin=$HERMES_BIN
  candidate=$(dirname "$(readlink -f "$hermes_bin")")
  while [[ $candidate != / && $candidate != . ]]; do
    if [[ -d $candidate/.git ]]; then
      run_as_hermes "git -C '$candidate' rev-parse HEAD" 2>/dev/null
      return
    fi
    candidate=$(dirname "$candidate")
  done
  return 1
}

run_as_hermes() {
  local hermes_uid
  hermes_uid=$(id -u "$HERMES_USER")
  runuser -u "$HERMES_USER" -- env \
    HOME="/home/$HERMES_USER" \
    HERMES_HOME="$HERMES_HOME" \
    XDG_RUNTIME_DIR="/run/user/$hermes_uid" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$hermes_uid/bus" \
    PATH="/home/$HERMES_USER/.local/bin:/usr/local/bin:/usr/bin:/bin" \
    bash -lc "$1"
}

runtime_tree_hash() (
  cd "$1" || return
  find install.sh kit.conf.example bin lib managed profile plugins support-profile templates \
    -name __pycache__ -prune -o -type f ! -name '*.pyc' -print0 |
    sort -z | xargs -0 sha256sum | sha256sum | cut -d ' ' -f 1
)

run_as_hermes_root() {
  local hermes_uid
  hermes_uid=$(id -u "$HERMES_USER")
  runuser -u "$HERMES_USER" -- env \
    HOME="/home/$HERMES_USER" \
    HERMES_HOME="$HERMES_ROOT" \
    XDG_RUNTIME_DIR="/run/user/$hermes_uid" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$hermes_uid/bus" \
    PATH="/home/$HERMES_USER/.local/bin:/usr/local/bin:/usr/bin:/bin" \
    bash -lc "$1"
}

ensure_line() {
  local line=$1 file=$2
  touch "$file"
  grep -qxF "$line" "$file" || printf '%s\n' "$line" >> "$file"
}

set_env_value() {
  local key=$1 value=$2 file=$3 temp escaped_value hermes_group literal_guard
  [[ $key =~ ^[A-Z][A-Z0-9_]*$ ]] || { echo "Invalid environment key: $key" >&2; return 1; }
  [[ $value != *$'\n'* && $value != *$'\r'* ]] || { echo 'Environment values must be one line' >&2; return 1; }
  hermes_group=$(id -gn "$HERMES_USER")
  install -d -m 0700 -o "$HERMES_USER" -g "$hermes_group" "$(dirname "$file")"
  touch "$file"
  chown "$HERMES_USER:$hermes_group" "$file"
  chmod 0600 "$file"
  # Hermes uses python-dotenv, which expands ${NAME} even inside quoted values.
  # Give each literal dollar a unique, intentionally-unset default expansion so
  # the parser produces the original dollar without retaining a backslash.
  escaped_value=${value//\\/\\\\}
  escaped_value=${escaped_value//\"/\\\"}
  if [[ $escaped_value == *'$'* ]]; then
    literal_guard="HERMES_KIT_LITERAL_$(od -An -N16 -tx1 /dev/urandom | tr -d ' \\n')"
    escaped_value=${escaped_value//\$/\$\{${literal_guard}:-\$\}}
  fi
  temp=$(mktemp "$file.XXXXXX")
  { grep -Ev "^${key}=" "$file" || true; printf '%s="%s"\n' "$key" "$escaped_value"; } > "$temp"
  chown "$HERMES_USER:$hermes_group" "$temp"
  chmod 0600 "$temp"
  mv "$temp" "$file"
}

persist_kit_config() {
  local source=$1 destination=${2:-/etc/hermes-kit/kit.conf}
  [[ -f $source ]] || { echo "Missing kit configuration: $source" >&2; return 1; }
  install -d -m 0700 "$(dirname "$destination")"
  if [[ ! -e $destination || ! $source -ef $destination ]]; then
    install -m 0600 "$source" "$destination"
  else
    chmod 0600 "$destination"
  fi
}

write_version() {
  local kit_dir=$1 version hermes_version
  version=$(git -C "$kit_dir" describe --tags --always --dirty 2>/dev/null || printf 'unversioned')
  hermes_version=$(run_as_hermes '"$HERMES_BIN" --version' 2>/dev/null | head -n 1)
  [[ -n $hermes_version ]] || { echo 'Could not determine installed Hermes version.' >&2; return 1; }
  install -d -m 0755 /etc/hermes-kit
  printf 'kit=%s\nhermes=%s\ninstalled_at=%s\n' "$version" "$hermes_version" "$(date -u +%FT%TZ)" > /etc/hermes-kit/version
  chmod 0644 /etc/hermes-kit/version
}
