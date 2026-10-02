---
name: social-media-content-calendar
description: "Plan multi-platform social campaigns: briefs to posting."
version: 0.1.0
author: Ben Barclay (benbarclay), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Social-Media, Content-Calendar, Campaigns, Publishing]
    related_skills: [xurl, humanizer]
---

## Client kit boundaries

Work only with files under `/home/hermes/vault`. This skill is guidance, not permission to read a client's mailbox, send email, post publicly, use a paid API, install packages, schedule jobs, or connect an account. Ask for explicit client approval before any external action. Read the Business Brief before customer-facing output.

# Social Media Content Calendar

Plan a concrete calendar across selected social platforms. This skill owns campaign structure, post briefs, and channel adaptation. The client kit stops at local drafts for the owner to review. Never schedule or publish through this skill.

## When to Use

- "Build next month's social calendar."
- "Turn this launch into posts for X, LinkedIn, Instagram, and TikTok."
- "Draft and schedule a campaign."
- "Repurpose these articles/videos into social content."

Don't use for: single one-off posts (use the platform skill directly).

## Procedure

### 1. Define campaign constraints

Record objective, audience, offer/message, platforms, date range, cadence, voice, mandatory/prohibited claims, links, tracking convention, localization, and approval/publishing authority. Done when each proposed post has a clear business purpose.

### 2. Inventory source material

Collect verified product facts, launches, articles, media, testimonials with permission, brand assets, and key dates using `read_file` and `web_extract`. Mark claim owners and expiration. Done when unsupported claims and missing assets are visible.

### 3. Build themes and calendar slots

Create a balanced mix such as education, proof, product, community, event, behind-the-scenes, and conversation. Account for platform cadence and campaign milestones. Done when dates, platforms, themes, and objectives form a coherent calendar rather than duplicate cross-posts.

### 4. Write platform-specific briefs

For each post specify hook, core message, format, copy length, CTA, link, asset dimensions/content, accessibility text, tags/mentions, and success metric. Adapt rather than copy-paste between platforms. Done when a creator can produce the asset without hidden context.

### 5. Draft copy and assets

Load `humanizer` for voice; use existing approved assets when needed. Preserve factual claims and shared campaign identity while respecting platform norms. Done when every calendar slot has draft copy and asset status.

### 6. Run editorial and risk review

Check factual accuracy, tone, repetition, rights/permissions, accessibility, disclosures, link destination, date relevance, and crisis sensitivity. Mark `draft`, `needs review`, or `approved`; do not publish from draft. Done when every post has a disposition and owner.

### 7. Hand off drafts

Save the approved calendar in the vault and tell the owner which slots still need assets or review. Do not claim anything was scheduled or published. Scheduling or publishing requires a separately approved capability and fresh approval for the exact content.

## Pitfalls

- Identical copy on every platform.
- Filling cadence with low-value repetitive posts.
- Publishing unverified metrics, testimonials, or future claims.
- Confusing generated asset completion with scheduled publication.
- Claiming "scheduled" for platforms where the handoff ended at drafts.

## Verification

- [ ] Every post traces to a campaign objective and a verified claim inventory.
- [ ] No post was published from `draft` or `needs review` state.
- [ ] Published slots have provider-confirmed IDs; handed-off slots are marked as such.
- [ ] Rights, permissions, and disclosures checked before any publish.
