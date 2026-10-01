"""Client consent and Hermes toolset policy for optional capabilities."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from hermes_runtime import HERMES_BIN

ETC = Path(os.environ.get("KIT_POWERUP_ETC", "/etc/hermes-kit"))
HOME = Path(os.environ.get("KIT_POWERUP_HOME", "/home/hermes/.hermes/profiles/client"))
KIT = Path(__file__).resolve().parent.parent
LEDGER = ETC / "consents.json"
POWERUPS = {"base", "builder", "website", "schedules", "logins"}
BASE_DISABLED = ["terminal", "code_execution", "browser", "computer_use", "delegation", "kanban", "cronjob", "image_gen", "tts", "homeassistant", "messaging"]
BASE_TOOLS = ["clarify", "file", "memory", "search", "skills", "todo", "vision", "web"]
BLOCKED = ["paypal.com", "*.paypal.com", "stripe.com", "*.stripe.com", "chase.com", "*.chase.com", "bankofamerica.com", "*.bankofamerica.com", "wellsfargo.com", "*.wellsfargo.com", "gmail.com", "*.gmail.com", "outlook.com", "*.outlook.com", "mail.google.com", "adp.com", "*.adp.com", "gusto.com", "*.gusto.com"]


def run(args: list[str]):
    subprocess.run(args, check=True)


def config_set(key: str, value):
    if os.environ.get("KIT_POWERUP_TEST_MODE") == "1":
        path = ETC / "test-config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        cfg = json.loads(path.read_text()) if path.exists() else {}
        cfg[key] = value
        path.write_text(json.dumps(cfg))
        return
    encoded = json.dumps(value) if not isinstance(value, str) else value
    run(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client", "config", "set", key, encoded])


def enabled_plugins():
    if os.environ.get("KIT_POWERUP_TEST_MODE") == "1":
        path = ETC / "test-config.json"
        return json.loads(path.read_text()).get("plugins.enabled", []) if path.exists() else []
    result = subprocess.run(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client", "config", "get", "plugins.enabled", "--json"], capture_output=True, text=True, check=True)
    value = json.loads(result.stdout)
    return value if isinstance(value, list) else []


def consents():
    return json.loads(LEDGER.read_text()) if LEDGER.exists() else {"consents": []}


def save(data):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    temp = LEDGER.with_suffix(".tmp")
    temp.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    temp.chmod(0o600)
    temp.replace(LEDGER)


def on(name: str, waiver: str | None, client: str):
    if name == "logins" and (not waiver or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", waiver)):
        raise ValueError("Logins requires a signed waiver id from the client")
    if not re.fullmatch(r"[A-Za-z0-9 .'-]{1,80}", client):
        raise ValueError("Client name is required")
    data = consents()
    if name in {"logins", "schedules"} and ({x.get("integration") for x in data["consents"]} & ({"schedules"} if name == "logins" else {"logins"})):
        raise ValueError("Logins and Schedules cannot be enabled together on this profile")
    if name in [x.get("integration") for x in data["consents"]]:
        return
    # Fail before provisioning anything when the service user's launcher is broken.
    enabled_plugins()
    if name == "schedules":
        validate_cron_jobs()
    entry = {"integration": name, "client_name": client, "date": datetime.now(timezone.utc).date().isoformat(),
             "scopes": [name], "risk_level": "RED" if name == "logins" else "YELLOW",
             "warnings_shown": "Client controls this power-up; actions still require approval", "confirmation": "client-on", "waiver_id": waiver or "none"}
    data["consents"].append(entry)
    # Configure first, record the consent only after all guardrails are present.
    config_path = ETC / "test-config.json" if os.environ.get("KIT_POWERUP_TEST_MODE") == "1" else HOME / "config.yaml"
    old_config = config_path.read_bytes() if config_path.exists() else None
    try:
        apply_policy({x.get("integration") for x in data["consents"]})
        if name == "builder":
            run([str(KIT / "bin" / "kit-tools-setup")])
        if name == "logins":
            install_logins()
    except Exception:
        if old_config is None:
            config_path.unlink(missing_ok=True)
        else:
            config_path.write_bytes(old_config)
        raise
    save(data)
    if os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        run(["systemctl", "restart", "hermes-gateway.service"])
    if name == "builder" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        run(["systemctl", "enable", "--now", "hermes-kit-tools-backup.timer"])
    if name == "logins":
        plugin_consent = dict(entry, integration="plugin:kit-logins")
        data["consents"].append(plugin_consent)
        save(data)


def off(name: str):
    if name == "base":
        raise ValueError("Base is always on")
    data = consents()
    if name == "schedules" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        schedule_ids = ETC / "schedules-ids.json"
        for job_id in json.loads(schedule_ids.read_text()) if schedule_ids.exists() else []:
            run(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client", "cron", "pause", job_id])
    data["consents"] = [x for x in data["consents"] if x.get("integration") not in {name, "plugin:kit-logins" if name == "logins" else ""}]
    apply_policy({x.get("integration") for x in data["consents"]})
    save(data)
    if os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        run(["systemctl", "restart", "hermes-gateway.service"])
    if name == "builder" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        subprocess.run(["systemctl", "stop", "hermes-kit-cloudflared.service"], check=False)
        subprocess.run(["systemctl", "disable", "--now", "hermes-kit-tools-certs.timer"], check=False)
        subprocess.run(["systemctl", "disable", "--now", "hermes-kit-tools-backup.timer"], check=False)
        for unit in Path("/etc/systemd/system").glob("hermes-kit-tool-*.service"):
            subprocess.run(["systemctl", "stop", unit.name], check=False)
        registry = Path("/srv/tools/registry.json")
        if registry.exists():
            recorded = json.loads(registry.read_text())
            for tool in recorded.get("tools", []):
                tool["up"] = False
            registry.write_text(json.dumps(recorded, indent=2) + "\n")
    if name == "website" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        subprocess.run(["systemctl", "stop", "hermes-kit-website-preview.service"], check=False)
    if name == "logins" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        subprocess.run(["systemctl", "stop", "hermes-kit-logins-browser.service"], check=False)
        subprocess.run(["systemctl", "stop", "hermes-kit-logins-proxy.service"], check=False)
        Path("/var/lib/hermes-kit/logins-active-domain").unlink(missing_ok=True)


def apply_policy(enabled: set[str]):
    disabled = [x for x in BASE_DISABLED if not (x == "browser" and "logins" in enabled)]
    config_set("agent.disabled_toolsets", disabled)
    tools = BASE_TOOLS + (["browser"] if "logins" in enabled else [])
    for platform in ("cli", "telegram", "photon", "whatsapp", "signal", "slack", "agentmail"):
        config_set(f"platform_toolsets.{platform}", tools)
    # Cron is never given browser or mutation tools. Hermes docs: per-job
    # enabled_toolsets can override platform_toolsets.cron, so validate jobs.
    config_set("platform_toolsets.cron", BASE_TOOLS)
    plugins = [name for name in enabled_plugins() if name != "kit-logins"]
    if "logins" in enabled:
        plugins.append("kit-logins")
    config_set("plugins.enabled", plugins)
    if "logins" in enabled:
        config_set("security.website_blocklist.enabled", True)
        config_set("security.website_blocklist.domains", BLOCKED)
        config_set("browser.cdp_url", "http://127.0.0.1:9222")
        config_set("browser.cloud_provider", "local")
        config_set("browser.dialog_policy", "must_respond")


def validate_cron_jobs():
    path = HOME / "cron" / "jobs.json"
    jobs = json.loads(path.read_text()) if path.exists() else []
    jobs = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
    for job in jobs:
        if job.get("enabled") is False:
            continue
        tools = set(job.get("enabled_toolsets", BASE_TOOLS))
        if tools - set(BASE_TOOLS) or job.get("deliver", "local") != "local" or job.get("script") or job.get("monitor_script") or job.get("no_agent"):
            raise ValueError("Cron job has a non-read/draft toolset")


def install_logins():
    source = KIT / "plugins" / "kit-logins"
    target = HOME / "plugins" / "kit-logins"
    if target.exists():
        if not (ETC / "kit-logins.installed").exists():
            raise ValueError("Existing logins plugin is not kit-owned")
        shutil.rmtree(target)
    shutil.copytree(source, target)
    (ETC / "kit-logins.installed").write_text("kit-logins\n")
    if os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        run(["chown", "-R", "root:root", str(target)])
        run(["useradd", "--system", "--create-home", "--shell", "/usr/sbin/nologin", "logins"]) if subprocess.run(["id", "-u", "logins"], capture_output=True).returncode else None
        profiles = Path("/var/lib/hermes-kit/logins/profiles")
        profiles.mkdir(parents=True, exist_ok=True)
        run(["chown", "logins:logins", str(profiles)])
        browser = shutil.which("chromium") or shutil.which("chromium-browser")
        if not browser:
            run(["apt-get", "-y", "--no-install-recommends", "install", "chromium-browser"])
            browser = shutil.which("chromium") or shutil.which("chromium-browser")
        if not browser:
            raise ValueError("Local Chromium is required for Logins")
        proxy = Path("/etc/systemd/system/hermes-kit-logins-proxy.service")
        proxy.write_text(f"""[Unit]
Description=HTTPS domain guard for Hermes Logins
[Service]
User=logins
Group=logins
ExecStart=/usr/bin/python3 {KIT}/lib/logins_proxy.py
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
[Install]
WantedBy=multi-user.target
""")
        proxy.chmod(0o644)
        unit = Path("/etc/systemd/system/hermes-kit-logins-browser.service")
        unit.write_text(f"""[Unit]
Description=Site-isolated local Chromium for Hermes Logins
After=network-online.target hermes-kit-logins-proxy.service
Requires=hermes-kit-logins-proxy.service
[Service]
User=logins
Group=logins
EnvironmentFile=/etc/hermes-kit/logins-browser.env
ExecStart={browser} --headless --no-first-run --no-default-browser-check --disable-quic --force-webrtc-ip-handling-policy=disable_non_proxied_udp --proxy-server=http://127.0.0.1:9223 --proxy-bypass-list=<-loopback> --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir=${{LOGIN_PROFILE}}
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/hermes-kit/logins/profiles
[Install]
WantedBy=multi-user.target
""")
        unit.chmod(0o644)
        run(["systemctl", "daemon-reload"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["on", "off"])
    parser.add_argument("name", choices=sorted(POWERUPS))
    parser.add_argument("--waiver")
    parser.add_argument("--client")
    args = parser.parse_args()
    try:
        if os.geteuid() != 0 and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
            raise ValueError("Run as root")
        if args.action == "on":
            on(args.name, args.waiver, args.client or "Client")
        else:
            off(args.name)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
