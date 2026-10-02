---
name: quote-follow-up
description: Draft polite follow-ups for an open customer quote.
version: 1.0.0
license: MIT
---
# Quote follow-up

Read `/home/hermes/vault/business/BRIEF.md` first, using the business-brief skill. Match its voice samples, use only confirmed prices, and obey its never-say list.

Input: customer, quoted work, amount, quote date, and any earlier reply. Draft a brief, useful follow-up for day 2, 7, or 14 after the quote. Ask whether they have questions and offer a simple next step. Do not imply that the quote is accepted, still valid, or that a slot is held unless confirmed.

Keep a small private ledger at `/home/hermes/vault/business/quotes.md`: customer, work, amount, quote date, last touch, next touch (day 2/7/14), and status. Create or update only after the owner confirms the facts and approves saving them. Do not put private customer details in a public location. After day 14, ask the owner before any further follow-up.

Return **DRAFT** and a short **Check before sending** list with missing or assumed facts. The owner sends it. Never send, post, call, charge, or promise anything.

For insurance, never promise coverage or give advice. For real estate, follow Fair Housing: do not mention protected classes, schools, or neighborhood safety.

## Worked example: Mike's Plumbing

Input: Quote for a faucet replacement, $240, sent to Jordan on Monday; today is Wednesday.

**DRAFT**
Hi Jordan, following up on the $240 faucet replacement quote I sent Monday. Any questions I can clear up? If you'd like to go ahead, reply here and we can discuss a time.

**Check before sending**
- Confirm the $240 amount, quote date, and whether the quote is still valid.
- Confirm Jordan has not already replied or booked.
