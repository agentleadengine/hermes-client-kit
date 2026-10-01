#!/usr/bin/env python3
"""Restricted transport: copy only unread AgentMail text into the vault queue."""
import json
import os
from pathlib import Path

from agentmail import AgentMail

inbox = os.environ["AGENTMAIL_INBOX_ID"]
client = AgentMail(api_key=os.environ["AGENTMAIL_API_KEY"])
queue = Path("/home/hermes/vault/mailroom/incoming")
queue.mkdir(mode=0o700, parents=True, exist_ok=True)
processed = queue.parent / "processed"
processed.mkdir(mode=0o700, parents=True, exist_ok=True)

# The Hermes job writes an acknowledgement only after it has saved its note and
# draft. Deleting then, rather than at staging time, preserves a recoverable
# queue while meeting AgentMail's explicit-retention requirement.
for acknowledgement in processed.glob("*.json"):
    payload = json.loads(acknowledgement.read_text(encoding="utf-8"))
    message_id = payload.get("message_id")
    if not isinstance(message_id, str) or not message_id or "/" in message_id:
        continue
    client.inboxes.messages.delete(inbox, message_id)
    (queue / (message_id.replace("/", "_") + ".json")).unlink(missing_ok=True)
    acknowledgement.unlink()
for message in client.inboxes.messages.list(inbox, labels=["unread"]).messages:
    message_id = message.message_id
    target = queue / (message_id.replace("/", "_") + ".json")
    if not target.exists():
        payload = {
            "message_id": message_id,
            "from": getattr(message, "from_", None) or getattr(message, "from", None),
            "subject": getattr(message, "subject", ""),
            "text": getattr(message, "extracted_text", None) or getattr(message, "text", ""),
            "attachments_omitted": True,
        }
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)
