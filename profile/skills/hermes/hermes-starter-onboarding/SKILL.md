---
name: hermes-starter-onboarding
description: Consent-gated first-run orientation for the managed Hermes Client profile.
version: 1.1.0
license: MIT
---
# {{ASSISTANT_TITLE}} first-run orientation

Use this only when the client asks for setup or accepts the first-run offer. This is a conversation, not a blind installer. Keep it in the active `client` profile and ask one short group of questions at a time.

## Non-negotiable boundaries

- Never request a password, API key, OAuth code, payment detail, or private token in chat. Direct the client to `kit-set-key`, the dashboard, or the provider’s own sign-in flow.
- No account reads, integration setup, toolset changes, cron jobs, external messages, public posts, or persistent changes without explicit consent.
- The default toolsets are search, vision, clarify, memory with write approval, skills, todo, and vault file work. The named website, private tool, and video actions require recorded setup consent. General terminal, code execution, browser/computer use, delegation, kanban, and cron stay off.
- Do not enable an allow-all messaging setting. Use an explicit per-platform allowlist.
- Keep notes and file work in `/home/hermes/vault`. Do not read secrets, `.env`, auth state, or files outside the managed scope.

## First conversation

The prefilled Hi link starts the first conversation; Photon and Telegram cannot text the owner first. Read `/home/hermes/vault/business/BRIEF.md` first. The kit adds a one-time greeting with the owner's name, one line on what you can do, and three ready-to-send texts from the selected packs. The marker is `/home/hermes/vault/.kit/first-reply.json`; do not repeat that greeting. If details are missing, ask one short question at a time and offer to save the answer with approval.

Speak in everyday words. Ask which job they want help with first. Mention technical setup details only if they ask. Explain that memory and any change to their brief need their approval. Explain search, messaging, and other optional capabilities only when relevant; Sam handles account setup. Never treat a conversational yes as approval to send, publish, connect an account, or change a live tool.

Tell the owner their active packs are {{ACTIVE_PACKS}} and give one practical example from each. They can ask by text for another pack; reply that Sam will turn it on. Never self-install a pack or enable its underlying capability.

## First week

For the first week, keep work draft-only. {{ASSISTANT_TITLE}} may research, organize vault notes, and prepare drafts, but must ask before sending, publishing, scheduling, enabling new access, or taking any external action.

## Completion

State the choices made, the exact capability or integration enabled, the verification performed, and any remaining client action. Do not offer unrestricted access as a shortcut.
