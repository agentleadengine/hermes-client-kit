---
name: integration-guide
description: Explain client-chosen integrations and obtain an informed, least-privilege consent record before any connection.
---

# Integration guide

The client chooses whether to connect a tool. Never connect one yourself and never ask for passwords, OAuth codes, recovery codes, or API keys in chat. Direct the client to the provider's own sign-in flow or the local `kit-set-key` prompt.

For every proposed integration, explain in plain English:

1. What the agent could see and do with the requested scopes.
2. The bad-day story, including what a malicious prompt or compromised account could expose or change.
3. Its risk level: GREEN for narrow read-only data, YELLOW for sensitive data or reversible changes, RED for sending as the client, payments/refunds, deletion, or publishing.
4. The safest setup: least-privilege read-only scopes first, and a separate limited account where possible.
5. How the client disconnects it, revokes its credential, and removes its consent record.

## Risk cards

| Tool | Start with | Bad-day story | Level | Disconnect |
| --- | --- | --- | --- | --- |
| Gmail, Outlook | Do not connect a mailbox in this kit. Use AgentMail. | A hostile email causes a forward or send. | GREEN read-only, RED send/delete | Revoke provider grant. |
| Calendar | Read availability/events only. | A poisoned event changes or invites attendees. | GREEN read, YELLOW edit, RED delete | Revoke OAuth grant. |
| Drive, OneDrive, SharePoint, Dropbox | One selected read-only folder/site. | A file induces sharing, overwrite, or upload. | GREEN read, RED share/delete | Revoke grant and selected-resource access. |
| Slack | Dedicated bot in selected channels, read only. | A channel message induces a false post or leak. | GREEN read, RED send | Revoke token and uninstall app. |
| Notion, Airtable, Trello, Asana | Selected pages/base/project, read only. | A record or task induces edits or deletion. | GREEN read, RED delete/post | Remove connection and revoke token. |
| HubSpot, GoHighLevel, Salesforce | Dedicated low-privilege reporting account. | A CRM note induces outreach or changes. | GREEN read, RED send/delete | Revoke app/token and integration user. |
| QuickBooks, Xero, Stripe, Square | Sandbox or read-only reporting data only. | An invoice induces payment, refund, or export. | GREEN read, RED money/delete | Revoke token in provider console. |
| Shopify, WordPress | Development/staging and drafts only. | Content induces a price change or publication. | YELLOW drafts, RED publish/delete | Uninstall app or revoke application password. |
| Calendly | `scheduled_events:read` only. | An event induces cancellation or outbound mail. | GREEN read, RED cancel/send | Revoke OAuth token. |

For all tools: connect one at a time, use a separate limited account where possible, test with synthetic data, and keep external sends, money movement, deletion, sharing, and publishing behind a per-action human approval. Generic MCP, custom skills, and third-party hub installs remain off unless separately reviewed and pinned.

Run `sudo kit-consent add <integration>` only with the client present after they type `I understand`. A ledger entry does not grant action authority. RED actions always require a separate, per-action client approval.

Refuse to store regulated data: patient records, legal case files, Social Security numbers, card numbers, bank logins, passwords, or recovery codes.
