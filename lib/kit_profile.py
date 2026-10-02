"""Render and verify the client-owned assistant name in installed profile files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from kit_packs import skill_sets, validate

TEMPLATES = ("SOUL.md", "distribution.yaml", "skills/hermes/hermes-starter-onboarding/SKILL.md")
NAME = re.compile(r"[A-Za-z0-9 '-]{1,40}\Z")


def replacements(name: str, selection: dict | None = None) -> dict[str, str]:
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
        "{{ACTIVE_PACKS}}": ", ".join(selection["packs"]) if selection else "the packs selected by Sam",
    }


def rendered(source: Path, name: str, selection: dict | None = None) -> str:
    content = source.read_text()
    for marker, replacement in replacements(name, selection).items():
        content = content.replace(marker, replacement)
    return content


def expected_manifest(source: Path, name: str, selection: dict | None = None) -> str:
    lines = []
    chosen = skill_sets(source, selection)[0] if selection else None
    for path in sorted((source / "skills").rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if chosen is not None and not any(path.is_relative_to(source / "skills" / skill) for skill in chosen) and path.name != "SOURCES.md":
            continue
        relative = path.relative_to(source).as_posix()
        content = rendered(path, name, selection).encode() if relative in TEMPLATES else path.read_bytes()
        lines.append(f"{hashlib.sha256(content).hexdigest()}  {relative}\n")
    return "".join(lines)


def profile(source: Path, installed: Path, name: str, verify: bool, selection: dict | None = None) -> None:
    if selection:
        validate(source, selection)
        chosen, optional = skill_sets(source, selection)
        if not verify:
            for skill in optional - chosen:
                target = installed / "skills" / skill
                if target.is_dir():
                    shutil.rmtree(target)
    for relative in TEMPLATES:
        target = installed / relative
        content = rendered(source / relative, name, selection)
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
                if description != replacements(name, selection)["{{ASSISTANT_DESCRIPTION}}"]:
                    raise ValueError("Installed distribution description differs")
                continue
            if actual != content:
                raise ValueError(f"Installed profile differs: {relative}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
    manifest = expected_manifest(source, name, selection)
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
    parser.add_argument("--selection", type=Path)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text()) if args.selection else None
    profile(args.source, args.installed, args.name, args.action == "verify", selection)


if __name__ == "__main__":
    main()
