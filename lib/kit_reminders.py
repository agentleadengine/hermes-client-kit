"""Owner-only rules shared by kit-verify and the Hermes cron hook."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import re

CONFIG = Path(os.environ.get("KIT_REMINDERS_CONFIG", "/etc/hermes-kit/kit.conf"))
JOBS = Path(os.environ.get("KIT_REMINDERS_JOBS", "/home/hermes/.hermes/profiles/client/cron/jobs.json"))
VAULT = Path(os.environ.get("KIT_REMINDERS_VAULT", "/home/hermes/vault/reminders"))
SAFE_TOOLS = {"clarify", "file", "memory", "search", "skills", "todo", "vision", "web", "no_mcp"}


def origin_target(origin: object) -> str:
    if not isinstance(origin, dict) or origin.get("thread_id"):
        return ""
    platform, chat_id = origin.get("platform"), origin.get("chat_id")
    if not isinstance(platform, str) or not isinstance(chat_id, str):
        return ""
    return f"{platform}:{chat_id}"


def current_origin_target() -> str:
    try:
        from gateway.session_context import get_session_env
        return origin_target({"platform": get_session_env("HERMES_SESSION_PLATFORM"),
                              "chat_id": get_session_env("HERMES_SESSION_CHAT_ID"),
                              "thread_id": get_session_env("HERMES_SESSION_THREAD_ID")})
    except ImportError:
        return ""


def allowed_delivery(deliver: object, target: str, origin: object = None) -> bool:
    return deliver == "local" or bool(target and (deliver == target or (deliver == "origin" and origin_target(origin) == target)))


def owner_target_from_values(values: dict[str, str]) -> str:
    platform = values.get("MESSAGING_PLATFORM")
    key = {"photon": "PHOTON_ALLOWED_USERS", "telegram": "TELEGRAM_ALLOWED_USERS",
           "whatsapp": "WHATSAPP_ALLOWED_USERS", "signal": "SIGNAL_ALLOWED_USERS",
           "slack": "SLACK_ALLOWED_USERS"}.get(platform)
    owner = values.get(key, "") if key else ""
    if platform == "photon" and re.fullmatch(r"\+[1-9][0-9]{6,14}", owner):
        return f"photon:{owner}"
    if platform == "telegram" and re.fullmatch(r"[0-9]{5,15}", owner):
        return f"telegram:{owner}"
    if platform in {"whatsapp", "signal", "slack"} and re.fullmatch(r"[A-Za-z0-9._:@+-]{3,128}", owner):
        return f"{platform}:{owner}"
    return ""


def owner_target() -> str:
    values = {}
    try:
        for line in CONFIG.read_text().splitlines():
            match = re.fullmatch(r'([A-Z_]+)=["\']?([^"\']*)["\']?', line)
            if match:
                values[match[1]] = match[2]
    except FileNotFoundError:
        return ""
    return owner_target_from_values(values)


def valid_schedule(schedule: object, *, new: bool = False) -> bool:
    if isinstance(schedule, str):
        try:
            from cron.jobs import parse_schedule  # installed pinned Hermes
            schedule = parse_schedule(schedule)
        except ImportError:
            value = schedule.strip().lower()
            match = re.fullmatch(r"(?:every )?([0-9]+)\s*(m|h|d)", value)
            if match:
                amount = int(match[1]) * {"m": 1, "h": 60, "d": 1440}[match[2]]
                schedule = {"kind": "interval", "minutes": amount}
            elif value.startswith("every ") and re.fullmatch(r"every (monday|tuesday|wednesday|thursday|friday|saturday|sunday) [0-9]{1,2}(?:am|pm)", value):
                day, clock = value.split()[1:]
                hour = int(clock[:-2]) % 12 + (12 if clock.endswith("pm") else 0)
                schedule = {"kind": "cron", "expr": f"0 {hour} * * {['sunday','monday','tuesday','wednesday','thursday','friday','saturday'].index(day)}"}
            elif len(schedule.split()) == 5:
                schedule = {"kind": "cron", "expr": schedule}
            else:
                return False
        except ValueError:
            return False
    if not isinstance(schedule, dict):
        return False
    kind = schedule.get("kind")
    if kind == "interval":
        return isinstance(schedule.get("minutes"), (int, float)) and schedule["minutes"] >= 15
    if kind == "once":
        try:
            due = datetime.fromisoformat(schedule["run_at"].replace("Z", "+00:00"))
            if due.tzinfo is None:
                return False
            return not new or (due - datetime.now(timezone.utc)).total_seconds() >= 15 * 60 - 2
        except (KeyError, TypeError, ValueError):
            return False
    if kind == "cron":
        expr = schedule.get("expr", "")
        fields = expr.split() if isinstance(expr, str) else []
        if len(fields) != 5:
            return False
        minute = fields[0]
        if re.fullmatch(r"[0-5]?[0-9]", minute):
            return True
        match = re.fullmatch(r"\*/([0-9]+)", minute)
        if match and int(match[1]) >= 15 and 60 % int(match[1]) == 0:
            return True
        if re.fullmatch(r"[0-5]?[0-9](,[0-5]?[0-9])+", minute):
            points = sorted({int(x) for x in minute.split(",")})
            return len(points) > 1 and min((b-a) % 60 for a, b in zip(points, points[1:] + points[:1])) >= 15
    return False


def audit_prompt(prompt: str, schedule: str) -> None:
    if VAULT.is_symlink():
        raise ValueError("Reminder vault directory cannot be a link")
    VAULT.mkdir(mode=0o700, parents=True, exist_ok=True)
    owner = os.geteuid() == 0 and os.environ.get("KIT_POWERUP_TEST_MODE") != "1"
    if owner:
        account = pwd.getpwnam("hermes")
        os.chown(VAULT, account.pw_uid, account.pw_gid)
    digest = hashlib.sha256((schedule + "\n" + prompt).encode()).hexdigest()[:20]
    path = VAULT / f"{digest}.txt"
    if path.is_symlink():
        raise ValueError("Reminder audit file cannot be a link")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) if not path.exists() else None
    if fd is not None:
        with os.fdopen(fd, "w") as output:
            output.write(f"Schedule: {schedule}\nPrompt: {prompt}\n")
        if owner:
            os.chown(path, account.pw_uid, account.pw_gid)


def validate_tool_call(args: dict) -> None:
    action = args.get("action")
    if action == "list":
        return
    if action not in {"create", "update", "pause", "resume", "remove"}:
        raise ValueError("Only list, create, update, pause, resume, and remove are allowed")
    jobs_doc = json.loads(JOBS.read_text()) if JOBS.exists() else []
    jobs = jobs_doc if isinstance(jobs_doc, list) else jobs_doc.get("jobs", [])
    if not isinstance(jobs, list) or len(jobs) >= 20 and action == "create":
        raise ValueError("Limit of 20 reminders reached")
    if action != "create":
        found = next((job for job in jobs if job.get("id") == args.get("job_id")), None)
        if not found:
            raise ValueError("List reminders first and use an existing job ID")
    else:
        found = {}
    target = owner_target()
    if found and (not allowed_delivery(found.get("deliver"), target, found.get("origin")) or
                  (found.get("failure_deliver") not in {None, ""} and
                   not allowed_delivery(found.get("failure_deliver"), target, found.get("origin"))) or
                  any(found.get(field) for field in ("script", "monitor_script", "monitor_url", "no_agent", "workdir")) or
                  not valid_schedule(found.get("schedule"))):
        raise ValueError("This job is outside the owner reminder policy")
    if action in {"pause", "remove"}:
        return
    for field in ("script", "monitor", "monitor_script", "monitor_url", "workdir", "no_agent", "context_from", "continuity"):
        if args.get(field):
            raise ValueError(f"{field} is unavailable for reminders")
    deliver = args.get("deliver", found.get("deliver"))
    if action == "create" and deliver is None:
        deliver = "origin"
    origin = found.get("origin") if found else None
    if deliver == "origin" and origin is None and current_origin_target() == target:
        origin = {"platform": target.split(":", 1)[0], "chat_id": target.split(":", 1)[1]}
    if not allowed_delivery(deliver, target, origin):
        raise ValueError("A reminder may deliver only to the allowlisted owner or local")
    failure = args.get("failure_deliver", found.get("failure_deliver"))
    if failure not in {None, ""} and not allowed_delivery(failure, target, origin):
        raise ValueError("Failure notices must go only to the owner or local")
    tools = args.get("enabled_toolsets", found.get("enabled_toolsets"))
    if tools is not None and (not isinstance(tools, list) or set(tools) - SAFE_TOOLS):
        raise ValueError("Reminder toolset is too broad")
    if tools and "no_mcp" not in tools:
        raise ValueError("Reminder toolsets must include no_mcp")
    prompt = args.get("prompt", found.get("prompt"))
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ValueError("Reminder needs a short auditable prompt")
    schedule = args.get("schedule", found.get("schedule"))
    if not valid_schedule(schedule, new=isinstance(args.get("schedule"), str)):
        raise ValueError("Reminder must be at least 15 minutes away or apart")
    if action in {"create", "update"}:
        audit_prompt(prompt, str(schedule))
