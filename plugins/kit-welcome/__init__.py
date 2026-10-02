"""Hermes final-response hook for the first owner chat."""
from .kit_welcome import first_reply
from .kit_quota_notice import notify


def welcome(response_text: str, platform: str, **kwargs):
    return first_reply(response_text, platform)


def register(ctx):
    ctx.register_hook("transform_llm_output", welcome)
    ctx.register_hook("api_request_error", quota_error)


def quota_error(status_code=None, reason=None, error=None, **kwargs):
    notify(status_code=status_code, reason=reason, error=error)
