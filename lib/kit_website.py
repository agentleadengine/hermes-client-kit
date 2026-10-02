"""Git site preview and owner approval with a reversible published commit."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(os.environ.get("KIT_WEBSITE_ROOT", "/home/hermes/vault/website"))
STATE = Path(os.environ.get("KIT_WEBSITE_STATE", "/home/hermes/.local/state/hermes-kit/website.json"))
TEST = os.environ.get("KIT_WEBSITE_TEST_MODE") == "1"
NETLIFY = os.environ.get("KIT_NETLIFY_BIN", "/usr/local/bin/netlify")
ENV = Path(os.environ.get("KIT_WEBSITE_ENV", "/home/hermes/.hermes/profiles/client/.env"))
PRIVATE_NAME = re.compile(r"(?i)(^|/)(secret|private)([._/-]|$)|(?:\.env|auth\.json|\.pem|\.key)$")


def run(*args, capture=False, check=True):
    command = ["git", "-C", str(ROOT), *args]
    if not TEST and os.geteuid() == 0:
        command = ["runuser", "-u", "hermes", "--", *command]
    return subprocess.run(command, capture_output=capture, text=True, check=check)


def require():
    if os.geteuid() != 0 and not TEST:
        import pwd
        if os.geteuid() != pwd.getpwnam("hermes").pw_uid:
            raise ValueError("Run as the client agent or root")
    if not TEST:
        ledger = Path("/etc/hermes-kit/consents.json")
        if not ledger.exists() or not any(x.get("integration") == "website" for x in json.loads(ledger.read_text()).get("consents", [])):
            raise ValueError("Website power-up is off")


def read():
    return json.loads(STATE.read_text())


def save(data):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    if not TEST and os.geteuid() == 0:
        subprocess.run(["chown", "hermes:hermes", STATE.parent], check=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.chmod(0o600)
    if not TEST and os.geteuid() == 0:
        subprocess.run(["chown", "hermes:hermes", tmp], check=True)
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
    if not TEST and os.geteuid() == 0: command = ["runuser", "-u", "hermes", "--", *command]
    subprocess.run(command, check=True)
    branch = run("branch", "--show-current", capture=True).stdout.strip()
    if not branch:
        raise ValueError("Remote has no default branch")
    if not TEST:
        subprocess.run(["chown", "-R", "hermes:hermes", ROOT], check=True)
    save({"remote": remote, "main": branch, "preview": None, "base": None, "published": None, "before": None})


def setup_netlify(site_id):
    require()
    if not TEST:
        ledger = json.loads(Path("/etc/hermes-kit/consents.json").read_text())
        if not any(x.get("integration") == "netlify" for x in ledger.get("consents", [])):
            raise ValueError("Netlify power-up is off")
    if not re.fullmatch(r"[A-Za-z0-9-]{3,100}", site_id):
        raise ValueError("Use the client's Netlify site ID")
    if ROOT.exists() and any(ROOT.iterdir()):
        if not STATE.exists() or read().get("netlify_site_id") != site_id:
            raise ValueError("Existing website directory is not kit-owned")
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    if not TEST and os.geteuid() == 0:
        subprocess.run(["chown", "hermes:hermes", ROOT], check=True)
    run("init", "-b", "main")
    (ROOT / "index.html").write_text("<!doctype html><title>Coming soon</title><h1>Coming soon</h1>\n")
    if not TEST and os.geteuid() == 0:
        subprocess.run(["chown", "hermes:hermes", ROOT / "index.html"], check=True)
    run("add", "index.html")
    run("-c", "user.name=Hermes Kit", "-c", "user.email=kit@localhost", "commit", "-m", "Initial client website")
    save({"netlify_site_id": site_id, "main": "main", "preview": None, "base": None, "published": None, "before": None})


def netlify_token():
    if TEST:
        return "test-token"
    # kit-set-key restricts this credential to simple token characters.
    match = re.search(r'^NETLIFY_AUTH_TOKEN="([A-Za-z0-9_-]+)"$', ENV.read_text(), re.MULTILINE)
    token = match.group(1) if match else None
    if not token:
        raise ValueError("Netlify token is missing; add it with kit-set-key")
    return token


def deploy(commit, site_id):
    if not TEST:
        ledger = json.loads(Path("/etc/hermes-kit/consents.json").read_text())
        if not any(x.get("integration") == "netlify" for x in ledger.get("consents", [])):
            raise ValueError("Netlify power-up is off")
    with tempfile.TemporaryDirectory(prefix="kit-netlify-") as directory:
        target = Path(directory) / "site"
        target.mkdir()
        # subprocess text capture is unsuitable for binary tar. Archive into
        # a temporary file and reject links and hidden paths before extraction.
        archive_file = Path(directory) / "site.tar"
        command = ["git", "-C", str(ROOT), "archive", "--format=tar", "-o", str(archive_file), commit]
        subprocess.run(command, check=True)
        with tarfile.open(archive_file) as bundle:
            for member in bundle.getmembers():
                parts = Path(member.name).parts
                if member.issym() or member.islnk() or member.name.startswith("/") or ".." in parts or any(part.startswith(".") for part in parts) or PRIVATE_NAME.search(member.name):
                    raise ValueError("Site archive contains an unsafe path")
            bundle.extractall(target, filter="data")
        archive_file.unlink()
        if not (target / "index.html").is_file():
            raise ValueError("Website needs an index.html before publishing")
        if not TEST:
            if os.geteuid() == 0:
                import pwd
                hermes = pwd.getpwnam("hermes")
                os.chown(directory, hermes.pw_uid, hermes.pw_gid)
                os.chown(target, hermes.pw_uid, hermes.pw_gid)
            for item in target.rglob("*"):
                if os.geteuid() == 0:
                    os.chown(item, hermes.pw_uid, hermes.pw_gid)
                item.chmod(0o700 if item.is_dir() else 0o600)
        environment = os.environ.copy()
        environment["NETLIFY_AUTH_TOKEN"] = netlify_token()
        environment["NETLIFY_TELEMETRY_DISABLED"] = "1"
        command = [NETLIFY, "deploy", "--prod", "--no-build", "--dir", str(target), "--site", site_id, "--json"]
        if not TEST and os.geteuid() == 0:
            command = ["runuser", "-u", "hermes", "--", *command]
        result = subprocess.run(command, check=True, capture_output=True, text=True, env=environment, cwd=target)
        try:
            outcome = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("Netlify returned an invalid deployment result") from error
        url = outcome.get("url") or outcome.get("ssl_url") or outcome.get("deploy_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("Netlify did not confirm a live deployment URL")
        return {"id": outcome.get("deploy_id") or outcome.get("id") or outcome.get("deployId"), "url": url}


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
        if name.startswith(".") or any(part.startswith(".") for part in Path(name).parts) or PRIVATE_NAME.search(name):
            raise ValueError("Preview includes a private or hidden file")
    if state.get("remote"):
        run("fetch", "origin", state["main"])
    base = run("rev-parse", "HEAD", capture=True).stdout.strip()
    remote = run("rev-parse", "FETCH_HEAD", capture=True).stdout.strip() if state.get("remote") else base
    if base != remote:
        raise ValueError("Remote default branch changed; rebase locally first")
    branch = "kit-preview/" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run("checkout", "-b", branch)
    run("add", "-A")
    run("-c", "user.name=Hermes Kit", "-c", "user.email=kit@localhost", "commit", "-m", "Client website preview")
    state.update({"preview": branch, "base": base, "preview_commit": run("rev-parse", "HEAD", capture=True).stdout.strip()})
    save(state)
    if not TEST and os.geteuid() == 0:
        subprocess.run(["systemctl", "start", "hermes-kit-website-preview.service"], check=True)
    print("Preview branch:", branch, "Local preview: http://127.0.0.1:8899")


def approve():
    require(); state = read()
    if not state.get("preview"):
        raise ValueError("No preview pending")
    if run("status", "--porcelain", "-z", capture=True).stdout:
        raise ValueError("Website draft changed after preview; create a new preview")
    if state.get("remote"):
        run("fetch", "origin", state["main"])
        if run("rev-parse", "FETCH_HEAD", capture=True).stdout.strip() != state["base"]:
            raise ValueError("Remote changed since preview; approval refused")
    if run("rev-parse", "HEAD", capture=True).stdout.strip() != state["preview_commit"]:
        raise ValueError("Preview branch changed since review")
    if state.get("netlify_site_id"):
        outcome = deploy(state["preview_commit"], state["netlify_site_id"])
        run("checkout", state["main"])
        run("merge", "--ff-only", state["preview_commit"])
    else:
        run("push", "origin", f"{state['preview_commit']}:refs/heads/{state['main']}")
        outcome = None
    state.update({"published": state["preview_commit"], "before": state["base"], "preview": None, "base": None, "last_deploy": outcome})
    save(state)
    if not TEST and os.geteuid() == 0:
        subprocess.run(["systemctl", "stop", "hermes-kit-website-preview.service"], check=False)


def undo():
    require(); state = read()
    if not state.get("published") or not state.get("before"):
        raise ValueError("No kit-published site version to undo")
    if state.get("remote"):
        run("fetch", "origin", state["main"])
        if run("rev-parse", "FETCH_HEAD", capture=True).stdout.strip() != state["published"]:
            raise ValueError("Remote changed since publish; undo refused")
    run("checkout", state["main"])
    if state.get("remote"):
        run("merge", "--ff-only", state["published"])
    elif run("rev-parse", "HEAD", capture=True).stdout.strip() != state["published"]:
        raise ValueError("Website changed since publish; undo refused")
    run("-c", "user.name=Hermes Kit", "-c", "user.email=kit@localhost", "revert", "--no-edit", state["published"])
    commit = run("rev-parse", "HEAD", capture=True).stdout.strip()
    if state.get("netlify_site_id"):
        outcome = deploy(commit, state["netlify_site_id"])
    else:
        run("push", "origin", f"{commit}:refs/heads/{state['main']}")
        outcome = None
    state.update({"published": None, "before": None, "last_deploy": outcome, "undone_at": datetime.now(timezone.utc).isoformat()})
    save(state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "setup-netlify", "preview", "approve", "undo"])
    parser.add_argument("remote", nargs="?")
    args = parser.parse_args()
    if args.action == "setup":
        if not args.remote:
            parser.error("setup requires a git remote")
        setup(args.remote)
    elif args.action == "setup-netlify":
        if not args.remote:
            parser.error("setup-netlify requires a site ID")
        setup_netlify(args.remote)
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
