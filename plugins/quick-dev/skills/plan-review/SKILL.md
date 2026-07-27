---
name: plan-review
description: This skill should be used when an orchestrating flow needs an independent review of a written implementation plan before execution begins — invoked by quick-dev:develop on the superpowers build path, or directly when the user asks to "review this plan", "check the plan before implementing", or "is this plan sound". Dispatches a fresh review-only agent that verifies the plan against the actual codebase, triages its findings, revises the plan, and returns a machine-parseable verdict. Superpowers-path only; not for the feature-dev flow, which produces no plan artifact.
argument-hint: "--plan=<path> [--auto] [--spec-file=<path>]"
---

# plan-review — independent review of a plan before implementation

Review a written implementation plan with a **fresh agent that did not write it**, verify the plan against the **actual codebase**, revise it, and return a verdict the caller can gate on.

This exists because nothing else checks a plan against reality. `superpowers:writing-plans` self-reviews its own output against the spec; `local-code-review` reviews the diff two phases later, after the implementation has already been paid for. Neither reads the repo at plan time.

**This review must never block development on its own failure.** If the reviewer cannot run, degrade and let the build continue.

## Input

Arguments: `$ARGUMENTS`

Flags:

- `--plan=<path>` — **required.** Path to the plan file. If missing, unreadable, or empty, **stop with an error naming the path** — that is a caller bug, not something to degrade around.
- `--auto` — non-interactive: the caller will not present a human gate. Changes the end behaviour (see "Non-interactive outcome").
- `--spec-file=<path>` — optional path to the spec the plan implements. Use when the intent lives in a file rather than inline.

Everything after the flags is the **context packet**, in labelled blocks:

```
INTENT:
<the requirement text the plan must satisfy — a ticket body, a spec, or "(see --spec-file)">
SCOUT-FINDINGS:
<flow-triage's SCOUT-FINDINGS block verbatim, or "NONE — not available">
MICRO-PLAN:
<flow-triage's MICRO-PLAN block verbatim, or "NONE — not available">
VERIFY:
<the project's verify/test commands, one per line, or NONE>
```

`SCOUT-FINDINGS` and `MICRO-PLAN` are legitimately absent when the caller skipped triage (for example a resumed run). When they are, tell the reviewer they are unavailable — never fabricate a stand-in.

## Step 1 — Build the reviewer prompt

Assemble a **self-contained** prompt. The reviewer is a fresh agent with an empty conversation; it inherits nothing. Include:

1. The full text of `references/reviewer-rubric.md` — instruct the reviewer to apply it exactly, including its output contract.
2. The plan file's absolute path and its full current contents.
3. The plan's identity for the echo line: the current HEAD sha if the plan is committed, otherwise `uncommitted`.
4. The `INTENT` block and, when `--spec-file` was given, that file's contents — together these are what the plan is judged against. When the caller supplies both they are complementary, not alternatives: the spec file carries the full requirement, `INTENT` the caller's framing of it. Include both; neither overrides the other.
5. The `SCOUT-FINDINGS` and `MICRO-PLAN` blocks, labelled as precomputed context from triage, or explicitly marked unavailable.
6. The `VERIFY` commands, so the reviewer knows what verification exists in this repo.
7. The repo root as the codebase to verify against, plus a pointer to `CLAUDE.md` and `.claude/rules/` if present.
8. An explicit statement that it is **review-only**: it must not edit files, commit, or push.

## Step 2 — Dispatch the reviewer

Dispatch **one** `general-purpose` agent, **synchronously**, with that prompt. (This matches how `../develop/SKILL.md` Phase 4 already spawns its local-mode reviewer.)

Parse from its output: the findings list with severities, `NOT-IN-SCOPE-PRESENT`, and the `VERDICT` line.

**Contract check.** The reviewer's output is only usable if it carries **every** element the rubric's output contract mandates — the `Reviewed plan:` echo, a `COVERAGE-MAP:` block, a findings list (one or more `- [<Severity>] …` lines, or the literal `No findings.`), a `NOT-IN-SCOPE-PRESENT` line, and a `VERDICT` line — plus, when the verdict is `NOT-CLEAN`, at least one parseable Critical or Required finding. A `COVERAGE-MAP:` whose whole body is `(no test suite in this repo)` satisfies that element; the rubric permits exactly that. Two failure shapes get different treatment:

- **Verdict contradicts its own findings** — `VERDICT: CLEAN` alongside a listed Critical or Required finding. Derive the verdict from the findings (`NOT-CLEAN`) and continue; the findings are what you triage. This is the safe direction and needs no retry.
- **Output unusable** — any mandatory element above is missing or malformed, or the output **contradicts itself**: it declares a defect in one field while the findings list carries no Critical or Required finding to triage. Never resolve such a contradiction in favour of a clean plan — with nothing to triage the counts come out zero and the status computes to `clean`, silently converting a declared defect into a pass. The general rule: **every field that asserts a defect must be matched by its own blocking finding** — one blocking finding does not discharge two separate assertions. The three instances that arise in practice:
  - `VERDICT: NOT-CLEAN` with no blocking finding at all.
  - `COVERAGE-MAP:` listing a `GAP` entry with no blocking finding covering *that* gap — the rubric turns every gap into a finding, and the severity ladder makes "a new codepath with no verification" Required, so gaps paired with `No findings.` *or* with only non-blocking findings are contradictory.
  - `NOT-IN-SCOPE-PRESENT: no` with no blocking finding naming the missing deferred work — the rubric emits `no` only when concrete deferrable work is missing from the plan, and requires a Required finding naming those items.

  Separately, a **missing** `COVERAGE-MAP:` is disqualifying on its own terms: it means the test-coverage axis was probably never performed, so a `clean` result would be unearned.

**Degradation.** If the agent fails, or its output is unusable per the check above, retry **once** with the same prompt. If it fails again, emit the output block with `PLAN-REVIEW: degraded`, all counts `0`, `NONE` on both `NOT-IN-SCOPE:` and `DECLINED-WITH-REASONING:`, and a one-line reason on the `UNRESOLVED:` line. Every one of the nine keys must be present even in this path — callers parse the whole block. Do not block the build.

## Step 3 — Triage the findings

Apply the `quick-dev:receiving-code-review` skill to the findings: agree, partially agree, or disagree with each one, with reasoning. Never apply a finding blindly, and never perform agreement you do not hold.

Verify before accepting. The reviewer was told to check the repo, but it can still be wrong — if it claims a file does not exist, look. A well-reasoned decline beats a low-confidence plan edit.

Classify every finding as exactly one of:

- **accepted** — you agree; you will edit the plan.
- **declined** — you disagree, with a stated reason. **A declined finding is resolved and does not block.** (Same rule `../develop/SKILL.md` Phase 4 already applies to code review.)
- **unresolved** — you agree, but it cannot be fixed in the plan (it needs a decision you do not own, or information nobody has). These are the only findings that count toward the blocking rule.

Non-blocking severities (`Optional`, `Nit`, `FYI`) may be applied or skipped at your discretion; they never produce an `unresolved` entry. A non-blocking finding you skip counts as **declined**, with `discretionary skip` as its reason — so the three buckets stay exhaustive and `FINDINGS` always equals `ACCEPTED + DECLINED + UNRESOLVED`.

## Step 4 — Revise the plan and verify your edits

Edit the plan file in place for every accepted finding. Keep edits surgical — fix the finding, do not rewrite the plan. Preserve its structure and its task numbering where possible, and keep every **remaining** task's `- [ ]` checkbox: callers rely on unchecked boxes for resume detection. A task an accepted finding deliberately merges away or deletes takes its checkbox with it — that is the fix landing, not a checkbox lost.

If accepted findings identified deferrable work and the plan has no `## Not in scope` section, add one with those items and a one-line rationale each.

If task numbering must change, update every cross-reference to the renumbered tasks in the same edit.

**Then verify your own edits.** Applied review feedback frequently fails to resolve the finding it was meant to resolve, and nothing downstream checks this. Walk the list of accepted findings and confirm for each one that the plan now contains the change you made for it — read the edited region; do not trust your memory of having edited it. `git diff -- <plan path>` shows everything you changed at once — but only if the plan is tracked by git. When it is untracked (the normal case for a plan written fresh into a worktree) that command prints nothing and exits successfully, which is **not** evidence that nothing changed: compare against the plan contents you put in the reviewer's prompt in Step 1 instead.

Any accepted **Critical or Required** finding whose fix is missing, or which the edit does not actually address, is **reclassified as `unresolved`** and counts toward the blocking rule in Step 5. A non-blocking finding (`Optional`, `Nit`, `FYI`) whose edit did not land stays **declined** with `edit not applied` as its reason — consistent with Step 3, where non-blocking severities never produce an `unresolved` entry. Never leave such a finding as `accepted` — an accepted-but-unapplied finding is precisely the failure this check exists to catch.

**Then check the revised plan as a whole**, not just the edited regions. Your own edits can introduce defects the per-finding check cannot see: a merged or renumbered task leaves a cross-reference pointing at the wrong content, a deleted step strands a later step that depended on it, a reworded task now contradicts its neighbour. Re-read the plan end to end and confirm task numbering is still sequential, every task cross-reference resolves to the task it means, every task that remains still carries its `- [ ]` checkbox, and no edit contradicts text you left in place. A defect **you** introduced is treated exactly like one the reviewer found: fix it, or record it as `unresolved`.

This self-check stands in for a second review round. A fresh second reviewer would arrive with no knowledge of what the first round found, so it could only re-review the whole plan and infer success from a finding's absence — expensive, and not a verification. You know exactly which edits you made and why, so you are the right party to check them.

## Step 5 — Compute status and emit the output block

Status is computed from the **unresolved counts, not from the reviewer's raw verdict**:

| Status | Condition |
|---|---|
| `blocked` | ≥1 unresolved **Critical** |
| `proceed-with-warnings` | 0 unresolved Critical, ≥1 unresolved **Required** |
| `clean` | 0 unresolved Critical and 0 unresolved Required |
| `degraded` | reviewer unavailable after one retry (Step 2) |

A review whose `VERDICT` was `NOT-CLEAN` but whose findings were **all declined with reasoning** therefore yields `PLAN-REVIEW: clean`. That is correct, not a contradiction — the declines are listed under `DECLINED-WITH-REASONING` for the human to overrule.

End with exactly this block so callers can parse it:

```
PLAN-REVIEW: <clean | proceed-with-warnings | blocked | degraded>
FINDINGS: <total>
ACCEPTED: <n>
DECLINED: <n>
UNRESOLVED-CRITICAL: <n>
UNRESOLVED-REQUIRED: <n>
NOT-IN-SCOPE:
<deferred items, one per line with a one-line rationale, or NONE>
DECLINED-WITH-REASONING:
<finding — why it was declined, one per line, or NONE>
UNRESOLVED:
<accepted-but-unfixed blockers, one per line, or NONE>
```

`ACCEPTED` counts findings whose fix was applied **and verified** in Step 4. Anything reclassified there leaves `ACCEPTED`: a blocking severity moves to `UNRESOLVED`, a non-blocking one to `DECLINED`. `FINDINGS` always equals `ACCEPTED + DECLINED + UNRESOLVED`.

## Non-interactive outcome

Without `--auto`, the caller presents a human gate and this skill simply returns.

With `--auto` there is no human gate, so the status decides and **the caller acts on it**:

- `blocked` — the caller **stops the run**, leaving the worktree and branch intact. Building a full implementation on a known-Critical plan wastes the entire run.
- `proceed-with-warnings` — the caller proceeds and logs the blockers. A plan flaw is recoverable, and the PR review loop and merge gate still guard the actual landing.
- `clean` / `degraded` — the caller proceeds.

State the applicable outcome explicitly in your final message so the caller does not have to infer it.

## Ledger

This skill writes **nothing** to the ledger. The counts in the output block are folded into the outcome line the caller already writes at the end of its run (`plan_review_*` fields — see `../flow-triage/references/ledger.md`). One writer per event, and no worktree-versus-primary-checkout root confusion here.

## Additional Resources

- **`references/reviewer-rubric.md`** — the four review axes, the mandatory codebase-verification clause, severity definitions, the coverage map, and the reviewer's output contract.
