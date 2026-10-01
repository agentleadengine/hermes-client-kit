"""Git site preview and owner approval with a reversible published commit."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(os.environ.get("KIT_WEBSITE_ROOT", "/home/hermes/vault/website"))
STATE = Path(os.environ.get("KIT_WEBSITE_STATE", "/var/lib/hermes-kit/website.json"))
TEST = os.environ.get("KIT_WEBSITE_TEST_MODE") == "1"


def run(*args, capture=False, check=True):
    command = ["git", "-C", str(ROOT), *args]
    if not TEST:
        command = ["runuser", "-u", "hermes", "--", *command]
    return subprocess.run(command, capture_output=capture, text=True, check=check)


def require():
    if os.geteuid() != 0 and not TEST:
        raise ValueError("Run as root with the client present")
    if not TEST:
        ledger = Path("/etc/hermes-kit/consents.json")
        if not ledger.exists() or not any(x.get("integration") == "website" for x in json.loads(ledger.read_text()).get("consents", [])):
            raise ValueError("Website power-up is off")


def read():
    return json.loads(STATE.read_text())


def save(data):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(STATE)


def setup(remote):
    require()
    if not TEST and not (re.fullmatch(r"https://[A-Za-z0-9.-]+/[A-Za-z0-9._/-]+\.git", remote) or re.fullmatch(r"git@[A-Za-z0-9.-]+:[A-Za-z0-9._/-]+\.git", remote)):
        raise ValueError("Use a credential-free HTTPS or SSH git remote")
    if ROOT.exists():
        if not STATE.exists() or read().get("remote") != remote:
            raise ValueError("Existing website directory is not kit-owned")
        return
    command = ["git", "clone", "--", remote, str(ROOT)]
    if not TEST: command = ["runuser", "-u", "hermes", "--", *command]
    subprocess.run(command, check=True)
    branch = run("branch", "--show-current", capture=True).stdout.strip()
    if not branch:
        raise ValueError("Remote has no default branch")
    if not TEST:
        subprocess.run(["chown", "-R", "hermes:hermes", ROOT], check=True)
    save({"remote": remote, "main": branch, "preview": None, "base": None, "published": None, "before": None})


def preview():
    require(); state = read()
    if state.get("preview"):
        raise ValueError("A preview is already awaiting approval")
    status = run("status", "--porcelain", "-z", capture=True).stdout.split("\0")
    if not [x for x in status if x]:
        raise ValueError("No website changes to preview")
    for item in ROOT.rglob("*"):
        if item.is_symlink():
            raise ValueError("Site preview cannot include symlinks")
    for item in status:
        if not item:
            continue
        name = item[3:]
        if name.startswith(".") or any(part.startswith(".") for part in Path(name).parts) or re.search(r"(?i)(\.env|auth\.json|private|secret|\.pem|\.key)$", name):
            raise ValueError("Preview includes a private or hidden file")
    run("fetch", "origin", state["main"])
    base = run("rev-parse", "HEAD", capture=True).stdout.strip()
    remote = run("rev-parse", "FETCH_HEAD", capture=True).stdout.strip()
    if base != remote:
        raise ValueError("Remote default branch changed; rebase locally first")
    branch = "kit-preview/" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run("checkout", "-b", branch)
    run("add", "-A")
    run("-c", "user.name=Hermes Kit", "-c", "user.email=kit@localhost", "commit", "-m", "Client website preview")
    state.update({"preview": branch, "base": base, "preview_commit": run("rev-parse", "HEAD", capture=True).stdout.strip()})
    save(state)
    if not TEST:
        subprocess.run(["systemctl", "start", "hermes-kit-website-preview.service"], check=True)
    print("Preview branch:", branch, "Local preview: http://127.0.0.1:8899")


def approve():
    require(); state = read()
    if not state.get("preview"):
        raise ValueError("No preview pending")
    run("fetch", "origin", state["main"])
    if run("rev-parse", "FETCH_HEAD", capture=True).stdout.strip() != state["base"]:
        raise ValueError("Remote changed since preview; approval refused")
    if run("rev-parse", "HEAD", capture=True).stdout.strip() != state["preview_commit"]:
        raise ValueError("Preview branch changed since review")
    run("push", "origin", f"{state['preview_commit']}:refs/heads/{state['main']}")
    state.update({"published": state["preview_commit"], "before": state["base"], "preview": None, "base": None})
    save(state)
    if not TEST:
        subprocess.run(["systemctl", "stop", "hermes-kit-website-preview.service"], check=False)


def undo():
    require(); state = read()
    if not state.get("published") or not state.get("before"):
        raise ValueError("No kit-published site version to undo")
    run("fetch", "origin", state["main"])
    if run("rev-parse", "FETCH_HEAD", capture=True).stdout.strip() != state["published"]:
        raise ValueError("Remote changed since publish; undo refused")
    run("checkout", state["main"])
    run("merge", "--ff-only", state["published"])
    run("-c", "user.name=Hermes Kit", "-c", "user.email=kit@localhost", "revert", "--no-edit", state["published"])
    commit = run("rev-parse", "HEAD", capture=True).stdout.strip()
    run("push", "origin", f"{commit}:refs/heads/{state['main']}")
    state.update({"published": None, "before": None, "undone_at": datetime.now(timezone.utc).isoformat()})
    save(state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "preview", "approve", "undo"])
    parser.add_argument("remote", nargs="?")
    args = parser.parse_args()
    if args.action == "setup":
        if not args.remote:
            parser.error("setup requires a git remote")
        setup(args.remote)
    elif args.remote:
        parser.error("Unexpected argument")
    else:
        globals()[args.action]()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
