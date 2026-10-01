#!/usr/bin/env python3
"""Fail closed on Photon sidecar and adapter liveness. Never print runtime tokens."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time


def _service() -> tuple[int, float]:
    result = subprocess.run(
        ["systemctl", "show", "hermes-gateway.service", "--property=MainPID,ExecMainStartTimestamp"],
        capture_output=True, text=True, timeout=5, check=True,
    )
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    pid = int(fields["MainPID"])
    started = datetime.strptime(fields["ExecMainStartTimestamp"], "%a %Y-%m-%d %H:%M:%S %Z")
    if pid <= 0:
        raise ValueError("no gateway pid")
    return pid, started.replace(tzinfo=timezone.utc).timestamp()


def _json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid runtime record")
    return data


def ready(root: Path, profile: Path, proc: Path = Path("/proc")) -> bool:
    try:
        gateway_pid, started = _service()
        now = time.time()
        record_path = profile / "runtime/photon-sidecar.json"
        record = _json(record_path)
        sidecar_pid = record.get("pid")
        if (type(sidecar_pid) is not int or sidecar_pid <= 0 or record.get("port") != 8789
                or not isinstance(record.get("token"), str) or not record["token"]
                or not started - 2 <= record_path.stat().st_mtime <= now + 5):
            return False
        status = (proc / str(sidecar_pid) / "status").read_text(encoding="utf-8")
        parent = re.search(r"^PPid:\s*(\d+)\s*$", status, re.MULTILINE)
        command = (proc / str(sidecar_pid) / "cmdline").read_bytes().split(b"\0")
        if not parent or int(parent.group(1)) != gateway_pid or not command:
            return False
        if command[0].decode(errors="replace") != str(root / "node/bin/node"):
            return False
        if not any(arg.endswith(b"/sidecar/index.mjs") for arg in command[1:]):
            return False
        sockets = subprocess.run(["ss", "-lntpH"], capture_output=True, text=True, timeout=5, check=True).stdout
        port_rows = [line for line in sockets.splitlines() if line.split()[3].rsplit(":", 1)[-1] == "8789"]
        if len(port_rows) != 1 or port_rows[0].split()[3] != "127.0.0.1:8789":
            return False
        if not re.search(r"pid=" + str(sidecar_pid) + r"(?:,|\))", port_rows[0]):
            return False
        gateway_status_path = root / "gateway_state.json"
        gateway_status = _json(gateway_status_path)
        adapter = gateway_status.get("platforms", {}).get("client:photon", {})
        return (gateway_status.get("pid") == gateway_pid and adapter.get("state") == "connected"
                and adapter.get("writer_pid") == gateway_pid
                and started - 2 <= gateway_status_path.stat().st_mtime <= now + 5)
    except (OSError, ValueError, KeyError, IndexError, TypeError, subprocess.SubprocessError):
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(2)
    raise SystemExit(0 if ready(Path(sys.argv[1]), Path(sys.argv[2])) else 1)
