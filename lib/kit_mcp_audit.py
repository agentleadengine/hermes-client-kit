#!/usr/bin/env python3
"""Audit the client profile's effective MCP policy without printing server config."""
import json
from pathlib import Path
import subprocess
import sys

from hermes_runtime import HERMES_BIN
from kit_mcp_policy import audit


def effective(key: str, optional: bool = False):
    result = subprocess.run(
        ["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes",
         "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client",
         "config", "get", key, "--json"], capture_output=True, text=True)
    if result.returncode:
        if optional and "not set" in (result.stdout + result.stderr).lower():
            return {}
        raise ValueError(f"Cannot read effective {key}")
    return json.loads(result.stdout)


def read_json(path: Path, fallback):
    return json.loads(path.read_text()) if path.exists() else fallback


def main():
    home = Path("/home/hermes/.hermes/profiles/client")
    ledger = Path("/etc/hermes-kit/consents.json")
    if len(sys.argv) == 2:  # Stubbed effective config for offline tests.
        fixture = read_json(Path(sys.argv[1]), {})
        platforms = fixture["platform_toolsets"]
        servers = fixture.get("mcp_servers", {})
        profile = fixture.get("profile_mcp", {})
        jobs = fixture.get("jobs", [])
        entries = fixture.get("consents", [])
    else:
        platforms = effective("platform_toolsets")
        servers = effective("mcp_servers", optional=True)
        profile = read_json(home / "mcp.json", {})
        jobs = read_json(home / "cron" / "jobs.json", [])
        entries = read_json(ledger, {"consents": []})["consents"]
    errors = audit(platforms, servers, profile, entries, jobs)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
