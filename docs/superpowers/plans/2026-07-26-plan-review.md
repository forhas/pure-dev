# plan-review Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `plan-review` skill to both `quick-dev` and `notion-dev` that dispatches a fresh review-only agent against a written implementation plan — verifying it against the actual codebase — before `subagent-driven-development` executes it, with a bounded revise-and-re-review loop and a machine-parseable verdict.

**Architecture:** An orchestrator skill (`SKILL.md`) owns the loop, severity split, and output block; a reference file (`references/reviewer-rubric.md`) holds the contract the fresh agent applies. Authored once in `quick-dev`, then vendored into `notion-dev` with exactly four documented deltas (see Global Constraints). Callers (`quick-dev:develop` Phase 2b, `notion-dev:ticket` Phase 4.2) invoke it and parse its output block.

**Tech Stack:** Markdown prompt files and JSON manifests only. Claude Code plugin conventions: `skills/<name>/SKILL.md` with YAML frontmatter, `references/*.md` for progressive disclosure.

## Global Constraints

- **This repo contains no executable code.** No test runner, no build, no lint. TDD red-green gating does not apply. Every task's verification is: re-read the written file against the spec, plus `claude plugin validate` where a manifest or skill directory changed. Do not go looking for a test suite; there isn't one.
- **Spec of record:** `docs/superpowers/specs/2026-07-26-plan-review-design.md`. Where this plan and the spec disagree, the spec wins — except for the one documented deviation in Task 2, Step 1.
- **Superpowers path only.** Nothing in this work touches the `feature-dev` build path.
- **The two vendored copies must differ only in four documented places**, all inside `SKILL.md`: the frontmatter `description`'s naming of the calling flow, the `receiving-code-review` reference (`quick-dev:` / `superpowers:`), and two sibling-skill cross-references that must point at `../review-and-merge/` in notion-dev because that plugin has no `develop` skill. `references/reviewer-rubric.md` must be **byte-identical** in both. Task 4 Step 3 and Task 6 Step 3 verify this by diff.
  - The spec's packaging table lists a third delta, the ledger directory. It does **not** apply to these files: `plan-review` writes nothing to the ledger and names no ledger path, referring only to `../flow-triage/references/ledger.md`. The `.claude/quick-dev/` vs `.claude/notion-dev/` difference lives in the two `ledger.md` copies, which already differ that way.
- **Repo-agnostic content.** The rubric must hardcode no language, framework, test runner, or engineering preference. Project standards come from the target repo's `CLAUDE.md`, `.claude/rules/`, and the conventions visible in the files the plan touches.
- **Conventional Commits** for every commit: `feat`, `fix`, `docs`, `chore`, `refactor`.
- **Version bumps are Task 6 only.** Do not bump `plugin.json` in any earlier task — the repo root has no `.claude-plugin/plugin.json`, so no automated bump will fire, and a per-task bump would produce two bumps in one release.

---

## Task 1: quick-dev reviewer rubric

**Files:**
- Create: `plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md`

**Interfaces:**
- Consumes: nothing. This file is self-contained prose handed to a fresh agent.
- Produces: the reviewer output contract that Task 2 parses —
  `Reviewed plan:` echo line, `COVERAGE-MAP:` block, `- [<Severity>] …` finding lines,
  `NOT-IN-SCOPE-PRESENT: <yes|no>`, and a final `VERDICT: CLEAN` / `VERDICT: NOT-CLEAN` line.
  Severity vocabulary: `Critical`, `Required`, `Optional`, `Nit`, `FYI`.

Sibling file to read first for tone and structure: `plugins/quick-dev/skills/local-code-review/SKILL.md`. This rubric is deliberately its sibling — same severity ladder, same honesty-first framing, same mechanical verdict rule. Reference files in this repo carry no YAML frontmatter (see `skills/flow-triage/references/scorecard.md`); start at the `#` heading.

- [ ] **Step 1: Write the rubric file**

Create `plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md` with exactly this content:

```markdown
# Plan reviewer rubric

You are a **fresh, independent reviewer** of an implementation plan that has **not yet been executed**. You did NOT write this plan. Review it with the discipline of an engineer who will have to implement it, and who will be blamed if it sends the team down the wrong path. Apply extra scrutiny to AI-generated plans — their confident structure hides real defects.

Your job is to catch what is wrong with the plan **before anyone pays to implement it**. A defect caught here costs one review. The same defect caught after implementation costs the whole implementation plus rework.

## Mandatory verification — do this before reporting anything

**Read the repository. Do not review the plan as a document.**

1. Read **every file the plan names**. Confirm it exists at that path.
2. For every claim that something does not exist yet, **grep for it**. Plans routinely propose building what the repo already has.
3. For every new file the plan proposes, look at its intended neighbours. Does the repo already have a pattern for this kind of thing?

A finding asserted from the plan's own text alone, without checking the repo, is exactly the speculative finding this rubric forbids. The verification above is the reason this review exists — the plan's author already checked it against the spec, but nobody checked it against reality.

## Honesty first — do not manufacture findings

Only flag real defects. A sound plan gets `No findings.`

Do not raise theoretical, speculative, or cosmetic findings. Do not trade one wording for an equivalent one. Do not flag a plan for being longer than you would have written it — length is not a defect, unnecessary work is, and you must name the specific unnecessary work.

You are reviewing a document produced by a capable model. The temptation is to invent plausible findings to justify the review. Resist it. An empty finding list is a valid and useful result; a list of invented findings actively costs the team time and teaches them to ignore you.

The verdict is decided **solely** by the rule in the output contract below. Never emit `VERDICT: NOT-CLEAN` without at least one Critical or Required finding.

## Selectivity — review the plan in front of you

Apply only the axes that fit. A docs-only plan gets no test-coverage analysis. A pure-config plan gets no scope challenge. A plan for a repo with no test suite cannot be faulted for lacking test tasks — say so once as FYI and move on. Forcing every axis onto every plan produces exactly the theoretical findings this rubric forbids.

## Project standards come from the repo

Derive the standards you judge against from the target repository:

- `CLAUDE.md` at the repo root, and any `.claude/rules/` files.
- The conventions visible in the files the plan touches — naming, structure, error handling, test style.

Do not import preferences from anywhere else. You have no license to impose a style the repo does not already use.

## Review axes

### 1. Scope discipline

- Does something in the repo already solve this, fully or partly? Name the file and symbol.
- Is any task rebuilding a helper, adapter, or pattern that already exists?
- What is the minimum set of changes that achieves the stated intent? Name specific tasks that could be deferred without blocking it.
- Does the plan introduce a new abstraction where a direct implementation would do?

The finding this axis exists to catch: *"Task 3 rebuilds what `lib/foo.ts:validate` already does."*

### 2. Codebase fit

- Does every file path the plan names actually exist (for modifications) or sit in a sensible location (for creations)?
- Does every symbol the plan references — function, class, config key, command — actually exist?
- Does the plan follow the repo's established patterns, or invent a parallel one without justification?
- Do line-number references, where the plan gives them, still point at what the plan claims?

The finding this axis exists to catch: *"Task 4 modifies `src/api/router.ts` — that file does not exist."*

### 3. Dependency order and actionability

- Does any task depend on a task that comes **later**? The plan will be executed **sequentially, by a fresh agent per task, with no shared context** — a forward dependency is a hard failure, not an inconvenience.
- Does any task reference a type, function, or file that no earlier task creates?
- Is any task too vague to act on? A fresh implementing agent sees only its own task. "Wire up caching" with no named approach means that agent invents one.
- Do the names used across tasks match? A helper called `parseConfig` in Task 2 and `readConfig` in Task 5 is a defect.

The finding this axis exists to catch: *"Task 5 depends on Task 8."*

### 4. Test coverage

Build the coverage map (below) first, then judge it.

- Does every new codepath, branch, and error path have a task that tests it?
- Are the tests testing behaviour, or restating the implementation?
- Does the plan skip verification for a task that changes behaviour?

If the repo has no test suite at all, state that once and skip this axis.

The finding this axis exists to catch: *"The new retry branch has no test task."*

## The coverage map

Before reporting findings, enumerate what the plan introduces and map each item to the task that verifies it. This is a **reviewing instrument, not a deliverable** — you emit it in your output so the caller can see your reasoning, and each `GAP` becomes a finding. Do not ask for it to be written into the plan file.

Format:

```
COVERAGE-MAP:
  <new codepath, branch, or behaviour>  → Task <N>, Step <M>
  <new codepath, branch, or behaviour>  → GAP
```

Use `(no test suite in this repo)` as the whole map when the repo has none.

## Severity labels

- **Critical** — the plan, executed as written, produces a wrong or broken outcome: it addresses a different problem than the stated intent, a task cannot be executed at all, there is a forward dependency or dependency cycle, or a step would destroy data or state.
- **Required** — must be fixed before implementation: rebuilds existing functionality, violates a documented project rule, names a nonexistent file or symbol, or leaves a new codepath with no verification.
- **Optional** — worth considering; non-blocking.
- **Nit** — cosmetic; non-blocking.
- **FYI** — informational; non-blocking.

When a finding fits both Critical and Required, choose **Required** — unless the flaw blocks the plan as a whole, in which case it is Critical.

Be conservative with Critical. It stops unattended runs outright. Reserve it for "implementing this plan wastes the entire run."

## Lead with what matters

Order findings by leverage: scope and correctness first, then codebase-fit errors, then everything else. A few high-conviction findings beat a long list. If you have one structural problem and ten nits, the structural problem is the review.

## Propose the fix, in plan terms

Every finding must say what to change **in the plan** — not in the eventual code. "Merge Tasks 4 and 5; Task 5's only step is already covered by Task 4 Step 3" is actionable. "Consider consolidating" is not.

## Deferred work

If your review identifies work the plan could reasonably defer, check whether the plan has a `## Not in scope` section listing it.

Emit the `NOT-IN-SCOPE-PRESENT:` line per these three cases:

- **Deferrable work found, no such section** — raise one Required finding asking for the section with those items and a one-line rationale each, and emit `NOT-IN-SCOPE-PRESENT: no`.
- **Deferrable work found, the section already covers it** — no finding; emit `NOT-IN-SCOPE-PRESENT: yes`.
- **Nothing to defer** — no finding; emit `NOT-IN-SCOPE-PRESENT: yes`, regardless of whether the heading exists. Requiring the heading for its own sake is exactly the cosmetic finding this rubric forbids.

The line reports whether the deferred-work requirement is *satisfied*, not merely whether the heading exists.

## Output contract (MUST follow exactly)

Emit, in order:

1. A one-line **`Reviewed plan: <plan path> @ <sha or "uncommitted">`** echo.
2. The `COVERAGE-MAP:` block.
3. A findings list, each finding on the form:
   `- [<Severity>] <plan section or task> — <problem>. Fix: <concrete change to the plan>.`
   If there are no findings at all, write `No findings.`
4. `NOT-IN-SCOPE-PRESENT: <yes | no>`
5. A final line, alone, exactly one of:
   - `VERDICT: CLEAN` — iff there are **zero Critical and zero Required** findings.
   - `VERDICT: NOT-CLEAN` — iff there is **≥1 Critical or Required** finding.

You are **review-only**. Do not edit the plan, do not edit any other file, do not commit, do not push. Report findings; the caller triages, decides, and revises.
```

- [ ] **Step 2: Verify the file against its contract**

Confirm by reading the file back that all five output-contract elements are present and that the severity vocabulary is exactly `Critical`, `Required`, `Optional`, `Nit`, `FYI` — Task 2 parses these strings.

Run:
```bash
grep -c "VERDICT: CLEAN\|VERDICT: NOT-CLEAN\|NOT-IN-SCOPE-PRESENT\|COVERAGE-MAP\|Reviewed plan" plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md
```
Expected: a count of at least `5`.

Confirm no hardcoded language or framework leaked in:
```bash
grep -ni "rails\|pytest\|jest\|npm\|activerecord\|TODOS.md" plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md
git commit -m "feat(quick-dev): add plan reviewer rubric for plan-review skill"
```

---

## Task 2: quick-dev plan-review orchestrator

**Files:**
- Create: `plugins/quick-dev/skills/plan-review/SKILL.md`
- Read for reference: `plugins/quick-dev/skills/flow-triage/SKILL.md` (output-block and degradation patterns), `plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md` (from Task 1)

**Interfaces:**
- Consumes: `references/reviewer-rubric.md` from Task 1, and its reviewer output contract (`VERDICT: CLEAN|NOT-CLEAN`, `- [<Severity>] …`, `NOT-IN-SCOPE-PRESENT:`, `COVERAGE-MAP:`).
- Produces: the invocation signature and output block that Tasks 3 and 5 wire into callers.
  - Invocation: `--plan=<path>` (required), `[--auto]`, `[--spec-file=<path>]`, plus a positional argument carrying `INTENT:` / `SCOUT-FINDINGS:` / `MICRO-PLAN:` / `VERIFY:` labelled blocks.
  - Output block keys, in order: `PLAN-REVIEW:` (`clean|proceed-with-warnings|blocked|degraded`), `ROUNDS:`, `FINDINGS:`, `ACCEPTED:`, `DECLINED:`, `UNRESOLVED-CRITICAL:`, `UNRESOLVED-REQUIRED:`, `PLAN-CHANGED:`, `NOT-IN-SCOPE:`, `DECLINED-WITH-REASONING:`, `UNRESOLVED:`.

- [ ] **Step 1: Note the one deviation from the spec**

The spec's "Invocation" section lists `--ledger-root=<path>` and `--run-id=<id>` flags, but its "The skill writes nothing to the ledger" section establishes that the **caller** writes the ledger outcome line. Those two flags therefore have no reader inside this skill.

**Drop both flags.** Do not implement them, and do not have callers pass them (Tasks 3 and 5 reflect this). Everything else in the spec is implemented as written.

No file change in this step — it exists so the implementing agent does not "restore" the flags from the spec.

- [ ] **Step 2: Write the orchestrator SKILL.md**

Create `plugins/quick-dev/skills/plan-review/SKILL.md` with exactly this content:

````markdown
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
4. The `INTENT` block (or the contents of `--spec-file`) — this is what the plan is judged against.
5. The `SCOUT-FINDINGS` and `MICRO-PLAN` blocks, labelled as precomputed context from triage, or explicitly marked unavailable.
6. The `VERIFY` commands, so the reviewer knows what verification exists in this repo.
7. The repo root as the codebase to verify against, plus a pointer to `CLAUDE.md` and `.claude/rules/` if present.
8. An explicit statement that it is **review-only**: it must not edit files, commit, or push.

## Step 2 — Round 1

Dispatch **one** `general-purpose` agent, **synchronously**, with that prompt. (This matches how `../develop/SKILL.md` Phase 4 already spawns its local-mode reviewer.)

Parse from its output: the findings list with severities, `NOT-IN-SCOPE-PRESENT`, and the `VERDICT` line.

**Degradation.** If the agent fails, or its output lacks the `VERDICT` line, retry **once** with the same prompt. If it fails again, stop the loop and emit the output block with `PLAN-REVIEW: degraded`, `ROUNDS: 1`, all counts `0`, `PLAN-CHANGED: no`, and a one-line reason on the `UNRESOLVED:` line. Do not block the build.

## Step 3 — Triage the findings

Apply the `quick-dev:receiving-code-review` skill to the findings: agree, partially agree, or disagree with each one, with reasoning. Never apply a finding blindly, and never perform agreement you do not hold.

Verify before accepting. The reviewer was told to check the repo, but it can still be wrong — if it claims a file does not exist, look. A well-reasoned decline beats a low-confidence plan edit.

Classify every finding as exactly one of:

- **accepted** — you agree; you will edit the plan.
- **declined** — you disagree, with a stated reason. **A declined finding is resolved and does not block.** (Same rule `../develop/SKILL.md` Phase 4 already applies to code review.)
- **unresolved** — you agree, but it cannot be fixed in the plan (it needs a decision you do not own, or information nobody has). These are the only findings that count toward the blocking rule.

Non-blocking severities (`Optional`, `Nit`, `FYI`) may be applied or skipped at your discretion; they never produce an `unresolved` entry.

## Step 4 — Revise the plan

Edit the plan file in place for every accepted finding. Keep edits surgical — fix the finding, do not rewrite the plan. Preserve its structure, its task numbering where possible, and every `- [ ]` checkbox: callers rely on unchecked boxes for resume detection.

If accepted findings identified deferrable work and the plan has no `## Not in scope` section, add one with those items and a one-line rationale each.

If task numbering must change, update every cross-reference to the renumbered tasks in the same edit.

Record whether the plan file changed at all — that is `PLAN-CHANGED`.

## Step 5 — Round 2 (conditional)

**Run round 2 only if `PLAN-CHANGED: yes`.** If the plan did not change, there is nothing new to review: end at `ROUNDS: 1`.

Dispatch a **new** fresh `general-purpose` agent — never reuse the round-1 agent — with the same prompt rebuilt against the **revised** plan. Triage its findings exactly as in Step 3.

**Hard cap: 2 rounds.** Never a third, whatever round 2 returns. Remaining blockers are reported, not iterated on.

## Step 6 — Compute status and emit the output block

Status is computed from the **unresolved counts, not from the reviewer's raw verdict**:

| Status | Condition |
|---|---|
| `blocked` | ≥1 unresolved **Critical** |
| `proceed-with-warnings` | 0 unresolved Critical, ≥1 unresolved **Required** |
| `clean` | 0 unresolved Critical and 0 unresolved Required |
| `degraded` | reviewer unavailable after one retry (Step 2) |

A round whose `VERDICT` was `NOT-CLEAN` but whose findings were **all declined with reasoning** therefore yields `PLAN-REVIEW: clean`. That is correct, not a contradiction — the declines are listed under `DECLINED-WITH-REASONING` for the human to overrule.

End with exactly this block so callers can parse it:

```
PLAN-REVIEW: <clean | proceed-with-warnings | blocked | degraded>
ROUNDS: <1|2>
FINDINGS: <total across all rounds>
ACCEPTED: <n>
DECLINED: <n>
UNRESOLVED-CRITICAL: <n>
UNRESOLVED-REQUIRED: <n>
PLAN-CHANGED: <yes|no>
NOT-IN-SCOPE:
<deferred items, one per line with a one-line rationale, or NONE>
DECLINED-WITH-REASONING:
<finding — why it was declined, one per line, or NONE>
UNRESOLVED:
<accepted-but-unfixed blockers, one per line, or NONE>
```

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
````

- [ ] **Step 3: Verify the frontmatter parses and the contract matches Task 1**

Run:
```bash
head -6 plugins/quick-dev/skills/plan-review/SKILL.md
```
Expected: a `---` fenced YAML block with `name: plan-review`, a `description:` starting `This skill should be used when`, and `argument-hint:` listing only `--plan`, `--auto`, and `--spec-file`.

Confirm the dropped flags are absent:
```bash
grep -n "ledger-root\|run-id" plugins/quick-dev/skills/plan-review/SKILL.md
```
Expected: no output.

Confirm every output-block key is present:
```bash
grep -c "PLAN-REVIEW:\|ROUNDS:\|FINDINGS:\|ACCEPTED:\|DECLINED:\|UNRESOLVED-CRITICAL:\|UNRESOLVED-REQUIRED:\|PLAN-CHANGED:\|NOT-IN-SCOPE:\|DECLINED-WITH-REASONING:\|UNRESOLVED:" plugins/quick-dev/skills/plan-review/SKILL.md
```
Expected: at least `11`.

- [ ] **Step 4: Validate the plugin**

Run:
```bash
claude plugin validate plugins/quick-dev
```
Expected: validation passes. If the CLI is unavailable in this environment, say so explicitly in the task report rather than claiming it passed.

- [ ] **Step 5: Commit**

```bash
git add plugins/quick-dev/skills/plan-review/SKILL.md
git commit -m "feat(quick-dev): add plan-review orchestrator skill"
```

---

## Task 3: Wire plan-review into quick-dev

**Files:**
- Modify: `plugins/quick-dev/skills/develop/SKILL.md` (Phase 2b superpowers chain, lines 65-73; Phase 6 ledger outcome, line 146)
- Modify: `plugins/quick-dev/skills/flow-triage/references/ledger.md` (outcome schema, lines 22-33)
- Modify: `plugins/quick-dev/README.md` (Flow diagram line 16; Skills table after line 78)

**Interfaces:**
- Consumes: the invocation signature and output block from Task 2.
- Produces: `plan_review_rounds`, `plan_review_findings`, `plan_review_accepted`, `plan_review_declined`, `plan_review_unresolved` — the ledger field names Task 5 must reuse verbatim in notion-dev.

- [ ] **Step 1: Insert plan-review and a human plan gate into Phase 2b**

In `plugins/quick-dev/skills/develop/SKILL.md`, the `FLOW=superpowers` chain is currently three numbered steps. Replace step 2's trailing sentence and step 3 so the chain reads as five steps.

Find this text (end of step 2 and step 3):

```
2. `superpowers:writing-plans` — produces the implementation plan under `docs/superpowers/plans/`, committed on the branch. (Spec and plan land in the squash merge.) Brainstorming's own hand-off already invokes this skill after spec approval — when that happened, this step is complete; never invoke it a second time to produce a duplicate plan.
3. `superpowers:subagent-driven-development` — executes the plan in-session, fresh subagent per task with per-task review.
```

Replace with:

```
2. `superpowers:writing-plans` — produces the implementation plan under `docs/superpowers/plans/`, committed on the branch. (Spec and plan land in the squash merge.) Brainstorming's own hand-off already invokes this skill after spec approval — when that happened, this step is complete; never invoke it a second time to produce a duplicate plan. **Record the plan's path as `PLAN_PATH`** and the spec's path as `SPEC_PATH` — the next step needs both, and this flow uses writing-plans' default location rather than a fixed filename.
3. `quick-dev:plan-review` — independent review of the plan before any of it is built. Invoke via the Skill tool with `--plan="$PLAN_PATH" --spec-file="$SPEC_PATH"` (add `--auto` in non-interactive mode), and a context packet whose `INTENT:` block is the feature description, `SCOUT-FINDINGS:` and `MICRO-PLAN:` are the blocks recorded in Phase 2a, and `VERIFY:` lists the project's test/build commands if any exist. It dispatches a fresh reviewer against the plan **and the codebase**, triages the findings, revises the plan, and returns a `PLAN-REVIEW:` output block. Record its `PLAN-REVIEW`, `ROUNDS`, `FINDINGS`, `ACCEPTED`, `DECLINED`, `UNRESOLVED-CRITICAL`, `UNRESOLVED-REQUIRED`, and `NOT-IN-SCOPE` values for the ledger (Phase 6) and the final report; carry `NOT-IN-SCOPE` into the PR body in Phase 3.

   **`--auto` and `PLAN-REVIEW: blocked`** (≥1 unresolved Critical): STOP per "Failure handling" below — leave the worktree, branch, and plan intact and report the blockers. Do not implement a plan already known to be Critically flawed. `proceed-with-warnings`, `clean`, and `degraded` all continue.
4. **Hard gate — plan approval** (interactive only; skipped entirely under `--non-interactive`, where step 3's rule already decided). Present a short summary — not the whole plan file: what the review changed, what it declined and why (`DECLINED-WITH-REASONING`), and anything still unresolved. Then ask via `AskUserQuestion`: **Approve** — proceed to step 5; **Revise** — capture the user's feedback, edit the plan, and re-ask. Blocking: do not implement without approval. When `PLAN-REVIEW: blocked`, say so plainly and make Revise the recommended option.
5. `superpowers:subagent-driven-development` — executes the plan in-session, fresh subagent per task with per-task review.
```

- [ ] **Step 2: Add the plan-review metrics to the Phase 6 ledger line**

In the same file, find the Phase 6 ledger outcome JSON:

```
`{"event":"outcome","run_id":"<SLUG>","ts":"<UTC now>","result":"merged","review_rounds":<n>,"fix_commits":<n>,"files_changed":<n>,"insertions":<n>,"deletions":<n>,"duration_minutes":<n>}`
```

Replace with:

```
`{"event":"outcome","run_id":"<SLUG>","ts":"<UTC now>","result":"merged","review_rounds":<n>,"fix_commits":<n>,"files_changed":<n>,"insertions":<n>,"deletions":<n>,"duration_minutes":<n>,"plan_review_rounds":<n>,"plan_review_findings":<n>,"plan_review_accepted":<n>,"plan_review_declined":<n>,"plan_review_unresolved":<n>}`
```

Then, in the sentence immediately following that JSON, after "diff stats from the squash commit (`git -C "$REPO_ROOT" show --shortstat --format= <squash-sha>`); duration from `RUN_START` to now.", insert:

```
Plan-review metrics come from Phase 2b step 3's output block (`ROUNDS`, `FINDINGS`, `ACCEPTED`, `DECLINED`, and `UNRESOLVED-CRITICAL` + `UNRESOLVED-REQUIRED` summed); all five are `null` on the `feature-dev` path, which has no plan to review, and on a `degraded` review.
```

- [ ] **Step 3: Document the fields in the ledger schema**

In `plugins/quick-dev/skills/flow-triage/references/ledger.md`, find the sample outcome line:

```
{"event":"outcome","run_id":"add-api-rate-limiting","ts":"2026-07-17T11:05:00Z","result":"merged","review_rounds":2,"fix_commits":1,"files_changed":6,"insertions":180,"deletions":22,"duration_minutes":65}
```

Replace with:

```
{"event":"outcome","run_id":"add-api-rate-limiting","ts":"2026-07-17T11:05:00Z","result":"merged","review_rounds":2,"fix_commits":1,"files_changed":6,"insertions":180,"deletions":22,"duration_minutes":65,"plan_review_rounds":2,"plan_review_findings":5,"plan_review_accepted":3,"plan_review_declined":2,"plan_review_unresolved":0}
```

Then add this bullet to the "Field notes" list, immediately before the final `- Any outcome metric that cannot be determined is \`null\`, never guessed.` bullet:

```
- `plan_review_*` — written by the `plan-review` step on the `superpowers` build path (rounds run, total findings, accepted, declined, and accepted-but-unfixed). All `null` on the `feature-dev` path, which has no plan artifact to review, and when the review degraded. Added after the original schema; readers must tolerate their absence in older lines.
```

- [ ] **Step 4: Update the README Flow diagram and Skills table**

In `plugins/quick-dev/README.md`, find this line in the Flow diagram:

```
   │                    or superpowers: brainstorm → write plan → subagent-driven execution
```

Replace with:

```
   │                    or superpowers: brainstorm → write plan → plan-review (fresh agent
   │                    checks the plan against the codebase; revises it) → approve →
   │                    subagent-driven execution
```

Then add this row to the Skills table, immediately after the `review-and-merge` row:

```
| `plan-review` | (invoked by `develop` on the superpowers path) | Independent pre-implementation review of a written plan: fresh agent verifies it against the actual codebase, bounded revise-and-re-review loop, machine-parseable verdict |
```

- [ ] **Step 5: Verify the wiring is internally consistent**

Confirm the chain is five steps and the flags match Task 2's signature:

```bash
grep -n "quick-dev:plan-review\|Hard gate — plan approval\|PLAN_PATH\|SPEC_PATH" plugins/quick-dev/skills/develop/SKILL.md
for f in plugins/quick-dev/skills/develop/SKILL.md plugins/quick-dev/skills/flow-triage/references/ledger.md; do
  echo "$f: $(grep -o 'plan_review_[a-z]*' "$f" | sort -u | wc -l)"
done
```
Expected: the first shows the new step 3 and step 4 plus both path variables; the second prints `5` for each file — all five distinct `plan_review_*` field names present. (Count distinct names, not matching lines: the fields all sit on one JSON line.)

Confirm no `--ledger-root` or `--run-id` was passed to plan-review:

```bash
grep -n "plan-review" plugins/quick-dev/skills/develop/SKILL.md | grep -c "ledger-root\|run-id"
```
Expected: `0`.

Then:
```bash
claude plugin validate plugins/quick-dev
```
Expected: validation passes.

- [ ] **Step 6: Commit**

```bash
git add plugins/quick-dev/skills/develop/SKILL.md plugins/quick-dev/skills/flow-triage/references/ledger.md plugins/quick-dev/README.md
git commit -m "feat(quick-dev): run plan-review and a plan gate before implementation"
```

---

## Task 4: Vendor plan-review into notion-dev

**Files:**
- Create: `plugins/notion-dev/skills/plan-review/SKILL.md`
- Create: `plugins/notion-dev/skills/plan-review/references/reviewer-rubric.md`

**Interfaces:**
- Consumes: both files authored in Tasks 1 and 2.
- Produces: `notion-dev:plan-review`, with an identical invocation signature and output block, for Task 5 to wire in.

The three permitted deltas, and nothing else: skill prefix, `receiving-code-review` reference, ledger path. `notion-dev` has no vendored `receiving-code-review` — it uses the superpowers one, as its README documents.

- [ ] **Step 1: Copy both files verbatim**

```bash
mkdir -p plugins/notion-dev/skills/plan-review/references
cp plugins/quick-dev/skills/plan-review/SKILL.md plugins/notion-dev/skills/plan-review/SKILL.md
cp plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md plugins/notion-dev/skills/plan-review/references/reviewer-rubric.md
```

- [ ] **Step 2: Apply the three deltas to the copied SKILL.md**

Edit `plugins/notion-dev/skills/plan-review/SKILL.md` and make exactly these four replacements. `reviewer-rubric.md` needs **no changes** — it names no plugin.

1. In the frontmatter `description:`, replace `invoked by quick-dev:develop on the superpowers build path` with `invoked by notion-dev:ticket on the superpowers build path`.
2. In Step 3, replace `Apply the \`quick-dev:receiving-code-review\` skill` with `Apply the \`superpowers:receiving-code-review\` skill`.
3. In Step 2, replace the parenthetical `(This matches how \`../develop/SKILL.md\` Phase 4 already spawns its local-mode reviewer.)` with `(This matches how \`../review-and-merge/SKILL.md\` already spawns its local fallback reviewer.)` — `notion-dev` has no `develop` skill, so the original cross-reference would dangle.
4. In Step 3, replace `(Same rule \`../develop/SKILL.md\` Phase 4 already applies to code review.)` with `(Same rule \`../review-and-merge/SKILL.md\` already applies to code review.)`.

- [ ] **Step 3: Verify the deltas and that nothing else drifted**

```bash
diff plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md \
     plugins/notion-dev/skills/plan-review/references/reviewer-rubric.md
```
Expected: no output — the rubric is byte-identical.

```bash
diff plugins/quick-dev/skills/plan-review/SKILL.md \
     plugins/notion-dev/skills/plan-review/SKILL.md
```
Expected: exactly four differing hunks, matching the four replacements above. Any fifth difference is drift — fix it before committing.

Confirm no dangling reference to a skill notion-dev lacks:
```bash
grep -n "quick-dev:\|\.\./develop/" plugins/notion-dev/skills/plan-review/SKILL.md
```
Expected: no output.

```bash
claude plugin validate plugins/notion-dev
```
Expected: validation passes.

- [ ] **Step 4: Commit**

```bash
git add plugins/notion-dev/skills/plan-review/
git commit -m "feat(notion-dev): vendor plan-review skill from quick-dev"
```

---

## Task 5: Wire plan-review into notion-dev

**Files:**
- Modify: `plugins/notion-dev/commands/ticket.md` (Phase 4.2, lines 132-154; prerequisites line 25; Ledger outcome section, line ~309)
- Modify: `plugins/notion-dev/skills/flow-triage/references/ledger.md` (outcome schema, lines 22-33)
- Modify: `plugins/notion-dev/README.md` (layout tree line 189; Credits line 198)

**Interfaces:**
- Consumes: `notion-dev:plan-review` from Task 4, and the ledger field names established in Task 3 Step 3 — reuse them verbatim.
- Produces: no new interface.

- [ ] **Step 1: Insert plan-review as Phase 4.2 step (b) and renumber**

In `plugins/notion-dev/commands/ticket.md`, the `FLOW=superpowers` section has steps (a) writing-plans, (b) hard gate, (c) subagent-driven-development. Insert plan-review as the new (b), making the gate (c) and the execution (d).

Find this text:

```
(b) Hard gate — plan approval. Present a short summary of the plan (not the whole file). Ask `AskUserQuestion`: "Approve this plan, or revise?" Options:
- **Approve** — proceed.
- **Revise** — capture the user's feedback, edit PLAN.md, re-ask.

Blocking. Do not implement without approval.

(c) Invoke `superpowers:subagent-driven-development` on `<worktree>/PLAN.md`.
```

Replace with:

```
(b) Invoke `notion-dev:plan-review` — independent review of the plan before any of it is built. Pass `--plan="<worktree>/PLAN.md"` (add `--auto` in non-interactive mode) and a context packet whose `INTENT:` block is the ticket body (the `Requirements` / `Acceptance Criteria` / `Context` / `Open Questions` sections), `SCOUT-FINDINGS:` and `MICRO-PLAN:` are the blocks recorded in Phase 3 — or `NONE — not available` when Phase 3 was skipped on resume — and `VERIFY:` lists the `verify.steps` commands from config. No `--spec-file`: the ticket body is the spec and travels inline.

It dispatches a fresh reviewer against the plan **and the codebase**, triages the findings, revises `PLAN.md`, and returns a `PLAN-REVIEW:` output block. Record `PLAN-REVIEW`, `ROUNDS`, `FINDINGS`, `ACCEPTED`, `DECLINED`, `UNRESOLVED-CRITICAL`, `UNRESOLVED-REQUIRED`, and `NOT-IN-SCOPE` as `PLAN_REVIEW_REPORT` for the ledger outcome and the ticket's `## Implementation` section (6.5). The revision preserves every `- [ ]` checkbox, so Phase 1.2's resume detection is unaffected.

**Non-interactive mode and `PLAN-REVIEW: blocked`** (≥1 unresolved Critical): stop the run per the command's failure handling, leaving the worktree, branch, and `PLAN.md` intact, and report the blockers. Do not implement a plan already known to be Critically flawed. `proceed-with-warnings`, `clean`, and `degraded` all continue — with any blockers logged for the final report.

(c) Hard gate — plan approval. Present a short summary (not the whole file): what the review changed, what it declined and why (`DECLINED-WITH-REASONING`), and anything still unresolved. Ask `AskUserQuestion`: "Approve this plan, or revise?" Options:
- **Approve** — proceed.
- **Revise** — capture the user's feedback, edit PLAN.md, re-ask.

Blocking. Do not implement without approval. When `PLAN-REVIEW: blocked`, say so plainly and make **Revise** the recommended option.

(d) Invoke `superpowers:subagent-driven-development` on `<worktree>/PLAN.md`.
```

- [ ] **Step 2: Fix the stale cross-reference to the old step letter**

The prerequisites paragraph (line 25) needs **no change**: `plan-review` ships with this plugin so needs no availability check, and `superpowers:receiving-code-review` is already listed there — which is exactly what plan-review's triage step uses.

One place does need updating. In Phase 1.2, find the resume bullet:

```
- **Worktree + `PLAN.md` with unchecked boxes**: this is the `FLOW=superpowers` path. Confirm via `AskUserQuestion` that the user wants to continue with the existing plan, then resume at Phase 4's `superpowers:subagent-driven-development` step, starting from the first unchecked task.
```

Replace with:

```
- **Worktree + `PLAN.md` with unchecked boxes**: this is the `FLOW=superpowers` path. Confirm via `AskUserQuestion` that the user wants to continue with the existing plan, then resume at Phase 4.2 step (d), `superpowers:subagent-driven-development`, starting from the first unchecked task. Skip the plan review — the existing plan was already reviewed and approved in the interrupted run.
```

- [ ] **Step 3: Add plan-review metrics to the ledger outcome**

In the same file's "Ledger outcome" section, find:

```
{"event":"outcome","run_id":"<KEY>-<id>","ts":"<UTC now>","result":"merged","review_rounds":N,"fix_commits":N,"files_changed":N,"insertions":N,"deletions":N,"duration_minutes":N}
```

Replace with:

```
{"event":"outcome","run_id":"<KEY>-<id>","ts":"<UTC now>","result":"merged","review_rounds":N,"fix_commits":N,"files_changed":N,"insertions":N,"deletions":N,"duration_minutes":N,"plan_review_rounds":N,"plan_review_findings":N,"plan_review_accepted":N,"plan_review_declined":N,"plan_review_unresolved":N}
```

Then, in the sentence that follows, after "duration from `RUN_START` to now.", insert:

```
Plan-review metrics come from `PLAN_REVIEW_REPORT` (Phase 4.2 step (b)); all five are `null` on the `feature-dev` path, which has no plan to review, on a `degraded` review, and on a resume that skipped the review.
```

- [ ] **Step 4: Document the fields in notion-dev's ledger schema**

Apply the **same two edits as Task 3 Step 3** to `plugins/notion-dev/skills/flow-triage/references/ledger.md` — the sample outcome line and the new `plan_review_*` field-notes bullet, with identical wording. These two files are vendored copies of each other and must stay in sync.

- [ ] **Step 5: Update the notion-dev README**

In `plugins/notion-dev/README.md`, find the layout tree lines:

```
│   ├── review-and-merge/     # PR review loop: Codex rounds, local fallback, merge gates
│   └── local-code-review/    # fallback reviewer contract (used by review-and-merge)
```

Replace with:

```
│   ├── review-and-merge/     # PR review loop: Codex rounds, local fallback, merge gates
│   ├── local-code-review/    # fallback reviewer contract (used by review-and-merge)
│   └── plan-review/          # pre-implementation plan review: fresh agent vs. the codebase (used by ticket)
```

Then find the Credits paragraph:

```
`skills/flow-triage/`, `skills/review-and-merge/`, and `skills/local-code-review/` are vendored and adapted from the `quick-dev` plugin.
```

Replace with:

```
`skills/flow-triage/`, `skills/review-and-merge/`, `skills/local-code-review/`, and `skills/plan-review/` are vendored and adapted from the `quick-dev` plugin.
```

Finally, in the `/notion-dev:ticket` row of the Commands table, replace `worktree → triage (feature-dev or superpowers) → build → verify → PR` with:

```
worktree → triage (feature-dev or superpowers) → plan review (superpowers path) → build → verify → PR
```

- [ ] **Step 6: Verify the wiring**

```bash
grep -n "notion-dev:plan-review\|step (d)\|(d) Invoke" plugins/notion-dev/commands/ticket.md
for f in plugins/notion-dev/commands/ticket.md plugins/notion-dev/skills/flow-triage/references/ledger.md; do
  echo "$f: $(grep -o 'plan_review_[a-z]*' "$f" | sort -u | wc -l)"
done
```
Expected: the first shows the new step (b) and the renumbered (d) plus the Phase 1.2 resume reference; the second prints `5` for each file.

Confirm the two ledger reference copies are now identical again:
```bash
diff plugins/quick-dev/skills/flow-triage/references/ledger.md \
     plugins/notion-dev/skills/flow-triage/references/ledger.md
```
Expected: only the pre-existing `.claude/quick-dev/` vs `.claude/notion-dev/` path differences — three hunks, no new ones.

```bash
claude plugin validate plugins/notion-dev
```
Expected: validation passes.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/commands/ticket.md plugins/notion-dev/skills/flow-triage/references/ledger.md plugins/notion-dev/README.md
git commit -m "feat(notion-dev): run plan-review before the plan-approval gate"
```

---

## Task 6: Version bumps and final verification

**Files:**
- Modify: `plugins/quick-dev/.claude-plugin/plugin.json` (`version`)
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json` (`version`)
- Modify: `plugins/notion-dev/README.md` (Status line 5)

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: the release. No further interface.

Both plugins are at `0.5.0`. A new skill and a new gate is a **new capability for existing users → minor bump**: `0.5.0 → 0.6.0`. The repo root has no `.claude-plugin/plugin.json`, so no automated bump fires; and `.claude-plugin/marketplace.json` does not pin plugin versions, so it needs no edit.

- [ ] **Step 1: Bump both plugin versions**

Edit `plugins/quick-dev/.claude-plugin/plugin.json` and `plugins/notion-dev/.claude-plugin/plugin.json`, changing `"version": "0.5.0"` to `"version": "0.6.0"` in each.

Verify:
```bash
grep -h '"version"' plugins/*/.claude-plugin/plugin.json
```
Expected: two lines, both `"version": "0.6.0",`.

- [ ] **Step 2: Update the notion-dev Status line**

In `plugins/notion-dev/README.md`, find:

```
**Status**: pre-release (0.5.0).
```

Replace with:

```
**Status**: pre-release (0.6.0).
```

Leave the rest of that paragraph unchanged.

- [ ] **Step 3: Run the parity check**

The two vendored `plan-review` copies must differ only in the documented deltas. This is a verification step, not a new script — a general parity script would have to cover all five vendored skills to be coherent, which is outside this plan's scope.

```bash
diff -u plugins/quick-dev/skills/plan-review/references/reviewer-rubric.md \
        plugins/notion-dev/skills/plan-review/references/reviewer-rubric.md
```
Expected: no output.

```bash
diff -u plugins/quick-dev/skills/plan-review/SKILL.md \
        plugins/notion-dev/skills/plan-review/SKILL.md
```
Expected: exactly the four hunks from Task 4 Step 2 — the `description` prefix, the `receiving-code-review` reference, and the two `../develop/` → `../review-and-merge/` cross-references. Nothing else.

- [ ] **Step 4: Validate both plugins**

```bash
claude plugin validate plugins/quick-dev && claude plugin validate plugins/notion-dev
```
Expected: both pass. If `claude` is unavailable in this environment, report that plainly instead of claiming success.

- [ ] **Step 5: Confirm no dangling references anywhere**

```bash
grep -rn "plan-review" plugins/ --include=*.md --include=*.json | grep -v "skills/plan-review/"
```
Expected: references only from `quick-dev/skills/develop/SKILL.md`, `quick-dev/README.md`, `notion-dev/commands/ticket.md`, and `notion-dev/README.md`.

```bash
grep -rn "ledger-root\|run-id" plugins/*/skills/plan-review/
```
Expected: no output — those flags were deliberately dropped (Task 2, Step 1).

- [ ] **Step 6: Commit**

```bash
git add plugins/quick-dev/.claude-plugin/plugin.json plugins/notion-dev/.claude-plugin/plugin.json plugins/notion-dev/README.md
git commit -m "chore: bump quick-dev and notion-dev to 0.6.0 for plan-review"
```

---

## Manual smoke test (after implementation)

Not a task — run this yourself, in a scratch repo, once the plan is implemented. It is the only check that the reviewer produces *real* findings rather than plausible-sounding ones.

1. In a throwaway git repo with a `CLAUDE.md` and a couple of source files, write a plan by hand containing two deliberate defects: one task modifying a **file that does not exist**, and one task **depending on a later task**.
2. Invoke `quick-dev:plan-review --plan=<that plan>` with an `INTENT:` block describing the intended feature.
3. Confirm the reviewer catches **both** defects, that its findings cite the real paths, that the plan gets edited, that round 2 fires (`ROUNDS: 2`, `PLAN-CHANGED: yes`), and that the output block parses.
4. Re-run with `--auto` and a defect severe enough to be Critical; confirm `PLAN-REVIEW: blocked`.
5. **Watch for manufactured findings.** If the review reports findings the codebase does not support, the mandatory-verification clause in `reviewer-rubric.md` is not biting hard enough — tighten it before trusting the gate.
