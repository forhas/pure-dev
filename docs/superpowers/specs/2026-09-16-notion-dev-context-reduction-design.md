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

`/context` gives one number for Messages and no breakdown, so the same run's transcript
(`a51dfabf-0b70-4c21-9981-69c809503f0e.jsonl`, `isSidechain` false throughout — orchestrator only)
was bucketed by source with `scripts/analysis/bucket-context.py`. **657k tokens of context-bearing
content**, top buckets:

| bucket | n | ~tokens | % | owner |
|---|---|---|---|---|
| `user text` — skill bodies + command expansion + reminders | 66 | 173,313 | 26.4% | **this design** |
| `hook:PreToolUse:Agent` — `context-mode` plugin | 37 | 78,277 | 11.9% | client config |
| `result:Bash` | 213 | 56,679 | 8.6% | the work |
| `hook:PreToolUse:Bash` — `context-mode` plugin | 292 | 56,174 | 8.5% | client config |
| `call:Agent` — subagent prompts written | 37 | 47,302 | 7.2% | cost of delegation |
| `attach:prompt_snapshot` — compaction | 2 | 44,400 | 6.8% | harness |
| `call:Bash` | 213 | 37,830 | 5.8% | the work |
| `call:Write` | 8 | 34,417 | 5.2% | the work |
| `attach:deferred_tools_record` | 1 | 23,613 | 3.6% | client config |
| `attach:output_style` | 322 | 12,638 | 1.9% | harness |
| `result:Agent` — everything 37 subagents returned | 37 | 10,471 | 1.6% | — |

Three conclusions.

**1. The instruction axis is the largest single bucket, and the static estimate above was right.**
`user text` (173,313) is where `SKILL.md` bodies and the `/notion-dev:ticket` expansion land — within
5% of the 165k estimated by summing the files. This design targets **~31.7k** of it, **~4.8% of
the run**.

**The ~48.4k first written here was wrong, and the way it was wrong is the reusable lesson.** It
was computed from what the *delegated unit uses* rather than from what the *orchestrator stops
loading*, and those differ whenever an earlier phase already loaded the same skill: a skill enters
the context whole at its first invocation, so moving a later phase that happens to use
`knowledge` (Phase 1 already invoked it) or `epic-doc` (Phase 2 already invoked it) saves nothing
at all — 10,866 of the claimed 30,200. The rest was optimism about the prose: `ticket.md` shed
4,853 rather than 7,561, because the dispatch instruction, its payload list and the whole
inline-fallback path stay in the orchestrator; and every one of Change 2's five files landed above
its per-file estimate. Estimate the next one from the orchestrator's own file list before and
after, never from the size of what was moved.

**2. The largest non-work consumer is a client plugin, not notion-dev.** `context-mode`'s
`PreToolUse` hooks fired **329 times** for **~140k tokens (21.3%)** — a reminder to use
context-saving tools, injected before every Bash call and every Agent dispatch, the Agent one
averaging 2,100 tokens per dispatch. Removing or scoping that plugin in the client is one config
change worth ~3× this entire design, and it costs notion-dev nothing. Recorded here because it is
the first thing to do and the last thing this repo can do anything about. `attach:deferred_tools_record`
(23.6k) is the same kind of item: ~14 MCP servers connected, most untouched by a ticket run.

**3. Delegation works, and it is not free.** 37 subagents returned **10,471 tokens in total** —
their tool output is genuinely contained, which is the direct evidence for Change 1. But writing
their prompts cost **47,302**, ~1,280 tokens per dispatch. Change 1's prompt carries
`REVIEW_REPORT`, `COMPLETENESS_REPORT`, `FILING_DECISIONS` and — once the unit's real inputs were
accounted for — `PLAN_REVIEW_REPORT`, `KNOWLEDGE_CONTEXT`, the ticket body and the caller's
pre-dispatch draft, so **budget 6k as a floor against its ~16,641 saving**; it remains net
positive, but by a narrower margin than the first draft of this section assumed, and the plan must
not assume the dispatch is free.

One earlier finding stands, and is not actionable here:
`mcp__notion__notion-query-data-sources` costs 30.7k of tool schema by itself and is not droppable —
`ticket-system` documents three measured client runs where the alternatives silently returned wrong
rows for numeric-ID equality, and the schema is the Notion MCP's own.

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

**~16,600 tokens.** The largest single win, and the one with a pre-existing degradation path.

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
| `ticket.md` Phases 8–10 prose → `references/record.md` | 4,853 |
| **subtotal** | **~16,641** |

`epic-update` is the only skill this change actually unloads: it is invoked nowhere else in the
run. **`knowledge` (6,521) and `epic-doc` (4,345) are not savings and an earlier draft of this
table wrongly counted them.** Phase 1 invokes `knowledge` `retrieve` and Phase 2 invokes
`epic-doc` `refresh`, and a skill loads **whole** — there is no partial load of a write path — so
both files are already in the orchestrator's context before Phase 8 is reached, whoever runs it.
`ticket.md`'s own line is the measured 4,853, not the estimated 7,561: Phase 8's dispatch
instruction, its payload list and the entire inline-fallback path stay behind.

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

**~9,473 tokens** on the `/notion-dev:ticket` path (measured after the split; the ~12,600 first estimated here assumed a ~4,000-token dispatcher and five smaller references, and every one of the six landed above its estimate).

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

**~5,610 tokens on a clean run — and the saving is conditional, not flat.**
`signatures.md` (5,763 on this branch, 5,671 on `main` plus a new registry row) is skipped only
on a run that records **nothing**, while `issue-log` entries are written throughout Phases 1–7 in
the orchestrator itself. Any run logging a single degradation pays the file in full, and pays it
**+92 against `main`**, on top of the +61 `issue-log/SKILL.md` grew to state the deferral. So the
range is **−153 in the worst case to +5,610 in the best**, not a flat +5,671; it is a bet that
most runs are clean, and it is the only change here whose sign depends on the run.

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
| 1 — delegate Phases 8–10 | 16,641 | instructions **and** tool output |
| 2 — split `ticket-system` | 9,473 | instructions |
| 3 — `signatures.md` on first record | 5,610 | instructions, **clean runs only** (see Change 3) |
| **total** | **~31,724** | |

Orchestrator instruction load **~165,000 → ~133,000**, a 19% reduction on that axis and **~4.8% of
the measured 657k run** — and ~26,100 / ~3.9% on a run that logs anything. Change 1 additionally removes its phase's tool output and pays 3–6k for its
dispatch prompt; both are excluded from the table.

For scale, the client-side actions that are not this repo's to make — removing or scoping
`context-mode` (~140k) and trimming unused MCP servers (~24k) — are together **~5.2×** this design.
They should be done first; they are independent of it and cost nothing here.

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

## Order of work

1. **Client config, first and outside this repo** — remove or scope `context-mode` in BTC-Gateway
   (~140k) and disconnect MCP servers a ticket run never touches (~24k). Independent of everything
   below, and larger than all of it.
2. **This design** — changes 1–3, ~31.7k.
3. **Re-measure** with `scripts/analysis/bucket-context.py` on a fresh run, and decide whether a
   further round is warranted from the new buckets rather than from a hypothesis.

An earlier draft of this spec predicted that the Phase 7 review loop would dominate the variable
axis. The measurement does not support it: `result:Bash` and `call:Bash` together are 94.5k (14.4%)
across 213 calls spanning the whole run, not a review-loop concentration. That prediction is
recorded as refuted so it is not re-derived.

## Re-running the measurement

```bash
python3 scripts/analysis/bucket-context.py <path-to-session>.jsonl
```

Transcripts live in `~/.claude/projects/<escaped-cwd>/<session-uuid>.jsonl`; from WSL, a
Windows-side client is reachable at `/mnt/c/Users/<user>/.claude/projects/...`. The script counts
assistant turns, user turns and `attachment` records (where hook output and listings land), excludes
transcript bookkeeping, and reports whether any subagent (`isSidechain`) records are mixed in — a
transcript carrying them is not an orchestrator-only measurement and its buckets must not be read as
one.
