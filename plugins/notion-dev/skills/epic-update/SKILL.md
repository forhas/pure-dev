---
name: epic-update
description: Record a merged ticket on its epic; load follow-up creation/recovery only when needed.
---

# epic-update

Inputs: ticket id, REPO_ROOT, REVIEW_REPORT, optional FILING_DECISIONS and LOCK_HELD.
Reuse retained ticket identity and report paths, then read live pages before writes.
Use configured status mappings and the ticket-system operation references.

## Route

For fully specified approved FILED items on a lean run, or recovery with their existing approved
JSON packets and child journal, read only
`references/approved-followup.md`; execute it after step 2 below, then continue steps 3–5.
Read `references/with-followups.md` and follow it when findings are incomplete, review/filing
history is missing or unknown without those retained packets, a prior resolution has legacy follow-ups to reconcile,
or this is a legacy workflow. Do not load create-task/interview instructions otherwise.
A missing report is not an empty FILED list and cannot authorize epic closure.

## Resolution-only path

1. Fetch the ticket's live parent relation. Empty and usable means EPIC-UPDATE: none.
   Missing/wrong-type parent property is reported via issue-log, not silently interpreted as
   a known absent epic. Validate the candidate epic: empty parent AND true epic-marker checkbox.
   Invalid parent: write nothing, return the cause. Do not mutate an arbitrary parent ticket.
2. Fetch the epic body and parse any matching Resolution Log entry for this ticket and PR.
   Unknown/failed approved packets use approved-followup's journal reconciliation; missing
   packets or legacy follow-up state use the recovery reference above. Never reinterpret an
   approved JSON packet as a legacy indexed Markdown packet or derive a new finding identity.
   An already-complete matching entry skips only the append: still refresh live children and
   reconsider closure below, then report already-recorded with its known outcomes.
3. List live epic children. Render the Tasks table from that list with configured statuses and
   actual links; update only that section, preserving other content and concurrent edits.
   No child-list query error may be treated as an empty, completed epic.
4. Close the epic only when every child is in the configured resolved set, the complete known
   review has no unfiled wanted follow-ups, and existing log/history has no unknown or failed
   filing obligations. A merge is not a deployment: use the plugin's implemented mapping,
   never a release status. Otherwise leave epic status unchanged and state why.
5. Append one dated resolution entry only after those operations are checked. Include ticket,
   PR, absorbed/dropped/blocked outcomes, child counts and
   next blocker or epic complete. Use the established `### [<key>] resolved — <UTC>` shape;
   preserve old entries. Omit empty follow-up lines (never serialize `none` as a follow-up item);
   retain the established **Follow-ups dropped**, **Epic status** and **Next** field names.
   When the approved path filed/deduped items, also include **Follow-ups filed** with actual URLs.
   If that path failed or its outcome is unknown, retain the packet identity and failure explicitly;
   never write a complete resolution or close the epic while a wanted filing is unresolved.
   Journal each provider mutation under the caller's operation when
   RUNTIME_STATE is supplied; a lost response needs readback, not a repeated append.

Return EPIC-UPDATE, EPIC, FILED, ALREADY-FILED, DROPPED, FAILED-TO-FILE, CHILDREN and NEXT as the
existing epic-doc/report consumers expect. Empty buckets say none; unknown is never none.
Failures are best-effort but explicit: record partial:epic-update and return the actual cause.
The caller decides completion from verified outcomes, not from this skill returning.
