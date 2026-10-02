"""Send one plain owner notice for model plan failures, at most every six hours."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import subprocess
import time

try:
    from .kit_reminders import owner_target
except ImportError:  # local offline tests load the shared module directly
    from kit_reminders import owner_target

MARKER = Path(os.environ.get("KIT_QUOTA_MARKER", "/home/hermes/vault/.kit/quota-notice.epoch"))
MESSAGE = "I've hit your AI plan's limit. I'll be back when it resets, or upgrade your plan."


def is_plan_error(status_code=None, reason=None, error=None) -> bool:
    words = (str(reason or "") + " " + str(error or "")).lower()
    return str(status_code) in {"401", "403", "429"} or any(token in words for token in (
        "auth_failed", "rate_limited", "rate limit", "insufficient_quota", "quota exceeded", "plan limit", "authentication failed"))


def notify(*, status_code=None, reason=None, error=None, now=None, send=None) -> bool:
    if not is_plan_error(status_code, reason, error):
        return False
    target = owner_target()
    if not target:
        return False
    MARKER.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    clock = time.time() if now is None else now
    fd = os.open(MARKER, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+") as marker:
        fcntl.flock(marker, fcntl.LOCK_EX)
        marker.seek(0)
        try:
            last = float(marker.read().strip() or "0")
        except ValueError:
            last = 0
        if clock - last < 6 * 3600:
            return False
        command = ["/home/hermes/.local/bin/hermes", "-p", "client", "send", "--to", target, MESSAGE]
        if send is None:
            try:
                success = subprocess.run(command, capture_output=True, timeout=45, check=False).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                success = False
        else:
            success = send(command)
        if success:
            marker.seek(0)
            marker.truncate()
            marker.write(str(clock) + "\n")
            marker.flush()
            os.fsync(marker.fileno())
        return bool(success)
