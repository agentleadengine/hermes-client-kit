#!/usr/bin/env bash
# shellcheck disable=SC2034

# Uses kit-verify's pass, warn, and fail callbacks. KIT_SETUP_TEST_ROOT is only
# used by the isolated lifecycle test; production reads the actual server.
verify_setup_window() {
  local root=${KIT_SETUP_TEST_ROOT:-} state expiry=0 traces=false valid=true policy
  setup_open=false
  state=$root/var/lib/hermes-kit/setup-window
  if id -u hermes-setup >/dev/null 2>&1 || [[ -e $root/etc/ssh/kit-setup.keys || -e $root/etc/sudoers.d/92-hermes-kit-setup || -e $root/etc/ssh/sshd_config.d/12-hermes-kit-setup.conf ]] || systemctl is-active --quiet hermes-kit-setup-expiry.timer; then traces=true; fi
  if [[ -f $state/expires-at && $(<"$state/expires-at") =~ ^[0-9]+$ ]]; then expiry=$(<"$state/expires-at"); fi
  if [[ -f $state/closed-at ]]; then
    if [[ $traces == true ]]; then fail 'SETUP access remains after close'; else pass 'SETUP access removed after close'; fi
  elif (( expiry > 0 && expiry <= $(date -u +%s) )); then
    if [[ $traces == true ]]; then fail 'SETUP access remains past expiry'; else pass 'SETUP access removed after expiry'; fi
  elif (( expiry > 0 )); then
    id -u hermes-setup >/dev/null 2>&1 || valid=false
    [[ -s $root/etc/ssh/kit-setup.keys && -f $root/etc/sudoers.d/92-hermes-kit-setup && -f $root/etc/ssh/sshd_config.d/12-hermes-kit-setup.conf && -f $root/etc/tlog/tlog-rec-session.conf ]] || valid=false
    systemctl is-active --quiet hermes-kit-setup-expiry.timer || valid=false
    [[ $(getent passwd hermes-setup | cut -d: -f7) == /usr/bin/tlog-rec-session ]] || valid=false
    policy=$(sshd -T -C user=hermes-setup,host=localhost,addr=127.0.0.1 2>/dev/null || true)
    grep -Fqx "authorizedkeysfile $root/etc/ssh/kit-setup.keys" <<<"$policy" || valid=false
    grep -Fqx 'allowtcpforwarding no' <<<"$policy" || valid=false
    grep -Fq "expiry-time=\"$(date -u -d "@$expiry" +%Y%m%d%H%M%SZ)\"" "$root/etc/ssh/kit-setup.keys" 2>/dev/null || valid=false
    if [[ $valid == true ]]; then setup_open=true; warn "SETUP access open until $(date -u -d "@$expiry" +%FT%TZ)"; else fail 'SETUP window is incomplete'; fi
  elif [[ $traces == true ]]; then
    fail 'SETUP access exists without an expiry'
  else
    pass 'SETUP access absent'
  fi
}
