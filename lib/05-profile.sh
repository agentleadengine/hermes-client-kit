#!/usr/bin/env bash

log 'Installing the Hermes profile distribution and client-profile baseline'
if [[ -f "$HERMES_HOME/distribution.yaml" ]]; then
  # The marker is the documented opt-out state. It must exist before the
  # distribution update so Hermes never re-seeds its bundled catalog.
  touch "$HERMES_HOME/.no-bundled-skills"
  chown "$HERMES_USER:$HERMES_USER" "$HERMES_HOME/.no-bundled-skills"
  chmod 0600 "$HERMES_HOME/.no-bundled-skills"
  run_as_hermes_root "'$HERMES_BIN' profile update '$HERMES_PROFILE_NAME' --yes"
else
  run_as_hermes_root "'$HERMES_BIN' profile install '$KIT_DIR/profile' --name '$HERMES_PROFILE_NAME' --yes"
  # A non-interactive profile install seeds bundled skills. Opt out before any
  # later profile update or skill sync, then remove the unconsented seeded set.
  touch "$HERMES_HOME/.no-bundled-skills"
  chown "$HERMES_USER:$HERMES_USER" "$HERMES_HOME/.no-bundled-skills"
  chmod 0600 "$HERMES_HOME/.no-bundled-skills"
fi
run_as_hermes_root "'$HERMES_BIN' profile use '$HERMES_PROFILE_NAME'"
install -d -m 0700 -o "$HERMES_USER" -g "$HERMES_USER" "$HERMES_HOME/plugins"
if [[ -f /etc/hermes-kit/kit-logins.installed && -d "$HERMES_HOME/plugins/kit-logins" ]]; then
  chmod 0755 "$HERMES_HOME/plugins/kit-logins"
fi
# AgentMail is the only mail capability shipped in the baseline. The official
# skill documents its constrained inbox API; no client-mailbox skill is added.
run_as_hermes_root '"$HERMES_BIN" -p client skills install official/email/agentmail --yes'
agentmail_skill=$(run_as_hermes_root "find '$HERMES_HOME/skills' -path '*/email/agentmail/SKILL.md' -print -quit")
[[ -n $agentmail_skill ]] || { echo 'Official AgentMail skill was not installed.' >&2; exit 1; }
(cd "$HERMES_HOME" && sha256sum "${agentmail_skill#$HERMES_HOME/}" > /etc/hermes-kit/official-agentmail.sha256)
chown root:root /etc/hermes-kit/official-agentmail.sha256
chmod 0644 /etc/hermes-kit/official-agentmail.sha256
# Profile installation can have seeded the bundled catalog before its marker
# existed. Remove only non-baseline, unconsented skills; consented client
# additions and the deliberately installed AgentMail skill are retained.
while IFS= read -r skill; do
  if grep -Fqx "$skill" < <(awk '{print $2}' "$KIT_DIR/profile/SKILLS.sha256") || [[ $skill == skills/email/agentmail/SKILL.md ]]; then
    continue
  fi
  integration=${skill#skills/}
  integration=${integration%/SKILL.md}
  if [[ -f /etc/hermes-kit/consents.json ]] && jq -e --arg integration "$integration" '.consents[]? | select(.integration == $integration)' /etc/hermes-kit/consents.json >/dev/null; then
    continue
  fi
  rm -rf -- "$HERMES_HOME/skills/${skill#skills/}"
done < <(cd "$HERMES_HOME" && find skills -type f -name SKILL.md -printf 'skills/%P\n' | sort)
# The SDK is the restricted transport used by the user service below. It reads
# only the inbox-scoped key; the LLM cron job never receives a terminal tool.
# Ubuntu 24.04 blocks pip into system Python (PEP 668); the mailroom gets its own venv.
run_as_hermes_root 'test -x /home/hermes/.local/share/hermes-kit/mailroom-venv/bin/python || python3 -m venv /home/hermes/.local/share/hermes-kit/mailroom-venv'
run_as_hermes_root '/home/hermes/.local/share/hermes-kit/mailroom-venv/bin/pip install --quiet --upgrade agentmail'
install -d -m 0700 -o "$HERMES_USER" -g "$HERMES_USER" "$HERMES_HOME"
touch "$HERMES_HOME/.env"
chown "$HERMES_USER:$HERMES_USER" "$HERMES_HOME/.env"
chmod 0600 "$HERMES_HOME/.env"
set_env_value SEARXNG_URL http://127.0.0.1:8080 "$HERMES_HOME/.env"
set_env_value OBSIDIAN_VAULT_PATH /home/hermes/vault "$HERMES_HOME/.env"
set_env_value HERMES_WRITE_SAFE_ROOT /home/hermes/vault "$HERMES_HOME/.env"
case $MESSAGING_PLATFORM in
  none) messaging_allowlist_key= ; messaging_allowlist_value= ;;
  photon) messaging_allowlist_key=PHOTON_ALLOWED_USERS; messaging_allowlist_value=$PHOTON_ALLOWED_USERS ;;
  telegram) messaging_allowlist_key=TELEGRAM_ALLOWED_USERS; messaging_allowlist_value=$TELEGRAM_ALLOWED_USERS ;;
  whatsapp) messaging_allowlist_key=WHATSAPP_ALLOWED_USERS; messaging_allowlist_value=$WHATSAPP_ALLOWED_USERS ;;
  signal) messaging_allowlist_key=SIGNAL_ALLOWED_USERS; messaging_allowlist_value=$SIGNAL_ALLOWED_USERS ;;
  slack) messaging_allowlist_key=SLACK_ALLOWED_USERS; messaging_allowlist_value=$SLACK_ALLOWED_USERS ;;
  agentmail) messaging_allowlist_key= ; messaging_allowlist_value= ;;
  *) echo 'MESSAGING_PLATFORM must be photon, telegram, whatsapp, signal, slack, agentmail, or none.' >&2; exit 1 ;;
esac
if [[ -n $messaging_allowlist_key ]]; then
  validate_explicit_allowlist "$messaging_allowlist_value" || {
    echo "$messaging_allowlist_key must be a non-empty explicit allowlist." >&2
    exit 1
  }
fi
if [[ $MESSAGING_PLATFORM == agentmail ]]; then
  validate_explicit_allowlist "$MAIL_ALLOWED_SENDERS" || { echo 'MAIL_ALLOWED_SENDERS must be an explicit allowlist.' >&2; exit 1; }
  validate_explicit_allowlist "$MAIL_ALLOWED_RECIPIENTS" || { echo 'MAIL_ALLOWED_RECIPIENTS must be an explicit allowlist.' >&2; exit 1; }
fi
if [[ -n $messaging_allowlist_key ]] && ! grep -Eq "^${messaging_allowlist_key}=" "$HERMES_HOME/.env"; then
  set_env_value "$messaging_allowlist_key" "$messaging_allowlist_value" "$HERMES_HOME/.env"
fi
install -d -m 0700 -o "$HERMES_USER" -g "$HERMES_USER" /home/hermes/vault
