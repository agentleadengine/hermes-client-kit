"""Narrow root bridge from the client agent to the existing Builder lane."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import socketserver
import struct
import subprocess

import kit_tools

SOCKET = Path("/run/hermes-kit/starter.sock")
SOURCE = Path("/home/hermes/vault/tools")
CONSENTS = Path("/etc/hermes-kit/consents.json")
VAULT = Path("/home/hermes/vault")
PREVIEWS = VAULT / "media/tool-previews"


def staged_previews(name: str, commit: str) -> dict[str, str]:
    """Copy only small PNG test artifacts out of the isolated Builder checkout."""
    staged = kit_tools.ROOT / "staging" / name / commit
    artifacts = staged / "tests" / "artifacts"
    if not artifacts.is_dir() or artifacts.is_symlink() or not artifacts.resolve().is_relative_to(staged.resolve()):
        return {}
    destination = PREVIEWS / name / commit
    vault = VAULT.resolve()
    for parent in (PREVIEWS.parent, PREVIEWS, PREVIEWS / name, destination):
        if parent.is_symlink() or not parent.resolve().is_relative_to(vault):
            raise ValueError("Unsafe preview destination")
        parent.mkdir(mode=0o700, exist_ok=True)
        os.chown(parent, pwd.getpwnam("hermes").pw_uid, pwd.getpwnam("hermes").pw_gid)
    result = {}
    for label in ("phone", "desktop"):
        source = artifacts / f"{label}.png"
        if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(staged.resolve()):
            continue
        if source.stat().st_size > 5_000_000 or source.stat().st_size < 24:
            raise ValueError("Preview image size is invalid")
        with source.open("rb") as image:
            signature = image.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Preview image is not a PNG")
        target = destination / source.name
        if target.is_symlink():
            raise ValueError("Unsafe preview file")
        shutil.copyfile(source, target)
        os.chown(target, pwd.getpwnam("hermes").pw_uid, pwd.getpwnam("hermes").pw_gid)
        target.chmod(0o600)
        result[label] = str(target)
    return result


def consent(name):
    return CONSENTS.exists() and any(x.get("integration") == name for x in json.loads(CONSENTS.read_text()).get("consents", []))


def dispatch(request):
    if not isinstance(request, dict) or set(request) - {"action", "name", "commit", "client"}:
        raise ValueError("Invalid starter request")
    if not consent("builder"):
        raise ValueError("Builder consent is missing")
    action = request.get("action")
    name = kit_tools.valid_name(request.get("name", ""))
    if action == "stage":
        source = SOURCE / name
        if source.is_symlink() or not source.resolve().is_relative_to(SOURCE.resolve()) or not source.is_dir():
            raise ValueError("Tool source must be inside the client's vault tools area")
        kit_tools.stage(name, source=str(source), commit=request.get("commit"))
        item = kit_tools.entry(kit_tools.registry(), name)
        return {"staged": item["staged"], "port": item["port"], "previews": staged_previews(name, item["staged"])}
    if action == "publish":
        if not consent("tailscale"):
            raise ValueError("Tailscale consent is required for private tool publication")
        status = subprocess.run(["tailscale", "status", "--json"], check=True, capture_output=True, text=True)
        if json.loads(status.stdout).get("BackendState") != "Running":
            raise ValueError("Client tailnet is not connected")
        item = kit_tools.entry(kit_tools.registry(), name)
        if request.get("commit") != item.get("staged"):
            raise ValueError("Approved commit does not match the staged tool")
        client = request.get("client")
        kit_tools.publish(name, client, ack_unreviewed=True)
        try:
            subprocess.run(["/usr/local/bin/kit-tailscale", "serve", str(item["port"])], check=True, capture_output=True)
        except subprocess.CalledProcessError as error:
            subprocess.run(["systemctl", "stop", f"hermes-kit-tool-{name}.service"], check=False, capture_output=True)
            data = kit_tools.registry()
            kit_tools.entry(data, name)["up"] = False
            kit_tools.save_registry(data)
            raise ValueError("Tool publication stopped because private tailnet serving failed") from error
        return {"published": item["staged"], "port": item["port"], "access": "tailnet"}
    if action == "rollback":
        kit_tools.rollback(name, request.get("client"))
        return {"rolled_back": name}
    raise ValueError("Unknown starter request")


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        credentials = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", credentials)
        if uid != pwd.getpwnam("hermes").pw_uid:
            return
        line = self.rfile.readline(8193)
        if len(line) > 8192 or not line.endswith(b"\n"):
            return
        try:
            result = {"ok": True, "result": dispatch(json.loads(line))}
        except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
            result = {"ok": False, "error": str(error)[:200]}
        self.wfile.write((json.dumps(result) + "\n").encode())


def main():
    SOCKET.parent.mkdir(parents=True, exist_ok=True)
    SOCKET.unlink(missing_ok=True)
    with socketserver.UnixStreamServer(str(SOCKET), Handler) as server:
        os.chown(SOCKET, 0, pwd.getpwnam("hermes").pw_gid)
        SOCKET.chmod(0o660)
        server.serve_forever()


if __name__ == "__main__":
    main()
