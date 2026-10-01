"""Small, consent-gated client tools. No general shell or browser access."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit_website
import kit_video

LEDGER = Path("/etc/hermes-kit/consents.json")
TOOLS = Path("/home/hermes/vault/tools")
SOCKET = "/run/hermes-kit/starter.sock"
NAME = re.compile(r"[a-z][a-z0-9-]{1,31}\Z")


def consent(name):
    return LEDGER.exists() and any(x.get("integration") == name for x in json.loads(LEDGER.read_text()).get("consents", []))


def guard(tool_name: str, args: dict, **kwargs):
    del kwargs
    if tool_name in {"starter_site_publish", "starter_site_undo", "starter_tool_publish", "starter_tool_rollback"}:
        return {"action": "approve", "message": "The client must approve this public or tool-changing action", "rule_key": "kit-starter:" + tool_name}
    if tool_name == "starter_make_video" and args.get("voice"):
        return {"action": "approve", "message": "The client must approve paid voice generation for this video", "rule_key": "kit-starter:voice"}
    return None


def bridge(action, name, **extras):
    if not NAME.fullmatch(name):
        raise ValueError("Invalid tool name")
    payload = json.dumps({"action": action, "name": name, **extras}).encode() + b"\n"
    if len(payload) > 8192:
        raise ValueError("Tool request is too long")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(120)
        client.connect(SOCKET)
        client.sendall(payload)
        response = b""
        while not response.endswith(b"\n") and len(response) < 8192:
            chunk = client.recv(8192)
            if not chunk:
                break
            response += chunk
    result = json.loads(response)
    if not result.get("ok"):
        raise ValueError(result.get("error", "Builder operation failed"))
    return result["result"]


def site_preview(args, **kwargs):
    del args, kwargs
    if not consent("website"):
        raise ValueError("Website consent is missing")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        kit_website.preview()
    message = out.getvalue()
    if consent("tailscale"):
        status = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, check=False)
        if status.returncode == 0:
            data = json.loads(status.stdout)
            if data.get("BackendState") == "Running":
                address = data.get("Self", {}).get("DNSName", "").rstrip(".")
                if re.fullmatch(r"[A-Za-z0-9.-]+", address):
                    message += f"Private client preview: http://{address}:8899\n"
    return message


def site_publish(args, **kwargs):
    del args, kwargs
    if not consent("netlify"):
        raise ValueError("Netlify consent is missing")
    kit_website.approve()
    return json.dumps(kit_website.read().get("last_deploy"))


def site_undo(args, **kwargs):
    del args, kwargs
    if not consent("netlify"):
        raise ValueError("Netlify consent is missing")
    kit_website.undo()
    return json.dumps(kit_website.read().get("last_deploy"))


def make_video(args, **kwargs):
    del kwargs
    return str(kit_video.render(Path(args["script"]), args["output"], bool(args.get("voice")), bool(args.get("voice"))))


def share_video(args, **kwargs):
    del kwargs
    if not consent("media") or not consent("website"):
        raise ValueError("Media and Website consent are required")
    name = args["name"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.mp4", name):
        raise ValueError("Use a simple video filename")
    source = kit_video.VAULT / "media" / name
    destination = kit_website.ROOT / "videos" / name
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 50_000_000:
        raise ValueError("Video is missing or exceeds the 50 MB sharing limit")
    if kit_website.ROOT.is_symlink() or not kit_website.ROOT.is_dir() or not kit_website.STATE.is_file() or not kit_website.ROOT.resolve().is_relative_to(kit_video.VAULT.resolve()):
        raise ValueError("Website location is outside the client's vault")
    if destination.parent.is_symlink() or destination.is_symlink() or not destination.parent.resolve().is_relative_to(kit_website.ROOT.resolve()):
        raise ValueError("Website video location is unsafe")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return f"Video added to website draft: videos/{name}. Preview and approval are still required."


def tool_prepare(args, **kwargs):
    del kwargs
    if not consent("builder"):
        raise ValueError("Builder consent is missing")
    name = args["name"]
    if not NAME.fullmatch(name):
        raise ValueError("Invalid tool name")
    source = TOOLS / name
    if not source.is_dir() or source.is_symlink() or not source.resolve().is_relative_to(TOOLS.resolve()):
        raise ValueError("Create the tool's files inside the vault tools area first")
    for item in source.rglob("*"):
        if item.is_symlink() or (".git" not in item.parts and any(part.startswith(".") or part.lower() in {"secret", "private", "auth.json"} for part in item.relative_to(source).parts)):
            raise ValueError("Tool source has a hidden, private, or linked file")
    if not (source / ".git").exists():
        subprocess.run(["git", "-C", str(source), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(source), "add", "-A"], check=True, capture_output=True)
    changed = subprocess.run(["git", "-C", str(source), "diff", "--cached", "--quiet"], check=False)
    if changed.returncode == 1:
        subprocess.run(["git", "-C", str(source), "-c", "user.name=Client Agent", "-c", "user.email=kit@localhost", "commit", "-m", "Client tool draft"], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def tool_stage(args, **kwargs):
    del kwargs
    return json.dumps(bridge("stage", args["name"], commit=args["commit"]))


def tool_publish(args, **kwargs):
    del kwargs
    return json.dumps(bridge("publish", args["name"], commit=args["commit"], client="client"))


def tool_rollback(args, **kwargs):
    del kwargs
    return json.dumps(bridge("rollback", args["name"], client="client"))


def register(ctx):
    from tools.registry import registry
    ctx.register_hook("pre_tool_call", guard)
    definitions = (
        ("starter_site_preview", "Prepare a local website preview from changed vault website files.", {}, site_preview),
        ("starter_site_publish", "Publish the approved preview to the client's Netlify site.", {}, site_publish),
        ("starter_site_undo", "Redeploy the previous client website version.", {}, site_undo),
        ("starter_make_video", "Make a captioned MP4 from a vault text script.", {"script": {"type": "string"}, "output": {"type": "string"}, "voice": {"type": "boolean"}}, make_video),
        ("starter_video_share", "Copy a vault MP4 into the website draft before preview and approval.", {"name": {"type": "string"}}, share_video),
        ("starter_tool_prepare", "Commit tool source files from the vault tools area.", {"name": {"type": "string"}}, tool_prepare),
        ("starter_tool_stage", "Stage and test a committed client tool.", {"name": {"type": "string"}, "commit": {"type": "string"}}, tool_stage),
        ("starter_tool_publish", "Publish an approved staged tool to the client tailnet.", {"name": {"type": "string"}, "commit": {"type": "string"}}, tool_publish),
        ("starter_tool_rollback", "Roll back a client tool's code.", {"name": {"type": "string"}}, tool_rollback),
    )
    for name, description, properties, handler in definitions:
        schema = {"description": description, "parameters": {"type": "object", "additionalProperties": False, "properties": properties, "required": [key for key, value in properties.items() if key != "voice"]}}
        registry.register(name=name, toolset="file", schema=schema, handler=handler, description=description, emoji="")
