---
name: first-response
description: Draft a fast first reply to a new customer inquiry.
version: 1.0.0
license: MIT
---
# First response

Read `/home/hermes/vault/business/BRIEF.md` first, using the business-brief skill. Match its real voice samples, use only its confirmed prices, and obey its never-say list. If the brief is blank, ask for the missing facts before using them.

Input: the customer's message, name if known, and reply channel. Aim to give the owner a draft they can send within five minutes of receiving the inquiry. Include a greeting, exactly two useful qualifying questions, and a clear next step. Do not invent availability or a price.

Return **DRAFT** with the complete reply, then **Check before sending** with a short list of missing or assumed details. The owner sends it. Never send, post, call, charge, or promise anything for the owner.

For insurance, never promise coverage or give advice. For real estate, follow Fair Housing: do not mention protected classes, schools, or neighborhood safety.

## Worked example: Mike's Plumbing

Input: “Kitchen sink is backing up. Can someone come?” Brief confirms a friendly, direct voice but has no available time.

**DRAFT**
Hi, thanks for reaching out to Mike's Plumbing. Is the kitchen sink the only drain backing up? Has any water overflowed? Send the address and a good callback time, and Mike can check the schedule and get back to you.

**Check before sending**
- Confirm the customer's name and preferred reply channel.
- Confirm this is in Mike's service area; no visit time is promised.
