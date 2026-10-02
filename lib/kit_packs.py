"""Validate the local pack catalog and the root-owned pack selection."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

# Catalog names retained from intake; these files live at different kit paths.
ALIASES = {
    "research/grounded-citations": "business/grounded-citations",
    "productivity/weekly-review-planning": "business/weekly-review-planning",
    "business/social-media-content-calendar": "writing/social-media-content-calendar",
}
NEEDS = {"dashboards": ("builder",), "marketing": ("website", "media")}


def catalog(profile: Path) -> dict:
    data = json.loads((profile / "packs.json").read_text())
    ids = [pack["id"] for pack in data["packs"]]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("Pack catalog has duplicate or missing IDs")
    for item in [data["included"], *data["packs"]]:
        for skill in item["skills"]:
            path = profile / "skills" / ALIASES.get(skill, skill) / "SKILL.md"
            if not path.is_file():
                raise ValueError(f"Pack catalog skill is missing: {skill}")
    for segment in data["segments"]:
        if any(pack not in ids for pack in segment["defaults"]):
            raise ValueError(f"Unknown default pack for {segment['id']}")
    return data


def choose(profile: Path, segment: str, raw: str) -> dict:
    data = catalog(profile)
    segments = {item["id"]: item for item in data["segments"]}
    if segment not in segments:
        raise ValueError(f"Invalid KIT_SEGMENT: {segment}")
    ids = [pack["id"] for pack in data["packs"]]
    picks = segments[segment]["defaults"] if raw == "" else raw.split(",")
    if not picks or len(picks) != len(set(picks)) or any(p not in ids for p in picks):
        raise ValueError("KIT_PACKS must be a comma list of unique pack IDs from packs.json")
    return {"segment": segment, "packs": picks,
            "requires": {pack: list(NEEDS[pack]) for pack in picks if pack in NEEDS}}


def validate(profile: Path, selection: dict) -> dict:
    data = catalog(profile)
    if not isinstance(selection, dict) or selection.get("segment") not in {s["id"] for s in data["segments"]}:
        raise ValueError("Invalid pack segment")
    ids = [p["id"] for p in data["packs"]]
    picks = selection.get("packs")
    if not isinstance(picks, list) or len(picks) != len(set(picks)) or any(p not in ids for p in picks):
        raise ValueError("Invalid saved pack selection")
    expected_needs = {pack: list(NEEDS[pack]) for pack in picks if pack in NEEDS}
    if selection.get("requires", expected_needs) != expected_needs:
        raise ValueError("Saved pack capability requirements differ from catalog")
    return selection


def skill_sets(profile: Path, selection: dict) -> tuple[set[str], set[str]]:
    data = catalog(profile)
    validate(profile, selection)
    optional = {ALIASES.get(s, s) for pack in data["packs"] for s in pack["skills"]}
    chosen = {ALIASES.get(s, s) for s in data["included"]["skills"]}
    chosen.update(ALIASES.get(s, s) for pack in data["packs"] if pack["id"] in selection["packs"] for s in pack["skills"])
    all_skills = {p.parent.relative_to(profile / "skills").as_posix() for p in (profile / "skills").rglob("SKILL.md")}
    # Legacy kit skills outside the pack catalog remain part of the core profile.
    return (all_skills - optional) | chosen, optional


def unmet_needs(selection: dict, consents: Path) -> dict[str, list[str]]:
    recorded = set()
    if consents.is_file():
        recorded = {item.get("integration") for item in json.loads(consents.read_text()).get("consents", [])}
    return {pack: [need for need in needs if need not in recorded]
            for pack, needs in NEEDS.items() if pack in selection["packs"] and any(need not in recorded for need in needs)}


def prune_installed(profile: Path, installed: Path, selection: dict, consents: Path) -> None:
    """Remove only known kit pack skills after profile update, honoring consent."""
    chosen, optional = skill_sets(profile, selection)
    if (installed / "skills").is_symlink():
        raise ValueError("Refusing linked installed skill root")
    recorded = set()
    if consents.is_file():
        recorded = {item.get("integration") for item in json.loads(consents.read_text()).get("consents", [])}
    for skill in optional - chosen - recorded:
        path = installed / "skills" / skill
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError(f"Refusing linked installed skill: {skill}")
        if path.is_dir():
            shutil.rmtree(path)


def read_state(profile: Path, path: Path) -> dict:
    return validate(profile, json.loads(path.read_text()))


def write_state(path: Path, selection: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".new")
    tmp.write_text(json.dumps(selection, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)


def main() -> None:
    action, *args = sys.argv[1:]
    if action == "validate-config":
        choose(Path(args[0]), args[1], args[2])
    elif action == "init":
        profile, state = map(Path, args[:2])
        configured = choose(profile, args[2], args[3])  # Validate current config on every install.
        if state.is_file():
            saved = read_state(profile, state)
            if not saved.get("consent_id") and saved != configured:
                write_state(state, configured)
        else:
            write_state(state, configured)
    elif action == "prune":
        profile, installed, state, consents = map(Path, args)
        prune_installed(profile, installed, read_state(profile, state), consents)
    elif action == "verify":
        profile, installed, state, consents = map(Path, args)
        selected = read_state(profile, state)
        chosen, optional = skill_sets(profile, selected)
        recorded = set()
        if consents.is_file():
            recorded = {item.get("integration") for item in json.loads(consents.read_text()).get("consents", [])}
        for skill in chosen:
            if not (installed / "skills" / skill / "SKILL.md").is_file():
                raise ValueError(f"Selected skill missing: {skill}")
        for skill in optional - chosen - recorded:
            if (installed / "skills" / skill / "SKILL.md").exists():
                raise ValueError(f"Unselected skill installed: {skill}")
    elif action == "needs":
        profile, state, consents = map(Path, args)
        for pack, needs in unmet_needs(read_state(profile, state), consents).items():
            print(f"Sam still needs to switch on {', '.join(needs)} for {pack} through the existing consent path.")
    else:
        raise ValueError("Unknown pack operation")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, IndexError) as exc:
        print(f"kit-packs: {exc}", file=sys.stderr)
        sys.exit(1)
