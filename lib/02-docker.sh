#!/usr/bin/env bash

log 'Installing rootless Docker for hermes'
export DEBIAN_FRONTEND=noninteractive
apt-get -y --no-install-recommends install uidmap dbus-user-session slirp4netns fuse-overlayfs

docker_packages=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras)
docker_ce_ready=true
for docker_package in "${docker_packages[@]}"; do
  if [[ $(dpkg-query -W -f='${db:Status-Status}' "$docker_package" 2>/dev/null || true) != installed ]]; then
    docker_ce_ready=false
    break
  fi
done

if [[ $docker_ce_ready != true ]]; then
  log "Installing Docker CE and rootless extras from Docker's signed Ubuntu repository"
  install -d -m 0755 /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    curl --fail --silent --show-error --location --retry 6 --retry-all-errors --retry-delay 5 --retry-max-time 300 https://download.docker.com/linux/ubuntu/gpg | gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg
  fi
  chmod 0644 /etc/apt/keyrings/docker.gpg
  # shellcheck disable=SC1091
  . /etc/os-release
  printf '%s\n' "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get -y remove docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc || true
  apt-get -y --no-install-recommends install "${docker_packages[@]}"
fi

systemctl disable --now docker.service docker.socket >/dev/null 2>&1 || true

subid_start=$(awk -F: '
  $1 != "hermes" && $2 ~ /^[0-9]+$/ && $3 ~ /^[0-9]+$/ {
    end = $2 + $3
    if (end > max) max = end
  }
  END {
    if (max < 100000) max = 100000
    printf "%d\n", int((max + 65535) / 65536) * 65536
  }
' /etc/subuid /etc/subgid)
for subid_file in /etc/subuid /etc/subgid; do
  subid_temp=$(mktemp "${subid_file}.XXXXXX")
  awk -F: '$1 != "hermes" { print }' "$subid_file" > "$subid_temp"
  printf '%s:%s:%s\n' "$HERMES_USER" "$subid_start" 65536 >> "$subid_temp"
  install -m 0644 "$subid_temp" "$subid_file"
  rm -f "$subid_temp"
done
loginctl enable-linger "$HERMES_USER"
systemctl start "user@$(id -u "$HERMES_USER")"
run_as_hermes 'if ! systemctl --user is-active --quiet docker; then dockerd-rootless-setuptool.sh install; systemctl --user enable --now docker.service; fi'

install -d -m 0755 /etc/systemd/system/user@.service.d
install -m 0644 /dev/stdin /etc/systemd/system/user@.service.d/hermes-kit.conf <<'EOF'
[Service]
Environment=DOCKER_HOST=unix:///run/user/%U/docker.sock
EOF
systemctl daemon-reload
systemctl restart "user@$(id -u "$HERMES_USER")"
