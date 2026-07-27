# plan-review — design

**Date:** 2026-07-26
**Status:** approved design, not yet implemented
**Revised:** 2026-07-27 — round 2 removed in favour of an orchestrator self-verification pass; see "Revision history" at the end.
**Scope:** new `plan-review` skill vendored into both `quick-dev` and `notion-dev`

## Problem

On the `superpowers` build flow, both plugins go from a written plan straight into
implementation. The only thing that reviews the plan is the agent that wrote it.

`superpowers:writing-plans` performs a **self-review** — spec coverage, placeholder scan,
type consistency — and its own SKILL.md is explicit that this is *"a checklist you run
yourself — not a subagent dispatch."* It also ships
`plan-document-reviewer-prompt.md`, a fresh-subagent plan reviewer covering Completeness,
Spec Alignment, Task Decomposition, and Buildability — but **nothing dispatches it**. It is
referenced only in that plugin's release notes and historical planning docs, never in a
live skill.

The result: no independent review of a plan ever happens, and nothing at any stage compares
the plan against the **actual codebase**. Both the self-review and the dormant reviewer judge
the plan against the *spec*. So the following defects reach implementation unchallenged:

- A task modifying a file that does not exist.
- A task rebuilding a helper the repo already has.
- A plan that is three times larger than the goal requires.
- A task that depends on a later task, which breaks `subagent-driven-development`'s
  sequential fresh-agent execution.

Caught at plan time, each costs one cheap review. Caught at PR review two phases later, each
costs the entire implementation plus rework — and the scope and duplication findings usually
are not caught at all, because a code reviewer judges the diff on its own terms rather than
against the alternative that was never built.

## Non-goals

- **Not for the `feature-dev` flow.** That flow has no written plan artifact;
  `feature-dev:feature-dev` architects internally and rolls into implementation.
  `plan-review` is `superpowers`-path only.
- **Not a code review.** Line-level quality, performance analysis, and security
  implementation are `local-code-review`'s job, on the real diff, at the PR stage.
- **Not a project-level review.** No sprint plans, cost estimates, ROI, or risk registers.
- **Not a replacement for human judgment.** The human gate remains the only place a plan
  that solves the wrong problem gets caught.

## Architecture

```
                    superpowers path only
                    ─────────────────────
  spec source                              plan artifact
  ───────────                              ─────────────
  notion-dev: ticket body                  notion-dev: <worktree>/PLAN.md
  quick-dev:  docs/superpowers/specs/*.md  quick-dev:  docs/superpowers/plans/*.md
        │                                        │
        └──────────────┬─────────────────────────┘
                       ▼
        ┌──────────────────────────────────────┐
        │  plan-review  (orchestrator skill)   │
        │                                      │
        │  build context packet                │
        │       ▼                              │
        │  REVIEW ── spawn fresh agent ────────┼──▶ general-purpose, synchronous,
        │       │     applies reviewer-rubric  │    review-only (no edit/commit/push)
        │       ▼                              │    reads the repo to verify claims
        │  findings + VERDICT: CLEAN|NOT-CLEAN │
        │       ▼                              │
        │  triage via receiving-code-review    │
        │  (agree / partially agree / disagree)│
        │       ▼                              │
        │  edit the plan file in place         │
        │       ▼                              │
        │  self-verify: git diff the plan,     │  reclassify any accepted-but-
        │  confirm each accepted fix landed    │  unlanded finding to unresolved
        │       ▼                              │
        │  emit PLAN-REVIEW output block       │
        └──────────────┬───────────────────────┘
                       ▼
         interactive?  ├── yes ──▶ HUMAN GATE: approve / revise
                       │              sees: what changed, what was
                       │              declined & why, what is unresolved
                       │
                       └── no ───▶ unresolved Critical? ── yes ──▶ STOP
                                          │                    worktree intact
                                          └── no ──▶ proceed, log blockers
                       ▼
              subagent-driven-development
```

### Packaging

An **orchestrator** skill, not a bare rubric, vendored per plugin exactly as `flow-triage`,
`review-and-merge`, and `local-code-review` already are:

```
plugins/{quick-dev,notion-dev}/skills/plan-review/
  SKILL.md                      # orchestrator: args, packet, loop, severity split, output
  references/reviewer-rubric.md # the contract the fresh reviewer agent applies
```

The loop is the non-trivial part — a single review round, triage, an orchestrator
self-verification pass, the severity split, degradation, ledger counts. A rubric-only skill would force that logic to be written twice,
in `ticket.md` and in `develop/SKILL.md`, where it would drift. Splitting the rubric into
`references/` mirrors how `review-and-merge` points at `local-code-review` for its reviewer
contract, and keeps `SKILL.md` readable.

The two vendored copies differ **only** in:

| | quick-dev | notion-dev |
|---|---|---|
| frontmatter calling flow | `quick-dev:develop` | `notion-dev:ticket` |
| triage skill | `quick-dev:receiving-code-review` | `superpowers:receiving-code-review` |
| sibling cross-reference (×2) | `../develop/SKILL.md` | `../review-and-merge/SKILL.md` |

Four deltas, all inside `SKILL.md`; `references/reviewer-rubric.md` is byte-identical in both. The ledger directory (`.claude/quick-dev/` vs `.claude/notion-dev/`) is **not** among them — `plan-review` writes nothing to the ledger and names no ledger path. That difference lives in the two `flow-triage/references/ledger.md` copies, which already differ that way.

`notion-dev` has no vendored `receiving-code-review`; it uses the superpowers one, as its
README already documents.

## The reviewer rubric

`references/reviewer-rubric.md`, written to read as a sibling of `local-code-review`: same
severity ladder (**Critical / Required / Optional / Nit / FYI**), same honesty-first framing,
same selectivity rule, same verdict rule.

Carried over verbatim in spirit from `local-code-review`, because they matter more here than
there — a plan has no compiler to contradict a bad finding:

- **Do not manufacture findings.** A sound plan gets `No findings.` No theoretical,
  speculative, or cosmetic findings. Never trade one wording for an equivalent one.
- **Selectivity.** Apply only the axes that fit the plan in front of you. A docs-only plan
  gets no test-coverage analysis.
- **Verdict is mechanical.** `NOT-CLEAN` iff ≥1 Critical or Required finding. Never emit
  `NOT-CLEAN` without one.

### The mandatory verification clause

This is the core of the skill's value and the defense against manufactured findings:

> Before reporting any finding about the codebase, the reviewer **must** read every file the
> plan names and grep for every symbol the plan claims does or does not exist. A finding
> asserted from the plan's own text alone, without checking the repo, is exactly the
> speculative finding this rubric forbids.

Neither `writing-plans`' self-review nor its dormant reviewer reads a single source file.
This clause is what makes axes 1 and 2 possible, and it is why those two axes are where the
value is.

### The four axes

| Axis | The finding it exists to catch |
|---|---|
| 1. Scope discipline | "Task 3 rebuilds what `lib/foo.ts:validate` already does" / "this achieves the goal in half the tasks" |
| 2. Codebase fit | "Task 4 modifies `src/api/router.ts` — that file does not exist" / "this introduces a new pattern where the repo already has one" |
| 3. Dependency order & actionability | "Task 5 depends on Task 8" / "Task 6 says 'wire up caching' with no approach — a fresh agent will invent one" |
| 4. Test coverage | "The new retry branch has no test task" |

**Deliberately excluded, with reasons:**

- **Spec fidelity (AC → task mapping)** — `writing-plans`' self-review already does this
  ("if you find a spec requirement with no task, add the task"). A fresh reviewer will notice
  a gap in passing; it does not need to be an axis.
- **Failure-mode analysis** — the most speculative thing to assess before code exists, and
  `local-code-review` does it properly on the real diff two phases later.
- **Code quality, performance, security implementation** — `local-code-review`, at the PR
  stage.

### Standards come from the target repo

The rubric derives the project's standards from the repo's `CLAUDE.md`, `.claude/rules/`, and
the conventions visible in the files the plan touches. It hardcodes no engineering
preferences and assumes no language, framework, or test runner. These plugins run in
arbitrary repos.

### Reviewer output contract

```
Reviewed plan: <plan path> @ <sha or "uncommitted">
COVERAGE-MAP:
<ASCII diagram: new codepaths/branches → covering task, or GAP>
- [Critical] <plan section/task> — <problem>. Fix: <concrete change to the plan>.
- [Required] ...
NOT-IN-SCOPE-PRESENT: <yes | no>
VERDICT: CLEAN | NOT-CLEAN
```

The reviewer is **review-only**: it must not edit files, commit, or push. It is spawned as a
`general-purpose` agent, synchronously — matching how `develop` Phase 4's local-mode reviewer
is already spawned.

The **coverage map is a reviewing instrument, not a deliverable.** The reviewer builds it to
*find* untested codepaths; each gap becomes a finding that edits the plan. It is not written
into the plan file as a permanent artifact.

## Orchestrator contract

### Invocation

Short scalars are flags; multiline context goes in the positional argument using the same
labeled-block shape `flow-triage` already emits, so callers paste what they already hold:

```
plan-review --plan=<path> [--auto] [--spec-file=<path>]

INTENT:
<ticket body, or spec text, or "(see --spec-file)">
SCOUT-FINDINGS:
<verbatim from flow-triage, or "NONE — not available">
MICRO-PLAN:
<verbatim from flow-triage, or "NONE — not available">
VERIFY:
<verify commands one per line, or NONE>
```

- `--plan` is **required**. A missing or unreadable plan file stops with an error — that is a
  caller bug, not a degradation.
- `--auto` — no human gate; the caller is in non-interactive mode.
- `SCOUT-FINDINGS` / `MICRO-PLAN` are legitimately absent on notion-dev's resume path, where
  Phase 3 triage is skipped. The reviewer is told they are unavailable rather than handed a
  fabricated stand-in.

### Output block

```
PLAN-REVIEW: <clean | proceed-with-warnings | blocked | degraded>
FINDINGS: <n>
ACCEPTED: <n>
DECLINED: <n>
UNRESOLVED-CRITICAL: <n>
UNRESOLVED-REQUIRED: <n>
NOT-IN-SCOPE:
<deferred items with one-line rationale, or NONE>
DECLINED-WITH-REASONING:
<finding — why declined, or NONE>
UNRESOLVED:
<accepted-but-unfixed blockers, or NONE>
```

Status semantics:

| Status | Meaning |
|---|---|
| `clean` | Review `CLEAN`; zero unresolved Critical or Required |
| `proceed-with-warnings` | Unresolved Required only |
| `blocked` | ≥1 unresolved Critical |
| `degraded` | Reviewer unavailable after one retry; review did not run |

Status is computed from the **unresolved counts, not from the reviewer's raw verdict.** A
`VERDICT: NOT-CLEAN` whose findings were all declined with reasoning yields
`PLAN-REVIEW: clean`, with the declines listed under `DECLINED-WITH-REASONING`. This follows
directly from the declined-is-resolved rule below and must not be treated as a contradiction.

### Loop rules

One rule keeps the loop honest, taken from precedent already in these plugins:

1. **A declined finding is resolved.** `develop` Phase 4 already states that findings the
   flow declined with reasoning are resolved and do not block. Same here — `UNRESOLVED`
   counts only *accepted-but-unfixed* items. This is what makes an unresolved Critical rare
   enough to justify stopping on.

Triage of the reviewer's findings uses `receiving-code-review` (the vendored copy in
quick-dev, the superpowers one in notion-dev): agree / partially agree / disagree per finding,
never applied blindly. A well-reasoned decline beats a low-confidence plan edit.

### Step 4 self-verification

There is no second review round. Instead, after editing the plan for every accepted finding,
the orchestrator **re-reads its own edits** — `git diff` on the plan file (or a comparison
against the contents the reviewer was given, when the plan is uncommitted) — and confirms,
finding by finding, that each accepted fix is actually present. Any accepted finding whose fix
is missing, or whose edit does not actually address it, is **reclassified from `accepted` to
`unresolved`**, so it counts toward the blocking rule in Step 5. An accepted-but-unapplied
finding must never be left as `accepted` — that is precisely the failure this check exists to
catch. The orchestrator made the edits, so it is the party positioned to verify them, at no
extra agent cost.

### Non-interactive behavior

With `--auto` there is no human gate, so the severity split decides:

- **Unresolved Critical** → **stop the run**, worktree and branch intact, report the blockers
  and the resume command. Building a full implementation on a known-Critical plan wastes the
  entire run.
- **Unresolved Required only** → **proceed** to implementation, with the blockers logged in
  the final summary and the ledger. A plan flaw is recoverable, and Phase 7's review loop and
  merge gate still guard the actual landing.
- **`degraded`** → proceed and log. The review must never block development on its own
  failure.

### Degradation

Reviewer agent fails, or returns output missing the required sections → retry once with the
same prompt (`flow-triage`'s scout pattern) → still failing → emit
`PLAN-REVIEW: degraded` with a reason line and continue. Interactive mode still runs the human
gate, telling the user the review could not run.

### Deferred work

Items the review defers go into the plan's own `## Not in scope` section, with a one-line
rationale each, and are echoed in the output block so callers can carry them onward —
notion-dev into the ticket's `## Implementation` section, quick-dev into the PR body.

The reviewer raises a finding for a missing `## Not in scope` section **only when it has
something concrete to put there** — that is, when its own review identified work the plan
could defer. An absent section on a plan with nothing to defer is not a finding; requiring
the heading for its own sake would be exactly the cosmetic finding the rubric forbids.

No `TODOS.md`. That file does not exist in most repos.

### The skill writes nothing to the ledger

It returns counts in its output block; the **caller** folds them into the outcome line it
already writes at the end of the run. One writer per event, and no
worktree-versus-primary-checkout root confusion inside a new skill.

## Integration

### notion-dev — `commands/ticket.md` Phase 4.2

Insert plan-review as a new step (b) and renumber. The existing hard gate becomes (c) and
gains the review summary.

```
(a) writing-plans → <worktree>/PLAN.md                     [unchanged]
(b) NEW: invoke notion-dev:plan-review
        --plan=<worktree>/PLAN.md
        (+ --auto when non-interactive)
        INTENT = ticket body
        SCOUT-FINDINGS / MICRO-PLAN from Phase 3 (absent on resume)
        VERIFY = verify.steps cmds from config
(c) hard gate — plan approval    [existing gate, now shows the review outcome]
(d) subagent-driven-development                            [was (c)]
```

Phase 1.2's resume detection is unaffected: it keys off `PLAN.md` with unchecked boxes, which
plan-review preserves.

### quick-dev — `skills/develop/SKILL.md` Phase 2b

The superpowers chain goes from 3 steps to 5. **This plugin gains a human plan gate it does
not have today.**

```
1. brainstorming → spec under docs/superpowers/specs/      [unchanged]
2. writing-plans → docs/superpowers/plans/…                [+ record PLAN_PATH]
3. NEW: quick-dev:plan-review --plan=$PLAN_PATH --spec-file=<spec path> (+ --auto)
4. NEW: human plan gate (approve / revise) — skipped under --non-interactive
5. subagent-driven-development                             [was 3]
```

Step 2 must record the path `writing-plans` reported, since quick-dev uses that skill's
default location rather than a fixed `PLAN.md`.

### Ledger fields

Add optional fields to the `outcome` event in both copies of
`skills/flow-triage/references/ledger.md`. No new event kind; the existing tolerance rules
already say unknown metrics are `null`, so old readers and old ledger files keep working.

```json
{"event":"outcome","run_id":"…","result":"merged","review_rounds":2,
 "plan_review_findings":5,"plan_review_accepted":3,
 "plan_review_declined":2,"plan_review_unresolved":0}
```

All `plan_review_*` fields are `null` when plan-review did not run — the `feature-dev` flow,
or a degraded review.

### Supporting changes

- Version bump both plugins `0.5.0 → 0.6.0` (new capability → minor).
- Both READMEs: layout tree, skills list, and notion-dev's Credits note on vendored skills.

## Verification

Prompt files have no unit-test surface, so three checks:

1. **`claude plugin validate`** on both plugins.
2. **Parity diff** between the two vendored copies, asserting `references/reviewer-rubric.md` is byte-identical and `SKILL.md` differs *only* in the four deltas of the packaging table above. Compare the set of differing lines, not the hunk count — `diff` may group two of the four together, since both live in the skill's Step 3. Worth having as a repeatable check given four skills are
   already vendored in duplicate.
3. **Smoke run against a deliberately flawed plan** — one task naming a nonexistent file, one
   task depending on a later task. Confirm: the reviewer catches both, the plan is edited, the
   self-verification pass confirms both fixes landed, the gate shows what changed, and
   `--auto` with an unresolved Critical stops with the worktree intact.

The thing to watch in (3) is not whether findings appear — it is whether they are *real*. A
reviewer asked to critique a document written by a capable model will manufacture plausible
findings to justify itself. If the smoke run produces findings that the codebase does not
support, the verification clause is not biting hard enough.

## Cost

One fresh agent reading a plan plus the ~5–15 files it names ≈ one `flow-triage` scout probe;
the Step 4 self-verification pass costs no extra agent — the orchestrator re-reads its own
edits. Against a superpowers-path run that already pays for a multi-task
implementation with per-task reviews plus 2–3 code-review rounds, that is roughly 5–10% of run
cost.

The real cost is latency, and — for quick-dev — a new human gate in a flow that is currently
fire-and-forget. That gate is skipped under `--non-interactive`, which is where the severity
split earns its place.

## Decisions record

| Decision | Chosen | Why |
|---|---|---|
| Ordering | Review → triage → revise → human gate | Human attention goes to the plan that survived scrutiny, not the first draft |
| Loop | Main agent revises, then self-verifies its own edits via `git diff` | Verifies the revision landed, without a second fresh-agent round |
| Context | Intent + scout findings inline; codebase verification mandatory | Precomputed context is cheap; verification is the value |
| Rubric | 4 axes | Trimmed from 7 after finding overlap with writing-plans and local-code-review |
| Non-interactive | Critical stops, Required proceeds | Plan flaws are recoverable; Critical wastes the whole run |
| Ledger | Optional fields on existing outcome line | No new event kind; schema stays backward-compatible |
| Packaging | Orchestrator + rubric reference, vendored per plugin | Loop logic lives in one place per plugin, not duplicated into callers |
| Flow support | superpowers only | feature-dev has no plan artifact to review |

## Revision history

**2026-07-27 — round 2 removed, replaced with an orchestrator self-verification pass.**

The original design's round 2 dispatched a *fresh* agent to re-review the plan after
revision, on the theory that something had to confirm round 1's fixes actually landed. But a
fresh agent has no knowledge of what round 1 found or why — it cannot check that a specific
finding was resolved, only re-review the whole plan from scratch and infer success from that
finding's absence. That is a full second review's cost for something that is not actually a
verification.

Worse, it barely changed outcomes. Status is computed from *unresolved* counts, not from
raw verdicts: if round 2 rediscovered a fix that had not landed, that finding went back
through the same triage as before, was accepted again, and the run proceeded exactly as it
would have without round 2 ever running. What round 2 gave that a single round could not was
two things: a second sample from a stochastic reviewer, and a whole-artifact review of the
plan *after* revision — both real but much weaker justifications than "verify the revision
landed," which is what it was designed for and could not actually do. The second of those is
now recovered by Step 4's added coherence check (see below); the stochastic second-sample is
the one loss this change does not recover.

The orchestrator is the party that made the edits in the first place, so it is also the party
best positioned to check them, and doing so costs no extra agent: Step 4 now ends with a
self-verification pass — `git diff` on the plan, finding by finding, confirming each accepted
finding's fix is actually present. Anything missing is reclassified from `accepted` to
`unresolved`, so it still counts toward the blocking rule in Step 5, exactly as an unresolved
finding from round 2 would have.

Consequences: the output block drops from eleven keys to nine (`ROUNDS` and `PLAN-CHANGED`
gone); the ledger drops from five `plan_review_*` fields to four (`plan_review_rounds` gone);
the orchestrator's steps are renumbered 1–5, with Step 4 now "Revise the plan and verify your
edits" and Step 5 "Compute status and emit the output block." The reviewer rubric and the
four review axes are unaffected — this change is entirely in the orchestrator's loop, not in
what a single review pass checks for.
