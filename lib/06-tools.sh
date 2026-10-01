#!/usr/bin/env bash

log 'Installing private search and local sync services'
export DEBIAN_FRONTEND=noninteractive
apt-get -y --no-install-recommends install syncthing
[[ ${SEARXNG_IMAGE:-} =~ ^docker\.io/searxng/searxng@sha256:[0-9a-fA-F]{64}$ ]] || { echo 'SEARXNG_IMAGE must be pinned by a reviewed sha256 digest.' >&2; exit 1; }

install -d -m 0755 -o "$HERMES_USER" -g "$HERMES_USER" /home/hermes/.config/systemd/user
install -d -m 0700 -o "$HERMES_USER" -g "$HERMES_USER" "$HERMES_HOME/searxng"
# The unit intentionally refuses registry pulls.  Prime the hermes user's
# rootless image store first, including on a host whose cache starts empty.
run_as_hermes "/usr/bin/docker pull '$SEARXNG_IMAGE'"
searx_settings="$HERMES_HOME/searxng/settings.yml"
if [[ ! -f $searx_settings ]]; then
  searx_secret=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  install -m 0644 -o "$HERMES_USER" -g "$HERMES_USER" /dev/stdin "$searx_settings" <<EOF
use_default_settings: true
server:
  secret_key: "$searx_secret"
search:
  formats:
    - html
    - json
EOF
else
  chmod 0644 "$searx_settings"
  chown "$HERMES_USER:$HERMES_USER" "$searx_settings"
  if ! grep -Eq '^  secret_key:' "$searx_settings"; then
    searx_secret=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
    if grep -q '^server:' "$searx_settings"; then
      sed -i "/^server:/a\\  secret_key: \"$searx_secret\"" "$searx_settings"
    else
      printf '\nserver:\n  secret_key: "%s"\n' "$searx_secret" >> "$searx_settings"
    fi
  fi
fi
install -m 0644 -o "$HERMES_USER" -g "$HERMES_USER" /dev/stdin /home/hermes/.config/systemd/user/searxng.service <<EOF
[Unit]
Description=Private SearXNG search service
After=docker.service

[Service]
Environment=DOCKER_HOST=unix:///run/user/%U/docker.sock
ExecStartPre=-/usr/bin/docker rm -f searxng
ExecStart=/usr/bin/docker run --name searxng --pull=never --restart=unless-stopped -p 127.0.0.1:8080:8080 -v /home/hermes/.hermes/profiles/client/searxng/settings.yml:/etc/searxng/settings.yml:ro ${SEARXNG_IMAGE}
ExecStop=/usr/bin/docker stop searxng
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
run_as_hermes 'systemctl --user daemon-reload; systemctl --user enable --now searxng.service'
curl --fail --silent --show-error --max-time 2 --retry 6 --retry-all-errors --retry-delay 5 --retry-max-time 60 'http://127.0.0.1:8080/search?q=hermes&format=json' >/dev/null
systemctl enable --now syncthing@hermes.service

syncthing_config=/home/hermes/.local/state/syncthing/config.xml
for _ in $(seq 1 15); do
  [[ -f $syncthing_config ]] && break
  sleep 1
done
[[ -f $syncthing_config ]] || { echo 'Syncthing did not create its configuration.' >&2; exit 1; }
systemctl stop syncthing@hermes.service
sed -i -E '/<gui /,/<\/gui>/ s#<address>[^<]*</address>#<address>127.0.0.1:8384</address>#; s#<listenAddress>[^<]*</listenAddress>#<listenAddress>tcp://127.0.0.1:22000</listenAddress>#g; s#<globalAnnounceEnabled>[^<]*</globalAnnounceEnabled>#<globalAnnounceEnabled>false</globalAnnounceEnabled>#; s#<localAnnounceEnabled>[^<]*</localAnnounceEnabled>#<localAnnounceEnabled>false</localAnnounceEnabled>#; s#<relaysEnabled>[^<]*</relaysEnabled>#<relaysEnabled>false</relaysEnabled>#' "$syncthing_config"
if ! grep -q '<listenAddress>tcp://127.0.0.1:22000</listenAddress>' "$syncthing_config"; then
  sed -i '/<options>/a\    <listenAddress>tcp://127.0.0.1:22000</listenAddress>' "$syncthing_config"
fi
grep -q '<address>127.0.0.1:8384</address>' "$syncthing_config"
grep -q '<globalAnnounceEnabled>false</globalAnnounceEnabled>' "$syncthing_config"
grep -q '<relaysEnabled>false</relaysEnabled>' "$syncthing_config" || sed -i '/<options>/a\    <relaysEnabled>false</relaysEnabled>' "$syncthing_config"
grep -q '<localAnnounceEnabled>false</localAnnounceEnabled>' "$syncthing_config"
chown "$HERMES_USER:$HERMES_USER" "$syncthing_config"
systemctl start syncthing@hermes.service

if [[ "$ENABLE_HINDSIGHT" == true ]]; then
  [[ -n $HINDSIGHT_LLM_PROVIDER && -n $HINDSIGHT_LLM_MODEL && -n $HINDSIGHT_LLM_BASE_URL ]] || {
    echo 'ENABLE_HINDSIGHT=true requires HINDSIGHT_LLM_PROVIDER, HINDSIGHT_LLM_MODEL, and HINDSIGHT_LLM_BASE_URL.' >&2
    exit 1
  }
  run_as_hermes 'hermes plugins install hindsight'
  install -d -m 0700 -o "$HERMES_USER" -g "$HERMES_USER" "$HERMES_HOME/hindsight"
  jq -n \
    --arg provider "$HINDSIGHT_LLM_PROVIDER" \
    --arg model "$HINDSIGHT_LLM_MODEL" \
    --arg base_url "$HINDSIGHT_LLM_BASE_URL" \
    '{mode: "local_embedded", llm_provider: $provider, llm_model: $model, llm_base_url: $base_url}' \
    > "$HERMES_HOME/hindsight/config.json"
  chown "$HERMES_USER:$HERMES_USER" "$HERMES_HOME/hindsight/config.json"
  chmod 0600 "$HERMES_HOME/hindsight/config.json"
  run_as_hermes 'hermes config set memory.provider hindsight'
fi
