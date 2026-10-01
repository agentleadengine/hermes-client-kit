"""Hermes pre_tool_call guard. Docs: plugin hooks, 2026-09-28 dump 21167."""
import json
from pathlib import Path
from urllib.parse import urlparse

ALLOW = Path("/var/lib/hermes-kit/logins-domains.json")
DENY_TOKENS = ("bank", "credit", "payment", "payroll", "mail", "inbox", "stripe", "paypal", "chase", "wellsfargo", "gusto", "adp")


def permitted(host):
    try:
        domains = json.loads(ALLOW.read_text())
    except (OSError, ValueError):
        return False
    host = host.lower().rstrip(".")
    if any(token in host for token in DENY_TOKENS):
        return False
    return any(host == domain or host.endswith("." + domain) for domain in domains if isinstance(domain, str) and domain)


def guard(tool_name: str, args: dict, task_id: str = "", **kwargs):
    del task_id, kwargs
    if not tool_name.startswith("browser_"):
        return None
    # Browser script/eval primitives can synthesize clicks and navigations.
    # They cannot be inspected reliably, so refuse them.
    if tool_name in {"browser_exec", "browser_eval", "browser_execute", "browser_script", "browser_cdp"} or tool_name.startswith("browser_vault_"):
        return {"action": "block", "message": "Browser scripting is disabled for Logins"}
    text = json.dumps(args, sort_keys=True)
    for value in args.values():
        if isinstance(value, str) and (value.startswith("https://") or value.startswith("http://")):
            url = urlparse(value)
            if url.scheme != "https" or not permitted(url.hostname or ""):
                return {"action": "block", "message": "Site is outside the client's Logins allowlist"}
    if tool_name in {"browser_navigate", "browser_click", "browser_type", "browser_press", "browser_submit", "browser_fill"}:
        return {"action": "approve", "message": "Approve this browser action before it runs", "rule_key": "kit-logins:browser"}
    if "http://" in text or "https://" in text:
        return {"action": "block", "message": "Browser URL cannot be validated"}
    return {"action": "approve", "message": "Approve this browser action before it runs", "rule_key": "kit-logins:browser"}


def register(ctx):
    ctx.register_hook("pre_tool_call", guard)
