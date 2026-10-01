#!/usr/bin/env bash

report_key_file=${KIT_REPORT_KEY_FILE:-/etc/hermes-kit/report/box_ed25519.pem}
# shellcheck disable=SC2034 # consumed by sourced callers
report_state_dir=${KIT_REPORT_STATE_DIR:-/var/lib/hermes-kit/report}

report_pub_b64() {
  openssl pkey -in "$report_key_file" -pubout -outform DER 2>/dev/null | tail -c 32 | base64 | tr -d '\n'
}

report_words() {
  local pub_b64=$1 words_file=$2
  local byte0 byte1 byte2 byte3 hash_bytes
  [[ $(wc -l < "$words_file" | tr -d ' ') == 256 ]] || return 1
  [[ $(printf '%s' "$pub_b64" | base64 -d | wc -c | tr -d ' ') == 32 ]] || return 1
  hash_bytes=$(printf '%s' "$pub_b64" | base64 -d | openssl dgst -sha256 -binary | od -An -tu1 -N4)
  read -r byte0 byte1 byte2 byte3 <<< "$hash_bytes"
  printf '%s %s %s %s\n' \
    "$(sed -n "$((byte0 + 1))p" "$words_file")" \
    "$(sed -n "$((byte1 + 1))p" "$words_file")" \
    "$(sed -n "$((byte2 + 1))p" "$words_file")" \
    "$(sed -n "$((byte3 + 1))p" "$words_file")"
}

report_sign_b64() {
  local input=$1
  openssl pkeyutl -sign -rawin -inkey "$report_key_file" -in "$input" | base64 | tr -d '\n'
}

report_valid_timestamp() {
  report_epoch "$1" >/dev/null
}

report_epoch() {
  [[ $1 =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || return 1
  if date -u -d "$1" +%s 2>/dev/null; then return 0; fi
  date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$1" +%s 2>/dev/null
}
