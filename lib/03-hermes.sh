#!/usr/bin/env bash

log 'Installing Hermes as the hermes service user'
[[ ${HERMES_COMMIT:-} =~ ^[0-9a-fA-F]{40}$ ]] || { echo 'HERMES_COMMIT must be a reviewed full 40-character Git commit SHA.' >&2; exit 1; }
installed_revision=$(installed_hermes_revision 2>/dev/null || true)
if [[ $installed_revision != "$HERMES_COMMIT" ]]; then
  installer_dir=$(mktemp -d /root/hermes-installer.XXXXXX)
  installer="$installer_dir/install.sh"
  # Fetch the installer from the same pinned commit it installs; the latest installer can require modules an older release lacks.
  curl --fail --silent --show-error --location --retry 6 --retry-all-errors --retry-delay 5 --retry-max-time 300 "https://raw.githubusercontent.com/NousResearch/hermes-agent/$HERMES_COMMIT/scripts/install.sh" --output "$installer"
  sha256sum "$installer" | tee -a /var/log/hermes-kit.log
  installer_for_hermes=/home/hermes/.cache/hermes-kit-installer.sh
  install -d -m 0700 -o "$HERMES_USER" -g "$HERMES_USER" /home/hermes/.cache
  install -m 0644 -o "$HERMES_USER" -g "$HERMES_USER" "$installer" "$installer_for_hermes"
  installer_args="--non-interactive --commit $HERMES_COMMIT"
  run_as_hermes_root "bash '$installer_for_hermes' $installer_args"
  rm -f "$installer_for_hermes"
  rm -f "$installer"
  rmdir "$installer_dir"
fi
installed_revision=$(installed_hermes_revision) || { echo 'Could not determine the actual installed Hermes Git revision.' >&2; exit 1; }
[[ $installed_revision == "$HERMES_COMMIT" ]] || { echo "Installed Hermes revision $installed_revision does not match reviewed commit $HERMES_COMMIT." >&2; exit 1; }
run_as_hermes_root '"$HERMES_BIN" --version'
install -d -m 0755 /etc/hermes-kit
printf '%s\n' "$installed_revision" > /etc/hermes-kit/hermes-commit
chmod 0644 /etc/hermes-kit/hermes-commit
