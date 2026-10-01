---
name: private-tools
description: Draft, test, publish, and roll back small client tools using Builder and the client's tailnet.
version: 1.0.0
license: MIT
---
# Private client tools

Draft a small tool in `/home/hermes/vault/tools/TOOL_NAME`. Use a simple lowercase name with hyphens. Do not read private data outside the draft area. Do not add credentials, hidden files, symlinks, payment, banking, payroll, or mailbox functions.

Call `starter_tool_prepare` to make an exact source commit, then `starter_tool_stage` with that commit. Staging runs the existing Builder checks under the separate builder account. Tell the client what the tool will do and which commit was tested. Wait for their explicit approval by text before calling `starter_tool_publish` for that exact commit. The published tool runs under its own account and is served only inside the client's Tailscale network.

For rollback, explain that only code is restored and new database records remain. Ask for approval, then call `starter_tool_rollback`. Never bypass the Builder review and publish path.
