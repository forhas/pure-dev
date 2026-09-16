# notion-dev — reducing the orchestrator's context load

**Date:** 2026-09-16
**Status:** design, approved
**Scope:** `plugins/notion-dev` — `commands/ticket.md`, `skills/ticket-system`, `skills/issue-log`

## Problem

Client sessions running `/notion-dev:ticket` grow context fast enough to compact mid-flow.

Measured, `chars / 4`, for one end-to-end `/notion-dev:ticket` run: **~165,000 tokens of
instruction text** land in the top-level orchestrator before a single line of client code, diff,
or reviewer comment.

| Phase | Loaded into the top-level context | ~tokens |
|---|---|---|
| entry | `commands/ticket.md` | 24,850 |
| 1 Fetch | `ticket-system` 28,405 + `epic-doc` 10,529 | 38,934 |
| ambient | `issue-log` 7,460 + `references/signatures.md` 5,671 | 13,131 |
| 3 Triage | `flow-triage` + `scorecard` + `ledger` | 6,213 |
| 4 Build | `plan-review` 5,168 + `reviewer-rubric` 3,152 + `writing-plans` 1,763 + `subagent-driven-development` 8,084 | 18,167 |
| 7 Review | `review-and-merge` 35,302 + `github-api` 2,866 + `local-code-review` 1,400 + `session-closeout` 4,767 + `receiving-code-review` 1,550 | 45,885 |
| 8 Record | `epic-update` 11,788 + `knowledge` 6,521 | 18,309 |
| | **total** | **~165,000** |

The obvious hypothesis — *delegate more work to subagents* — is already implemented at the leaf
level and is not where the cost is. Every independence seat is a fresh agent today:
`plan-review`'s reviewer, `flow-triage`'s `Explore` scout, `review-and-merge`'s local reviewer and
completeness verifier, `subagent-driven-development`'s per-task agents, `create-task`'s
proxy-respondent. Adding more leaf delegation buys nothing.

**The cost is not tasks the orchestrator performs. It is `SKILL.md` files the orchestrator reads.**
A file enters the conversation when the Skill tool loads it and stays for the rest of the session.
Only two things remove it: never loading it (progressive disclosure), or loading it somewhere else
(phase-level delegation).

Forking a subagent is the wrong instrument for this goal: a fork inherits the parent's full
context, which doubles the cost rather than containing it. Everything below uses fresh agents with
self-contained prompts.

## What a real client run shows — and what it means for this design

A `/context` reading taken after one `/notion-dev:ticket` run in BTC-Gateway (Opus 5, 1M window):

| category | tokens | % |
|---|---|---|
| **Messages** | **774.1k** | **77.4%** |
| MCP tools | 37.8k | 3.8% |
| System tools | 24.2k | 2.4% |
| Skills (index descriptions only) | 9.9k | 1.0% |
| Memory files | 9.1k | 0.9% |
| System prompt | 4.6k | 0.5% |
| Custom agents | 1.5k | 0.1% |
| | **861.1k / 1M (86%)** | |

**The instruction load measured above is a subset of Messages** — a `SKILL.md` body enters the
conversation as message content when the Skill tool loads it. So ~165k of the 774k is instructions
and **~609k is the variable axis**: tool output, diffs, reviewer comments, file reads, verification
output. The variable axis outweighs the instruction axis roughly 4 : 1.

This design therefore saves **~48.4k of 861k, or 5.6% of the window.** It is worth doing and it is
not sufficient. The next round of work is on the variable axis, and it needs its own measurement —
`/context` reports one number for Messages and no breakdown.

**This re-ranks the three changes.** Change 1 delegates a *phase*, so the subagent's tool output —
Notion writes, `git` cleanup, `knowledge.py` — also stays out of the orchestrator. It is the only
one of the three that touches both axes. Changes 2 and 3 are instruction-axis only.

Two findings from the same reading that are **not** actionable in this repo, recorded so they are
not re-derived:

- `mcp__notion__notion-query-data-sources` costs **30.7k of tool schema by itself** — larger than
  Change 1. It is not droppable: `ticket-system` documents three measured client runs where the
  alternatives silently returned wrong rows for numeric-ID equality, and the schema is the Notion
  MCP's own. The only lever is client-side — that session had ~14 MCP servers connected, and
  trimming the ones a ticket run never touches is BTC-Gateway config, not plugin design.
- The `Skills` category (9.9k) is the skill *index* — one description line per skill. It is not
  where skill bodies are counted.

## Non-goals

- **Fixing the variable axis.** Reviewer comments, diffs, fix edits across review rounds, and
  `VERIFY_OUTPUT` are untouched by this design. Per the measurement above they are the larger half,
  and they are deliberately deferred to a follow-up with its own measurement — see *Next round*.
- **Delegating Phase 7.** `review-and-merge` is the largest single file (35,302) and moving it
  behind one dispatch is the largest theoretical win. It is rejected: the skill's own text records
  measured dispatch failures on client hosts — zero-byte returns, never-returns, runs stopped only
  after 75 and 50 minutes. Today a broken dispatch costs a reviewer *seat* and degrades gracefully;
  behind a phase-level dispatch it would cost the entire merge. Phase 7 is also interactive on the
  non-`--non-interactive` path, and a subagent cannot ask the user.
- **Splitting `review-and-merge`.** Investigated and rejected on the evidence — see *Rejected*
  below.
- **Splitting `epic-doc`, `epic-update`, `knowledge`.** Change 1 removes them from the
  orchestrator wholesale, so splitting them would be work for a benefit already taken.

## What makes this tractable

The phase contract is already narrow. Each phase hands the next a small, named, machine-parseable
block — `FLOW`, `PLAN_REVIEW_REPORT`, `VERIFY_OUTPUT`, `REVIEW_REPORT`, `COMPLETENESS_REPORT`,
`COMPLETION_CLOSEOUT`, `EPIC_REPORT`. That contract *is* the subagent interface. The flow was
already architected for phase-level delegation; it simply is not using it.

---

## Change 1 — delegate Phases 8–10 (the record unit)

**~30,200 tokens.** The largest single win, and the one with a pre-existing degradation path.

### Why this unit

Phases 8 (Record), 9 (Clean up) and 10 (Report) are already a standalone, resumable,
non-interactive unit, and `/notion-dev:finalize` already proves it. That command's Phase 1 carries
a `MERGED` **post-merge recovery path** that skips its review phase entirely and runs
Record → Clean up → Report from the persisted `review-report-<KEY>-<id>.md` that
`/notion-dev:ticket` Phase 7 writes. Same work, same artifact, already in use.

That is the property the other candidates lacked: **the fallback exists today.** If the dispatch
returns zero bytes or never returns, the orchestrator runs the recovery inline, or hands the user
`/notion-dev:finalize <pr>`. Nothing is lost, and the work is idempotent.

### What leaves the orchestrator

| | ~tokens |
|---|---|
| `epic-update/SKILL.md` | 11,788 |
| `knowledge/SKILL.md` | 6,521 |
| `epic-doc` `record` + `note` write paths | 4,345 |
| `ticket.md` Phases 8–10 prose → `commands/references/record.md` | 7,561 |
| **subtotal** | **~30,200** |

`epic-doc`'s read path stays in the orchestrator — Phase 1 needs it.

### The delegation boundary

Three things in Phases 8–10 cannot move, and the boundary is drawn around them.

1. **8.2's interactive filing gate stays with the orchestrator.** It puts every `FILED` item to
   the user with `AskUserQuestion`, and a subagent cannot ask. This costs nothing to keep: the
   current text already resolves that gate *before* the lock is taken, precisely so a human
   deciding cannot outlast the lock's 60-minute stale threshold. The orchestrator asks, then
   passes the answers in as `FILING_DECISIONS`.

2. **The primary lock stays with the orchestrator.** It is taken at 8.2 and held through Phase
   10's `record`. A subagent that took it and then died would leave it stale for an hour. The
   orchestrator takes it, dispatches with `LOCK_HELD`, and releases it. This needs no new
   mechanism: `LOCK_HELD` is already threaded through every invocation in this section precisely
   so a caller can hold the lock on their behalf.

3. **The orchestrator must leave the worktree before dispatching.** Phase 9 step 1 removes the
   worktree, and the orchestrator is normally sitting inside it. `cd $REPO_ROOT` before the
   dispatch — the existing text already requires this of whoever runs Phase 9; the requirement
   moves to the dispatch site.

So the orchestrator's Phase 8 becomes:

1. Resolve the interactive filing gate over `REVIEW_REPORT`'s `FILED` list → `FILING_DECISIONS`.
2. Take the primary lock (`knowledge.py lock take --section record`), unchanged.
3. `cd $REPO_ROOT`.
4. Dispatch **one** `general-purpose` agent, synchronously, with a self-contained prompt.
5. Receive one parseable block; release the lock; render the user-facing report from the block.

**Phase 10 splits.** Its `epic-doc record(<id>)` step goes into the unit — that is what the lock is
held through, and it is the last of the `epic-doc` write paths. Its closing `session-closeout` pass
and the user-facing summary stay with the orchestrator: `session-closeout` is already loaded at
Phase 7 so keeping it costs nothing, it may need to ask the user, and the zero-tails discipline
belongs where the user is. The orchestrator renders that summary from the returned `RECORD:` block.

### The subagent's prompt

Self-contained; it inherits nothing. It carries:

- the ticket id, PR number and URL, `$REPO_ROOT`, the worktree path, the branch name, `baseRefName`
- `REVIEW_REPORT`, `COMPLETENESS_REPORT`, `COMPLETION_CLOSEOUT`, `CRITERIA_FILE` (path), the run id
- `FILING_DECISIONS` and `LOCK_HELD: true`
- `--non-interactive` when the run has it
- an instruction to read `commands/references/record.md` — the moved Phases 8–10 prose — and follow
  it exactly, invoking `notion-dev:epic-update`, `notion-dev:knowledge` and `notion-dev:epic-doc`
  itself

### The return contract

One block, `RECORD:`, carrying what Phase 10's report and the ledger outcome need:
`EPIC_REPORT` verbatim, the ticket-record outcome, the cleanup outcome per step, the `record` step's
result, and an `ISSUES` list of any `issue-log` signatures recorded inside the unit.

### Failure handling

Bound the wait at ~15 minutes — the same bound `review-and-merge`'s checks gate, `plan-review` and
`flow-triage` already use, and for the same reason: a dispatch that never returns emits nothing, so
no check written against a delivered result can ever fire.

On a failed, zero-byte, or timed-out dispatch: **do not retry, and do not stop.** Record
`unexpected:record-unit-not-dispatched` per `notion-dev:issue-log`, then run the recovery inline —
the orchestrator reads `commands/references/record.md` itself and executes it, exactly as
`/notion-dev:finalize`'s `MERGED` path would. The context saving is forfeited for that run; nothing
else is. Say so in the final report.

This is the reverse of Phase 7's reasoning and deliberately so: there, a lost dispatch costs the
merge and has no fallback; here it costs only the saving, because the fallback is the code path that
already exists.

---

## Change 2 — split `ticket-system`

**~12,600 tokens** on the `/notion-dev:ticket` path.

`skills/ticket-system/SKILL.md` is 28,405 tokens documenting 19 operations plus a write-path styling
block. `/notion-dev:ticket` calls nine of them and never creates a ticket or an epic.

`SKILL.md` becomes a **~4,000-token dispatcher** holding only what every operation needs: purpose,
config-path resolution against the primary checkout, ID normalization, the project-scoping
guardrail, MCP unavailability, and the operation index.

Five references, clustered **by operation**, not by consumer — consumers overlap on `fetchTicket`,
`findEpics` and `getEpicContext`, so a by-consumer split would duplicate them:

| file | contents | ~tok | read when |
|---|---|---|---|
| `references/config.md` | Configuration, Property type handling, Notion page heading parsing | 3,800 | before the first Notion call |
| `references/read-ops.md` | `fetchTicket`, `findEpics`, `getEpicContext`, `listEpicChildren` | 4,600 | before the first read |
| `references/write-ops.md` | `updateStatus`, `setPullRequest`, `postComment`, `upsertSection`, `appendToSection`, `refreshAcceptanceCriteria`, `updateTicket` | 1,800 | before the first write |
| `references/create-ops.md` | `createTicket`, `createEpic`, `setParent`, `setDependencies`, `resolveAssignee`, `getSelectOptions`, `addSelectOption`, `refreshEpicTasks`, Title prefix, Epic containers | 7,700 | before the first create |
| `references/styling.md` | Styling conventions — palette, zone dividers, callouts, rich content | 1,600 | before writing page content |

`/notion-dev:ticket` then loads dispatcher + `config` + `read-ops` + `write-ops` + `styling` ≈
**15,800** instead of 28,405. `/notion-dev:create-task` loads `create-ops` in place of most of
`read-ops` and lands near where it is today — it was always the heavy consumer.

### How the disclosure is enforced

Two mechanisms, chosen because they cover each other:

1. **Mandatory read at a named moment**, the repo's existing idiom — the pointer sits at the step
   that needs it, imperatively, as `review-and-merge` already does for `references/github-api.md`:
   *"Read it before the first API call; the pagination and thread-mapping rules there are
   load-bearing."*
2. **An operation index with a hard gate** in the dispatcher: a table mapping each operation to its
   reference file, plus the rule *you may not perform an operation whose reference file you have not
   read in this run.*

The pointer gets the read to happen at the right moment; the table makes a missed read visible,
because every operation has a named home the agent can check itself against.

A third option — a caller-declared manifest, where each command declares up front which operations
it will call — was rejected: it couples every command to the split and breaks the moment a branch
calls an unplanned operation.

---

## Change 3 — `issue-log`'s `signatures.md` read on first record

**~5,671 tokens** on a clean run.

`references/signatures.md` is a lookup table of enumerated degradation signatures. It is consulted
only when something is actually being recorded. Today it is loaded with the skill.

`issue-log/SKILL.md` already points at it in four places. The change is to make the *first* of those
pointers the read site and state plainly that the file is not read until a record is being written —
`Read references/signatures.md before writing the first entry of this run; cite a registered name
whenever one applies.`

On a run with no degradations — the intended case — it is never read.

---

## Rejected: splitting `review-and-merge`

Investigated because it is the largest file (35,302) and the initial read suggested §2 *Process
existing review comments* (8,512) was dead weight on the `/notion-dev:ticket` path, where Phase 6
opens the PR moments before Phase 7 runs, so there are never pre-existing comments.

That was wrong. Lines 90–161 (~1,622) are the comment pass; lines 162–536 (~6,952) are the
**convergence controls** — the findings ledger, severity normalization, induced-chain depth, and
Rules 1–4 — which sit under §2 only because that is where feedback is first processed. They are
cross-referenced from §4 (line 899), the final sweep (1009–1083), §5 Merge (1120), and the
`CONVERGENCE` report block (1311–1376). Every round depends on them; they cannot sit behind a
"does this PR have comments" gate.

The genuinely conditional regions are ~1,400 (comment processing proper) and ~2,100 (the local
fallback loop, dead whenever the configured reviewer is healthy) — ~3,500 tokens in two places, in a
densely cross-referenced document that exists in three copies (`plugins/quick-dev`, the deliberate
`plugins/notion-dev` fork, and the `.claude/skills/` byte-identical mirror), with
`verify-ticket-system.sh` asserting across all three. The saving does not justify the blast radius.

---

## Result

| change | ~tokens | axis |
|---|---|---|
| 1 — delegate Phases 8–10 | 30,200 | instructions **and** tool output |
| 2 — split `ticket-system` | 12,600 | instructions |
| 3 — `signatures.md` on first record | 5,671 | instructions |
| **total** | **~48,400** | |

Orchestrator instruction load **~165,000 → ~117,000**, a 29% reduction on that axis — but **5.6% of
the 861k measured window**, since instructions are only ~21% of Messages. Change 1 additionally
removes its phase's tool output, which the table does not attempt to size.

## Verification

Each change gets a standing invariant, per `CLAUDE.md`'s preference for invariants over
change-scoped harnesses with version floors. New assertions go in `scripts/verify-context-split.sh`
(discovered by `.github/workflows/verify.yml`'s glob, so no workflow edit), using only
`scripts/lib/assert.sh`.

**Change 2 — the operation index resolves.** Every operation named in the dispatcher's index
resolves to a reference file that exists and carries that operation's `##` heading, and no operation
body remains in the dispatcher. This cannot rot: it goes red the moment an operation is added,
moved, or renamed without its index entry.

**Change 1 — the delegation has both paths.** The dispatch site names the bounded wait, names
`unexpected:record-unit-not-dispatched`, and names the inline-recovery fallback; the moved prose
exists at `commands/references/record.md` and the orchestrator's Phase 8 no longer names
`epic-update`, `knowledge`, or `epic-doc`'s write operations. The interactive gate and the lock
take precede the dispatch in document order — `assert_order`.

**Change 3 — the read site is the first pointer.** `signatures.md` is pointed at with a read
imperative before any other mention of it in `issue-log/SKILL.md`.

**Existing harness.** `scripts/verify-ticket-system.sh`'s 17 assertions are re-anchored to whichever
file now owns each region. Every re-anchored and new assertion is mutation-tested — break the file
it guards, confirm `FAIL`, restore — after committing, so a `git checkout -- .` cannot silently
revert the work.

All harnesses run before the work is reported done:

```bash
for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done
```

## Delivery

One pull request, per `CLAUDE.md`'s convergence policy. `plugins/notion-dev` manifest version bumps
once: **minor** — Change 1 is a new capability. Nothing under `.claude/skills/` is touched, and no
`quick-dev` file changes, so the mirror is unaffected.

## Next round — the variable axis

The BTC-Gateway reading establishes that ~609k of the window is tool output, not instructions, but
`/context` gives no breakdown of it. Before designing anything there, bucket that 774k by source:
which tool produced it, how many calls, how many tokens each.

`scripts/analysis/bucket-context.py` (throwaway analysis, not part of either plugin) reads a session
transcript and reports chars and approximate tokens per bucket — `result:<tool>`, `call:<tool>`,
assistant text, thinking — plus the list of `Skill` invocations, which is the direct measurement of
the instruction axis this design estimated statically. Run it against the BTC-Gateway session:

```bash
python3 scripts/analysis/bucket-context.py ~/.claude/projects/*BTC*/<session>.jsonl
```

The hypothesis it is meant to confirm or kill: **the review loop dominates.** Phase 7 applies fixes
across N rounds, and each round reads source files, edits them, re-runs `verify.steps`, and reads
reviewer comments — all in the orchestrator, all retained. A secondary hypothesis worth checking in
the same output: `FLOW=feature-dev` runs should be markedly heavier than `FLOW=superpowers` ones,
because `subagent-driven-development` delegates each build task while `feature-dev:feature-dev`
implements in the main loop.

Neither hypothesis is acted on in this design. They are what the next measurement decides.
