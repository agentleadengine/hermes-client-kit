"""MCP platform policy matching Hermes f97608f toolset and cron resolvers."""
from __future__ import annotations

import re

# hermes_cli/platforms.py at f97608f, plus the kit's plugin platforms and ACP.
PLATFORMS = (
    "cli", "telegram", "discord", "slack", "whatsapp", "whatsapp_cloud",
    "signal", "bluebubbles", "email", "homeassistant", "mattermost",
    "matrix", "dingtalk", "feishu", "wecom", "wecom_callback", "weixin",
    "qqbot", "yuanbao", "webhook", "api_server", "cron", "photon",
    "agentmail", "acp",
)
BASE_PLATFORMS = frozenset(("cli", "telegram", "photon", "whatsapp", "signal", "slack", "agentmail", "cron"))
SERVER_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
# Hermes' pinned resolver classifies these as native/plugin toolsets, not MCP
# passthrough names. A server with one of these names cannot form an allowlist.
RESERVED_SERVER_NAMES = frozenset((
    "web", "browser", "terminal", "file", "code_execution", "vision", "video",
    "image_gen", "video_gen", "x_search", "tts", "stt", "skills", "todo",
    "kanban", "memory", "context_engine", "session_search", "connections",
    "clarify", "delegation", "cronjob", "homeassistant", "spotify", "discord",
    "discord_admin", "yuanbao", "computer_use", "no_mcp", "all", "search",
    "messaging", "process", "acp",
))


def enabled_servers(config_servers: object, profile_servers: object) -> set[str]:
    """Config servers are enabled unless explicitly false; profile mcp.json is additive."""
    def enabled(entry: dict) -> bool:
        value = entry.get("enabled", True)
        if value is None:
            return True
        if isinstance(value, (bool, int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        return True

    config = config_servers if isinstance(config_servers, dict) else {}
    profile = profile_servers if isinstance(profile_servers, dict) else {}
    result = {name for name, entry in config.items() if isinstance(entry, dict) and enabled(entry)}
    result.update(name for name, entry in profile.items() if name not in config and isinstance(entry, dict) and enabled(entry))
    return result


def grants(entries: list[dict]) -> dict[str, set[str]]:
    allowed: dict[str, set[str]] = {platform: set() for platform in PLATFORMS}
    for entry in entries:
        server = entry.get("mcp_server")
        if server is None:
            continue
        platforms = entry.get("mcp_platforms")
        if not isinstance(server, str) or not SERVER_NAME.fullmatch(server) or server in RESERVED_SERVER_NAMES or server.startswith("hermes-") or not isinstance(platforms, list) or not platforms or any(p not in allowed for p in platforms):
            raise ValueError("Invalid MCP consent server or platforms")
        for platform in platforms:
            allowed[platform].add(server)
    return allowed


def platform_tools(platform: str, base_tools: list[str], allowed: dict[str, set[str]]) -> list[str]:
    servers = sorted(allowed[platform])
    # Hermes' no_mcp sentinel wins over named servers, so it is absent on a granted platform.
    return base_tools + (servers if servers else ["no_mcp"])


def audit(platform_toolsets: object, config_servers: object, profile_servers: object,
          entries: list[dict], jobs: object = None) -> list[str]:
    """Compute effective reachability using Hermes' pinned merge and cron override rules."""
    errors = []
    try:
        allowed = grants(entries)
    except ValueError as exc:
        return [str(exc)]
    enabled = enabled_servers(config_servers, profile_servers)
    if not isinstance(platform_toolsets, dict):
        return ["platform_toolsets is not a mapping"]
    for platform in sorted(set(PLATFORMS) | set(platform_toolsets)):
        selected = platform_toolsets.get(platform)
        if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected):
            errors.append(f"{platform}: no explicit platform toolset list")
            continue
        named = set(selected) & enabled
        reachable = set() if "no_mcp" in selected else (named or enabled)
        unexpected = reachable - allowed.get(platform, set())
        if unexpected:
            errors.append(f"{platform}: unconsented MCP access to {','.join(sorted(unexpected))}")
        if not named and "no_mcp" not in selected:
            errors.append(f"{platform}: MCP default merge is open")
        if "no_mcp" in selected and (allowed.get(platform, set()) & enabled):
            errors.append(f"{platform}: consented server blocked by no_mcp")
        if named and named != (allowed.get(platform, set()) & enabled):
            errors.append(f"{platform}: MCP server list differs from consent")
    if jobs is None:
        jobs = []
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", [])
    if not isinstance(jobs, list):
        return errors + ["cron jobs are not a list"]
    for index, job in enumerate(jobs):
        if not isinstance(job, dict) or job.get("enabled") is False:
            continue
        selected = job.get("enabled_toolsets")
        if not selected:
            continue  # Hermes uses platform_toolsets.cron.
        if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected):
            errors.append(f"cron job {index}: invalid enabled_toolsets")
            continue
        named = set(selected) & enabled
        reachable = set() if "no_mcp" in selected else (named or enabled)
        unexpected = reachable - allowed["cron"]
        if unexpected:
            errors.append(f"cron job {index}: unconsented MCP access to {','.join(sorted(unexpected))}")
        if not named and "no_mcp" not in selected:
            errors.append(f"cron job {index}: MCP default merge is open")
    return errors
