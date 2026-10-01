"""Render and verify the client-owned assistant name in installed profile files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

TEMPLATES = ("SOUL.md", "distribution.yaml", "skills/hermes/hermes-starter-onboarding/SKILL.md")
NAME = re.compile(r"[A-Za-z0-9 '-]{1,40}\Z")


def replacements(name: str) -> dict[str, str]:
    if name and (not NAME.fullmatch(name) or not name.strip()):
        raise ValueError("ASSISTANT_NAME must be 1-40 letters, digits, spaces, apostrophes, or hyphens")
    name = name.strip()
    label = name or "your assistant"
    # JSON escaping is valid YAML string escaping, including apostrophes.
    description = (name if name else "Your assistant") + ", a safe client-owned private Hermes assistant"
    return {
        "{{ASSISTANT_TITLE}}": label,
        "{{ASSISTANT_INTRO}}": f"You are {name}: a discreet, composed executive assistant." if name else "You are the client's private assistant: discreet, composed, and useful.",
        "{{ASSISTANT_GREETING}}": f'For a clear delegated task, you may introduce yourself as “{name}.” Use it only when you can actually begin. ' if name else "",
        "{{ASSISTANT_DESCRIPTION}}": description.replace("\\", "\\\\").replace('"', '\\"'),
    }


def rendered(source: Path, name: str) -> str:
    content = source.read_text()
    for marker, replacement in replacements(name).items():
        content = content.replace(marker, replacement)
    return content


def expected_manifest(source: Path, name: str) -> str:
    lines = []
    for path in sorted((source / "skills").rglob("SKILL.md")):
        relative = path.relative_to(source).as_posix()
        content = rendered(path, name) if relative in TEMPLATES else path.read_text()
        lines.append(f"{hashlib.sha256(content.encode()).hexdigest()}  {relative}\n")
    return "".join(lines)


def profile(source: Path, installed: Path, name: str, verify: bool) -> None:
    for relative in TEMPLATES:
        target = installed / relative
        content = rendered(source / relative, name)
        if verify:
            if not target.is_file():
                raise ValueError(f"Installed profile differs: {relative}")
            actual = target.read_text()
            if relative == "distribution.yaml":
                # Hermes owns these install records and rewrites them on update.
                fields = dict(line.split(":", 1) for line in actual.splitlines() if ":" in line and not line.startswith(" "))
                if not fields.get("source", "").strip():
                    raise ValueError("Installed profile has no recorded source")
                if not fields.get("installed_at", "").strip():
                    raise ValueError("Installed profile has no install timestamp")
                description = fields.get("description", "").strip()
                if description.startswith('"'):
                    description = json.loads(description)
                elif description.startswith("'"):
                    description = description[1:-1].replace("''", "'")
                if description != replacements(name)["{{ASSISTANT_DESCRIPTION}}"]:
                    raise ValueError("Installed distribution description differs")
                continue
            if actual != content:
                raise ValueError(f"Installed profile differs: {relative}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
    manifest = expected_manifest(source, name)
    target = installed / "SKILLS.sha256"
    if verify:
        if not target.is_file() or target.read_text() != manifest:
            raise ValueError("Installed skill manifest differs")
        for line in manifest.splitlines():
            digest, relative = line.split(maxsplit=1)
            path = installed / relative
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Installed skill differs: {relative}")
    else:
        target.write_text(manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "verify"))
    parser.add_argument("source", type=Path)
    parser.add_argument("installed", type=Path)
    parser.add_argument("name")
    args = parser.parse_args()
    profile(args.source, args.installed, args.name, args.action == "verify")


if __name__ == "__main__":
    main()
