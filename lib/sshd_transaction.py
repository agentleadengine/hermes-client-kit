"""Validate each sshd file change and restore its previous state on failure."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import tempfile


def apply(path: Path, content: str | None) -> None:
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Refusing non-regular sshd file: {path}")
    previous = path.read_bytes() if path.exists() else None
    metadata = path.stat() if previous is not None else None

    def replace(data: bytes) -> None:
        fd, name = tempfile.mkstemp(prefix=".hermes-ssh-", dir=path.parent)
        try:
            os.fchmod(fd, stat.S_IMODE(metadata.st_mode) if metadata else 0o644)
            if metadata:
                os.fchown(fd, metadata.st_uid, metadata.st_gid)
            with os.fdopen(fd, "wb") as output:
                output.write(data)
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    if content is None:
        path.unlink(missing_ok=True)
    else:
        replace(content.encode())
    result = subprocess.run(["sshd", "-t"], capture_output=True, text=True)
    if result.returncode == 0:
        return
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        replace(previous)
    restored = subprocess.run(["sshd", "-t"], capture_output=True, text=True)
    suffix = "" if restored.returncode == 0 else " (sshd still fails after restore)"
    raise RuntimeError(f"sshd validation failed for {path}; previous state restored{suffix}: {result.stderr.strip()}")
