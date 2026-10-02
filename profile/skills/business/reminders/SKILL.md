---
name: reminders
description: Create and manage reminders sent only to the owner after Schedules is enabled.
version: 1.0.0
license: MIT
---
# Reminders

When the owner asks for a reminder or a recurring plan, use `cronjob_manage`. Confirm the time, timezone, and exact message in plain words before creating it. One reminder is one job. Set `deliver` to the owner's allowlisted chat ID; use `local` only when the owner asks for a saved job with no message. Omit `enabled_toolsets`, or include `no_mcp` in a narrow list. The kit refuses other destinations, scripts, intervals under 15 minutes, and more than 20 jobs. Keep the prompt short and clear; the kit saves it in the vault for audit.

List jobs when asked. To cancel, list first and remove the chosen job ID. To pause or turn on a job, list first and use its ID. The paused Monday plan and Friday wrap are optional examples; turn one on only when the owner asks. Tell the owner what time and wording you saved after each change.
