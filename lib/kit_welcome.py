"""One-time, owner-specific first reply for the messaging gateway."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

BRIEF = Path(os.environ.get("KIT_WELCOME_BRIEF", "/home/hermes/vault/business/BRIEF.md"))
SELECTION = Path(os.environ.get("KIT_WELCOME_SELECTION", "/etc/hermes-kit/packs.json"))
CATALOG = Path(os.environ.get("KIT_WELCOME_CATALOG", "/var/lib/hermes-kit/profile-source/packs.json"))
MARKER = Path(os.environ.get("KIT_WELCOME_MARKER", "/home/hermes/vault/.kit/first-reply.json"))


def owner_name() -> str:
    try:
        brief = BRIEF.read_text()
    except FileNotFoundError:
        return "there"
    owner = brief.split("## Owner", 1)[-1].split("## ", 1)[0]
    for label in ("Address me as", "Name"):
        match = re.search(rf"(?m)^- {label}:\s*(.+)$", owner)
        if match and not match[1].startswith("["):
            return match[1].strip()[:60]
    return "there"


def starter_texts() -> list[str]:
    try:
        selection = json.loads(SELECTION.read_text())
        catalog = json.loads(CATALOG.read_text())
        chosen = selection.get("packs", [])
        packs = [p for p in catalog["packs"] if p["id"] in chosen]
        examples = [p["examples"][0] for p in packs if p.get("examples")]
        for pack in packs:
            examples.extend(pack.get("examples", [])[1:])
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        examples = []
    examples.extend(["Plan my week from these notes", "Research this question and show me sources", "Organize these job notes into next steps"])
    return examples[:3]


def first_reply(response_text: str, platform: str) -> str | None:
    if platform not in {"photon", "telegram"} or MARKER.exists() or not response_text.strip():
        return None
    name = owner_name()
    tasks = starter_texts()
    intro = f"Hi {name}. I can help with your business notes, research, drafts, and weekly plans.\n\nTry texting me one of these:\n"
    welcome = intro + "\n".join(f"{i}. “{task}”" for i, task in enumerate(tasks, 1))
    MARKER.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None
    with os.fdopen(fd, "w") as out:
        out.write(json.dumps({"version": 1, "platform": platform}) + "\n")
    if response_text.strip().lower() in {"hi", "hello", "hey"}:
        return welcome
    return welcome + "\n\n" + response_text
