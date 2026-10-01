"""Client-owned domain allowlist and isolated local Chromium profiles."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from logins_policy import denied

ETC = Path("/etc/hermes-kit")
PROFILES = Path("/var/lib/hermes-kit/logins/profiles")
DOMAINS = Path("/var/lib/hermes-kit/logins-domains.json")
DOMAIN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,251}[a-z0-9]$")


def clean_domain(value):
    value = value.lower().rstrip(".")
    if not DOMAIN.fullmatch(value) or ".." in value or denied(value):
        raise ValueError("Domain is outside the Logins policy")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["allow", "remove", "open"])
    parser.add_argument("domain")
    args = parser.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run as root with the client present")
    name = clean_domain(args.domain)
    domains = json.loads(DOMAINS.read_text()) if DOMAINS.exists() else []
    if args.action == "allow":
        if name not in domains:
            domains.append(name)
    elif args.action == "remove":
        domains = [item for item in domains if item != name]
        active = DOMAINS.parent / "logins-active-domain"
        if active.exists() and active.read_text().strip() == name:
            subprocess.run(["systemctl", "stop", "hermes-kit-logins-browser.service"], check=False)
            active.unlink()
    else:
        if name not in domains:
            raise ValueError("Site is not allowlisted")
        # One active Chromium instance at a time. Each domain gets a distinct
        # logins-owned user-data-dir; CDP listens on loopback only.
        subprocess.run(["systemctl", "stop", "hermes-kit-logins-browser.service"], check=False)
        active = DOMAINS.parent / "logins-active-domain"
        active.write_text(name + "\n")
        active.chmod(0o644)
        profile = PROFILES / name
        profile.mkdir(parents=True, exist_ok=True)
        subprocess.run(["chown", "-R", "logins:logins", str(profile)], check=True)
        env = Path("/etc/hermes-kit/logins-browser.env")
        env.write_text(f"LOGIN_PROFILE={profile}\n")
        env.chmod(0o600)
        subprocess.run(["systemctl", "start", "hermes-kit-logins-proxy.service"], check=True)
        subprocess.run(["systemctl", "start", "hermes-kit-logins-browser.service"], check=True)
        return
    DOMAINS.parent.mkdir(parents=True, exist_ok=True)
    DOMAINS.write_text(json.dumps(sorted(domains)) + "\n")
    DOMAINS.chmod(0o644)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
