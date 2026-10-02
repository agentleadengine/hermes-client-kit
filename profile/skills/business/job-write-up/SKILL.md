---
name: job-write-up
description: Turn job notes and photos into a customer summary and private record.
version: 1.0.0
license: MIT
---
# Job write-up

Read `/home/hermes/vault/business/BRIEF.md` first, using the business-brief skill. Match its voice samples, use only confirmed prices, and obey its never-say list.

Input: brief job notes, optional photos, date, customer name, work performed, and any confirmed price. Describe only what the notes or photos support. Mark unclear details for the owner. Produce a ready-to-send **DRAFT — customer summary** and a separate **Internal record** for the private vault, followed by a short **Check before sending** list. Ask whether the owner wants a PDF; if yes, use the `office/pdf` skill when installed. Do not include private internal notes in the customer copy.

The owner sends the summary and approves any saved record. Never send, post, call, charge, or promise anything.

For insurance, never promise coverage or give advice. For real estate, follow Fair Housing: do not mention protected classes, schools, or neighborhood safety.

## Worked example: Mike's Plumbing

Input: Notes: “Oct 1, replaced worn faucet washer, tested faucet, no drip during test.” One photo shows the new washer. No price supplied.

**DRAFT — customer summary**
Thanks for having Mike's Plumbing out today. I replaced the worn faucet washer and tested the faucet afterward. It was not dripping during that test. Let me know if you notice anything else.

**Internal record**
- Date: Oct 1
- Work: Replaced worn faucet washer; tested faucet; no drip during test.
- Photo: New washer shown. Price and customer name not supplied.

**Check before sending**
- Confirm the date, customer name, and work details.
- Add a price only if the owner confirms one.
