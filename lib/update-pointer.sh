#!/usr/bin/env bash

verify_stable_pointer() {
  local pointer_file=$1 signature_file=$2 allowed_file=$3 signer_id=$4 state_dir=$5
  local pointer_sequence previous signed_at expires_at signed_epoch expires_epoch now tmp
  ssh-keygen -Y verify -f "$allowed_file" -I "$signer_id" -n hermes-kit-pointer -s "$signature_file" < "$pointer_file" >/dev/null || return 1
  jq -e 'type == "object" and (keys == ["expires_at","sequence","signed_at","tag","v"]) and .v == 1 and (.sequence | type == "number" and floor == . and . >= 1) and (.tag | type == "string" and test("^v[0-9]+\\.[0-9]+\\.[0-9]+$")) and (.signed_at | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")) and (.expires_at | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"))' "$pointer_file" >/dev/null || return 1
  pointer_sequence=$(jq -r '.sequence' "$pointer_file")
  signed_at=$(jq -r '.signed_at' "$pointer_file")
  expires_at=$(jq -r '.expires_at' "$pointer_file")
  if date -u -d "$signed_at" +%s >/dev/null 2>&1; then
    signed_epoch=$(date -u -d "$signed_at" +%s) || return 1
    expires_epoch=$(date -u -d "$expires_at" +%s) || return 1
  else
    signed_epoch=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$signed_at" +%s) || return 1
    expires_epoch=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$expires_at" +%s) || return 1
  fi
  now=$(date -u +%s)
  (( signed_epoch <= now && expires_epoch > now )) || return 1
  previous=$(cat "$state_dir/stable-pointer-sequence" 2>/dev/null || printf 0)
  [[ $previous =~ ^[0-9]+$ ]] || return 1
  (( pointer_sequence >= previous )) || return 1
  tmp=$(mktemp "$state_dir/.pointer.XXXXXX")
  printf '%s\n' "$pointer_sequence" > "$tmp"
  chmod 0600 "$tmp"
  mv "$tmp" "$state_dir/stable-pointer-sequence"
  printf '%s\n' "$pointer_sequence"
}

pointer_allows_manifest() {
  local channel=$1 manifest_sequence=$2 pointer_sequence=${3:-0}
  [[ $manifest_sequence =~ ^[1-9][0-9]*$ ]] || return 1
  if [[ $channel == canary ]]; then return 0; fi
  [[ $channel == stable && $pointer_sequence =~ ^[1-9][0-9]*$ ]] && (( manifest_sequence <= pointer_sequence ))
}
