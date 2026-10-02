---
name: invoice-reminder-drafts
description: Draft respectful payment reminders from owner-provided invoice facts.
version: 1.0.0
license: MIT
---
# Invoice reminder drafts

Read `/home/hermes/vault/business/BRIEF.md` first, using the business-brief skill. Match its voice samples, use only confirmed prices, and obey its never-say list.

Input: customer, invoice number, amount, due date, payment status, and the owner's preferred payment instructions. Compute days overdue from the confirmed due date. Use a friendly tone for an early reminder, a firmer factual tone for an older unpaid invoice, and a final tone only when the owner asks. Never invent fees, deadlines, consequences, or legal claims. If payment may be in transit, invite correction.

Keep a private aging ledger at `/home/hermes/vault/business/invoices.md`: customer, invoice number, amount, due date, days overdue, last touch, next review, and status. Update it only after the owner confirms facts and approves saving. Do not include bank or card details.

Return **DRAFT** and a short **Check before sending** list. The owner sends it. Never send, post, call, charge, or promise anything.

For insurance, never promise coverage or give advice. For real estate, follow Fair Housing: do not mention protected classes, schools, or neighborhood safety.

## Worked example: Mike's Plumbing

Input: Invoice 203 for $180, due 10 days ago, owner says unpaid; friendly reminder requested.

**DRAFT**
Hi Jordan, a quick note about Mike's Plumbing invoice 203 for $180, due 10 days ago. If you've already paid, please disregard this and let me know. Otherwise, could you tell me when you expect to take care of it? Thanks.

**Check before sending**
- Recheck payment status, amount, due date, and recipient.
- Add the owner's confirmed payment instructions if useful.
