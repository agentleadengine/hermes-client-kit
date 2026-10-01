#!/usr/bin/env python3
"""Root-side browser chat setup. Request and subprocess output are never logged."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import termios
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
from kit_powerup import BASE_TOOLS, config_set, consents  # noqa: E402

CONFIG = Path("/etc/hermes-kit/kit.conf")
ENV = Path("/home/hermes/.hermes/profiles/client/.env")
STATE = Path("/var/lib/hermes-kit")
BOT_TOKEN = re.compile(r"[0-9]{6,12}:[A-Za-z0-9_-]{30,}\Z")
TELEGRAM_ID = re.compile(r"[0-9]{5,15}\Z")
E164 = re.compile(r"\+[1-9][0-9]{6,14}\Z")  # ASCII E.164 subset of Hermes photon/auth.py E164_RE
PROJECT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class ChatError(Exception):
    pass


def validate(data: dict) -> tuple[str, dict[str, str]]:
    platform = data.get("platform", "")
    if platform not in ("telegram", "photon", "none"):
        raise ChatError("Choose Telegram, iMessage, or Skip.")
    if platform == "none":
        return platform, {}
    if platform == "telegram":
        token, user = data.get("bot_token", ""), data.get("telegram_user_id", "")
        if not isinstance(token, str) or not BOT_TOKEN.fullmatch(token):
            raise ChatError("Check the bot token from @BotFather and try again.")
        if not isinstance(user, str) or not TELEGRAM_ID.fullmatch(user):
            raise ChatError("Enter the numeric Telegram user ID shown by @userinfobot.")
        return platform, {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_ALLOWED_USERS": user}
    project, secret, phone = (data.get(key, "") for key in ("project_id", "project_secret", "phone"))
    if not isinstance(project, str) or not PROJECT_ID.fullmatch(project):
        raise ChatError("Enter the Photon Spectrum project ID from your Photon dashboard.")
    if not isinstance(secret, str) or not secret or len(secret) > 1024 or any(ord(c) < 32 or ord(c) == 127 for c in secret):
        raise ChatError("Enter the Photon project secret from your Photon dashboard.")
    if not isinstance(phone, str) or not E164.fullmatch(phone):
        raise ChatError("Enter an international phone number in E.164 format, such as +15551234567.")
    return platform, {"PHOTON_PROJECT_ID": project, "PHOTON_PROJECT_SECRET": secret, "PHOTON_ALLOWED_USERS": phone,
                      "PHOTON_HOME_CHANNEL": phone}


def run(args: list[str], *, input_text: str | None = None, timeout: int = 60) -> bool:
    try:
        return subprocess.run(args, input=input_text, text=True, capture_output=True, timeout=timeout, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def key_write(key: str, value: str | None) -> None:
    # kit-set-key owns key refusals and common.sh owns dotenv escaping/atomic writes.
    args = ["/usr/local/bin/kit-set-key", key, "--stdin" if value is not None else "--unset", "--no-restart"]
    if not run(args, input_text=value + "\n" if value is not None else None):
        raise ChatError("The server could not save chat settings. Please try again.")


def config_values() -> dict[str, str]:
    values = {}
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        if "=" in line and re.fullmatch(r"[A-Z][A-Z0-9_]*", line.split("=", 1)[0]):
            key, value = line.split("=", 1)
            values[key] = value.strip('"\'')
    return values


def write_config(platform: str, user: str) -> None:
    # Same kit.conf keys consumed by 05-profile.sh on install. Atomic and idempotent.
    replacements = {"MESSAGING_PLATFORM": platform, "TELEGRAM_ALLOWED_USERS": user if platform == "telegram" else "",
                    "PHOTON_ALLOWED_USERS": user if platform == "photon" else ""}
    lines = CONFIG.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if not any(line.startswith(key + "=") for key in replacements)]
    lines.extend(f'{key}="{value}"' for key, value in replacements.items())
    content = "\n".join(lines) + "\n"
    if CONFIG.read_text(encoding="utf-8") == content:
        return
    temp = CONFIG.with_name(CONFIG.name + ".chat-" + os.urandom(8).hex())
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, CONFIG)
    finally:
        temp.unlink(missing_ok=True)


def clear_photon_auth() -> None:
    # Hermes may place a dashboard device token in the host or a profile.
    # Preserve unrelated providers and serialize with Hermes's auth.lock.
    hermes_root = ENV.parents[2] if ENV.parent.parent.name == "profiles" else ENV.parent
    paths = {ENV.parent / "auth.json", hermes_root / "auth.json"}
    if ENV == Path("/home/hermes/.hermes/profiles/client/.env"):
        paths.add(Path("/root/.hermes/auth.json"))
        paths.add(Path("/var/lib/hermes-support/auth.json"))
        for home in Path("/home").glob("*/.hermes"):
            paths.add(home / "auth.json")
            paths.update((home / "profiles").glob("*/auth.json"))
    paths.update((hermes_root / "profiles").glob("*/auth.json"))
    for auth in sorted(paths):
        _clear_photon_auth_file(auth)


def _clear_photon_auth_file(auth: Path) -> None:
    if not auth.exists():
        return
    owner = auth.stat()
    lock_path = auth.with_suffix(".lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    os.fchown(fd, owner.st_uid, owner.st_gid)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(auth.read_text(encoding="utf-8"))
        pool = data.get("credential_pool", {})
        if not isinstance(pool, dict):
            raise ChatError("The stored Photon login needs a local check. Contact your setup guide.")
        changed = False
        for key in ("photon_project", "photon_user", "photon"):
            if key in pool:
                del pool[key]
                changed = True
        if not changed:
            return
        temp = auth.with_name(auth.name + ".chat-" + os.urandom(8).hex())
        try:
            out_fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.fchown(out_fd, owner.st_uid, owner.st_gid)
            with os.fdopen(out_fd, "w", encoding="utf-8") as out:
                json.dump(data, out, separators=(",", ":"))
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, auth)
        finally:
            temp.unlink(missing_ok=True)


def request_json(url: str, *, data: dict | None = None, headers: dict | None = None) -> dict | list:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, response_headers, newurl):
            return None  # never forward a bot-token URL or Photon Basic auth

    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=payload, headers=headers or {}, method="POST" if data is not None else "GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=25) as response:
            if response.status < 200 or response.status >= 300:
                raise ChatError("The chat provider did not accept these settings. Please check them and try again.")
            result = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ChatError("The chat provider rejected these credentials. Check the project or bot details and try again.") from None
        if error.code == 404:
            raise ChatError("The chat provider could not find that project or bot. Check the ID and try again.") from None
        raise ChatError("The chat provider could not complete setup. Please try again shortly.") from None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        raise ChatError("The chat provider could not be reached. Please try again shortly.") from None
    if not isinstance(result, (dict, list)):
        raise ChatError("The chat provider gave an unexpected response. Please try again.")
    return result


def telegram_check(user: str) -> None:
    # Read the saved value so the test uses exactly what the gateway will load.
    line = next((line for line in ENV.read_text().splitlines() if line.startswith("TELEGRAM_BOT_TOKEN=")), "")
    token = line.split("=", 1)[1].strip('"')
    if not BOT_TOKEN.fullmatch(token):
        raise ChatError("The bot token was not saved correctly. Please try again.")
    base = "https://api.telegram.org/bot" + token
    me = request_json(base + "/getMe")
    if not isinstance(me, dict) or me.get("ok") is not True:
        raise ChatError("Telegram rejected the bot token. Copy a fresh token from @BotFather.")
    try:
        sent = request_json(base + "/sendMessage", data={"chat_id": user, "text": "Hi, I'm your assistant. Text me anytime."},
                            headers={"Content-Type": "application/json"})
    except ChatError:
        raise ChatError("Bot verified, but the hello message could not be sent. Open your bot in Telegram, tap Start, then try again.") from None
    if not isinstance(sent, dict) or sent.get("ok") is not True:
        raise ChatError("Bot verified, but Telegram could not send the hello message. Open your bot, tap Start, then try again.")


def photon_check(project: str, secret: str, phone: str) -> tuple[str, str]:
    # Mirrors pinned Hermes photon/auth.py list_users/create_user. A Spectrum
    # credential check and idempotent user registration are the supported probe.
    basic = base64.b64encode((project + ":" + secret).encode()).decode()
    base = "https://spectrum.photon.codes/projects/" + urllib.parse.quote(project, safe="") + "/users/"
    headers = {"Authorization": "Basic " + basic, "Content-Type": "application/json"}
    users = request_json(base, headers=headers)
    listed = users if isinstance(users, list) else []
    if isinstance(users, dict):
        for key in ("data", "users", "items"):
            inner = users.get(key)
            if isinstance(inner, list):
                listed = inner
                break
            if isinstance(inner, dict):
                nested = next((inner[k] for k in ("users", "items") if isinstance(inner.get(k), list)), None)
                if nested is not None:
                    listed = nested
                    break
    if not isinstance(listed, list):
        raise ChatError("Photon returned an unexpected user list. Check the project settings.")
    person = next((item for item in listed if isinstance(item, dict) and item.get("phoneNumber") == phone), None)
    if person is None:
        created = request_json(base, data={"type": "shared", "phoneNumber": phone}, headers=headers)
        person = created.get("user", created.get("data", created)) if isinstance(created, dict) else None
    if not isinstance(person, dict):
        raise ChatError("Photon could not register this phone. Check the project settings.")
    line = person.get("assignedPhoneNumber")
    user_id = person.get("id") or person.get("userId")
    if type(user_id) is int:
        user_id = str(user_id)
    safe_id = user_id if isinstance(user_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", user_id) else ""
    return (line if isinstance(line, str) and E164.fullmatch(line) else "", safe_id)


def photon_hello(phone: str) -> bool:
    """True only for Photon's expected shared-line first-contact refusal."""
    args = ["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes",
            "/home/hermes/.local/bin/hermes", "-p", "client", "send", "--to", "photon:" + phone,
            "Hi, I'm your assistant. Text me anytime."]
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ChatError("Photon is connected, but the hello could not be sent. Please retry setup.") from None
    if result.returncode == 0:
        return False
    detail = (result.stdout + result.stderr).lower()
    if "target_not_allowed" in detail or "shared/free-tier photon lines cannot initiate" in detail:
        return True
    raise ChatError("Photon is connected, but the hello could not be sent. Please retry setup.")


def photon_hi_link(user_id: str) -> str:
    if not user_id:
        return ""
    return "https://spectrum.photon.codes/users/" + urllib.parse.quote(user_id, safe="") + "/redirect?msg=Hi"


def connect(data: dict) -> tuple[bool, str]:
    platform, values = validate(data)
    STATE.mkdir(mode=0o751, parents=True, exist_ok=True)
    with (STATE / "chat-connect.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = config_values().get("MESSAGING_PLATFORM", "none")
        if platform == "none":
            clear_photon_auth()
            for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS", "PHOTON_PROJECT_ID", "PHOTON_PROJECT_SECRET",
                        "PHOTON_ALLOWED_USERS", "PHOTON_HOME_CHANNEL"):
                key_write(key, None)
            write_config("none", "")
            (STATE / "chat-connected.sha256").unlink(missing_ok=True)
            (STATE / "chat-line.txt").unlink(missing_ok=True)
            if old != "none":
                if not run(["systemctl", "restart", "hermes-gateway.service"]):
                    raise ChatError("The settings were removed, but the assistant could not restart. Contact your setup guide.")
                if not run(["/usr/local/bin/kit-verify", "--json"], timeout=180):
                    raise ChatError("The chat app was removed, but a server safety check needs attention. Contact your setup guide.")
                append_event("chat-app-disconnected", old)
            run(["/usr/local/bin/kit-access-log"])
            run(["/usr/local/bin/kit-health"])
            return True, "Chat app disconnected. You can connect one again here anytime."

        fingerprint = hashlib.sha256(json.dumps([platform, values], sort_keys=True).encode()).hexdigest()
        marker = STATE / "chat-connected.sha256"
        clear_photon_auth()
        if marker.exists() and marker.read_text().strip() == fingerprint and old == platform:
            if not run(["/usr/local/bin/kit-verify", "--json"], timeout=180):
                raise ChatError("The chat connection is no longer healthy. Contact your setup guide.")
            return True, "Connected. Your chat app is already set up."
        # Probe Photon credentials and register the authorized user before changing local state.
        line, user_id = "", ""
        if platform == "photon":
            line, user_id = photon_check(values["PHOTON_PROJECT_ID"], values["PHOTON_PROJECT_SECRET"], values["PHOTON_ALLOWED_USERS"])
        for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS", "PHOTON_PROJECT_ID", "PHOTON_PROJECT_SECRET",
                    "PHOTON_ALLOWED_USERS", "PHOTON_HOME_CHANNEL"):
            key_write(key, values.get(key))
        user = values["TELEGRAM_ALLOWED_USERS" if platform == "telegram" else "PHOTON_ALLOWED_USERS"]
        write_config(platform, user)
        tools = BASE_TOOLS + (["browser"] if any(c.get("integration") == "logins" for c in consents().get("consents", [])) else [])
        config_set("platform_toolsets." + platform, tools)
        if platform == "photon":
            # Hermes can install the pinned sidecar dependencies without dashboard credentials.
            if not run(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes",
                        "NPM_CONFIG_CACHE=/home/hermes/.hermes/cache/npm",
                        "/home/hermes/.local/bin/hermes", "-p", "client", "photon", "install-sidecar"], timeout=180):
                raise ChatError("Photon details were saved, but its connection software could not start. Contact your setup guide.")
        if not run(["systemctl", "restart", "hermes-gateway.service"]) or not run(["systemctl", "is-active", "--quiet", "hermes-gateway.service"]):
            raise ChatError("Settings were saved, but the assistant could not start. Contact your setup guide.")
        if platform == "telegram":
            telegram_check(user)
            message = "Connected. Check your phone for a hello message."
        elif not line:
            raise ChatError("Photon accepted your details, but has not assigned a chat number yet. Check your Photon dashboard and return here.")
        if not run(["/usr/local/bin/kit-verify", "--json"], timeout=180):
            raise ChatError("The chat details were saved, but a server safety check needs attention. Contact your setup guide.")
        if platform == "photon":
            needs_first_text = photon_hello(user)
            if needs_first_text:
                message = "Connected. Ask the client to text 'hi' to " + line + " once"
                link = photon_hi_link(user_id)
                if link:
                    message += ". Open the prefilled message: " + link
            else:
                message = "Connected. Check your phone for a hello message from " + line + "."
            (STATE / "chat-line.txt").write_text(line + "\n")
            (STATE / "chat-line.txt").chmod(0o600)
        else:
            (STATE / "chat-line.txt").unlink(missing_ok=True)
        marker.write_text(fingerprint + "\n")
        marker.chmod(0o600)
        append_event("chat-app-connected", platform)
        run(["/usr/local/bin/kit-access-log"])
        run(["/usr/local/bin/kit-health"])
        return True, message


def append_event(kind: str, platform: str) -> None:
    with (STATE / "access-events.log").open("a", encoding="utf-8") as events:
        events.write(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + f" {kind} platform={platform}\n")


def hidden_prompt(label: str) -> str:
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    hidden = original.copy()
    hidden[3] &= ~termios.ECHO
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, hidden)
        print(label, end="", file=sys.stderr, flush=True)
        return sys.stdin.readline().rstrip("\r\n")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)
        print(file=sys.stderr, flush=True)


def main() -> int:
    if os.geteuid() != 0:
        return 1
    cli = bool(sys.argv[1:])
    try:
        if cli:
            if len(sys.argv) != 4 or sys.argv[1:3] != ["--photon", "--phone"] or not sys.stdin.isatty():
                raise ChatError("Usage: sudo kit-chat-connect --photon --phone +15551234567 (from a terminal)")
            phone = sys.argv[3]
            # Both fields are read from the operator's terminal with echo disabled.
            project = hidden_prompt("Photon Spectrum project ID: ")
            secret = hidden_prompt("Photon project secret: ")
            data = {"platform": "photon", "phone": phone, "project_id": project, "project_secret": secret}
        else:
            data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ChatError("Invalid form. Please try again.")
        ok, message = connect(data)
    except ChatError as error:
        ok, message = False, str(error)
    except Exception:
        ok, message = False, "The chat connection could not be completed. Please try again or contact your setup guide."
    if cli:
        print(message)
        return 0 if ok else 1
    print(json.dumps({"ok": ok, "message": message}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
