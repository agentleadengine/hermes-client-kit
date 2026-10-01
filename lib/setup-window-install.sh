#!/usr/bin/env bash

# Sourced after the setup helper has been linked into /usr/local/bin.
setup_window_bin=${KIT_SETUP_WINDOW_BIN:-/usr/local/bin/kit-setup-window}
setup_window_state=${KIT_SETUP_TEST_ROOT:-}/var/lib/hermes-kit/setup-window
if [[ -n ${OPS_SSH_PUBKEY:-} && ( ${KIT_SETUP_NEW_INSTALL:-0} == 1 || -e $setup_window_state/started-at ) ]]; then
  setup_key=$(mktemp)
  printf '%s\n' "$OPS_SSH_PUBKEY" > "$setup_key"
  chmod 0600 "$setup_key"
  if ! "$setup_window_bin" open --public-key "$setup_key"; then
    rm -f "$setup_key"
    exit 1
  fi
  rm -f "$setup_key"
elif [[ -z ${OPS_SSH_PUBKEY:-} && -f $setup_window_state/expires-at && ! -f $setup_window_state/closed-at ]]; then
  "$setup_window_bin" close
fi
