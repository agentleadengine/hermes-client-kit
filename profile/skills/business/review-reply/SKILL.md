---
name: review-reply
description: Draft a specific public reply to a customer review.
version: 1.0.0
license: MIT
---
# Review reply

Read `/home/hermes/vault/business/BRIEF.md` first, using the business-brief skill. Match its voice samples, use only confirmed prices, and obey its never-say list.

Input: the review text, rating, platform, and only the public facts the owner confirms. Draft a short, specific reply that reflects one real detail. Avoid a repeated template. For a complaint, acknowledge the concern calmly and offer an offline next step; never argue. Do not reveal customer private details, address, job history, payment, or contact information. Suggest owner review and posting the same day when practical.

Return **DRAFT** and a short **Check before sending** list. The owner posts it. Never send, post, call, charge, or promise anything.

For insurance, never promise coverage or give advice. For real estate, follow Fair Housing: do not mention protected classes, schools, or neighborhood safety.

## Worked example: Mike's Plumbing

Input: Public 5-star review: “Mike explained the leaky faucet and cleaned up afterward.”

**DRAFT**
Thanks for taking the time to share this. I'm glad the faucet explanation was clear and the work area was left tidy. We appreciate you choosing Mike's Plumbing.

**Check before sending**
- Confirm Mike's Plumbing is the correct public business name.
- Owner should review and post today if possible.
