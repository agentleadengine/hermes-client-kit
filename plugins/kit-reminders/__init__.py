"""Guard Hermes cronjob_manage before it changes a job."""
from .kit_reminders import validate_tool_call


def guard(tool_name: str, args: dict, **kwargs):
    if tool_name != "cronjob_manage":
        return None
    try:
        validate_tool_call(args)
    except (ValueError, OSError, TypeError) as error:
        return {"action": "block", "message": str(error)}
    return None


def register(ctx):
    ctx.register_hook("pre_tool_call", guard)
