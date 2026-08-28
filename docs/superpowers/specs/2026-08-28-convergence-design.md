# Convergence: absorb-by-default triage for deferred work

**Date:** 2026-08-28
**Status:** Approved design, pending implementation plan
**Scope:** `plugins/notion-dev`, `plugins/quick-dev`

## Problem

Clients report that resolving a ticket frequently produces *more* tickets, so epics and
missions never finish.

This is not a quality-of-judgment problem. It is a structural one: the plugin contains
three pumps that manufacture tickets, and one closure rule that cannot win the race
against them.

**Pump 1 — plan review is *required* to find deferrable work.**
`plan-review/references/reviewer-rubric.md:115-125` raises a blocking **Required** finding
when the plan lacks a `## Not in scope` section listing work the reviewer judged
deferrable. `plan-review/SKILL.md:94` then writes those items into the plan.
`commands/ticket.md:286` carries them into `REVIEW_REPORT`'s Notes. The reviewer is graded
on producing a deferral list, so every superpowers-flow ticket produces one.

**Pump 2 — code review deferrals.**
`review-and-merge/SKILL.md:374` triage produces partially-agreed and declined items that
land in `REVIEW_REPORT` as follow-ups.

**Pump 3 — `epic-update` files all of it as siblings.**
`epic-update/SKILL.md:48-78` turns every deferred item into a real ticket under the *same*
epic — unconditionally in `--non-interactive` mode.

**The closure rule cannot win.** `epic-update/SKILL.md:84-93` closes the epic only when
the child frontier is empty, but step 2 files new children before step 4 evaluates closure
(the ordering is deliberate — line 99). Each filed follow-up is itself a full ticket that
runs the interviewer, plan review, and the review loop again, so there is no decay with
depth. Whenever the mean deferrals-per-ticket is at or above 1, the epic is a supercritical
branching process and **provably never closes**.

Two things are notably *not* broken and are preserved by this design:

- `task-breakdown/SKILL.md` already defaults to `single` with explicit anti-split
  anti-patterns. Creation-time fragmentation is not the problem.
- Both review loops already have real stopping rules — "neither loop manufactures work from
  theoretical findings" (`review-and-merge/SKILL.md:419`), the oscillation guard, the round
  cap. The *within-ticket* loops converge.

The failure is entirely in *across-ticket filing*.

### Secondary defect: `SKIPPED` blocks closure forever

Independent of volume, `epic-update/SKILL.md:91` (closure condition 3) states that a
user-declined follow-up "keeps blocking closure until someone files it manually" and is
"never retried by a later invocation." A single **Skip** at the interactive gate leaves an
epic permanently uncloseable regardless of how few tickets are filed.

### Related defect in `quick-dev`

`quick-dev` has no ticket backend, so it has no convergence problem — but its develop flow
has no handling of `NOT-IN-SCOPE` at all. Deferred items die with `PLAN.md`. It has the
graveyard half of the same disease.

## Approach

Invert the default. Today the reviewer is rewarded for pushing work *out* of the ticket;
under this design it must justify pushing anything out, and work that stays in must
actually get done before merge.

Rejected alternatives, recorded so they are not re-litigated:

- **Relaxing epic closure instead of filing volume** — treats the symptom. The user
  explicitly chose to attack filing volume first.
- **An epic-scope admission test** (routing off-charter follow-ups out of the epic) —
  ruled out. Blast-radius criterion 3 covers part of it incidentally.
- **An absorption budget / generation-depth cap** — unnecessary. The existing review round
  cap already provides the termination guarantee (see "Why this terminates").
- **A notes-only bucket with no gate** — this is the current failure mode wearing a new
  name. The user's explicit requirement is that absorbed items get *done, in the same
  session*.
- **Unifying the four diverged skill copies** — a refactor riding a behavioral fix is two
  risks in one change. Out of scope here.

## Design

### 1. One triage vocabulary

Every item that today becomes a "not in scope" entry or a "deferred follow-up" gets exactly
one label. The vocabulary is shared by both reviewers and both plugins.

| Label | Meaning |
|---|---|
| `absorb` | Do it in this ticket, before merge. **The default.** |
| `file` | Genuinely separate work; becomes a real ticket |
| `drop` | Recorded with rationale; never becomes work |

`drop` is evaluated **first** and is behaviorally unchanged — it is the existing judgment
bar at `review-and-merge/SKILL.md:95` and `:419`. That rule already works; this design only
gives it a name so it composes with the other two.

### 2. The blast-radius test

Everything surviving `drop` is `absorb` **unless any** of the following is true, in which
case it is `file`:

1. It reaches code the ticket was not already changing — files outside the PR's diff. New
   files the ticket itself creates count as *inside*.
2. It requires a new public interface, dependency, config key, or data migration.
3. It needs a design decision the ticket's acceptance criteria do not already settle.

None true → `absorb`.

Criterion 1 is checkable rather than felt: `git diff --name-only origin/<PR_BASE>...HEAD`
at review time, the plan's declared file set at plan time. `<PR_BASE>` is the same value
`commands/ticket.md` 6.1 already resolves — not `git.baseBranch`, which misstates the diff
when `prTargetBranch` differs.

Whenever an item is labeled `file`, **the criterion number that caused it must be
recorded.** Naming the criterion is what makes the decision auditable rather than merely
asserted, and it is what makes the reclassification escape (§4) safe.

### 3. Plan time — absorption is plan content, and needs no gate

`reviewer-rubric.md:115-125` ("Deferred work") is rewritten from *list what you would
defer* to *triage what you would defer*:

- **`absorb`** → a Required finding **only if the plan does not already contain the item as
  a task**. The proposed fix is "add this task to the plan," never "add it to Not in
  scope."
- **`file`** → belongs in `## Not in scope`, with a one-line rationale **and** the
  blast-radius criterion number.
- **`drop`** → no finding, no listing.

Two distinct outputs are involved here and must not be conflated. `TRIAGE-COMPLETE:` is
emitted by the **reviewer agent**, per the rubric, and is parsed at `plan-review/SKILL.md:62`
— it replaces `NOT-IN-SCOPE-PRESENT:`. `TRIAGE:` is a key in the **plan-review skill's own
output block**, which callers parse — it replaces `NOT-IN-SCOPE:`. The two mirror the
existing pairing exactly.

The rubric's `NOT-IN-SCOPE-PRESENT: yes|no` line is replaced by `TRIAGE-COMPLETE: yes|no`,
emitted `no` only when an `absorb` item is missing from the plan's task list or a `file`
item lacks its criterion number — and, as today, `no` must be accompanied by a Required
finding naming the specific items.

Downstream in `plan-review/SKILL.md`:

- **Contract check (`:70`)** — the `NOT-IN-SCOPE-PRESENT: no` clause becomes the equivalent
  clause for `TRIAGE-COMPLETE: no`. The surrounding rule is unchanged and load-bearing:
  every field that asserts a defect must be matched by its own blocking finding.
- **Step 4 (`:94`)** — stops auto-creating a `## Not in scope` section from all deferrable
  work. `absorb` items are appended to `PLAN.md`'s task list, each with an unchecked `- [ ]`
  box so the existing resume detection sees them; only `file` items go to `## Not in scope`.
- **Output block (`:120-131`)** — the `NOT-IN-SCOPE:` key becomes `TRIAGE:`, carrying one
  line per item as `<label>: <item> — <rationale>` (plus the criterion number on `file`
  lines), or `NONE`. **The block stays at nine keys**, so the "every one of the nine keys
  must be present" rule at `:76` and all caller-side parsing survive a key rename rather
  than a shape change.
- **Degradation path (`:76`)** — emits `NONE` on `TRIAGE:` exactly where it emits `NONE` on
  `NOT-IN-SCOPE:` today.

After this, `subagent-driven-development` executes absorbed items as ordinary plan tasks.
**No enforcement gate is required at plan time** — by the time implementation starts,
absorbed work is indistinguishable from planned work.

### 4. Review time — the merge gate

`review-and-merge/SKILL.md` step 2's triage (agree / partially agree / disagree) gains a
second axis: every agreed-but-not-yet-fixed item is additionally labeled `absorb`, `file`,
or `drop`. Disagreed findings are unaffected — a decline is already resolved and already
does not block.

A gate is added before step 5 (merge), generalizing the one that already exists at
`quick-dev/skills/develop/SKILL.md:121`:

> **No `absorb` item may be outstanding at merge.**

The gate lands in **both** plugins' review-and-merge copies, and `quick-dev`'s existing
develop-flow gate at `:121` is widened from "accepted-but-unfixed Critical/Required" to
also cover outstanding `absorb` items. The two conditions are complementary, not
overlapping: an `absorb` item may be any severity.

The escape is a **reclassification, not a bypass**: `absorb` → `file` requires naming which
blast-radius criterion turned out true, recorded in `REVIEW_REPORT`. This is the only way
past the gate. A misjudged item can always get out; it can never get out silently. The gate
therefore cannot deadlock a non-interactive run.

The gate composes with the existing loop terminators rather than replacing them: the round
cap, the oscillation guard, and the judgment-based stop all still end the loop. The gate
only asserts that when the loop *does* end, no `absorb` item is left behind.

### 5. `REVIEW_REPORT` gains three lists

`REVIEW_REPORT`'s single undifferentiated deferred-follow-ups list becomes three:
`ABSORBED`, `FILED`, `DROPPED`.

**`epic-update` step 2 consumes only `FILED`.** This is the interface change where the
branching factor actually drops — `ABSORBED` items are already merged, `DROPPED` items are
already decided.

All three are still reported, so nothing becomes invisible:

- `commands/ticket.md:286` — `## Implementation` Notes carry the plan review's `file` items
  (its `absorb` items need no carrying; they were plan tasks and are already built).
- `commands/ticket.md:348-349` and `commands/finalize.md:108-109` — the "Review resolution"
  and "Deferred follow-ups" fields become three-way. The `## Merged` rendering in
  `ticket-system/SKILL.md:221-226` gains `Absorbed` and `Dropped` bullet groups alongside
  the existing `Deferred follow-ups`.
- `commands/ticket.md:391` and `commands/finalize.md:150` — the final report line reports
  absorbed / filed / dropped counts.

For `quick-dev`, which has no ticket backend: `FILED` items surface in `develop`'s final
report to the user rather than vanishing with `PLAN.md`.

### 6. Epic closure

Only `file`-labeled items now reach `epic-update`, which changes what its interactive gate
*means*. The item arriving there has already been judged `file`, so **Skip** is no longer
"leave it undone" — it is "I disagree with the triage; this is a `drop`." That is a
decision, not an outstanding item.

In `epic-update/SKILL.md`:

- **Gate (`:60`)** — options become **File as ticket** / **Drop (with rationale)**. The
  rationale is required and lands in the step-5 log entry.
- **`SKIPPED` → `DROPPED`** throughout: step 1a's repopulation (`:38`), step 2's outcome
  recording (`:78`), step 5's log line `**Follow-ups skipped**` → `**Follow-ups dropped**`
  (`:107`), and the output block's `SKIPPED:` key (`:139`).
- **Closure condition 3 is deleted** (`:91`). A recorded drop closes work; it does not
  block. Closure becomes conditions 1, 2, 4, 5.

Two consequences that require care rather than a blanket rename:

**Backward compatibility is a live-data problem.** Clients have real Notion epics whose
Resolution Logs already contain `**Follow-ups skipped**` lines, and step 1a parses them on
every recovery invocation. The parser **must accept both spellings** and treat both as
non-blocking. Without this, the change strands exactly the epics that are stuck today.
The `UNKNOWN` sentinel check (`:115`) must run first on either spelling, as it does now.

**Condition 5's two-sentinel structure collapses to one.** It currently guards `SKIPPED`
and `FAILED` independently against the `unknown` sentinel. With `DROPPED` non-blocking,
what an absent `REVIEW_REPORT` actually hides is whether unfiled `file` items exist — one
unknown, not two. `epic-update/SKILL.md:93` explicitly warns against collapsing distinct
failure modes, so this reduction is deliberate and must be justified in the edit itself.
The implementation must confirm no other reader depends on the split before removing it.

`FAILED` is untouched: it remains a transient filing failure, still retried by step 1a, and
still blocking under condition 4.

Because `absorb` is the default, this gate now fires rarely. Most tickets will reach
`epic-update` with an empty `FILED` list and close on condition 1 alone.

### 7. Non-interactive behavior

`--non-interactive` follows the same triage. It does not file everything by default any
more; it absorbs by default, files only criterion-justified items, and drops per the
judgment bar. `commands/create-task.md:102`'s one-item non-interactive mode is unchanged —
it still receives exactly one item by construction, now a `file`-labeled one.

## Why this terminates

An `absorb` item, by construction of criterion 1, adds no files outside the existing diff.
Absorbed work therefore re-enters `review-and-merge`'s **existing round-capped loop**, not
an unbounded one, and that cap is the backstop. No new budget mechanism is introduced.

The epic's child frontier now grows only by criterion-justified `file` items rather than by
every deferred thought, which drops the branching factor below 1 in the normal case.

## Risks

| Risk | Bound |
|---|---|
| Absorb makes PRs balloon — the mirror-image failure | Criterion 1 confines absorbed work to files already in the diff; the existing round cap bounds iterations |
| Reclassify becomes a rubber stamp | The escape must name which criterion turned out true. The ledger can count reclassifications per run; a high rate is the signal the test is miscalibrated |
| Quality drops because absorbing rushes work | Absorbed work goes through the same review loop as everything else. Nothing skips review; only filing changes |
| `epic-update`'s recovery logic breaks | Condition 3's deletion and the rename touch steps 1a, 2, 4, and 5 together. They are one atomic change, with the dual-spelling parser as an explicit requirement |
| The rubric re-diverges between plugins | It is byte-identical today. The change must keep it so, verified by a `diff` check |

## Verification

- `diff plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md plugins/notion-dev/skills/plan-review/references/reviewer-rubric.md` is empty after the change.
- The plan-review output block still has exactly nine keys, with `TRIAGE:` in the position
  `NOT-IN-SCOPE:` occupied.
- The tokens `NOT-IN-SCOPE-PRESENT` and `NOT-IN-SCOPE:` no longer appear in either plugin.
  The `## Not in scope` **plan heading** is retained by design — it is where `file` items
  live.
- The token `SKIPPED` no longer appears in `epic-update` except inside its dual-spelling
  backward-compatible parser, which must still recognize the legacy
  `**Follow-ups skipped**` log line.
- Every `absorb`/`file`/`drop` producer names the vocabulary identically; no plugin invents
  a synonym.
- A worked end-to-end trace, in the spec's own terms, of a ticket that produces one item of
  each label, showing where each is recorded and what closes.

## Not in scope

- Epic-scope admission testing for follow-ups — ruled out during design.
- Unifying the four diverged shared skills (`plan-review/SKILL.md`,
  `review-and-merge/SKILL.md`, `local-code-review/SKILL.md`, `flow-triage/SKILL.md`).
- Any change to `task-breakdown`, whose anti-split discipline is already correct.
- Any change to the review loops' round cap, oscillation guard, or judgment bar.

## Appendix: worked trace

Ticket `STO-41` ("Add token refresh to the session handler"), superpowers flow, epic
"Session Hardening". Its PR touches `src/session/handler.ts` and `src/session/token.ts`.

**Plan review** turns up three items:

| Item | Label | Why |
|---|---|---|
| "Cover the refresh path in the existing session test" | `absorb` | No criterion true — the test file is in the plan's declared set |
| "Rate-limit the refresh endpoint" | `file` (criterion 2) | Needs a new config key |
| "Rename `sess` to `session` throughout" | `drop` | Cosmetic churn under the judgment bar |

Emitted as `TRIAGE-COMPLETE: yes` plus three triage lines. The `absorb` item is appended to
`PLAN.md` as a task and built by `subagent-driven-development` — no gate needed.
`## Not in scope` gets the rate-limit item with "criterion 2". `PLAN.md` is deleted at 6.6;
the `file` and `drop` items survive in the ticket's `## Implementation` **Notes** (6.5).

**Code review** turns up two more:

| Item | Label | Why |
|---|---|---|
| "The TTL comparison is off by one" | `absorb` | Same file as the fix |
| "Session storage should move to Redis" | `file` (criterion 1) | Reaches the storage layer, outside the diff |

The absorb gate at merge step 5 holds until the TTL fix is pushed and reviewed; the round cap
bounds that. `REVIEW_REPORT` records `ABSORBED` = [TTL fix], `FILED` = [Redis, rate-limit],
`DROPPED` = [rename].

**Phase 8.** `epic-update` receives **only** `FILED` — two items, not five. Both file. The
user drops the rate-limit one at the prompt with "already tracked in infra backlog"; it lands
in `DROPPED` and does **not** block closure. The Redis ticket is created, so closure
condition 1 fails and the epic stays open — correctly, because real work is outstanding.

The ticket's `## Merged` section shows **Absorbed** (2), **Deferred follow-ups** (1, with its
ID), and **Dropped** (2, with rationales). Five findings; **one new ticket**. Under the old
design, all five would have been filed.
