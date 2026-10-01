"""Owner-controlled, staged client tool publishing and backup lane."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from urllib.request import urlopen
from datetime import datetime, timezone

KIT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("KIT_TOOLS_ROOT", "/srv/tools"))
ETC = Path(os.environ.get("KIT_TOOLS_ETC", "/etc/hermes-kit"))
BACKUP = Path(os.environ.get("KIT_TOOLS_BACKUP", "/var/backups/tools"))
REGISTRY = ROOT / "registry.json"
NAME = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
HASH = re.compile(r"^[0-9a-f]{40}$")
TEST = os.environ.get("KIT_TOOLS_TEST_MODE") == "1"
DATA_GROUP = "kit-tool-data"


def run(args, *, cwd=None, input=None, capture=False, user=None, check=True):
    argv = list(map(str, args))
    if user and not TEST:
        argv = ["runuser", "-u", user, "--", *argv]
    return subprocess.run(argv, cwd=cwd, input=input, text=True, check=check, capture_output=capture)


def root():
    if os.geteuid() != 0 and not TEST:
        raise ValueError("Run as root with the client present")


def valid_name(name):
    if not NAME.fullmatch(name):
        raise ValueError("Invalid tool name")
    return name


def registry():
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {"tools": []}


def save_registry(data):
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.chmod(0o644)
    tmp.replace(REGISTRY)


def entry(data, name):
    found = next((tool for tool in data["tools"] if tool["name"] == name), None)
    if found is None:
        found = {"name": name, "up": False, "version": "staged", "last_backup_ok_hours": 999999, "tests_ok": False}
        data["tools"].append(found)
    return found


def allocate_port(data):
    used = {int(tool["port"]) for tool in data["tools"] if tool.get("port")}
    for port in range(8801, 9000):
        if port in used:
            continue
        if TEST:
            return port
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise ValueError("No free tool port in 8801..8999")


def consent():
    path = ETC / "consents.json"
    return path.exists() and any(x.get("integration") == "builder" for x in json.loads(path.read_text()).get("consents", []))


def tailnet_mode():
    path = ETC / "consents.json"
    return path.exists() and any(x.get("integration") == "tailscale" for x in json.loads(path.read_text()).get("consents", []))


def need_builder():
    if not consent() and not TEST:
        raise ValueError("Builder power-up is off")


def stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def unique_stamp():
    return stamp().replace(":", "") + "-" + os.urandom(4).hex()


def audit(action, name, **details):
    path = ROOT / "publish-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as out:
        out.write(json.dumps({"at": stamp(), "action": action, "tool": name, **details}, sort_keys=True) + "\n")
    path.chmod(0o600)


def protect_data_parent():
    """Migrate existing tool accounts before closing the shared parent."""
    parent = ROOT / "data"
    ROOT.mkdir(parents=True, exist_ok=True)
    ROOT.chmod(0o755)
    parent.mkdir(mode=0o700, exist_ok=True)
    # Close an older 0711 parent before inspecting its children.
    parent.chmod(0o700)
    changed = []
    if not TEST:
        run(["chown", "root:root", ROOT])
        run(["groupadd", "--force", DATA_GROUP])
        for child in parent.iterdir():
            if not child.is_dir() or not NAME.fullmatch(child.name):
                continue
            user = "tool-" + child.name
            if run(["id", "-u", user], capture=True, check=False).returncode:
                continue
            groups = run(["id", "-nG", user], capture=True).stdout.split()
            if DATA_GROUP not in groups:
                run(["usermod", "-a", "-G", DATA_GROUP, user])
                changed.append(child.name)
        run(["chown", f"root:{DATA_GROUP}", parent])
    parent.chmod(0o710)
    if not TEST:
        for name in changed:
            run(["systemctl", "try-restart", f"hermes-kit-tool-{name}.service"], check=False)


def setup():
    root()
    if not TEST:
        run(["apt-get", "-y", "--no-install-recommends", "install", "podman", "uidmap", "nftables", "age"])
        if not tailnet_mode() and not shutil.which("cloudflared"):
            keyring = Path("/usr/share/keyrings/cloudflare-main.gpg")
            run(["curl", "--fail", "--silent", "--show-error", "--location", "https://pkg.cloudflare.com/cloudflare-main.gpg", "--output", keyring])
            keyring.chmod(0o644)
            Path("/etc/apt/sources.list.d/cloudflared.list").write_text("deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main\n")
            run(["apt-get", "update"])
            run(["apt-get", "-y", "--no-install-recommends", "install", "cloudflared"])
        if run(["id", "-u", "builder"], capture=True, check=False).returncode:
            run(["useradd", "--create-home", "--shell", "/bin/bash", "builder"])
        ensure_subids("builder")
        run(["loginctl", "enable-linger", "builder"])
        if not tailnet_mode() and run(["id", "-u", "cloudflared"], capture=True, check=False).returncode:
            run(["useradd", "--system", "--home", "/var/lib/cloudflared", "--shell", "/usr/sbin/nologin", "cloudflared"])
    for path in (ROOT / "src", ROOT / "staging", ROOT / "releases", BACKUP):
        path.mkdir(parents=True, exist_ok=True)
    BACKUP.chmod(0o700)
    (ROOT / "releases").chmod(0o755)
    if not TEST:
        run(["chown", "builder:builder", ROOT / "src", ROOT / "staging"])
    protect_data_parent()
    if not TEST:
        install_firewall()
    if not REGISTRY.exists():
        save_registry({"tools": []})


def ensure_tool(name):
    valid_name(name)
    user = "tool-" + name
    if not TEST and run(["id", "-u", user], capture=True, check=False).returncode:
        run(["useradd", "--system", "--create-home", "--shell", "/usr/sbin/nologin", user])
    if not TEST:
        run(["usermod", "-a", "-G", DATA_GROUP, user])
        ensure_subids(user)
        run(["loginctl", "enable-linger", user])
    data = ROOT / "data" / name
    data.mkdir(parents=True, exist_ok=True)
    data.chmod(0o700)
    if not TEST:
        run(["chown", "-R", f"{user}:{user}", data])
        install_firewall()
    return user


def ensure_subids(user):
    """Allocate a non-overlapping 65536-ID range for rootless Podman."""
    if TEST:
        return
    files = (Path("/etc/subuid"), Path("/etc/subgid"))
    if all(any(line.startswith(user + ":") for line in path.read_text().splitlines()) for path in files):
        return
    used = []
    for path in files:
        for line in path.read_text().splitlines():
            parts = line.split(":")
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                used.append((int(parts[1]), int(parts[1]) + int(parts[2]) - 1))
    start = 100000
    while any(not (start + 65535 < lo or start > hi) for lo, hi in used):
        start += 65536
    run(["usermod", "--add-subuids", f"{start}-{start + 65535}", "--add-subgids", f"{start}-{start + 65535}", user])


def install_firewall():
    """Install per-UID nftables output policy; rules persist across reboot."""
    if TEST:
        return
    users = ["builder"] + ["tool-" + p.name for p in (ROOT / "data").iterdir() if NAME.fullmatch(p.name)]
    ids = {user: int(run(["id", "-u", user], capture=True).stdout.strip()) for user in users}
    hosts = ("api.openai.com", "api.openrouter.ai", "api.ollama.com", "registry.npmjs.org", "pypi.org", "files.pythonhosted.org", "github.com", "api.github.com", "objects.githubusercontent.com")
    addresses = {"127.0.0.1"}
    for host in hosts:
        result = run(["getent", "ahostsv4", host], capture=True, check=False)
        addresses.update(line.split()[0] for line in result.stdout.splitlines() if line and re.fullmatch(r"[0-9.]+", line.split()[0]))
    dns_addresses = set()
    for line in Path("/etc/resolv.conf").read_text().splitlines():
        if line.startswith("nameserver ") and re.fullmatch(r"[0-9.]+", line.split()[1]):
            dns_addresses.add(line.split()[1])
    lines = ["table inet hermes_kit_tools {", "set builder_ipv4 { type ipv4_addr; flags interval; elements = { " + ", ".join(sorted(addresses)) + " } }", "set dns_ipv4 { type ipv4_addr; flags interval; elements = { " + ", ".join(sorted(dns_addresses or {"127.0.0.1"})) + " } }", "chain output { type filter hook output priority 0; policy accept;"]
    if tailnet_mode():
        ports = sorted({int(item["port"]) for item in registry().get("tools", []) if isinstance(item.get("port"), int) and 8801 <= item["port"] <= 8999})
        if ports:
            lines.append("ip daddr 127.0.0.1 tcp dport { " + ", ".join(map(str, ports)) + " } meta skuid != 0 drop")
    for user, uid in ids.items():
        lines += [f"meta skuid {uid} ip daddr 127.0.0.0/8 accept", f"meta skuid {uid} ip6 daddr ::1 accept"]
        if user == "builder":
            lines += [f"meta skuid {uid} ip daddr @dns_ipv4 udp dport 53 accept", f"meta skuid {uid} ip daddr @dns_ipv4 tcp dport 53 accept", f"meta skuid {uid} ip daddr @builder_ipv4 tcp dport 443 accept"]
        lines += [f"meta skuid {uid} drop"]
    lines += ["}", "}"]
    rules = ETC / "tools-egress.nft"
    rules.write_text("\n".join(lines) + "\n")
    rules.chmod(0o644)
    run(["nft", "delete", "table", "inet", "hermes_kit_tools"], check=False)
    run(["nft", "-f", rules])
    unit = Path("/etc/systemd/system/hermes-kit-tools-egress.service")
    unit.write_text("[Unit]\nDescription=Hermes Kit tool user egress policy\nAfter=nftables.service\nBefore=network-online.target\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStartPre=-/usr/sbin/nft delete table inet hermes_kit_tools\nExecStart=/usr/sbin/nft -f /etc/hermes-kit/tools-egress.nft\n[Install]\nWantedBy=multi-user.target\n")
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "hermes-kit-tools-egress.service"])


def stage(name, source=None, template=False, commit=None):
    root(); need_builder(); setup(); user = ensure_tool(name)
    bare = ROOT / "src" / (name + ".git")
    if template:
        if name != "lead-tracker" or bare.exists():
            raise ValueError("Template can seed only a new lead-tracker repo")
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            shutil.copytree(KIT / "templates" / "tools" / "lead-tracker", work / "code")
            run(["git", "init", "-q", work / "code"])
            run(["git", "add", "."], cwd=work / "code")
            run(["git", "-c", "user.name=Hermes Kit", "-c", "user.email=kit@localhost", "commit", "-qm", "Initial Lead Tracker"], cwd=work / "code")
            run(["git", "clone", "--bare", work / "code", bare])
    elif source:
        if not Path(source).is_dir():
            raise ValueError("Source must be a local git repository")
        if bare.exists():
            run(["git", "-c", f"safe.directory={bare}", "-c", f"safe.directory={Path(source).resolve()}", "-C", bare, "fetch", source, "+refs/heads/*:refs/heads/*"])
        else:
            run(["git", "-c", f"safe.directory={Path(source).resolve()}", "clone", "--bare", source, bare])
    elif not bare.exists():
        raise ValueError("No source repository; use --source or --template")
    if not TEST:
        run(["chown", "-R", "builder:builder", bare])
    resolved = run(["git", "-c", f"safe.directory={bare}", "-C", bare, "rev-parse", "--verify", (commit or "HEAD") + "^{commit}"], capture=True).stdout.strip()
    if not HASH.fullmatch(resolved):
        raise ValueError("Invalid commit")
    target = ROOT / "staging" / name / resolved
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        if not TEST:
            run(["chown", "builder:builder", target.parent])
            target.parent.chmod(0o700)
        run(["git", "clone", "--quiet", "--no-hardlinks", bare, target], user="builder")
        run(["git", "-C", target, "checkout", "--quiet", "--detach", resolved], user="builder")
    safe_tree(target)
    test_tool(target, user="builder")
    data = registry(); item = entry(data, name); item["staged"] = resolved; item["tests_ok"] = True
    if not item.get("port"):
        item["port"] = allocate_port(data)
    save_registry(data)
    if not TEST and tailnet_mode():
        install_firewall()
    audit("stage", name, commit=resolved)
    print(resolved)


def safe_tree(path):
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ValueError("Symlinks are not allowed in tool code")


def materialize_commit(bare, commit, destination):
    """Extract only tracked files from the immutable Git commit object."""
    archive = subprocess.run(["git", "-c", f"safe.directory={bare}", "-C", str(bare), "archive", "--format=tar", commit], capture_output=True, check=True).stdout
    destination.mkdir(parents=True, exist_ok=False)
    import io
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as members:
        for member in members.getmembers():
            relative = Path(member.name)
            if member.issym() or member.islnk() or relative.is_absolute() or ".." in relative.parts or not (member.isfile() or member.isdir()):
                raise ValueError("Unsafe object in tool commit")
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(members.extractfile(member).read())
    safe_tree(destination)


def hash_tree(path):
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if not item.is_file() or ".git" in item.parts or "__pycache__" in item.parts:
            continue
        digest.update(str(item.relative_to(path)).encode() + b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def make_release_readonly(path):
    for item in [path, *path.rglob("*")]:
        if item.is_dir():
            item.chmod(0o555)
        elif item.is_file():
            item.chmod(0o555 if item.stat().st_mode & 0o111 else 0o444)


def test_tool(path, user=None):
    if not (path / "tests").is_dir():
        raise ValueError("Tool has no tests")
    run(["python3", "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=path, user=user)


def migration_files(path):
    files = sorted((path / "migrations").glob("*.sql"))
    if not files:
        raise ValueError("Tool has no expand-only migrations")
    for file in files:
        sql = file.read_text().upper()
        if re.search(r"\b(DROP|RENAME|DELETE|TRUNCATE|VACUUM|REPLACE|UPDATE)\b", sql):
            raise ValueError("Destructive migration refused")
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement and not (statement.startswith("CREATE TABLE IF NOT EXISTS ") or statement.startswith("CREATE INDEX IF NOT EXISTS ") or re.match(r"ALTER TABLE [A-Z0-9_]+ ADD COLUMN [A-Z0-9_]+ ", statement)):
                raise ValueError("Migration is outside the expand-only grammar")
    return files


def apply_migrations(conn, files):
    """Apply the checked expand-only grammar, including to older restored DBs."""
    for file in files:
        for statement in file.read_text().split(";"):
            statement = statement.strip()
            if not statement:
                continue
            add = re.match(r"ALTER TABLE ([A-Za-z0-9_]+) ADD COLUMN ([A-Za-z0-9_]+)\b", statement, re.I)
            if add:
                columns = {row[1].lower() for row in conn.execute(f"PRAGMA table_info({add[1]})")}
                if add[2].lower() in columns:
                    continue
            conn.execute(statement)


def reviewer_signature(name, commit, reviewer):
    signature = ROOT / "src" / "signatures" / name / (commit + ".sig")
    allowed = ETC / "tools.allowed_signers"
    if not signature.is_file() or not allowed.is_file() or not reviewer:
        return False
    return run(["ssh-keygen", "-Y", "verify", "-f", allowed, "-I", reviewer, "-n", "hermes-tool-release", "-s", signature], input=commit + "\n", capture=True, check=False).returncode == 0


def scan(path):
    scanner = shutil.which("osv-scanner")
    if not scanner:
        return "skipped"
    run([scanner, "scan", "--recursive", path], user="builder")
    return "clean"


def snapshot(db, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.parent.chmod(0o700)
    source = sqlite3.connect(db)
    source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    copy = sqlite3.connect(dest)
    source.backup(copy)
    copy.close(); source.close()
    dest.chmod(0o600)
    checksum = hashlib.sha256(dest.read_bytes()).hexdigest()
    dest.with_suffix(dest.suffix + ".sha256").write_text(checksum + "  " + dest.name + "\n")
    dest.with_suffix(dest.suffix + ".sha256").chmod(0o600)
    return checksum


def publish(name, client, reviewer=None, ack_unreviewed=False):
    root(); need_builder(); valid_name(name)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", client):
        raise ValueError("Client owner id required")
    data = registry(); item = entry(data, name); commit = item.get("staged", "")
    if not HASH.fullmatch(commit):
        raise ValueError("No staged commit")
    staged = ROOT / "staging" / name / commit
    if not staged.exists() or run(["git", "-c", f"safe.directory={staged}", "-C", staged, "rev-parse", "HEAD"], capture=True).stdout.strip() != commit:
        raise ValueError("Staged commit changed")
    if not reviewer_signature(name, commit, reviewer) and not ack_unreviewed:
        raise ValueError("Reviewer signature or explicit unreviewed acknowledgment required")
    if reviewer and not reviewer_signature(name, commit, reviewer):
        raise ValueError("Reviewer signature invalid")
    review = reviewer if reviewer else "unreviewed-client-ack"
    bare = ROOT / "src" / (name + ".git")
    if run(["git", "-c", f"safe.directory={bare}", "-C", bare, "cat-file", "-t", commit], capture=True).stdout.strip() != "commit":
        raise ValueError("Staged commit is not in the tool repository")
    clean_parent = Path(tempfile.mkdtemp(prefix=".publish-", dir=ROOT / "staging" / name))
    clean = clean_parent / "code"
    try:
        materialize_commit(bare, commit, clean)
        if not TEST:
            run(["chown", "-R", "builder:builder", clean_parent])
        files = migration_files(clean)
        test_tool(clean, user="builder")
        scan_result = scan(clean)
        _publish_checked(name, client, reviewer, ack_unreviewed, data, item, commit, clean, files, scan_result)
    finally:
        shutil.rmtree(clean_parent)


def _publish_checked(name, client, reviewer, ack_unreviewed, data, item, commit, clean, files, scan_result):
    review = reviewer if reviewer else "unreviewed-client-ack"
    before = json.loads(json.dumps(data))
    if not TEST:
        validate_runtime()
    user = ensure_tool(name)
    data_dir = ROOT / "data" / name
    db = data_dir / "tool.db"
    if not db.exists():
        sqlite3.connect(db).close()
        if not TEST:
            run(["chown", f"{user}:{user}", db])
    applied_file = data_dir / "migrations.json"
    applied = json.loads(applied_file.read_text()) if applied_file.exists() else []
    pending = [file for file in files if file.name not in applied]
    # Prove pending migrations on a disposable copy before maintenance begins.
    with tempfile.TemporaryDirectory() as temporary:
        trial = Path(temporary) / "trial.db"
        snapshot(db, trial)
        with sqlite3.connect(trial) as conn:
            apply_migrations(conn, pending)
    maintenance = data_dir / "maintenance"
    maintenance.touch()
    previous = item.get("commit")
    try:
        snap = BACKUP / name / (unique_stamp() + ".db")
        checksum = snapshot(db, snap)
        with sqlite3.connect(db) as conn:
            apply_migrations(conn, pending)
        applied_file.write_text(json.dumps(applied + [file.name for file in pending]))
        if not TEST:
            run(["chown", f"{user}:{user}", applied_file])
        release = ROOT / "releases" / name / commit
        (ROOT / "releases").chmod(0o755)
        if not release.exists():
            release.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(clean, release, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
            if not TEST:
                run(["chown", "-R", "root:root", release])
        elif hash_tree(release) != hash_tree(clean):
            raise ValueError("Existing release does not match the staged commit")
        release.parent.chmod(0o755)
        make_release_readonly(release)
        current = release.parent / "current"
        temp_link = release.parent / ".current-next"
        temp_link.unlink(missing_ok=True)
        temp_link.symlink_to(release)
        temp_link.replace(current)
        port = item.get("port") or allocate_port(data)
        if not TEST:
            install_service(name, user, port)
            run(["systemctl", "restart", f"hermes-kit-tool-{name}.service"])
            if not origin_denies_without_token(port):
                raise ValueError("Tool origin failed its no-token health check")
        item.update({"commit": commit, "previous": previous or "none", "version": commit[:12], "up": True,
                     "tests_ok": True, "scan": scan_result, "snapshot_sha256": checksum, "snapshot_file": snap.name, "last_snapshot": stamp(), "reviewer": review,
                     "code_hash": hash_tree(release), "port": port})
        save_registry(data)
        if not TEST:
            backup({name})
        audit("publish", name, commit=commit, client=client, reviewer=review, scan=scan_result, snapshot_sha256=checksum)
    except Exception:
        save_registry(before)
        if previous:
            current = ROOT / "releases" / name / "current"
            next_link = current.parent / ".current-revert"
            next_link.unlink(missing_ok=True)
            next_link.symlink_to(ROOT / "releases" / name / previous)
            next_link.replace(current)
        else:
            (ROOT / "releases" / name / "current").unlink(missing_ok=True)
            if not TEST:
                run(["systemctl", "stop", f"hermes-kit-tool-{name}.service"], check=False)
        raise
    finally:
        maintenance.unlink(missing_ok=True)


def install_service(name, user, port):
    image = validate_runtime()
    local_image = prepare_image(user, image)
    if tailnet_mode():
        (ROOT / "access.json").write_text('{"mode":"tailscale"}\n')
        (ROOT / "access-certs.json").write_text('{}\n')
    else:
        shutil.copy2(ETC / "tools-access.json", ROOT / "access.json")
    (ROOT / "access.json").chmod(0o644)
    unit = Path(f"/etc/systemd/system/hermes-kit-tool-{name}.service")
    uid = run(["id", "-u", user], capture=True).stdout.strip()
    unit.write_text(f"""[Unit]
Description=Client tool {name}
After=network-online.target hermes-kit-tools-egress.service
[Service]
User={user}
Group={user}
Environment=HOME=/home/{user}
Environment=XDG_RUNTIME_DIR=/run/user/{uid}
Environment=TOOL_DATA=/data
Environment=TOOL_ACCESS_CONFIG=/run/access.json
Environment=TOOL_ACCESS_CERTS=/run/access-certs.json
ExecStart=/usr/bin/podman run --pull=never --rm --name kit-{name} --userns=keep-id --cap-drop=all --security-opt=no-new-privileges --read-only --pids-limit=128 --memory=512m --network=slirp4netns -p 127.0.0.1:{port}:8080 -v /srv/tools/releases/{name}/current:/app:ro -v /srv/tools/data/{name}:/data:rw -v /srv/tools/access.json:/run/access.json:ro -v /srv/tools/access-certs.json:/run/access-certs.json:ro -w /app {local_image} python3 app.py
ExecStop=/usr/bin/podman stop kit-{name}
Restart=on-failure
ProtectSystem=strict
ProtectHome=no
InaccessiblePaths=/home/hermes /var/lib/hermes-support
ReadWritePaths=/home/{user} /run/user/{uid} /srv/tools/data/{name}
[Install]
WantedBy=multi-user.target
""")
    unit.chmod(0o644)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", f"hermes-kit-tool-{name}.service"])


def prepare_image(user, pinned_image):
    """Import a pinned root-fetched image into a tool user's offline store."""
    if TEST:
        return pinned_image
    uid = run(["id", "-u", user], capture=True).stdout.strip()
    runtime = ["env", f"HOME=/home/{user}", f"XDG_RUNTIME_DIR=/run/user/{uid}"]
    if run(["podman", "image", "exists", pinned_image], check=False).returncode:
        run(["podman", "pull", pinned_image])
    image_id = canonical_image_id(run(["podman", "image", "inspect", "--format", "{{.Id}}", pinned_image], capture=True).stdout.strip())
    if run([*runtime, "podman", "image", "exists", image_id], user=user, check=False).returncode:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            archive = Path(temporary) / "image.tar"
            run(["podman", "save", "--format", "docker-archive", "-o", archive, pinned_image])
            Path(temporary).chmod(0o755)
            archive.chmod(0o644)
            run([*runtime, "podman", "load", "-i", archive], user=user)
    if run([*runtime, "podman", "image", "exists", image_id], user=user, check=False).returncode:
        raise ValueError("Pinned image was not available in the isolated tool store")
    return image_id


def canonical_image_id(value):
    if re.fullmatch(r"[0-9a-f]{64}", value):
        value = "sha256:" + value
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("Pinned image did not resolve to a local image ID")
    return value


def validate_runtime():
    image_file = ETC / "tools-python-image"
    image = image_file.read_text().strip() if image_file.exists() else ""
    if not re.fullmatch(r"[a-zA-Z0-9./_-]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("Set a reviewed pinned Python image in /etc/hermes-kit/tools-python-image")
    if not tailnet_mode() and not (ETC / "tools-access.json").is_file():
        raise ValueError("Cloudflare Access configuration is missing")
    if not (ETC / "tools-backup.json").is_file():
        raise ValueError("Client tool backup recovery key is required")
    if not tailnet_mode():
        certs = ROOT / "access-certs.json"
        if not certs.is_file() or datetime.now(timezone.utc).timestamp() - json.loads(certs.read_text()).get("fetched_at", 0) > 86400:
            raise ValueError("Fresh Cloudflare Access signing keys are required")
    return image


def origin_denies_without_token(port):
    import time
    for _ in range(10):
        result = run(["curl", "--silent", "--max-time", "2", "--output", "/dev/null", "--write-out", "%{http_code}", f"http://127.0.0.1:{port}/health"], user="hermes" if tailnet_mode() and not TEST else None, capture=True, check=False)
        if result.stdout == ("000" if tailnet_mode() and not TEST else "403"):
            return True
        time.sleep(1)
    return False


def rollback(name, client):
    root(); need_builder(); valid_name(name)
    data = registry(); item = entry(data, name); previous = item.get("previous")
    if not previous or previous == "none":
        raise ValueError("No previous code version")
    release = ROOT / "releases" / name / previous
    if not release.is_dir():
        raise ValueError("Previous code missing")
    current = release.parent / "current"
    link = release.parent / ".rollback-next"
    link.unlink(missing_ok=True)
    link.symlink_to(release); link.replace(current)
    old = item["commit"]
    item["commit"], item["previous"] = previous, old
    item["version"] = previous[:12]
    item["code_hash"] = hash_tree(release)
    save_registry(data)
    if not TEST:
        run(["systemctl", "restart", f"hermes-kit-tool-{name}.service"])
    audit("rollback-code-only", name, client=client, from_commit=old, to_commit=previous, database="untouched")
    print("Code rolled back. Database unchanged. Restoring a database snapshot separately would discard records entered after its timestamp.")


def import_csv(name, path, confirm):
    root(); need_builder(); valid_name(name)
    item = entry(registry(), name)
    if not item.get("commit"):
        raise ValueError("Tool is not published")
    script = ROOT / "releases" / name / "current" / "import_csv.py"
    if not script.exists():
        raise ValueError("Tool does not support CSV import")
    source = Path(path).resolve()
    if not source.is_file():
        raise ValueError("CSV not found")
    # The importer runs as its own unprivileged tool user, never as root.
    import_copy = ROOT / "data" / name / (".import-" + os.urandom(8).hex() + ".csv")
    shutil.copyfile(source, import_copy)
    import_copy.chmod(0o600)
    if not TEST:
        run(["chown", f"tool-{name}:tool-{name}", import_copy])
    try:
        cmd = ["env", f"TOOL_DATA={ROOT / 'data' / name}", "python3", str(script), str(import_copy)]
        run(cmd, user="tool-" + name)
        if confirm:
            run(cmd + ["--confirm"], user="tool-" + name)
            audit("import", name, file_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    finally:
        import_copy.unlink(missing_ok=True)


def backup(only=None):
    root(); need_builder()
    cfg = json.loads((ETC / "tools-backup.json").read_text())
    recipient = cfg["age_recipient"]
    folder = Path(cfg["syncthing_folder"])
    if not re.fullmatch(r"age1[ac-hj-np-z02-9]{20,100}", recipient) or not folder.is_dir() or (not TEST and not str(folder).startswith("/home/hermes/")):
        raise ValueError("Client age recipient and Syncthing folder required")
    data = registry()
    for item in data["tools"]:
        name = item["name"]
        if only is not None and name not in only:
            continue
        db = ROOT / "data" / name / "tool.db"
        if not db.is_file():
            continue
        with tempfile.TemporaryDirectory() as temp:
            plain = Path(temp) / (name + ".db")
            checksum = snapshot(db, plain)
            with sqlite3.connect(plain) as checked:
                if checked.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Tool backup restore test failed")
            output = BACKUP / name / (unique_stamp() + ".db.age")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.parent.chmod(0o700)
            run(["age", "-r", recipient, "-o", output, plain])
            output.chmod(0o600)
            output.with_suffix(output.suffix + ".sha256").write_text(hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n")
            shutil.copy2(output, folder / output.name)
            shutil.copy2(output.with_suffix(output.suffix + ".sha256"), folder / (output.name + ".sha256"))
            if not TEST:
                run(["chown", "hermes:hermes", folder / output.name, folder / (output.name + ".sha256")])
                run(["chmod", "0644", folder / output.name, folder / (output.name + ".sha256")])
            item["last_backup_ok_hours"] = 0
            item["last_backup_at"] = stamp()
            item["last_restore_test_at"] = stamp()
            audit("backup", name, plaintext_sha256=checksum)
    save_registry(data)


def restore_database(name, snapshot_name, confirm, client):
    root(); need_builder(); valid_name(name)
    if not re.fullmatch(r"[A-Za-z0-9T._-]+\.db", snapshot_name):
        raise ValueError("Invalid snapshot name")
    source = BACKUP / name / snapshot_name
    if not source.is_file() or source.resolve().parent != (BACKUP / name).resolve():
        raise ValueError("Local database snapshot not found")
    marker = source.stem
    if confirm != marker:
        raise ValueError(f"Restoring the {marker} snapshot will discard records entered after that time. Run again with --confirm {marker} only if the client accepts that loss")
    recorded = source.with_suffix(source.suffix + ".sha256").read_text().split()[0]
    if hashlib.sha256(source.read_bytes()).hexdigest() != recorded:
        raise ValueError("Snapshot checksum does not match")
    with sqlite3.connect(source) as checked:
        if checked.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Snapshot database integrity check failed")
    db = ROOT / "data" / name / "tool.db"
    if not db.exists():
        raise ValueError("Live database is missing")
    before = BACKUP / name / (unique_stamp() + ".before-restore.db")
    maintenance = db.parent / "maintenance"
    maintenance.touch()
    try:
        if not TEST:
            run(["systemctl", "stop", f"hermes-kit-tool-{name}.service"])
        snapshot(db, before)
        replacement = db.with_suffix(".restore-next")
        shutil.copy2(source, replacement)
        if not TEST:
            run(["chown", f"tool-{name}:tool-{name}", replacement])
        replacement.chmod(0o600)
        replacement.replace(db)
        # A snapshot may predate the active code's expand-only schema. Keep the
        # selected data timestamp while bringing its schema forward.
        current = ROOT / "releases" / name / "current"
        if current.is_dir():
            with sqlite3.connect(db) as conn:
                apply_migrations(conn, migration_files(current))
        if not TEST:
            run(["systemctl", "start", f"hermes-kit-tool-{name}.service"])
            port = entry(registry(), name)["port"]
            if not origin_denies_without_token(port):
                raise ValueError("Restored tool failed health check")
        audit("database-restore", name, client=client, snapshot=marker, before_snapshot=before.name)
    except Exception:
        if before.is_file():
            shutil.copy2(before, db)
            if not TEST:
                run(["chown", f"tool-{name}:tool-{name}", db])
                run(["systemctl", "start", f"hermes-kit-tool-{name}.service"], check=False)
        raise
    finally:
        maintenance.unlink(missing_ok=True)


def backup_key():
    """Generate a client recovery key, retain only its public recipient."""
    root(); need_builder()
    config = Path("/home/hermes/.local/state/syncthing/config.xml")
    if TEST:
        config = ETC / "syncthing.xml"
    if not config.is_file():
        raise ValueError("Syncthing must be paired before tool backup setup")
    tree = ET.parse(config)
    folders = tree.findall(".//folder")
    if not folders:
        raise ValueError("Syncthing has no shared folder")
    share = Path(folders[0].attrib["path"].replace("~", "/home/hermes", 1))
    if not share.is_dir() or not str(share).startswith("/home/hermes/") and not TEST:
        raise ValueError("Syncthing folder must be under the client home")
    destination = share / "Tool Backups"
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        private = Path(temporary) / "client-age-key.txt"
        run(["age-keygen", "-o", private])
        material = private.read_text()
        recipient = next((line.split(": ", 1)[1] for line in material.splitlines() if line.startswith("# public key: ")), "")
        if not recipient.startswith("age1"):
            raise ValueError("Could not derive the client backup recipient")
        config_path = ETC / "tools-backup.json"
        config_path.write_text(json.dumps({"age_recipient": recipient, "syncthing_folder": str(destination)}) + "\n")
        config_path.chmod(0o600)
        print("Save this recovery key in your password manager. It will not be shown again:\n" + material)


def connect(token):
    root(); need_builder()
    if tailnet_mode():
        raise ValueError("Public Cloudflare tunnel is disabled for client tailnet tools")
    if token == "-":
        token = sys.stdin.read(4097).strip()
    if not token or "\n" in token or len(token) > 4096:
        raise ValueError("Invalid tunnel token")
    cfg = json.loads((ETC / "tools-access.json").read_text())
    from access_jwt import CERTS_URL
    if not CERTS_URL.fullmatch(cfg.get("certs_url", "")) or cfg.get("issuer") != cfg["certs_url"].removesuffix("/cdn-cgi/access/certs") or not cfg.get("audience"):
        raise ValueError("Team certs URL, issuer and audience are required")
    if TEST:
        (ETC / "tunnel-token").write_text(token)
        return
    if run(["id", "-u", "cloudflared"], capture=True, check=False).returncode:
        run(["useradd", "--system", "--home", "/var/lib/cloudflared", "--shell", "/usr/sbin/nologin", "cloudflared"])
    refresh_certs()
    secret = Path("/var/lib/cloudflared/token")
    secret.parent.mkdir(parents=True, exist_ok=True)
    run(["chown", "cloudflared:cloudflared", secret.parent])
    secret.parent.chmod(0o700)
    secret.write_text(token + "\n")
    run(["chown", "cloudflared:cloudflared", secret]); secret.chmod(0o600)
    unit = Path("/etc/systemd/system/hermes-kit-cloudflared.service")
    unit.write_text("""[Unit]
Description=Client-owned Cloudflare Tunnel for tools
After=network-online.target
[Service]
User=cloudflared
Group=cloudflared
ExecStart=/usr/bin/cloudflared tunnel run --token-file /var/lib/cloudflared/token
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
[Install]
WantedBy=multi-user.target
""")
    unit.chmod(0o644)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "--now", "hermes-kit-cloudflared.service"])
    run(["systemctl", "enable", "--now", "hermes-kit-tools-certs.timer"])
    audit("tunnel-connected", "all")


def refresh_certs():
    root(); need_builder()
    from access_jwt import CERTS_URL
    cfg = json.loads((ETC / "tools-access.json").read_text())
    url = cfg.get("certs_url", "")
    if not CERTS_URL.fullmatch(url) or cfg.get("issuer") != url.removesuffix("/cdn-cgi/access/certs"):
        raise ValueError("Invalid team certs URL")
    data = json.loads(urlopen(url, timeout=10).read(200000))
    if not isinstance(data.get("keys"), list) or not data["keys"]:
        raise ValueError("Cloudflare certs response has no keys")
    allowed = [key for key in data["keys"] if key.get("kty") == "RSA" and key.get("alg") == "RS256" and key.get("use") == "sig" and all(key.get(k) for k in ("kid", "n", "e"))]
    if not allowed:
        raise ValueError("Cloudflare certs response has no RS256 signing key")
    ROOT.mkdir(parents=True, exist_ok=True)
    target = ROOT / "access-certs.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"keys": allowed, "fetched_at": int(datetime.now(timezone.utc).timestamp())}) + "\n")
    tmp.chmod(0o644)
    tmp.replace(target)


def configure_access(url, audience):
    root(); need_builder()
    if tailnet_mode():
        raise ValueError("Cloudflare Access is disabled for client tailnet tools")
    from access_jwt import CERTS_URL
    if not CERTS_URL.fullmatch(url) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", audience):
        raise ValueError("Enter the team's Cloudflare Access certs URL and application audience")
    cfg = ETC / "tools-access.json"
    cfg.write_text(json.dumps({"certs_url": url, "issuer": url.removesuffix("/cdn-cgi/access/certs"), "audience": audience}) + "\n")
    cfg.chmod(0o600)


def configure_image(image):
    root(); need_builder()
    if not re.fullmatch(r"docker\.io/library/python@sha256:[0-9a-f]{64}", image):
        raise ValueError("Use an official Python image pinned by SHA256 digest")
    path = ETC / "tools-python-image"
    path.write_text(image + "\n")
    path.chmod(0o600)
    audit("runtime-image-configured", "all", image=image)


def rebuild():
    root(); need_builder()
    data = registry()
    for item in data["tools"]:
        if not item.get("commit"):
            continue
        name = item["name"]
        release = ROOT / "releases" / name / "current"
        test_tool(release, user="builder")
        if not TEST:
            user = "tool-" + name
            unit = Path(f"/etc/systemd/system/hermes-kit-tool-{name}.service")
            previous_unit = unit.read_text()
            try:
                install_service(name, user, item["port"])
                run(["systemctl", "restart", unit.name])
                if not origin_denies_without_token(item["port"]):
                    raise ValueError("Rebuilt tool failed its origin health check")
            except Exception:
                unit.write_text(previous_unit)
                run(["systemctl", "daemon-reload"])
                run(["systemctl", "restart", unit.name], check=False)
                if not origin_denies_without_token(item["port"]) and item.get("previous") not in (None, "none"):
                    rollback(name, "rebuild-auto-revert")
                raise
        audit("rebuild", name, commit=item["commit"])


def main():
    name = Path(sys.argv[0]).name
    parser = argparse.ArgumentParser()
    if name == "kit-tools-setup":
        args = parser.parse_args(); setup(); return
    if name == "kit-tools-backup":
        args = parser.parse_args(); backup(); return
    if name == "kit-tools-backup-key":
        args = parser.parse_args(); backup_key(); return
    if name == "kit-tools-certs":
        args = parser.parse_args(); refresh_certs(); return
    if name == "kit-tools-rebuild":
        args = parser.parse_args(); rebuild(); return
    if name == "kit-tools-connect":
        parser.add_argument("token"); args = parser.parse_args(); connect(args.token); return
    if name == "kit-tools-configure":
        parser.add_argument("certs_url"); parser.add_argument("audience")
        args = parser.parse_args(); configure_access(args.certs_url, args.audience); return
    if name == "kit-tools-image":
        parser.add_argument("image")
        args = parser.parse_args(); configure_image(args.image); return
    parser.add_argument("tool")
    if name == "kit-tools-stage":
        parser.add_argument("--source"); parser.add_argument("--template", action="store_true"); parser.add_argument("--commit")
        args = parser.parse_args(); stage(args.tool, args.source, args.template, args.commit)
    elif name == "kit-tools-publish":
        parser.add_argument("--client", required=True); parser.add_argument("--reviewer"); parser.add_argument("--ack-unreviewed", action="store_true")
        args = parser.parse_args(); publish(args.tool, args.client, args.reviewer, args.ack_unreviewed)
    elif name == "kit-tools-rollback":
        parser.add_argument("--client", required=True); args = parser.parse_args(); rollback(args.tool, args.client)
    elif name == "kit-tools-import":
        parser.add_argument("csv"); parser.add_argument("--confirm", action="store_true")
        args = parser.parse_args(); import_csv(args.tool, args.csv, args.confirm)
    elif name == "kit-tools-db-restore":
        parser.add_argument("snapshot"); parser.add_argument("--confirm"); parser.add_argument("--client", required=True)
        args = parser.parse_args(); restore_database(args.tool, args.snapshot, args.confirm, args.client)
    else:
        raise ValueError("Unknown tools command")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
