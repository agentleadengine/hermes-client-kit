---
name: weekly-review-planning
description: "Weekly reset: commitments, stalled work, next-week plan."
version: 0.1.0
author: Ben Barclay (benbarclay), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Weekly-Review, Planning, Tasks, Calendar, Productivity]
    related_skills: [obsidian, notion, airtable, google-workspace, email-inbox-triage]
---

## Client kit boundaries

Work only with files under `/home/hermes/vault`. This skill is guidance, not permission to use disabled tools, read a client's mailbox, send email, post publicly, access a paid API, install packages, schedule jobs, or connect accounts. Ask for explicit client approval before any external action. If a helper needs execution, use only a separately approved kit lane; never ask the client agent to run a terminal command. Read the Business Brief before customer-facing output.

# Weekly Review and Planning

Run a bounded weekly reset from notes and task lists the owner has placed in the vault. Offer it on request. With Schedules enabled, the paused Monday plan can be turned on by the owner for an automatic weekly message to their allowlisted chat.

## When to Use

- "Run my weekly review."
- "What did I commit to and what is slipping?"
- "Plan next week from my calendar, tasks, and notes."
- "Find stale projects and waiting items."

Do not open a mailbox or connected account for this review.

## Procedure

### 1. Set systems and window

Confirm timezone, review period, planning horizon, authoritative task/project store, calendar notes already in the vault, and allowed local writes. Default to recommendations/drafts, not mutations. Done when source-of-truth conflicts have a declared winner.

### 2. Review calendar evidence

Use calendar notes the owner provided in the vault. Inspect the completed week for meetings and commitments, then the next 1-2 weeks for deadlines, travel, preparation, and capacity. Capture follow-ups implied by past events and conflicts ahead. Done when both retrospective and horizon are covered.

### 3. Clear capture inboxes

Review task lists and notes in the vault. Convert each item to next action, project, waiting, scheduled, someday, reference, archive, or delete proposal. Do not mutate until scope is approved. Done when remaining unprocessed items are counted and stated.

### 4. Reconcile active projects

For each project identify desired outcome, next action, owner, deadline, blocker, last meaningful activity, and source link. Flag projects with no next action, missed dates, duplicate records, or contradictory status. Done when every active project is actionable or explicitly paused.

### 5. Review waiting and commitments

Find promises made by the user and items owed by others. Propose follow-ups with dates and channels. Do not infer that silence means completion. Done when each waiting item has an owner and next review/follow-up date.

### 6. Build a capacity-aware plan

Estimate fixed calendar load and select a small set of weekly outcomes plus near-term next actions. Rank by consequence, deadline, dependency, and effort; do not fill every free hour. Done when the plan fits actual capacity and names deferred work.

### 7. Apply approved updates

Update local task notes and draft follow-ups only as approved. Read changed vault files back. Any external calendar or tracker change needs a separately enabled capability and explicit per-action approval. Done when verified writes match the review summary.

## Output Shape

1. Wins and completed commitments
2. Overdue or at risk
3. Waiting/follow-ups
4. Stalled or ambiguous projects
5. Next week's outcomes and calendar constraints
6. Proposed updates awaiting approval
7. Coverage gaps

## Pitfalls

- Planning from tasks without calendar capacity.
- Carrying every unfinished item forward as high priority.
- Marking projects active with no next action.
- Silently deleting or rescheduling personal commitments.
- Treating silence from others as completion.

## Verification

- [ ] Both the completed week and the planning horizon were covered, or gaps are stated.
- [ ] Every stalled/waiting flag traces to a specific record, event, or thread.
- [ ] No task, event, or note was mutated without approval; approved writes were read back.
- [ ] The plan names what was deferred, not just what was chosen.
