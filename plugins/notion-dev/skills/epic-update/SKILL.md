---
name: epic-update
description: Use after a ticket reaches Implemented, from /notion-dev:ticket Phase 8 or /notion-dev:finalize Phase 3, to record the resolution on the ticket's Epic container — file deferred follow-ups, refresh the Epic's task list, append a dated log entry, and close the Epic when everything under it is resolved.
---

# epic-update

Records a resolved ticket against its Epic container. Invoked by `/notion-dev:ticket` (Phase 8) and `/notion-dev:finalize` (Phase 3) — the two entry points that take a ticket to `Implemented`.

**Args:** `<ticket-id>` (the numeric or logical key of the just-resolved ticket), plus `--non-interactive` when the caller is in that mode.

**Caller-supplied context:** `REVIEW_REPORT` (the review loop's final report, source of the deferred follow-ups) and `REPO_ROOT` (the primary checkout — the caller recorded it before any `cd` into a worktree).

**Every step here is best-effort**: a failure logs a warning and continues to the next step. This skill never fails its caller's run — the merge has already landed by the time it is invoked, and epic bookkeeping is not worth losing that.

**1. Resolve the epic.** `fetchTicket(<ticket-id>)` and read `metadata.parentTaskProperty`. Empty (`""`), or the property absent from the live DB → **skip steps 2-5 entirely** and return `EPIC-UPDATE: none`. Not an error; most tickets have no epic. Otherwise `EPIC_ID` is the referenced page — fetch it for its title, Epic name, and body (used by step 1a). Also record this ticket's `key` (e.g. `"STO-67"`) from the same `fetchTicket(<ticket-id>)` result — used by step 1a.

Also record `TICKET_ASSIGNEE = metadata.assigneeProperty` from that same `fetchTicket` call — `""` when the ticket has no assignee, the property is absent, or it isn't People-typed. Used by step 2.

**1a. Idempotency check.** Before any mutation, parse `## Resolution Log` from the epic body fetched in step 1 into its `### [<KEY>-<n>] resolved — <datetime>` entries (same parse `getEpicContext` step 5 does). If an entry already exists whose `<KEY>-<n>` equals this ticket's `key` (step 1) → a prior invocation already recorded this exact resolution (e.g. `/notion-dev:finalize`'s post-merge recovery path re-invoking `epic-update` after an interrupted run had already appended the log entry). **Skip steps 2-5 entirely** — no follow-up filing, no task-list refresh, no log append, no close check — and return `EPIC-UPDATE: already-recorded`. This single check is what makes re-invoking this skill safe: both the duplicate-ticket-filing and duplicate-log-entry failure modes happen inside the same invocation this check short-circuits.

**2. File deferred follow-ups.** Source: `REVIEW_REPORT`'s deferred follow-ups — the same list written to the ticket's `## Merged` section.

This step is deduplicated **per follow-up**, not just at the whole-invocation level step 1a already covers. Step 1a's log-entry check is a fast path for the fully-completed case; it cannot catch a run that died after this step created a ticket but before step 4 appended the log entry, because the log entry is written *after* this step, not before. So each follow-up must recognize on its own whether it was already filed by a prior, interrupted invocation:

- Call `listEpicChildren(EPIC_ID)` once, before filing anything, to get the epic's current children. (This is separate from step 3's own `listEpicChildren` call below, which re-fetches *after* this step's creates so its list reflects them.)
- For each item, derive its ticket title **deterministically** from the review finding — the same finding text must always produce the same title, verbatim, on every invocation. This derived title is the dedup key: if the derivation varies run to run (paraphrasing, embedding a timestamp, truncating differently), a recovery run cannot recognize a follow-up it already filed, and dedup silently fails, refiling a duplicate.
- **Already filed** — if a child's title (case-insensitive, prefix-stripped) matches this item's derived title, do not create it again. Record it under `ALREADY_FILED` (with the existing child's `id`/`title`/`url`) and move to the next item.
- **Not yet filed** — gate creation:
  - **Interactive**: `AskUserQuestion` — **File as ticket** / **Skip**. Default File.
  - **Non-interactive**: file it. Nothing is left deferred.

For each item actually filed (i.e. not deduped as already-filed, and not user-skipped), write a context packet to `$REPO_ROOT/.claude/notion-dev/followup-<KEY>-<id>-<n>.md` (`<n>` = 1-based index; the same self-ignored directory the ledger lives in, so it never appears in `git status` or contaminates a branch) containing: the resolved ticket's title, body, and URL; the PR URL and `git show --stat <merge-commit>`; the review finding verbatim; and the rationale recorded when it was deferred. Leave the packet in place after the run as a record of what the ticket was generated from.

Then run:

```
/notion-dev:create-task --non-interactive --context-file=<packet> --epic="<epic name>" --parent=<EPIC_ID> [--assignee=<TICKET_ASSIGNEE>] prompt:<finding title>
```

Include `--assignee=<TICKET_ASSIGNEE>` only when `TICKET_ASSIGNEE` (step 1) is non-empty. When it's empty — the resolved ticket had no assignee — omit the flag entirely and let create-task's own Phase 2.75 `defaultAssignee` resolution decide; that fallback is exactly what Phase 2.75 already does for any caller that doesn't pass `--assignee`, so no special-casing is needed here.

Record `FILED` = `[{ id, title, url }]` for each newly created ticket, `ALREADY_FILED` = `[{ id, title, url }]` for each item deduped against an existing child, and `UNFILED` = the items the user chose to skip. A create-task failure is **non-fatal**: log it, add the item to `UNFILED`, continue. When `REVIEW_REPORT` has no deferred follow-ups, all three lists are empty and this step is a no-op.

**3. Refresh the epic's `## Tasks`.** Invoke `notion-dev:ticket-system` operation `refreshEpicTasks(EPIC_ID)`, then `listEpicChildren(EPIC_ID)` to hold the child list for steps 4 and 5. Do **not** render the task list here — `refreshEpicTasks` owns that format, and duplicating it is how this section drifts from the one `/notion-dev:create-task` writes.

The mirror is refreshed only on resolution, so between resolutions it lags reality; the live view is Notion's Parent task relation column, and the section exists so the epic reads as a coherent document.

**4. Append the log entry.** Invoke `appendToSection(EPIC_ID, "Resolution Log", <entry>)`. The entry is a `divider` block followed by:

```
### [<KEY>-<id>] resolved — <YYYY-MM-DD HH:MM UTC>
**Summary** — <2-4 sentences: what was actually done, distilled from the ticket's ## Implementation section and the merge>
**Follow-ups filed** — [<KEY>-69] Backfill historic wallets · <url>    (`FILED` ∪ `ALREADY_FILED`; omit the line when both are empty — this is the first log entry to record this ticket's resolution regardless of which invocation actually created the follow-up ticket)
**Follow-ups deferred** — <item>                                       (omit the line when UNFILED is empty)
**Epic status** — 2 of 3 tasks resolved
**Next** — <the remaining blocker, or "epic complete">
```

`## Resolution Log` is created on first use by `appendToSection`. Timestamp from `date -u +"%Y-%m-%d %H:%M UTC"`. `Epic status` counts against step 3's child list using the resolved set; when step 5 closes the epic it reads `all N tasks resolved — epic closed`.

**5. Close the epic.** Evaluate against the child list step 3 already fetched — read *after* step 2 filed its follow-ups, so new tickets are in it. Do not re-query.

Close only when **all** of:
1. Every child other than the just-resolved one has a status in the resolved set.
2. `FILED` and `ALREADY_FILED` are both empty. Strictly redundant with (1) — a freshly filed or already-filed follow-up is an unresolved child, so (1) already fails — but stated so the intent survives any future change to when the child list is read.
3. `UNFILED` is empty — a known-but-unfiled follow-up means the work is not finished.

Then `updateStatus(EPIC_ID, "implemented")`, and say so in step 4's `Epic status` and `Next` lines. Otherwise leave the epic's status untouched. The plugin never moves an epic *out* of a resolved status, and never sets an epic to `In Progress`.

Step 2 must run before step 5, or a run that files a follow-up would close the epic that follow-up belongs to.

## Output block

Return exactly one block for the caller's report:

```
EPIC-UPDATE: none | updated | closed | degraded | already-recorded
EPIC: [<KEY>-<n>] <name> · <url>          (omit on `none`)
FILED: <KEY>-69, <KEY>-70                 (or `none`)
ALREADY-FILED: <KEY>-71                   (or `none`)
DEFERRED: <one-liner>, …                  (or `none`)
CHILDREN: <resolved>/<total> resolved
```

`degraded` means the DB lacks `epicProperty` or `parentTaskProperty`, so epic containers are unavailable — distinct from `none`, which means this ticket simply has no epic. `already-recorded` means step 1a found an existing `## Resolution Log` entry for this ticket and skipped steps 2-5 — this is what makes the skill safe to invoke more than once for the same ticket (e.g. `/notion-dev:finalize`'s post-merge recovery path). `ALREADY-FILED` reports step 2's **per-follow-up** dedup — a follow-up whose deterministic title matched an existing epic child, so nothing new was created — distinct from `FILED` (newly created this run); a recovery run's report must show which follow-ups it actually did the work of creating versus which it correctly recognized as already done.
