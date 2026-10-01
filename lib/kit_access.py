"""Root owned access controls for the client kit.

The manager's SSH ForceCommand reaches this module through one sudo rule. No
shell interpretation of SSH_ORIGINAL_COMMAND is permitted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from hermes_runtime import HERMES_BIN
from sshd_transaction import apply as sshd_file_apply

ETC = Path(os.environ.get("KIT_ACCESS_ETC", "/etc/hermes-kit"))
STATE = Path(os.environ.get("KIT_ACCESS_STATE", "/var/lib/hermes-kit"))
PROFILE = Path(os.environ.get("KIT_ACCESS_PROFILE", "/home/hermes/.hermes/profiles/client"))
KIT = Path(__file__).resolve().parent.parent
MANAGER = ETC / "manager" / "authorized_keys"
FULL = ETC / "full" / "authorized_keys"
MANAGER_SSH = Path(os.environ.get("KIT_ACCESS_MANAGER_SSH", "/etc/ssh/kit-manager.keys"))
FULL_SSH = Path(os.environ.get("KIT_ACCESS_FULL_SSH", "/etc/ssh/kit-full.keys"))
EVENTS = STATE / "access-events.log"
KEY = re.compile(r"^(ssh-ed25519|sk-ssh-ed25519@openssh.com) ([A-Za-z0-9+/]+={0,3})(?: [^\r\n]*)?$")
ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
SAFE_KEYS = {"agent.max_turns", "web.search_backend"}
MODEL_PROVIDERS = {"openai-codex", "opencode-zen", "openrouter", "ollama-cloud", "custom"}
FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/=]{32,64}")


def run(argv: list[str], **kwargs):
    kwargs.setdefault("check", True)
    return subprocess.run(argv, text=True, **kwargs)


def require_root():
    if os.geteuid() != 0 and os.environ.get("KIT_ACCESS_TEST_MODE") != "1":
        raise ValueError("Run as root on the client server")


def tier():
    data = (ETC / "kit.conf").read_text() if (ETC / "kit.conf").exists() else ""
    match = re.search(r'^KIT_TIER="?(care|managed|full|ludicrous)"?$', data, re.M)
    return "full" if match and match.group(1) == "ludicrous" else match.group(1) if match else "care"


def event(kind: str, **fields):
    STATE.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = stamp + " " + kind + " " + " ".join(f"{k}={v}" for k, v in fields.items()) + "\n"
    with EVENTS.open("a") as out:
        out.write(line)
    EVENTS.chmod(0o600)
    report = STATE / "access-log.txt"
    with report.open("a") as out:
        out.write(line)
    report.chmod(0o644)


def public_key(path: str):
    lines = Path(path).read_text().splitlines()
    if len(lines) != 1 or not KEY.fullmatch(lines[0]):
        raise ValueError("Expected exactly one Ed25519 public key")
    match = KEY.fullmatch(lines[0])
    assert match
    raw = f"{match.group(1)} {match.group(2)}"
    result = run(["ssh-keygen", "-lf", path], capture_output=True)
    return raw, result.stdout.split()[1]


def write_keys(path: Path, keys: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o755)
    temp = path.with_suffix(".tmp")
    temp.write_text("".join(k + "\n" for k in keys))
    temp.chmod(0o600)
    temp.replace(path)


def mirror_ssh(source: Path, target: Path):
    if os.environ.get("KIT_ACCESS_TEST_MODE") == "1":
        return
    target.write_text(source.read_text())
    target.chmod(0o644)


def tree_digest(path: Path):
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if child.is_symlink():
            raise ValueError("Symlink in managed skill")
        if child.is_file():
            digest.update(str(child.relative_to(path)).encode() + b"\0" + child.read_bytes())
    return digest.hexdigest()


def ssh_reload():
    if os.environ.get("KIT_ACCESS_TEST_MODE") == "1":
        return
    run(["sshd", "-t"])
    run(["systemctl", "reload", "ssh"])


def setup_manager():
    if shutil.which("useradd") and run(["id", "-u", "kit-manager"], capture_output=True, check=False).returncode:
        run(["useradd", "--system", "--create-home", "--shell", "/bin/sh", "kit-manager"])
    sudoers = Path("/etc/sudoers.d/91-hermes-kit-manager")
    sudoers.write_text("kit-manager ALL=(root) NOPASSWD: /usr/local/sbin/kit-manage-dispatch *\n")
    sudoers.chmod(0o440)
    run(["visudo", "-cf", str(sudoers)])
    conf = Path("/etc/ssh/sshd_config.d/11-hermes-kit-manager.conf")
    sshd_file_apply(conf, """Match User kit-manager
    AuthenticationMethods publickey
    AuthorizedKeysFile /etc/ssh/kit-manager.keys
    ForceCommand /usr/local/sbin/kit-manage-dispatch
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    PermitTTY no
    AllowTcpForwarding no
    AllowAgentForwarding no
    X11Forwarding no
    PermitTunnel no
""")
    if MANAGER.exists():
        mirror_ssh(MANAGER, MANAGER_SSH)


def grant_manager(path: str):
    require_root()
    if tier() != "managed":
        raise ValueError("Manager access requires Managed tier")
    key, fingerprint = public_key(path)
    if os.environ.get("KIT_ACCESS_TEST_MODE") != "1":
        setup_manager()
    existing = MANAGER.read_text().splitlines() if MANAGER.exists() else []
    entry = 'restrict,command="/usr/local/sbin/kit-manage-dispatch" ' + key
    if entry not in existing:
        write_keys(MANAGER, existing + [entry])
    mirror_ssh(MANAGER, MANAGER_SSH)
    ssh_reload()
    event("manager-granted", fingerprint=fingerprint)


def revoke_manager(fingerprint: str | None):
    require_root()
    lines = MANAGER.read_text().splitlines() if MANAGER.exists() else []
    if fingerprint:
        if not fingerprint.startswith("SHA256:"):
            raise ValueError("Expected SHA256 fingerprint")
        kept = []
        for line in lines:
            plain = line[line.index("ssh-ed25519 "):] if "ssh-ed25519 " in line else line[line.index("sk-ssh-ed25519@openssh.com "):]
            proc = subprocess.run(["ssh-keygen", "-lf", "/dev/stdin"], input=plain + "\n", text=True, capture_output=True)
            if proc.returncode or fingerprint not in proc.stdout:
                kept.append(line)
    else:
        kept = []
    write_keys(MANAGER, kept)
    mirror_ssh(MANAGER, MANAGER_SSH)
    if os.environ.get("KIT_ACCESS_TEST_MODE") != "1":
        run(["loginctl", "terminate-user", "kit-manager"], check=False)
    ssh_reload()
    event("manager-revoked", fingerprint=fingerprint or "all")


def remove_team_key(fingerprint: str):
    require_root()
    if not FINGERPRINT.fullmatch(fingerprint):
        raise ValueError("Expected SHA256 fingerprint")
    changes = []
    for path, mirror in ((MANAGER, MANAGER_SSH), (FULL, FULL_SSH)):
        lines = path.read_text().splitlines() if path.exists() else []
        kept = []
        for line in lines:
            match = re.search(r"(?:^|\s)((?:sk-)?ssh-ed25519(?:@openssh.com)?)\s+([A-Za-z0-9+/=]+)", line)
            if not match:
                kept.append(line)
                continue
            key = f"{match.group(1)} {match.group(2)}"
            result = subprocess.run(["ssh-keygen", "-lf", "/dev/stdin"], input=key + "\n", text=True, capture_output=True)
            if result.returncode or result.stdout.split()[1] != fingerprint:
                kept.append(line)
        if len(kept) != len(lines):
            changes.append((path, mirror, kept))
    for path, mirror, kept in changes:
        write_keys(path, kept)
        mirror_ssh(path, mirror)
    if changes:
        ssh_reload()
        if os.environ.get("KIT_ACCESS_TEST_MODE") != "1":
            for path, _, _ in changes:
                run(["loginctl", "terminate-user", "kit-manager" if path == MANAGER else "hermes-ops"], check=False)
    event("team-key-removed", fingerprint=fingerprint, locations=",".join(path.parent.name for path, _, _ in changes) or "none")


def full_access(action: str, path_or_fingerprint: str, waiver: str | None):
    require_root()
    if tier() != "full":
        raise ValueError("Full access requires Full Service tier")
    if action == "grant":
        if not waiver or not ID.fullmatch(waiver):
            raise ValueError("A signed waiver id is required")
        key, fingerprint = public_key(path_or_fingerprint)
        if os.environ.get("KIT_ACCESS_TEST_MODE") != "1":
            if run(["id", "-u", "hermes-ops"], check=False, capture_output=True).returncode:
                run(["useradd", "--create-home", "--shell", "/usr/bin/tlog-rec-session", "hermes-ops"])
            sudoers = Path("/etc/sudoers.d/90-hermes-kit-hermes-ops")
            sudoers.write_text("hermes-ops ALL=(ALL:ALL) NOPASSWD: ALL\n")
            sudoers.chmod(0o440)
            run(["visudo", "-cf", str(sudoers)])
            # Existing certificate grants retain their CA and revocation policy.
            conf = Path("/etc/ssh/sshd_config.d/10-hermes-kit-access.conf")
            if not conf.exists():
                text = """TrustedUserCAKeys /etc/ssh/kit/client-ca.pub
AuthorizedPrincipalsFile /etc/ssh/auth_principals/%u
RevokedKeys /etc/ssh/kit/revoked.krl
Match User hermes-ops
    AuthenticationMethods publickey
    AuthorizedKeysFile /etc/ssh/kit-full.keys
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AllowTcpForwarding no
    X11Forwarding no
    PermitTunnel no
    PermitTTY yes
"""
                principals = Path("/etc/ssh/auth_principals/hermes-ops")
                principals.write_text("ops\n")
                principals.chmod(0o644)
            else:
                text = conf.read_text()
            text = text.replace("AuthorizedKeysFile none", "AuthorizedKeysFile /etc/ssh/kit-full.keys")
            text = re.sub(r"(?im)^[ \t]*PermitUserEnvironment[ \t]+[^\n]*\n", "", text)
            sshd_file_apply(conf, text)
        lines = FULL.read_text().splitlines() if FULL.exists() else []
        if key not in lines:
            write_keys(FULL, lines + [key])
        mirror_ssh(FULL, FULL_SSH)
        ssh_reload()
        event("full-granted", waiver=waiver, fingerprint=fingerprint)
    elif action == "revoke":
        fingerprint = path_or_fingerprint
        if not fingerprint.startswith("SHA256:"):
            raise ValueError("Expected SHA256 fingerprint")
        lines = FULL.read_text().splitlines() if FULL.exists() else []
        kept = []
        for line in lines:
            proc = subprocess.run(["ssh-keygen", "-lf", "/dev/stdin"], input=line + "\n", text=True, capture_output=True)
            if proc.returncode or fingerprint not in proc.stdout:
                kept.append(line)
        write_keys(FULL, kept)
        mirror_ssh(FULL, FULL_SSH)
        if os.environ.get("KIT_ACCESS_TEST_MODE") != "1":
            run(["loginctl", "terminate-user", "hermes-ops"], check=False)
            if not kept and not list(Path("/var/lib/hermes-kit/grants").glob("*-cert.pub")):
                sshd_file_apply(Path("/etc/ssh/sshd_config.d/10-hermes-kit-access.conf"), None)
                for file in (Path("/etc/sudoers.d/90-hermes-kit-hermes-ops"), Path("/etc/ssh/auth_principals/hermes-ops")):
                    file.unlink(missing_ok=True)
                run(["userdel", "--remove", "hermes-ops"], check=False)
        ssh_reload()
        event("full-revoked", fingerprint=fingerprint)


def menu(command: str):
    try:
        args = shlex.split(command)
    except ValueError:
        args = []
    if not args:
        raise ValueError("Command refused")
    op = args[0]
    expected = {"status": 1, "verify": 1, "show-config": 1, "restart": 1,
                "update-now": 1, "config-get": 2, "config-set": 3,
                "powerup-on": 2, "powerup-off": 2, "skill-install": 2,
                "skill-remove": 2, "model-set": 3, "team-key-remove": 2}
    if op not in expected or len(args) != expected[op]:
        raise ValueError("Command refused")
    if op.startswith("config-"):
        if args[1] not in SAFE_KEYS:
            raise ValueError("Key refused")
        if op == "config-set":
            if args[1] == "agent.max_turns" and (not args[2].isdigit() or not 1 <= int(args[2]) <= 100):
                raise ValueError("Value refused")
            if args[1] == "web.search_backend" and args[2] != "searxng":
                raise ValueError("Value refused")
    if op.startswith("powerup-") and args[1] not in {"builder", "website", "schedules", "logins"}:
        raise ValueError("Power-up refused")
    if op == "model-set" and (args[1] not in MODEL_PROVIDERS or not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", args[2])):
        raise ValueError("Model refused")
    if op.startswith("skill-") and not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", args[1]):
        raise ValueError("Skill refused")
    if op == "team-key-remove" and not FINGERPRINT.fullmatch(args[1]):
        raise ValueError("Expected SHA256 fingerprint")
    return args


def dispatch(command: str):
    require_root()
    try:
        args = menu(command)
        event("manager-command", command=args[0], outcome="started")
        _execute(args)
    except (ValueError, OSError, subprocess.CalledProcessError):
        event("manager-command", command=hashlib.sha256(command.encode()).hexdigest()[:16], outcome="refused")
        raise
    event("manager-command", command=args[0], outcome="accepted")


def _execute(args: list[str]):
    op = args[0]
    if op == "status":
        print((STATE / "health.json").read_text())
    elif op == "verify":
        run(["/usr/local/bin/kit-verify", "--json"])
    elif op == "show-config":
        print((PROFILE / "config.yaml").read_text())
    elif op in {"config-get", "config-set"}:
        run(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client", "config", "get" if op == "config-get" else "set", *args[1:]])
    elif op.startswith("powerup-"):
        run(["/usr/local/bin/kit-powerup", "on" if op.endswith("on") else "off", args[1]])
    elif op.startswith("skill-"):
        catalog = json.loads((KIT / "catalog" / "skills.json").read_text())
        if args[1] not in catalog:
            raise ValueError("Skill is outside the reviewed catalog")
        source = KIT / catalog[args[1]]
        dest = PROFILE / "skills" / args[1]
        marker = ETC / "manager" / "skills" / args[1]
        if op == "skill-install":
            if dest.exists() and not marker.exists():
                raise ValueError("Refusing to overwrite a client skill")
            if not dest.exists():
                shutil.copytree(source, dest)
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(tree_digest(dest))
            run(["chown", "-R", "hermes:hermes", str(dest)])
            ledger = ETC / "consents.json"
            data = json.loads(ledger.read_text()) if ledger.exists() else {"consents": []}
            if not any(x.get("integration") == args[1] for x in data["consents"]):
                data["consents"].append({"integration": args[1], "client_name": "Managed", "date": dt.date.today().isoformat(), "scopes": ["reviewed skill"], "risk_level": "YELLOW", "warnings_shown": "Reviewed catalog skill", "confirmation": "manager-menu"})
                ledger.write_text(json.dumps(data) + "\n")
                ledger.chmod(0o600)
        elif marker.exists():
            if tree_digest(dest) != marker.read_text():
                raise ValueError("Skill changed since installation")
            shutil.rmtree(dest)
            marker.unlink()
            ledger = ETC / "consents.json"
            if ledger.exists():
                data = json.loads(ledger.read_text())
                data["consents"] = [x for x in data.get("consents", []) if x.get("integration") != args[1]]
                ledger.write_text(json.dumps(data) + "\n")
                ledger.chmod(0o600)
    elif op == "model-set":
        for key, value in (("model.provider", args[1]), ("model.model", args[2])):
            run(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client", "config", "set", key, value])
    elif op == "restart":
        run(["systemctl", "restart", "hermes-gateway.service"])
    elif op == "update-now":
        run(["/usr/local/bin/kit-autoupdate", "now"])
    elif op == "team-key-remove":
        remove_team_key(args[1])


def main():
    try:
        name = Path(sys.argv[0]).name
        if name == "kit-manage-grant":
            parser = argparse.ArgumentParser(); parser.add_argument("--public-key", required=True)
            grant_manager(parser.parse_args().public_key)
        elif name == "kit-manage-revoke":
            parser = argparse.ArgumentParser(); parser.add_argument("fingerprint", nargs="?")
            revoke_manager(parser.parse_args().fingerprint)
        elif name == "kit-full-access":
            parser = argparse.ArgumentParser(); parser.add_argument("action", choices=["grant", "revoke"])
            parser.add_argument("key_or_fingerprint"); parser.add_argument("--waiver")
            a = parser.parse_args(); full_access(a.action, a.key_or_fingerprint, a.waiver)
        elif name == "kit-manage-dispatch":
            if os.geteuid() != 0:
                original = os.environ.get("SSH_ORIGINAL_COMMAND", "")
                os.execv("/usr/bin/sudo", ["sudo", "-n", "/usr/local/sbin/kit-manage-dispatch", original])
            if len(sys.argv) != 2:
                raise ValueError("Command refused")
            dispatch(sys.argv[1])
        else:
            raise ValueError("Unknown command")
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
