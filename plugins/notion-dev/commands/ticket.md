---
description: Implement a single ticket end-to-end. Creates a worktree, triages the build flow, implements (feature-dev or superpowers), verifies, ships a PR, runs the review-and-merge loop, merges, and cleans up. Updates the ticket status at each checkpoint.
argument-hint: "<ticket-id> [--non-interactive] [--flow=feature-dev|superpowers] [| <optional guidance>]"
disable-model-invocation: true
---

# /notion-dev:ticket

Full implementation cycle for one ticket, end to end: fetch → clarify → isolate → triage → build → verify → ship → review & merge → record → clean up.

Args: `<ticket-id> [--non-interactive] [--flow=feature-dev|superpowers] [| <optional user guidance>]`

`<ticket-id>` is either the Notion page id from the page URL (the 32-hex id, e.g. `383fdf83c4178177beebd41a69bf47bc` in `https://app.notion.com/p/.../...-383fdf83c4178177beebd41a69bf47bc`; a dashed UUID or the full page URL works too), or the logical key (`STO-42`).

If called with no argument, attempt to extract the **numeric** ticket id from the current branch name (pattern `<project.key>-<n>` or `ticket/<project.key>-<n>-*`); otherwise fail with guidance. This is the **resume** path — a fresh run passes the page id/URL or logical key, while resuming from inside a worktree relies on the numeric id already encoded in the branch.

Flag parsing (modeled on quick-dev's `develop` skill):
- If the arguments contain `--non-interactive`, remove it and set **non-interactive mode**: never pause for user input; whenever any step (including the build flow's own checkpoints) calls for asking the user, self-answer with the most reasonable option and log the decision for the final report (Phase 10).
- If the arguments contain `--flow=<value>`, remove it and record the value as `FLOW_OVERRIDE`. Valid values: `feature-dev`, `superpowers`. Any other value: stop immediately — before creating anything — and name the two valid values.
- Everything after a `|` is optional guidance and remains available context throughout the run.
- Whatever remains is the `<ticket-id>` (or empty, for the no-arg resume path above).

## Preconditions

- **Superpowers and feature-dev (required).** `dependencies.superpowers` **and** `dependencies.featureDev` in the config must both be `true` — if either is missing or false, abort and tell the user to re-run `/notion-dev:init` (which verifies and records both). Confirm `superpowers:writing-plans`, `superpowers:subagent-driven-development`, `superpowers:receiving-code-review`, and `feature-dev:feature-dev` are all available; this command delegates planning, execution, and review to them.
- **GitHub access**: authenticated `gh` CLI is **required** — the Phase 7 review loop (`notion-dev:review-and-merge`) depends on `gh` for paginated comment reads and GraphQL review-thread resolution, which the GitHub MCP cannot perform. Probe `gh auth status` at the top of the command; abort with "Install and authenticate `gh` (`gh auth login`), then re-run" if unavailable. The GitHub MCP (`mcp__github__create_pull_request` etc.) is optional: when present, prefer it for the operations it supports (PR create, metadata reads, merge) and fall back to `gh` when it fails or is absent.
- Record `REPO_ROOT` **first**, before loading config or invoking any skill: the first path listed by `git worktree list`, i.e. the **primary checkout** root, never a worktree path. (This recipe is correct from anywhere, including the no-arg resume path invoked from inside the ticket worktree, where `git rev-parse --show-toplevel` would wrongly return the worktree root.)
- `.claude/notion-dev.config.json` exists; load it. If missing, abort and tell the user to run `/notion-dev:init`. All config reads — here and in every later phase or invoked skill — resolve against the **primary checkout** (`$REPO_ROOT/.claude/notion-dev.config.json`), never the worktree: the worktree is cut from `origin/<git.baseBranch>`, which lacks the config whenever it is uncommitted, unpushed, or gitignored.
- The repo has an `origin` remote.
- The working tree is clean, OR the only dirt is the init-generated setup files (`.claude/notion-dev.config.json`, `.mcp.json` — init's commit step is optional, and this command must stay usable when it was declined; all implementation happens in the worktree and config is read from `$REPO_ROOT`, so these files never contaminate the ticket branch), OR the user is resuming inside an existing worktree for this ticket. Any other dirt: stop and ask the user to commit or stash first (non-interactive: stop and report).

---

## Phase 1 — Fetch and clarify

### 1.1 Fetch the ticket

Invoke the `notion-dev:ticket-system` skill, operation `fetchTicket(id)`, passing whatever was supplied — the page id/URL or logical key on a fresh run, or the numeric id on resume. The adapter accepts both. You get `{ title, key, body, status, url, metadata, type }`.

Derive the **numeric `<id>`** used for all naming below from `metadata.idProperty value` in the returned ticket. If the resolved page has no `idProperty` value, stop and tell the user the ticket DB needs an ID property — branch and worktree naming depend on it.

Record `TICKET_TYPE` from the returned `type` (the logical key, when the DB has a mapped type property) — it may be absent.

**Epic guard.** The fetched page is an epic container when the returned `metadata.parentTaskProperty` is `""` (empty) **and** `metadata.epicProperty` is non-empty **and** `listEpicChildren(id)` returns at least one child. In that case abort — an epic is a container, not implementable work:

```
[<KEY>-<n>] <name> is an epic container, not an implementable ticket.
Pick one of its children:
  [<KEY>-67] Fix stale index — Implemented
  [<KEY>-68] Add cache metrics — In Progress
```

Hard abort in both interactive and non-interactive mode. It runs before Phase 2, so no worktree, branch, status change, or ledger line is created.

An **epic-in-waiting** — Epic select set, empty parent, but no children yet — is deliberately **not** guarded: it is indistinguishable from a normal ticket that happens to carry an Epic tag, and blocking it would break the plain Epic-select tagging that works today. Skip the guard entirely when the DB lacks `parentTaskProperty` or `epicProperty`.

Record `RUN_START` (`date -u +%FT%TZ`). `REPO_ROOT` was already recorded at the preconditions gate — before the first config read and ticket-system call, both of which depend on it; the ledger, per `skills/flow-triage/references/ledger.md`, likewise lives in the primary checkout it points to.

Announce to the user: "Working on `<key>`: <title>" (`<key>` is the `key` field returned by `fetchTicket`, e.g. `"STO-67"` — display it as-is, don't rebuild it from `project.key`). Show the ticket URL.

### 1.2 Check for existing worktree (resumability)

Compute worktree path from config template `worktree.prefix` (tokens: `{name}`, `{key}`, `{id}` — `{id}` is the numeric `idProperty value` from the fetched ticket), resolved relative to the parent directory of `REPO_ROOT` (the primary checkout recorded in 1.1 — not the current directory, which on the no-arg resume path is the worktree itself).

Before any resume decision that involves triage: read `$REPO_ROOT/.claude/notion-dev/ledger.jsonl` for the most recent decision line with `run_id == <KEY>-<id>` that lacks a terminal outcome. If found, reuse its `flow_chosen` as `FLOW` and skip Phase 3 entirely when resuming into the build phase. If no unresolved decision line yields a `FLOW` (e.g. an interleaved run's orphan sweep already closed it), do not guess — run Phase 3 normally on resume.

If the worktree already exists:
- Announce: "Found existing worktree at `<path>`; resuming."
- **Worktree + `PLAN.md` with unchecked boxes**: this is the `FLOW=superpowers` path. Confirm via `AskUserQuestion` that the user wants to continue with the existing plan, then pick the resume point from the checkbox evidence — **never assume the plan was reviewed**:
  - **Some boxes already checked** — implementation began, so resume at step (d), `superpowers:subagent-driven-development`, from the first unchecked task, and do **not** run the plan review. For a run started on this version, reaching step (d) means the review and gate already cleared. For a worktree predating the review gate they did not — but the plan is already part-built, and `plan-review` has no way to review only the unchecked remainder: it judges the whole plan, so it could revise a task whose code has already shipped. That is worse than not reviewing. State plainly in the final report that this resumed plan was not reviewed by this version; Phase 7's review loop still examines the actual diff.
  - **No boxes checked at all** — there is no evidence the plan ever cleared review. The prior run may have stopped *because* the review returned `PLAN-REVIEW: blocked`, or been interrupted before step (b) ran at all. Resume at step **(b)** and run the review, gate, and build normally. Re-reviewing an already-approved plan costs one review; skipping review on a plan known to be Critically flawed is the failure this gate exists to prevent.
- **Worktree + `PLAN.md` with all boxes checked**: the build finished but the run was interrupted before ship (Phase 6.6 removes `PLAN.md` on a completed run). This is the `FLOW=superpowers` path. Confirm via `AskUserQuestion`, then resume at Phase 5 (verify) and continue the pipeline from there.
- **Worktree, no `PLAN.md`**: inspect state.
  - Commits ahead of base **and** an open PR exists for the branch → offer to jump straight to Phase 7 (or suggest running `/notion-dev:finalize <pr>` instead).
  - Commits ahead of base but no PR → ask (via `AskUserQuestion`) with three options: continue implementing (re-invoke the build flow with the existing diff as context), treat the implementation as complete (the build finished before the interrupt — resume at Phase 5 verify and ship; the feature-dev twin of the all-boxes-checked `PLAN.md` state), or start over.
  - Neither commits nor a PR → treat as fresh, but **reuse the existing worktree and branch**: skip 2.1's `git worktree add` (path and branch both exist — re-running it fails), `cd` into the existing worktree, run 2.1's status update (idempotent), and continue from there.

Otherwise, continue with a fresh setup.

Non-interactive mode: self-answer every resume question above with the most reasonable choice (continue existing plan / continue implementing) and log the decision.

### 1.3 Hard gate — requirement clarification

Read the ticket body together with `CLAUDE.md` at the repo root and any files the ticket references.

Ask yourself: do I understand the goal, scope, and acceptance criteria well enough to implement without guessing?

- **If yes**: proceed.
- **If no**: use `AskUserQuestion` for targeted clarifications. One question at a time; multiple choice preferred when the options are clear.
- **If severely under-spec** (missing goal or acceptance criteria, or the ticket is a one-liner): suggest re-running `/notion-dev:create-task <id>` to elaborate first; stop the current command.

This gate is **blocking**. Do not proceed to planning until the requirement is unambiguous.

Non-interactive mode: if severely under-spec, stop and report — never guess requirements. Otherwise self-answer clarifying questions with the most reasonable interpretation and log the decision.

---

## Phase 2 — Isolate

### 2.1 Create the worktree

Compute the branch slug: kebab-case the ticket title (lowercase, non-alphanumerics → `-`, collapse repeats, trim leading/trailing `-`), truncate to 40 characters, trim a trailing `-` if truncation left one. The branch name is `ticket/<project.key>-<id>-<slug>` — e.g. `ticket/STO-11-identify-interfaces`.

```
git fetch origin
git worktree add <worktree-path> origin/<git.baseBranch> -b ticket/<project.key>-<id>-<slug>
```

Read values from config: `git.baseBranch`. The branch-name parser in the preamble already accepts this form, so `/notion-dev:ticket` called from inside the worktree (with no args) resolves the ID correctly.

`cd` into the worktree for all subsequent work.

Mark the ticket as started — invoke `notion-dev:ticket-system`:

- `updateStatus(id, "inProgress")` — the ticket now stays in "In Progress" through triage, planning, implementation, and PR review. The plugin does not flip it to a further state until Phase 8. Idempotent on resume (re-running on an existing worktree is safe).

All subsequent file work happens in the worktree. Ledger writes go to `$REPO_ROOT/.claude/notion-dev/` — a sanctioned exception to the worktree-only rule, and a self-ignored directory that never appears in `git status`.

---

## Phase 3 — Triage

Invoke the `notion-dev:flow-triage` skill via the Skill tool from inside the worktree with:
- always: `--ledger-root="$REPO_ROOT" --run-id="<KEY>-<id>"`
- non-interactive: add `--auto`
- `FLOW_OVERRIDE` set: add `--forced-flow=$FLOW_OVERRIDE`
- `TICKET_TYPE` known: add `--ticket-type=<TICKET_TYPE>`
- description argument: the ticket title, a blank line, then the ticket body.

From its output block record `FLOW`, `MICRO_PLAN`, `SCOUT_FINDINGS` (sourced from that
block's `FLOW:`, `MICRO-PLAN:`, and `SCOUT-FINDINGS:` lines respectively). Triage owns its
own confirmation prompt, bug hard rule, ledger decision line, and degradation — do not
re-ask here.

If Phase 1.2 already resolved `FLOW` from an unresolved ledger decision on resume, skip this phase entirely.

---

## Phase 4 — Build

From inside the worktree, follow the branch matching `FLOW`:

### 4.1 `FLOW=feature-dev`

Invoke `feature-dev:feature-dev` with the ticket body plus `MICRO_PLAN`/`SCOUT_FINDINGS` as seed context for its exploration/architecture steps, when available (they are absent when Phase 3 was skipped on resume). Follow its full flow (explore → clarify → architect → implement → review).

### 4.2 `FLOW=superpowers`

(a) Invoke `superpowers:writing-plans`, passing the ticket body (the `Requirements` / `Acceptance Criteria` / `Context` / `Open Questions` sections — already a well-formed spec from `/notion-dev:create-task`) as the input, with these overrides (writing-plans honors a caller-supplied plan location):

- **Save location**: write the plan to `<worktree>/PLAN.md`. Do **not** use writing-plans' default `docs/superpowers/plans/...` path.
- **Feature name** for the plan header: `<KEY>-<id>: <title>`.

Writing-plans produces a TDD-structured plan with bite-sized (2-5 minute) tasks, explicit file-by-file create/modify paths, and checkbox (`- [ ]`) tracking.

For tickets that are genuinely not TDD-shaped (docs-only edit, config bump, pure refactor with existing coverage), say so in the spec you hand to writing-plans — it will still structure tasks appropriately, just without red-then-green gating.

(b) Invoke `notion-dev:plan-review` — independent review of the plan before any of it is built. Pass `--plan="<worktree>/PLAN.md"` (add `--auto` in non-interactive mode) and a context packet whose `INTENT:` block is the ticket body (the `Requirements` / `Acceptance Criteria` / `Context` / `Open Questions` sections), `SCOUT-FINDINGS:` and `MICRO-PLAN:` are the blocks recorded in Phase 3 — or `NONE — not available` when Phase 3 was skipped on resume — and `VERIFY:` lists the `verify.steps` commands from config. No `--spec-file`: the ticket body is the spec and travels inline.

It dispatches a fresh reviewer against the plan **and the codebase**, triages the findings, revises `PLAN.md`, and returns a `PLAN-REVIEW:` output block. Record the whole output block as `PLAN_REVIEW_REPORT` — `PLAN-REVIEW`, `FINDINGS`, `ACCEPTED`, `DECLINED`, `UNRESOLVED-CRITICAL`, `UNRESOLVED-REQUIRED`, `NOT-IN-SCOPE`, `DECLINED-WITH-REASONING`, and `UNRESOLVED` — for the ledger outcome and the ticket's `## Implementation` section (6.5). The revision preserves every `- [ ]` checkbox, so Phase 1.2's resume detection is unaffected.

**Non-interactive mode and `PLAN-REVIEW: blocked`** (≥1 unresolved Critical): stop the run per the command's failure handling, leaving the worktree, branch, and `PLAN.md` intact, and report the blockers. Do not implement a plan already known to be Critically flawed. `proceed-with-warnings`, `clean`, and `degraded` all continue — with any blockers logged for the final report.

(c) Hard gate — plan approval (**interactive only; skipped entirely in non-interactive mode**, where step (b)'s rule already decided — see 4.3). Present a short summary (not the whole file): what the review changed, what it declined and why (`DECLINED-WITH-REASONING`), and anything still unresolved. Ask `AskUserQuestion`: "Approve this plan, or revise?" Options:
- **Approve** — proceed.
- **Revise** — capture the user's feedback, edit PLAN.md, re-ask **this gate**. Do not re-invoke `notion-dev:plan-review`: it has already run, and human iteration is deliberately outside it. After each Revise iteration, refresh the recorded plan-review report before continuing: for every `UNRESOLVED` item record whether the revision addressed it, and recompute the status from what remains. Never carry pre-revision values into the ledger or the final report — a run whose blockers the user fixed at the gate must not be recorded as having proceeded past them, and one where the revision resolved nothing must not be recorded as clean. Write a status that only became clean through human revision as `clean (resolved at gate)`, so calibration keeps it distinguishable from a review that passed on its own.

Blocking when it runs. Do not implement without approval. When `PLAN-REVIEW: blocked`, say so plainly and make **Revise** the recommended option.

(d) Invoke `superpowers:subagent-driven-development` on `<worktree>/PLAN.md`. It walks the checkbox-tracked task list writing-plans produced, running a fresh subagent per task with per-task review. Two scoping instructions for this delegation, kept from the prior single-flow command:

- **Tick the file checkboxes**: as each task completes, mark its `- [ ]` as `- [x]` in `PLAN.md`. This keeps execution resumable across sessions — if interrupted, the next run resumes from the first unchecked task (paired with the resume detection in Phase 1.2).
- **Stop before `superpowers:finishing-a-development-branch`**: do not let the delegation proceed into it. Ship, review, merge, and cleanup are owned by Phases 6–9 below, not by this delegation.

State the explicit deviations from stock superpowers when invoking, so the flows do not fight: skip `superpowers:using-git-worktrees` (Phase 2 already made the worktree); the end-of-branch review that `subagent-driven-development`/`finishing-a-development-branch` would normally run is not a substitute for Phase 7's review loop, which runs identically for both build flows.

### 4.3 Non-interactive mode and shared context

Non-interactive mode: every build-flow user gate (clarifying questions, plan approval, per-task review pauses) is self-answered with the most reasonable choice and logged for the final report.

Throughout execution, project context matters: `CLAUDE.md` at the repo root, existing sibling files, and any skill files under `.claude/skills/` describe conventions the implementation must follow. Ensure these surfaces are available to whichever build flow is running.

---

## Phase 5 — Verify

### 5.1 Run verify

Iterate over `verify.steps` from config in order. For each step:
1. Run the `cmd`.
2. If it fails, attempt to fix and re-run.
3. Cap at `retries` attempts per step (default 3). If still failing, report to the user and stop.

### 5.2 Optional simplify

If the `simplify` skill or command is available in this environment, invoke it as a **non-blocking** pass: it may refactor for clarity, but if the verify suite breaks afterward, revert the simplify changes and continue. Correctness beats elegance.

---

## Phase 6 — Ship

### 6.1 Plugin version bump

If `.claude-plugin/plugin.json` exists at the worktree root, the manifest `version` must change exactly once per `/notion-dev:ticket` run before the commit. All base comparisons in this step use `<PR_BASE>` = `git.prTargetBranch`, falling back to `git.baseBranch` — the branch the PR will actually merge into (6.4's target), which is where the version must be greater:

1. Skip only if the ticket's work already **increased** it: parse `version` from `git show origin/<PR_BASE>:.claude-plugin/plugin.json` and from the worktree manifest, and compare as semver. Strictly greater → the bump already exists; never double-bump. Equal, lower, or merely a reformatted line → not a bump; continue to step 2. (Compare the working tree, not committed history — at this point the ticket's edits may still be uncommitted.) If the manifest does not exist at the base — this run created the plugin — the manifest's initial version **is** the release version: skip the bump and record it as `new plugin @ <version>`.
2. Otherwise classify this run's change and bump semver accordingly: breaking behavior for existing users → **major**; new capability (command, skill, option, mode) → **minor**; fix, docs, refactor, internal-only → **patch**.
3. Record `old → new` and the classification; state it in the PR body (6.4) and the final report (Phase 10).

Non-plugin repos skip this entirely.

### 6.2 Commit

Exclude `PLAN.md` from the commit:

```
git add . ':!PLAN.md'
git commit -m "<type>(<scope>): <short summary> (<KEY>-<id>)"
```

Commit type follows Conventional Commits: `feat`, `fix`, `refactor`, `chore`, `test`, `docs`. Skip cleanly when the tree is already clean — `superpowers:subagent-driven-development` commits as it goes, so there may be nothing left to commit here.

### 6.3 Push

Push the branch created in 2.1:

```
git push -u origin ticket/<project.key>-<id>-<slug>
```

### 6.4 Open PR

Target: `git.prTargetBranch` (falls back to `git.baseBranch`).

Prefer the GitHub MCP tool `mcp__github__create_pull_request` when available; fall back to `gh pr create`.

PR body structure:
- **Summary** — 1-3 bullets.
- **Ticket** — link to the ticket URL returned from fetchTicket.
- **Changes** — grouped list of files touched.
- **Test plan** — how to verify the change.

For plugin repos, add the version-bump line (`old → new`, classification) from 6.1.

### 6.5 Update ticket

Write a persistent `## Implementation` section onto the ticket so the ticket itself becomes a memory reference for what was built. Invoke `notion-dev:ticket-system`:

- **Do not change status here** — the ticket stays in "In Progress" through PR review. Phase 8 flips it to "Implemented" after the merge lands.
- `setPullRequest(id, <PR URL>)` — persists the PR URL into the dedicated `prProperty` column so the Notion DB stays filterable by PR. No-op when the DB has no such property.
- `upsertSection(id, "Implementation", { ... })` with this content:
  - **Plan** — a 2-4 sentence summary of the resolution approach, distilled from PLAN.md's Goal / Architecture / top-level Tasks. Not a copy of PLAN.md; a scan-readable overview. For the feature-dev path (no PLAN.md), distill this instead from the architecture summary feature-dev produced.
  - **Implementation** — what was actually done. Include: the ordered list of task headings completed, any notable decisions made during execution (e.g. a library chosen, a pattern introduced, an approach that replaced the planned one), and any deliberate deviations from the plan with the reason.
  - **Files Changed** — the list from `git diff --name-only origin/<PR_BASE>...HEAD` (6.1's `<PR_BASE>` — the branch the PR actually targets; `git.baseBranch` would misstate the PR's contents when `prTargetBranch` differs), grouped by directory — excluding `PLAN.md` if present: 6.6 removes it before review, so it never survives into the final PR diff even when an interim commit swept it in.
  - **PR** — the PR URL.
  - **Branch** — the branch name.
  - **Plan review** — `superpowers` path only, from `PLAN_REVIEW_REPORT`: the `PLAN-REVIEW` status, plus — when non-empty — the `UNRESOLVED` blockers the run proceeded past and the `DECLINED-WITH-REASONING` entries. Omit this bullet entirely on the `feature-dev` path, on a `degraded` review, and on a resume that skipped the review. This is the only durable home for that detail: `PLAN.md` is deleted in 6.6 and the ledger keeps only aggregate counts.
  - **Notes** — optional. Any caveats for the reviewer or follow-up items discovered but out of scope — including the plan review's `NOT-IN-SCOPE` deferred items, which otherwise die with `PLAN.md` in 6.6.

This section is the single source of truth for "what did this ticket do?" — it survives even if the PR is later squashed or comments are lost. Phase 8 will append a separate `## Merged` section later; the two coexist.

Also call `postComment(id, <one-line PR URL + "ready for review">)` so watchers get a notification.

### 6.6 Remove PLAN.md

`FLOW=superpowers` path: `rm -f PLAN.md` at the worktree root (`-f` keeps the step idempotent when the file is already gone, e.g. on re-entry). Its durable summary now lives in the ticket's `## Implementation` section (6.5), and the worktree must be clean before entering Phase 7 — review-and-merge's clean-tree gate (`git status --porcelain` empty) would otherwise deadlock on the untracked file, and its `git add -A` fix-commits would sweep PLAN.md into the PR. After the `rm`, check `git status --porcelain -- PLAN.md`: a ` D` entry means an earlier commit swept the file in (`superpowers:subagent-driven-development` commits as it goes and doesn't know 6.2's exclusion rule) — commit the removal (`git commit -m "chore(<KEY>-<id>): remove PLAN.md" -- PLAN.md`) and push, or the same clean-tree gate deadlocks on the tracked deletion. This is why Phase 1.2's resume logic treats "worktree with no `PLAN.md` + open PR" as the jump-to-Phase-7 state.

`FLOW=feature-dev` path: no-op — there is no PLAN.md.

---

## Phase 7 — Review and merge

Invoke the `notion-dev:review-and-merge` skill via the Skill tool with args:
`<pr-number>`, plus `--non-interactive` when set, plus — when the target repo is a
plugin (6.1 applied or verified a bump) — the stale-bump guard:
`--pre-merge-check "the manifest version in .claude-plugin/plugin.json on this branch
must be strictly greater, as semver, than in
git show origin/<the PR's baseRefName>:.claude-plugin/plugin.json (missing at base = new
plugin, check passes) — if equal or lower, the base moved: first update the branch
from the current base, then recompute the semver bump, commit, and push"`.

Remain in the worktree while it runs so review fixes land on the branch. It owns:
existing-comment processing, rounds with the configured code reviewer (Codex or Copilot,
resolved from `.claude/notion-dev.config.json`), the local fallback
(`notion-dev:local-code-review`), merge gates (including config `git.preMergeChecks`),
the merge itself per `git.mergeStrategy`, and remote branch deletion. Record its final
report (which loop ran, rounds, applied vs. declined) as `REVIEW_REPORT`.

---

## Phase 8 — Record

### 8.1 Update ticket

Append a separate `## Merged` section — do **not** touch the `## Implementation` section written in Phase 6.5; the two are meant to coexist as a chronological record.

Invoke `notion-dev:ticket-system`, `upsertSection(id, "Merged", { ... })` with these fields (order matters — the Notion adapter renders scalars as a table and narrative/lists below it, in this order):
- **PR** — the PR URL (same one written into `## Implementation` earlier; repeating it here makes the Merged record self-contained).
- **Merge commit** — SHA from the merge review-and-merge performed.
- **Merge strategy** — `squash`, `merge`, or `rebase`.
- **Base branch** — the branch merged into (from `git.baseBranch` or the PR's `baseRefName`).
- **Merged at** — ISO timestamp.
- **Review resolution** — 1-3 bullets summarizing how review feedback was handled, distilled from `REVIEW_REPORT` (e.g. "applied 4 comments, deferred 1 as follow-up, disagreed on 1").
- **Deferred follow-ups** — list of YAGNI/disagreement items and any follow-up ticket IDs created for them, distilled from `REVIEW_REPORT`.

### 8.2 Update status

`updateStatus(id, "implemented")` — marks the ticket as merged-and-code-complete. The plugin **never** transitions beyond this; release/deployment status is out of scope.

### 8.2a Update the epic

Invoke the `notion-dev:epic-update` skill via the Skill tool with args `<id>`, plus `--non-interactive` when set. Pass `REVIEW_REPORT` (Phase 7) and `$REPO_ROOT` as context.

It owns the whole epic-side record: filing deferred follow-ups as tickets under the epic, refreshing the epic's `## Tasks`, appending a dated log entry, and closing the epic when every child is resolved. Record its `EPIC-UPDATE:` output block as `EPIC_REPORT` for Phase 10.

Best-effort by construction — the skill never fails this run. A ticket with no epic is a no-op returning `EPIC-UPDATE: none`.

### 8.3 Post-merge hooks

Run `git.postMergeHooks` skills in order (empty default — no-op).

---

## Phase 9 — Clean up

Only start cleanup after confirming the merge landed: `gh pr view <pr> --json state` reports `MERGED`. **Never delete unmerged work.**

From `$REPO_ROOT`:

1. Checkout + pull the branch the PR merged into (its `baseRefName` — equals `git.baseBranch` in the simple flow): `git checkout <baseRefName> && git pull origin <baseRefName>`. Best-effort — on failure, do not stash or discard anything; continue with the remaining cleanup steps and report that the branch needs a manual checkout/pull.
2. Confirm `<worktree-path>` is the worktree this flow created (the path computed in Phase 1.2/2.1), then `git worktree remove <worktree-path>`. If it fails because of untracked leftovers (e.g. build artifacts — PLAN.md itself is already gone per 6.6), retry with `git worktree remove --force <worktree-path>`. Then `git worktree prune`.
3. `git branch -D <branch>` using the branch name recorded in 2.1 (`ticket/<project.key>-<id>-<slug>`) — do not re-spell the template here (`-D` required — squash merges aren't detected by `-d`; safe because the merge was verified above).
4. Verify the remote branch is gone (`git ls-remote --heads origin <branch>`); if not, `git push origin --delete <branch>` (swallow "already deleted" errors).
5. Remove the worktrees parent directory if now empty: `rmdir` (not `rm -rf`).

### Ledger outcome

Append one outcome line to `$REPO_ROOT/.claude/notion-dev/ledger.jsonl` per the schema in `skills/flow-triage/references/ledger.md`:

```json
{"event":"outcome","run_id":"<KEY>-<id>","ts":"<UTC now>","result":"merged","review_rounds":N,"fix_commits":N,"files_changed":N,"insertions":N,"deletions":N,"duration_minutes":N,"plan_review_findings":N,"plan_review_accepted":N,"plan_review_declined":N,"plan_review_unresolved":N}
```

Metrics come from `REVIEW_REPORT` (review rounds, fix commits) and `git show --shortstat` of the merge commit (files changed, insertions, deletions); duration from `RUN_START` to now. Plan-review metrics come from `PLAN_REVIEW_REPORT` (Phase 4.2 step (b)); all four are `null` wherever there is no review signal to record — the `feature-dev` path, which has no plan to review, a `degraded` review, where the reviewer never ran, and a resume that skipped the review. On a degraded review write `null`, **not** the zeros its output block carries: `0` findings would be indistinguishable from a review that ran and found nothing, and that is exactly the distinction this ledger exists to preserve. Any metric that cannot be determined is `null`. A ledger append failure never fails the run.

---

## Phase 10 — Report

Print a summary covering:
- Flow chosen (score/confidence/override, or the bug hard rule) and why.
- PR URL.
- Review summary — which loop ran (the configured code reviewer, Codex or Copilot, or the local fallback), rounds, applied vs. declined findings. When the local fallback ran, state prominently that no cross-model review validated the PR, and why.
- Plan-review outcome (`superpowers` path only) — status, findings, and accepted vs. declined counts from `PLAN_REVIEW_REPORT`. List any unresolved blockers the run proceeded past explicitly; a `proceed-with-warnings` run must not bury them. State `degraded` plainly when the reviewer could not run, and `skipped` when a resume bypassed the review.
- Ticket end state (`implemented`).
- Epic outcome, when the ticket had one: the epic's ID and URL, follow-ups filed (with their IDs) versus deferred, and whether the epic closed. Omit the line entirely when the ticket had no epic.
- Non-interactive decisions taken during the run, if any.
- Clean-workspace evidence (worktree removed, branch gone locally and remotely, base branch up to date).

---

## Failure and stop conditions

- 3+ consecutive verify failures with no progress → stop and report.
- > 15 files touched unplanned → stop and ask whether to continue or re-plan.
- Missing env vars or configuration → stop, never guess credentials.
- Any hard gate not passed → stop, do not proceed.
- **On any unrecoverable failure** (verify can't be made to pass, PR unmergeable, review loop stopped, unresolvable conflicts): STOP without running cleanup. Leave the worktree, branch, and PR (if one exists) intact for inspection. Report the exact remaining state (worktree path, branch name, PR number if any) and the exact commands to resume or clean up manually — including `/notion-dev:finalize <pr>` when a PR exists. Best-effort, before stopping: append a ledger outcome line with `result` `"failed"` (unrecoverable failure) or `"stopped"` (user abort) and `null` metrics — **except** the `plan_review_*` fields, which carry their real values from the plan-review output block whenever the review ran. A `blocked` exit is the single most valuable case to calibrate on, and the schema reserves `null` for *no review signal*, which is not what happened here — never let ledger bookkeeping mask the real failure report. The Notion ticket stays "In Progress" — no failure status is ever written to Notion.
