"""Client consent and Hermes toolset policy for optional capabilities."""
from __future__ import annotations

import argparse
import json
import os
import pwd
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from hermes_runtime import HERMES_BIN
from logins_policy import hermes_blocklist
from kit_mcp_policy import PLATFORMS, BASE_PLATFORMS, enabled_servers, grants, platform_tools

ETC = Path(os.environ.get("KIT_POWERUP_ETC", "/etc/hermes-kit"))
HOME = Path(os.environ.get("KIT_POWERUP_HOME", "/home/hermes/.hermes/profiles/client"))
KIT = Path(__file__).resolve().parent.parent
LEDGER = ETC / "consents.json"
POWERUPS = {"base", "builder", "website", "netlify", "tailscale", "media", "schedules", "logins"}
BASE_DISABLED = ["terminal", "code_execution", "browser", "computer_use", "delegation", "kanban", "cronjob", "image_gen", "tts", "homeassistant", "messaging"]
BASE_TOOLS = ["clarify", "file", "memory", "search", "skills", "todo", "vision", "web"]
BLOCKED = hermes_blocklist()
QA_PYTHON = Path("/opt/hermes-kit/qa-venv/bin/python")
QA_PLAYWRIGHT_VERSION = "1.55.0"


def run(args: list[str]):
    subprocess.run(args, check=True)


def local_chromium() -> str:
    browser = shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser:
        run(["apt-get", "-y", "--no-install-recommends", "install", "chromium-browser"])
        browser = shutil.which("chromium") or shutil.which("chromium-browser")
    # Ubuntu's Chromium snap can pull in and start the CUPS snap. Reinstalls
    # must also close this public listener left by older kit releases.
    if subprocess.run(
        ["systemctl", "is-active", "--quiet", "snap.cups.cupsd.service"],
        capture_output=True,
    ).returncode == 0:
        run(["systemctl", "disable", "--now", "snap.cups.cups-browsed.service", "snap.cups.cupsd.service"])
    if not browser:
        raise ValueError("Local Chromium is required for Logins")
    return browser


def install_builder_qa():
    """Use the kit's Chromium; install only Playwright's Python driver."""
    local_chromium()
    if not QA_PYTHON.exists():
        run(["python3", "-m", "venv", "--system-site-packages", str(QA_PYTHON.parent.parent)])
    result = subprocess.run(
        [str(QA_PYTHON), "-c", "from importlib.metadata import version; print(version('playwright'))"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != QA_PLAYWRIGHT_VERSION:
        run([str(QA_PYTHON.parent / "pip"), "install", "--no-cache-dir", f"playwright=={QA_PLAYWRIGHT_VERSION}"])


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
    result = subprocess.run(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client", "config", "get", "plugins.enabled", "--json"], capture_output=True, text=True)
    if result.returncode != 0:
        # A fresh profile has no plugins.enabled key yet; Hermes reports that as an error.
        if "not set" in (result.stdout + result.stderr).lower():
            return []
        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
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


def on(name: str, waiver: str | None, client: str, confirmation: str = "client-on"):
    if name == "logins" and (not waiver or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", waiver)):
        raise ValueError("Logins requires a signed waiver id from the client")
    if not re.fullmatch(r"[A-Za-z0-9 .'-]{1,80}", client):
        raise ValueError("Client name is required")
    data = consents()
    if name == "netlify" and not any(x.get("integration") == "website" for x in data["consents"]):
        raise ValueError("Enable Website before Netlify")
    if name in {"logins", "schedules"} and ({x.get("integration") for x in data["consents"]} & ({"schedules"} if name == "logins" else {"logins"})):
        raise ValueError("Logins and Schedules cannot be enabled together on this profile")
    if name in [x.get("integration") for x in data["consents"]]:
        return
    # Fail before provisioning anything when the service user's launcher is broken.
    enabled_plugins()
    if name == "schedules":
        validate_cron_jobs()
    entry = {"integration": name, "client_name": client, "date": datetime.now(timezone.utc).date().isoformat(),
             "scopes": [name], "risk_level": "RED" if name in {"logins", "netlify"} else "YELLOW",
             "warnings_shown": "Client controls this power-up; public, destructive and paid actions still require approval", "confirmation": confirmation, "waiver_id": waiver or "none"}
    data["consents"].append(entry)
    # Configure first, record the consent only after all guardrails are present.
    config_path = ETC / "test-config.json" if os.environ.get("KIT_POWERUP_TEST_MODE") == "1" else HOME / "config.yaml"
    old_config = config_path.read_bytes() if config_path.exists() else None
    try:
        if name in {"builder", "website", "media"}:
            install_starter()
        if name in {"builder", "website"} and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
            install_builder_qa()
        apply_policy({x.get("integration") for x in data["consents"]}, data["consents"])
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
    if name == "schedules":
        seed_schedule_jobs()
    if name in {"builder", "website", "media"} and os.environ.get("KIT_POWERUP_TEST_MODE") != "1" and not any(x.get("integration") == "plugin:kit-starter" for x in data["consents"]):
        data["consents"].append(dict(entry, integration="plugin:kit-starter"))
        save(data)
    if os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        run(["systemctl", "restart", "hermes-gateway.service"])
    if name == "builder" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        run(["systemctl", "enable", "--now", "hermes-kit-starter.service"])
        run(["systemctl", "enable", "--now", "hermes-kit-tools-backup.timer"])
    if name == "website" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        run(["systemctl", "enable", "--now", "hermes-kit-website-preview.service"])
    if name == "logins":
        plugin_consent = dict(entry, integration="plugin:kit-logins")
        data["consents"].append(plugin_consent)
        save(data)


def off(name: str):
    if name == "base":
        raise ValueError("Base is always on")
    data = consents()
    if name == "website" and any(x.get("integration") == "netlify" for x in data["consents"]):
        raise ValueError("Disable Netlify before Website")
    if name == "schedules" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        job_path = HOME / "cron" / "jobs.json"
        document = json.loads(job_path.read_text()) if job_path.exists() else []
        jobs = document if isinstance(document, list) else document.get("jobs", [])
        for job in jobs:
            if job.get("enabled") is not False:
                run(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client", "cron", "pause", str(job["id"])])
    removed = {name, "plugin:kit-logins" if name == "logins" else ""}
    if name in {"builder", "website", "media"} and not ({x.get("integration") for x in data["consents"]} - {name} & {"builder", "website", "media"}):
        removed.add("plugin:kit-starter")
    if name == "netlify":
        removed.add("env:NETLIFY_AUTH_TOKEN")
    if name == "media":
        removed.add("env:TTS_API_KEY")
    data["consents"] = [x for x in data["consents"] if x.get("integration") not in removed]
    apply_policy({x.get("integration") for x in data["consents"]}, data["consents"])
    save(data)
    if name == "builder" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        subprocess.run(["systemctl", "disable", "--now", "hermes-kit-starter.service"], check=False)
        subprocess.run(["tailscale", "serve", "reset"], check=False)
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
        subprocess.run(["systemctl", "disable", "--now", "hermes-kit-website-preview.service"], check=False)
    if name in {"netlify", "media"} and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        env_file = HOME / ".env"
        if env_file.exists():
            secret_key = "NETLIFY_AUTH_TOKEN" if name == "netlify" else "TTS_API_KEY"
            lines = [line for line in env_file.read_text().splitlines(keepends=True) if not line.startswith(secret_key + "=")]
            env_file.write_text("".join(lines))
            env_file.chmod(0o600)
    if name == "tailscale" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        subprocess.run(["tailscale", "serve", "reset"], check=False)
        subprocess.run(["tailscale", "down"], check=False)
    if name == "logins" and os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        subprocess.run(["systemctl", "stop", "hermes-kit-logins-browser.service"], check=False)
        subprocess.run(["systemctl", "disable", "--now", "hermes-kit-logins-cdp.service"], check=False)
        subprocess.run(["systemctl", "stop", "hermes-kit-logins-proxy.service"], check=False)
        Path("/var/lib/hermes-kit/logins-active-domain").unlink(missing_ok=True)
    if os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        run(["systemctl", "restart", "hermes-gateway.service"])


def apply_policy(enabled: set[str], entries: list[dict] | None = None):
    allowed = grants(entries if entries is not None else consents().get("consents", []))
    active_mcp = configured_mcp_servers() if any(allowed.values()) else set()
    reachable_grants = {platform: servers & active_mcp for platform, servers in allowed.items()}
    disabled = [x for x in BASE_DISABLED if not ((x == "browser" and "logins" in enabled) or (x == "cronjob" and "schedules" in enabled))]
    config_set("agent.disabled_toolsets", disabled)
    tools = BASE_TOOLS + (["browser"] if "logins" in enabled else [])
    from kit_reminders import owner_target
    selected_chat = owner_target().split(":", 1)[0] if "schedules" in enabled else ""
    for platform in PLATFORMS:
        native = (tools + (["cronjob"] if platform == selected_chat else [])) if platform in BASE_PLATFORMS and platform != "cron" else ([] if platform not in BASE_PLATFORMS else BASE_TOOLS)
        config_set(f"platform_toolsets.{platform}", platform_tools(platform, native, reachable_grants))
    # Cron is never given browser or mutation tools. Hermes docs: per-job
    # enabled_toolsets can override platform_toolsets.cron, so validate jobs.
    seal_cron_overrides()
    plugins = [name for name in enabled_plugins() if name not in {"kit-logins", "kit-starter", "kit-reminders", "kit-welcome"}]
    install_welcome()
    plugins.append("kit-welcome")
    if "schedules" in enabled:
        install_reminder_guard()
        plugins.append("kit-reminders")
    if "logins" in enabled:
        plugins.append("kit-logins")
    if enabled & {"builder", "website", "media"}:
        plugins.append("kit-starter")
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
    if not isinstance(jobs, list) or len(jobs) > 20:
        raise ValueError("At most 20 cron jobs are allowed")
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("Invalid cron job")
        configured_tools = job.get("enabled_toolsets")
        if configured_tools is not None and not isinstance(configured_tools, list):
            raise ValueError("Cron job toolset must be a list or null")
        tools = set(BASE_TOOLS if configured_tools is None else configured_tools)
        from kit_reminders import allowed_delivery, owner_target, valid_schedule
        if (tools - (set(BASE_TOOLS) | {"no_mcp"}) or
                (configured_tools and "no_mcp" not in tools) or
                not allowed_delivery(job.get("deliver", "local"), owner_target(), job.get("origin")) or
                (job.get("failure_deliver") not in {None, ""} and
                 not allowed_delivery(job.get("failure_deliver"), owner_target(), job.get("origin"))) or
                job.get("script") or job.get("monitor_script") or job.get("monitor_url") or
                job.get("no_agent") or job.get("workdir") or not valid_schedule(job.get("schedule"))):
            raise ValueError("Cron job violates owner-only reminder policy")
        if not isinstance(job.get("prompt"), str) or not job["prompt"].strip():
            raise ValueError("Cron job needs an auditable prompt")
        if job.get("enabled") is not False and "schedules" not in {x.get("integration") for x in consents().get("consents", [])}:
            raise ValueError("Active cron job needs Schedules consent")


def seed_schedule_jobs():
    """Create two paused examples after Schedules consent and owner chat setup."""
    if os.environ.get("KIT_POWERUP_TEST_MODE") == "1":
        return
    from kit_reminders import audit_prompt, owner_target
    target = owner_target()
    if not target:
        return
    path = HOME / "cron" / "jobs.json"
    document = json.loads(path.read_text()) if path.exists() else []
    jobs = document if isinstance(document, list) else document.get("jobs", [])
    examples = (
        ("Monday plan", "every monday 9am", "Use weekly-review-planning and the Business Brief to send me a concise Monday plan: priorities, follow-ups, and one decision to make."),
        ("Friday wrap", "every friday 4pm", "Use the Business Brief and notes in the vault to send me a concise Friday wrap: completed work, loose ends, and the first priority for Monday."),
    )
    missing = sum(not any(job.get("name") == name for job in jobs) for name, _, _ in examples)
    if len(jobs) + missing > 20:
        raise ValueError("Cannot seed reminders: 20 cron jobs already exist")
    for name, schedule, prompt in examples:
        if any(job.get("name") == name for job in jobs):
            continue
        args = ["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN,
                "-p", "client", "cron", "create", schedule, prompt, "--name", name, "--deliver", target, "--paused"]
        if name == "Monday plan":
            args.extend(["--skill", "weekly-review-planning"])
        before_ids = {str(job.get("id")) for job in jobs}
        created = subprocess.run(args, check=False, capture_output=True, text=True)
        if not path.exists():
            raise ValueError("Hermes did not write the seeded reminder")
        document = json.loads(path.read_text())
        jobs = document if isinstance(document, list) else document.get("jobs", [])
        new_jobs = [job for job in jobs if str(job.get("id")) not in before_ids]
        if len(new_jobs) != 1 or new_jobs[0].get("name") != name:
            raise subprocess.CalledProcessError(created.returncode or 1, args, created.stdout, created.stderr)
        audit_prompt(prompt, schedule)
    validate_cron_jobs()


def install_reminder_guard():
    if os.environ.get("KIT_POWERUP_TEST_MODE") == "1":
        return
    source = KIT / "plugins" / "kit-reminders"
    target = HOME / "plugins" / "kit-reminders"
    marker = ETC / "kit-reminders.installed"
    if target.exists() and not marker.exists():
        raise ValueError("Existing reminders plugin is not kit-owned")
    target.mkdir(parents=True, exist_ok=True)
    marker.write_text("kit-reminders\n")
    for filename in ("__init__.py", "plugin.yaml"):
        shutil.copy2(source / filename, target / filename)
    shutil.copy2(KIT / "lib" / "kit_reminders.py", target / "kit_reminders.py")
    run(["chown", "-R", "root:root", str(target)])


def install_welcome():
    if os.environ.get("KIT_POWERUP_TEST_MODE") == "1":
        return
    source = KIT / "plugins" / "kit-welcome"
    target = HOME / "plugins" / "kit-welcome"
    marker = ETC / "kit-welcome.installed"
    if target.exists() and not marker.exists():
        raise ValueError("Existing welcome plugin is not kit-owned")
    target.mkdir(parents=True, exist_ok=True)
    marker.write_text("kit-welcome\n")
    for filename in ("__init__.py", "plugin.yaml"):
        shutil.copy2(source / filename, target / filename)
    shutil.copy2(KIT / "lib" / "kit_welcome.py", target / "kit_welcome.py")
    shutil.copy2(KIT / "lib" / "kit_reminders.py", target / "kit_reminders.py")
    shutil.copy2(KIT / "lib" / "kit_quota_notice.py", target / "kit_quota_notice.py")
    run(["chown", "-R", "root:root", str(target)])


def seal_cron_overrides():
    path = HOME / "cron" / "jobs.json"
    if not path.exists():
        return
    document = json.loads(path.read_text())
    jobs = document if isinstance(document, list) else document.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError("Cron jobs must be a list")
    changed = False
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("Invalid cron job")
        selected = job.get("enabled_toolsets")
        if selected:
            if not isinstance(selected, list):
                raise ValueError("Cron job toolsets must be a list")
            if "no_mcp" not in selected:
                selected.append("no_mcp")
                changed = True
    if not changed:
        return
    stat = path.stat()
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".kit-cron-", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(document, handle)
        handle.write("\n")
        os.fchmod(handle.fileno(), stat.st_mode & 0o777)
        os.fchown(handle.fileno(), stat.st_uid, stat.st_gid)
    temporary.replace(path)


def configured_mcp_servers() -> set[str]:
    if os.environ.get("KIT_POWERUP_TEST_MODE") == "1":
        path = ETC / "test-config.json"
        config = json.loads(path.read_text()) if path.exists() else {}
        servers = config.get("mcp_servers", {})
    else:
        result = subprocess.run(
            ["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes",
             "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client",
             "config", "get", "mcp_servers", "--json"], capture_output=True, text=True)
        servers = json.loads(result.stdout) if result.returncode == 0 else {}
    profile = json.loads((HOME / "mcp.json").read_text()) if (HOME / "mcp.json").exists() else {}
    return enabled_servers(servers, profile)


def apply_consent_candidate(candidate: dict, server: str | None = None):
    entries = candidate.get("consents", [])
    if server and server not in configured_mcp_servers():
        raise ValueError("MCP server is not enabled in the client profile")
    grants(entries)
    config_path = ETC / "test-config.json" if os.environ.get("KIT_POWERUP_TEST_MODE") == "1" else HOME / "config.yaml"
    old_config = config_path.read_bytes() if config_path.exists() else None
    try:
        apply_policy({x.get("integration") for x in entries}, entries)
    except Exception:
        if old_config is None:
            config_path.unlink(missing_ok=True)
        else:
            config_path.write_bytes(old_config)
        raise


def cdp_rules(hermes_uid: int) -> str:
    return f"""table inet hermes_kit_logins {{
  chain output {{
    type filter hook output priority -10; policy accept;
    ip daddr 127.0.0.1 tcp dport 9222 meta skuid != {{ 0, {hermes_uid} }} drop
  }}
}}
"""


def install_logins():
    source = KIT / "plugins" / "kit-logins"
    target = HOME / "plugins" / "kit-logins"
    if target.exists():
        if not (ETC / "kit-logins.installed").exists():
            raise ValueError("Existing logins plugin is not kit-owned")
        shutil.rmtree(target)
    shutil.copytree(source, target)
    (ETC / "kit-logins.installed").write_text("kit-logins\n")
    target.parent.chmod(0o700)
    target.chmod(0o755)
    if os.environ.get("KIT_POWERUP_TEST_MODE") != "1":
        run(["chown", "-R", "root:root", str(target)])
        run(["chown", "hermes:hermes", str(target.parent)])
        run(["useradd", "--system", "--create-home", "--shell", "/usr/sbin/nologin", "logins"]) if subprocess.run(["id", "-u", "logins"], capture_output=True).returncode else None
        profiles = Path("/var/lib/hermes-kit/logins/profiles")
        profiles.mkdir(parents=True, exist_ok=True)
        run(["chown", "logins:logins", str(profiles)])
        browser = local_chromium()
        run(["apt-get", "-y", "--no-install-recommends", "install", "nftables"])
        hermes_uid = pwd.getpwnam("hermes").pw_uid
        rules = ETC / "logins-cdp.nft"
        rules.write_text(cdp_rules(hermes_uid))
        rules.chmod(0o644)
        firewall = Path("/etc/systemd/system/hermes-kit-logins-cdp.service")
        firewall.write_text("""[Unit]
Description=Restrict Hermes Logins browser debug port to Hermes
After=nftables.service
Before=hermes-kit-logins-browser.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=-/usr/sbin/nft delete table inet hermes_kit_logins
ExecStart=/usr/sbin/nft -f /etc/hermes-kit/logins-cdp.nft
ExecStop=/usr/sbin/nft delete table inet hermes_kit_logins
[Install]
WantedBy=multi-user.target
""")
        firewall.chmod(0o644)
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
After=network-online.target hermes-kit-logins-proxy.service hermes-kit-logins-cdp.service
Requires=hermes-kit-logins-proxy.service hermes-kit-logins-cdp.service
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
        run(["systemctl", "enable", "hermes-kit-logins-cdp.service"])
        run(["systemctl", "restart", "hermes-kit-logins-cdp.service"])


def install_starter():
    if os.environ.get("KIT_POWERUP_TEST_MODE") == "1":
        return
    source = KIT / "plugins" / "kit-starter"
    target = HOME / "plugins" / "kit-starter"
    if target.exists():
        if not (ETC / "kit-starter.installed").exists():
            raise ValueError("Existing starter plugin is not kit-owned")
        extras = {item.name for item in target.iterdir()} - {"__init__.py", "plugin.yaml", "kit_website.py", "kit_video.py", "kit_site_check.py", "__pycache__"}
        if extras:
            raise ValueError("Unexpected files in starter plugin")
    else:
        target.mkdir(parents=True)
    for filename in ("__init__.py", "plugin.yaml"):
        shutil.copy2(source / filename, target / filename)
    for filename in ("kit_website.py", "kit_video.py", "kit_site_check.py"):
        shutil.copy2(KIT / "lib" / filename, target / filename)
    (ETC / "kit-starter.installed").write_text("kit-starter\n")
    run(["chown", "-R", "root:root", str(target)])
    target.chmod(0o755)


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
