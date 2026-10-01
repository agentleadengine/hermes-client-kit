#!/usr/bin/env python3
"""Token-gated, content-free activation and support control surface."""
import hashlib
import hmac
import html
import json
import os
import re
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATE = Path("/var/lib/agent-care/activation")
SUPPORT = Path("/var/lib/agent-care/support")
HOME = Path("/var/lib/agent-care/home")
REPORT_STATE = Path("/var/lib/hermes-kit/report")
SAFE_DURATION = {"1", "2", "8", "24"}

def read(path, default=""):
    try: return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError: return default

def token_matches(directory, token):
    salt, expected, expiry = read(directory / "salt"), read(directory / "token.sha256"), read(directory / "expires-at")
    if not salt or not expected or not expiry.isdigit() or int(expiry) < int(time.time()): return False
    actual = hashlib.sha256((salt + token).encode()).hexdigest()
    return hmac.compare_digest(actual, expected)

def action(command, stdin=None):
    try:
        return subprocess.run(command, input=stdin, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False

def config_value(name):
    for line in read(Path("/etc/hermes-kit/kit.conf")).splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""

def enrollment_notice():
    words = read(STATE / "fingerprint-words")
    if (REPORT_STATE / "enrolled-agent-id").is_file() and words:
        return "<p>Read these 4 words to your setup guide: " + html.escape(words) + "</p>"
    return "<p>Connecting to Agent Care... refresh in a minute</p>"

def page(title, body):
    return f"<!doctype html><html><head><meta name=\"referrer\" content=\"no-referrer\"><meta name=\"viewport\" content=\"width=device-width\"><title>{html.escape(title)}</title><style>body{{font:16px system-ui;max-width:62rem;margin:2rem auto;padding:0 1rem;color:#17202b}}section{{border:1px solid #ccd3db;border-radius:.5rem;padding:1rem;margin:1rem 0}}form{{margin:.5rem 0}}input,textarea,select,button{{font:inherit;padding:.45rem}}textarea{{width:min(100%,40rem)}}button{{cursor:pointer}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:1rem}}.row{{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}}</style></head><body><main><h1>{html.escape(title)}</h1>{body}</main></body></html>".encode()

def form(token, action, label, fields=""):
    return f'<form method="post" action="/home/{token}/{action}">{fields}<button>{html.escape(label)}</button></form>'

def home_page(token):
    try: health_raw = Path("/var/lib/hermes-kit/health.json").read_text(encoding="utf-8")
    except FileNotFoundError: health_raw = "{}"
    try: health = json.loads(health_raw)
    except ValueError: health = {}
    tier = health.get("tier", config_value("KIT_TIER") or "care")
    access = health.get("access", {})
    powers = set(health.get("power_ups", ["base"]))
    tools = health.get("tools", [])
    section = enrollment_notice()
    section += '<p>This page closes after 2 hours. Only someone with this link can use it. Keep the link private.</p>'
    section += '<section><h2>What Sam can see</h2><p>This is the exact last health payload sent from your server. It does not include chats, files or tool data.</p><pre>' + html.escape(health_raw) + '</pre></section>'
    section += f'<section><h2>Your plan and team access</h2><p>Plan: <strong>{html.escape(tier.title())}</strong>. Manager key present: {str(bool(access.get("manager_key_present"))).lower()}. Full access active: {str(bool(access.get("full_access_active"))).lower()}.</p>'
    if tier == "managed":
        section += form(token, "manager-grant", "Give team manager access", '<label>Team Ed25519 public key<br><textarea name="public_key" rows="3" required></textarea></label>')
        section += form(token, "manager-revoke", "Remove manager access", '<p>Removes every manager key and ends manager sessions.</p>')
    elif tier == "full":
        section += form(token, "full-grant", "Give team Full Service access", '<p>Full Service can read chats, memory, files and tool data. Enter the signed waiver ID.</p><label>Team Ed25519 public key<br><textarea name="public_key" rows="3" required></textarea></label><label>Waiver ID <input name="waiver" required></label>')
        section += form(token, "full-revoke", "Remove Full Service access", '<label>Team key fingerprint (SHA256:...) <input name="fingerprint" required></label>')
    else:
        section += '<p>Care has no team login. We can see only the health payload above.</p>'
    section += '</section><section><h2>Power-ups</h2><p>Base is always on. Logins needs a signed waiver and a site allowlist. Scheduled jobs can save local drafts only.</p>'
    for name in ("base", "builder", "website", "schedules", "logins"):
        section += f'<h3>{name.title()} <small>{"on" if name in powers else "off"}</small></h3>'
        if name != "base":
            extra = '<label>Signed waiver ID <input name="waiver" required></label>' if name == "logins" else ""
            section += form(token, "powerup-on", "Turn on " + name.title(), f'<input type="hidden" name="name" value="{name}">' + extra)
            section += form(token, "powerup-off", "Turn off " + name.title(), f'<input type="hidden" name="name" value="{name}">')
    if "builder" in powers:
        section += '<h3>Tool access and backups</h3><p>Use your Cloudflare team certs URL and Access application audience. The tunnel token stays on your server.</p>'
        section += form(token, "tools-configure", "Save Access settings", '<label>Team certs URL <input name="certs_url" type="url" required size="55"></label><label>Application audience <input name="audience" required></label>')
        section += form(token, "tools-image", "Set Python runtime image", '<label>Official Python image pinned by SHA256 digest <input name="image" required size="75" placeholder="docker.io/library/python@sha256:..."></label>')
        section += form(token, "tools-connect", "Connect my tool tunnel", '<label>Tunnel token <input name="tunnel_token" type="password" required></label>')
        section += form(token, "tools-backup-key", "Create my tool backup recovery key", '<p>Save the key shown on the next page in your password manager. We do not keep a copy.</p>')
    section += '</section><section><h2>Your tools</h2>'
    if not tools: section += '<p>No tools are registered yet. Turn on Builder, then stage a tool before publishing.</p>'
    for tool in tools:
        name = tool.get("name", "")
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", name): continue
        section += f'<h3>{html.escape(name)}</h3><p>Version {html.escape(str(tool.get("version", "unknown")))}, {"running" if tool.get("up") else "stopped"}.</p>'
        section += form(token, "tool-publish", "Publish " + name, f'<input type="hidden" name="name" value="{name}"><label>Reviewer ID if signed <input name="reviewer"></label><label><input type="checkbox" name="ack_unreviewed" value="yes"> I understand this change was not reviewed by Agent Care</label>')
        section += form(token, "tool-rollback", "Roll back code for " + name, f'<input type="hidden" name="name" value="{name}"><p>Records in the database stay as they are.</p>')
    section += '</section><section><h2>Server controls</h2>'
    section += form(token, "update-pause", "Pause automatic updates") + form(token, "update-now", "Update now")
    section += form(token, "downtime-set", "Set planned downtime", '<label>End time in UTC (YYYY-MM-DDTHH:MM:SSZ) <input name="until" required></label>') + form(token, "downtime-clear", "Clear planned downtime")
    section += form(token, "lockdown", "Stop my assistant", '<p>This stops the assistant and connected services. You will need to restart them yourself.</p><label>Type STOP <input name="confirm" required></label>')
    section += '</section>'
    return section

class Handler(BaseHTTPRequestHandler):
    server_version = "HermesKitActivation"
    def log_message(self, *_): pass
    def send_html(self, code, title, body):
        payload = page(title, body); self.send_response(code); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.send_header("X-Frame-Options", "DENY"); self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def token(self, directory, prefix):
        path = urlparse(self.path).path
        match = re.fullmatch(prefix + r"/([A-Fa-f0-9]{64})(?:/.*)?", path)
        return match.group(1) if match and token_matches(directory, match.group(1)) else None
    def do_GET(self):
        token = self.token(HOME, "/home")
        if token:
            self.send_html(200, "Assistant Home", home_page(token))
            return
        token = self.token(STATE, "/activate")
        if token:
            log = html.escape(read(STATE / "codex-device.log")[-4000:])
            self.send_html(200, "Activate your private Hermes agent", enrollment_notice() + f"<p>Sign in with your own ChatGPT account. This page never displays agent data.</p><form method=post action='/activate/{token}/codex'><button>Show ChatGPT device code</button></form><pre>{log}</pre><form method=post action='/activate/{token}/complete'><button>Finish activation and close this page</button></form>")
            return
        token = self.token(SUPPORT, "/support")
        if token:
            expires = read(SUPPORT / "expires-at", "0"); grant = html.escape(read(SUPPORT / "grant-id", "none")); log = html.escape(read(Path("/var/lib/hermes-kit/access-log.txt"))[-3000:])
            self.send_html(200, "Private support access", f"<p id=countdown data-expiry='{html.escape(expires)}'>Access expires at {html.escape(expires)}.</p><p>Grant: {grant}</p><form method=post action='/support/{token}/revoke'><button>Remove access now</button></form><h2>Client-readable access log</h2><pre>{log}</pre><script>setInterval(()=>{{let e=document.querySelector('#countdown');e.textContent='Access expires in '+Math.max(0,Number(e.dataset.expiry)-Math.floor(Date.now()/1000))+' seconds';}},1000)</script>")
            return
        self.send_html(404, "Unavailable", "<p>This private page is unavailable.</p>")
    def do_POST(self):
        token = self.token(HOME, "/home")
        if token:
            part = urlparse(self.path).path.split("/")[-1]
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 16384:
                self.send_html(413, "Request too large", "<p>Use a shorter key or value.</p>"); return
            fields = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            get = lambda key: fields.get(key, [""])[0].strip()
            commands = {
                "update-pause": ["/usr/local/bin/kit-autoupdate", "pause"],
                "update-now": ["/usr/local/bin/kit-autoupdate", "now"],
                "downtime-clear": ["/usr/local/bin/kit-downtime", "clear"],
            }
            if part in ("powerup-on", "powerup-off") and get("name") in ("builder", "website", "schedules", "logins"):
                commands[part] = ["/usr/local/bin/kit-powerup", "on" if part.endswith("on") else "off", get("name")]
                if part.endswith("on") and get("name") == "logins": commands[part] += ["--waiver", get("waiver")]
            elif part in ("tool-publish", "tool-rollback") and re.fullmatch(r"[a-z][a-z0-9-]{1,31}", get("name")):
                commands[part] = ["/usr/local/bin/kit-tools-publish" if part == "tool-publish" else "/usr/local/bin/kit-tools-rollback", get("name"), "--client", "owner"]
                if part == "tool-publish":
                    if get("reviewer"): commands[part] += ["--reviewer", get("reviewer")]
                    if get("ack_unreviewed") == "yes": commands[part] += ["--ack-unreviewed"]
            elif part == "downtime-set" and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", get("until")):
                commands[part] = ["/usr/local/bin/kit-downtime", "set", get("until")]
            elif part == "tools-configure" and re.fullmatch(r"https://[a-z0-9-]+\.cloudflareaccess\.com/cdn-cgi/access/certs", get("certs_url")) and re.fullmatch(r"[A-Za-z0-9_-]{16,128}", get("audience")):
                commands[part] = ["/usr/local/bin/kit-tools-configure", get("certs_url"), get("audience")]
            elif part == "tools-image" and re.fullmatch(r"docker\.io/library/python@sha256:[0-9a-f]{64}", get("image")):
                commands[part] = ["/usr/local/bin/kit-tools-image", get("image")]
            elif part == "tools-connect" and get("tunnel_token"):
                commands[part] = ["/usr/local/bin/kit-tools-connect", "-"]
            elif part == "manager-revoke": commands[part] = ["/usr/local/bin/kit-manage-revoke"]
            elif part == "full-revoke" and re.fullmatch(r"SHA256:[A-Za-z0-9+/=]+", get("fingerprint")):
                commands[part] = ["/usr/local/bin/kit-full-access", "revoke", get("fingerprint")]
            elif part == "lockdown" and get("confirm") == "STOP": commands[part] = ["/usr/local/bin/kit-lockdown"]
            key_file = None
            if part in ("manager-grant", "full-grant") and get("public_key"):
                with tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="kit-home-key-", dir="/run") as key:
                    key.write(get("public_key") + "\n")
                    key_file = key.name
                if part == "manager-grant": commands[part] = ["/usr/local/bin/kit-manage-grant", "--public-key", key_file]
                elif re.fullmatch(r"[A-Za-z0-9._-]{1,80}", get("waiver")):
                    commands[part] = ["/usr/local/bin/kit-full-access", "grant", key_file, "--waiver", get("waiver")]
            try:
                if part == "tools-backup-key":
                    output = subprocess.run(["/usr/local/bin/kit-tools-backup-key"], text=True, capture_output=True, timeout=20, check=False)
                    if output.returncode == 0:
                        self.send_html(200, "Save your recovery key", '<p>Copy this key to your password manager now. It will not be shown again.</p><pre>' + html.escape(output.stdout) + '</pre>')
                        return
                ok = part in commands and action(commands[part], stdin=get("tunnel_token") if part == "tools-connect" else None)
            finally:
                if key_file: Path(key_file).unlink(missing_ok=True)
            if ok:
                action(["/usr/local/bin/kit-health"])
                self.send_html(200, "Change saved", f'<p>{html.escape(part.replace("-", " ").capitalize())} completed.</p><p><a href="/home/{token}">Back to Assistant Home</a></p>')
            else:
                self.send_html(409, "Change did not complete", f'<p>This action was refused or failed. Your server settings may need a local check.</p><p><a href="/home/{token}">Back to Assistant Home</a></p>')
            return
        token = self.token(STATE, "/activate")
        if token:
            if self.path.endswith("/codex"):
                log = STATE / "codex-device.log"
                if not log.exists():
                    with log.open("w", encoding="utf-8") as output:
                        subprocess.Popen(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes/profiles/client", "PATH=/home/hermes/.local/bin:/usr/local/bin:/usr/bin:/bin", "hermes", "auth", "add", "openai-codex"], stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                self.send_response(303); self.send_header("Location", f"/activate/{token}"); self.end_headers(); return
            if self.path.endswith("/complete"):
                # Do not trust the page alone: an auth store must exist before
                # consuming the one-time activation route.
                if not (Path("/home/hermes/.hermes/auth.json").is_file() or Path("/home/hermes/.hermes/profiles/client/auth.json").is_file()): self.send_html(409, "Sign-in incomplete", "<p>Complete the device-code sign-in first.</p>"); return
                action(["/usr/local/bin/kit-activation", "close"])
                self.send_html(200, "Activation complete", "<p>The activation page is now closed.</p>"); return
        token = self.token(SUPPORT, "/support")
        if token and self.path.endswith("/revoke"):
            action(["/usr/local/bin/kit-activation", "revoke-support"])
            self.send_html(200, "Access removed", "<p>Support access has been removed and this page is closing.</p>"); return
        self.send_html(404, "Unavailable", "<p>This private page is unavailable.</p>")

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
