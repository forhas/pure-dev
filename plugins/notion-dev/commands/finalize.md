---
description: Drive an already-open ticket PR to merged — review loop (configured code reviewer or local fallback), merge, ticket record, cleanup. Standalone entry point for resuming after /notion-dev:ticket was interrupted.
argument-hint: "[<pr-number>] [--non-interactive]"
disable-model-invocation: true
---

# /notion-dev:finalize

Standalone entry point that drives an already-open ticket PR to merged: resolve → review & merge → record → clean up.

Args: `<pr-number> [--non-interactive]` (`<pr-number>` optional — inferred from the current branch's open PR if omitted).

Flag parsing: if the arguments contain `--non-interactive`, remove it and set **non-interactive mode**: never pause for user input; whenever any step calls for asking the user, self-answer with the most reasonable option and log the decision for the final report (Phase 5). Whatever remains is the `<pr-number>` (or empty, for the current-branch inference path).

**Standing rule — runtime issues.** Anything unexpected at runtime — for example an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, or a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens, not batched to the end of the run. That skill is **authoritative** for the full trigger list, the entry format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must **not** be logged; the examples here are illustrative, not exhaustive. The rule applies to conditions nobody enumerated in advance. A failure to write the log never fails the run.

## Preconditions

- **GitHub access**: authenticated `gh` CLI is **required** — the Phase 2 review loop (`notion-dev:review-and-merge`) depends on `gh` for paginated comment reads and GraphQL review-thread resolution, which the GitHub MCP cannot perform. Probe `gh auth status` at the top of the command; abort with "Install and authenticate `gh` (`gh auth login`), then re-run" if unavailable. The GitHub MCP (`mcp__github__get_pull_request` etc.) is optional: when present, prefer it for the operations it supports (metadata reads, merge) and fall back to `gh` when it fails or is absent.
- **`jq` on `PATH` is required for Phase 2** — the review loop invoked there parses `gh api` JSON responses with it throughout; `gh api`'s own `--jq` flag does not substitute for the standalone binary. **Not** a top-of-command gate and **not** required on the `MERGED` post-merge-recovery path above, which skips Phase 2 entirely — probing it here would block exactly the recovery this gate exists to keep working, on the platform (Windows) this dependency is least likely to already have. Probed instead at the start of Phase 2, immediately before invoking `notion-dev:review-and-merge`.
- **Superpowers (required)**: confirm `superpowers:receiving-code-review` is available — the Phase 2 review loop evaluates every finding with it. If missing, abort before any Phase 1 side effects: "workflow requires the `superpowers` plugin — run `/notion-dev:init`". (feature-dev is not needed here; finalize runs no build flow.)
- Record `REPO_ROOT` **first**, before loading config or invoking any skill: the first path listed by `git worktree list` — the **primary checkout** root, never a worktree path. (Correct from anywhere: `finalize` is most commonly invoked with no args from inside the ticket worktree itself, where `git rev-parse --show-toplevel` would wrongly return the worktree root.)
- `.claude/notion-dev.config.json` exists; load it. If missing, abort and tell the user to run `/notion-dev:init`. As in `/notion-dev:ticket`, all config reads resolve against the **primary checkout** (`$REPO_ROOT/.claude/notion-dev.config.json`), never a worktree — the worktree may lack the config when it is uncommitted, unpushed, or gitignored.
- A PR exists for the work: **open** when `<pr-number>` was omitted (the no-arg path infers it from the current branch, and there is nothing to infer otherwise); with an explicit `<pr-number>`, `MERGED` is also acceptable — that is Phase 1's post-merge recovery path, which this gate must not block. `CLOSED`-without-merge or draft still aborts (Phase 1 step 2).
- The PR's head branch follows the `ticket/<project.key>-<n>-*` convention, so the numeric ticket id is recoverable from it. (PRs opened by `/notion-dev:ticket` always do.)

---

## Phase 1 — Resolve

Before anything else — record `RUN_START` = `date -u +%FT%TZ`. (`REPO_ROOT` was already recorded at the preconditions gate, before the first config read.)

These anchors, taken before any worktree resolution or `cd` below, keep Phase 4's cleanup and the ledger write pinned to the primary checkout even after this command `cd`s into a worktree (mirrors ticket.md's pattern).

Work PR-first — the PR number is the entry point, and the ticket id is derived from it:

1. Determine the PR: use the `<pr-number>` arg. If omitted, infer the open PR for the current branch (`gh pr view --json number` / list PRs for the branch). Derive `owner/repo` from `git remote get-url origin`.
2. Fetch PR metadata via `mcp__github__get_pull_request` (fallback: `gh pr view --json number,url,headRefName,baseRefName,reviews,state,isDraft`). State must be open and not draft — with one exception. **`MERGED` = post-merge recovery**: a prior run merged but was interrupted before record/cleanup. In that case skip Phase 2 (the review loop) entirely and continue at Phase 3 with the merge commit from `gh pr view <pr> --json mergeCommit` and "Review resolution" distilled from the PR's review history (or "n/a — recovered post-merge"); Phases 3–4 are idempotent — this includes 3.2's `notion-dev:epic-update` invocation, which detects an already-recorded resolution via its own idempotency check and returns `EPIC-UPDATE: already-recorded` rather than re-filing follow-up tickets or duplicating the Resolution Log entry, so re-invoking it here on recovery is safe and must not be special-cased or skipped — and step 4 below does **not** recreate a missing worktree on this path (nothing to fix on the branch — an absent worktree just means less to clean; the remote branch is typically already deleted, so recreation would fail anyway). `CLOSED`-without-merge or draft: stop and report.

   Skipping Phase 2 also means `REVIEW_REPORT` was never produced by *this* run — but 3.3's "Review resolution" field and, critically, 3.2's `notion-dev:epic-update` invocation both depend on it: epic-update reads it as the source of deferred follow-ups, and files none of them (its `SKIPPED` and `FAILED` both fall back to the **unknown** sentinel, per its step 2) if it never receives a report. Recover it, in order, once step 3 below has derived `<KEY>-<id>`: (a) read `$REPO_ROOT/.claude/notion-dev/review-report-<KEY>-<id>.md` — the file Phase 2 persists whenever it actually runs — and use its contents as `REVIEW_REPORT` when present; (b) when absent (this recovery sub-case: the merge landed but the run died *before* Phase 2 ever wrote that file, or before it existed at all in an older run), reconstruct `REVIEW_REPORT` from the PR's review history instead of only "n/a — recovered post-merge": the review comments, threads, and replies on the PR carry both the applied/declined summary for 3.3 *and* the deferred-follow-ups list 3.2 needs — decline/defer rationale lives in the reply text on each thread, so pull it from there rather than treating the merge as evidence of nothing outstanding. When reconstruction still yields nothing usable (no review history to read, e.g. a manually opened and merged PR), pass `REVIEW_REPORT` to 3.2 as explicitly **absent**, not as an empty report — the two mean different things to `epic-update`'s close check (see its fifth close condition). A persisted `REVIEW_REPORT` written before this change has no `ABSORBED`/`FILED`/`DROPPED` split — it carries one undifferentiated deferred list. Treat that list as `FILED`: this reproduces the old behavior exactly for in-flight work rather than silently dropping it.
3. Extract the **numeric ticket id** from the head branch name (pattern `ticket/<project.key>-<n>-*`, `<KEY>` = `project.key` from the config). This `<id>` is what every downstream `notion-dev:ticket-system` call uses.
4. Resolve the worktree path from the config's `worktree.prefix` template using that numeric `<id>`. If it's absent **and the PR is open**, recreate it (on the `MERGED` recovery path, never recreate — per step 2 — and when the worktree is absent there, skip the rest of this step including the `cd`; run Phases 3–4 from `$REPO_ROOT`):
   ```
   git fetch origin
   ```
   If a local branch `<headRefName>` exists: verify it matches `origin/<headRefName>` (fast-forward it if behind), then `git worktree add <worktree-path> <headRefName>`. If no local branch exists: `git worktree add <worktree-path> -b <headRefName> origin/<headRefName>`.
   Once the worktree is resolved (whether pre-existing or just created), if `PLAN.md` exists at its root, move it aside to `$REPO_ROOT/.claude/notion-dev/PLAN-<KEY>-<id>.md` rather than deleting it — first ensuring that self-ignored directory exists (`mkdir -p` + `.gitignore`, commands in `skills/flow-triage/references/ledger.md`; it survives worktree removal but may be absent when finalize is the first notion-dev command to run, e.g. on a manually opened PR) — the review loop's clean-tree gate requires the worktree clean, but if the interrupted run died before ticket.md 6.5 wrote the `## Implementation` section, this file is the only surviving plan record.
   `cd` into the worktree — work from there so review fixes land on the branch.
5. `fetchTicket(id)` via `notion-dev:ticket-system` — gives the ticket URL/title used in the Merged section.

---

## Phase 2 — Review and merge

Reached only when Phase 1 did **not** take the `MERGED` recovery path (that path skips this
phase entirely). Probe `jq --version` here — abort with install instructions if missing:
`winget install jqlang.jq` (or `choco install jq` / `scoop install jq`) on Windows, where it is
commonly absent; `brew install jq` / `apt install jq` otherwise.

Invoke the `notion-dev:review-and-merge` skill via the Skill tool with args:
`<pr-number>`, plus `--non-interactive` when set, plus — when the target repo is a
plugin (`.claude-plugin/plugin.json` exists in the worktree) — the stale-bump guard:
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
report (which loop ran, rounds, applied vs. declined) as `REVIEW_REPORT`. When that report
shows the local fallback ran because the configured reviewer was unavailable, record
`fallback:local-code-review` per `notion-dev:issue-log`.

Persist it: write `REVIEW_REPORT` to `$REPO_ROOT/.claude/notion-dev/review-report-<KEY>-<id>.md` (`mkdir -p` + self-ignoring `.gitignore` first — same self-ignored directory the ledger and the rescued `PLAN.md` live in, per `skills/flow-triage/references/ledger.md`, so it never appears in `git status`). This is what lets a *later* recovery run of this same command find the report if this run dies between Phase 2 and Phase 3 completing. Best-effort — a write failure here must not fail the run.

---

## Phase 3 — Record

### 3.1 Update status

`updateStatus(id, "implemented")` — marks the ticket as merged-and-code-complete. The plugin **never** transitions beyond this; release/deployment status is out of scope.

### 3.2 Update the epic

Invoke the `notion-dev:epic-update` skill via the Skill tool with args `<id>`, plus `--non-interactive` when set. Pass `REVIEW_REPORT` (Phase 2, or — on the `MERGED` recovery path — the persisted-file/reconstructed-history recovery in Phase 1 step 2, absent when neither yielded anything usable) and `$REPO_ROOT` as context.

**Only the `FILED` list** from `REVIEW_REPORT` is passed to `epic-update`. `ABSORBED` items are already merged and `DROPPED` items are already decided; filing either would recreate the non-convergence this split exists to stop.

It owns the whole epic-side record: filing deferred follow-ups as tickets under the epic, refreshing the epic's `## Tasks`, appending a dated log entry, and closing the epic when every child is resolved. Record its `EPIC-UPDATE:` output block as `EPIC_REPORT` for Phase 5 and for 3.3 below. When `EPIC_REPORT`'s `FAILED-TO-FILE` bucket is non-empty, or either `SKIPPED` or `FAILED-TO-FILE` carries `epic-update`'s `unknown` sentinel, record `partial:epic-update` per `notion-dev:issue-log`. Never merely because `SKIPPED` holds concrete items — per `epic-update/SKILL.md`, a `SKIPPED` item there is a user decision (the interactive gate offered File/Skip and the user chose Skip), the routine kind of interaction this log must never record. `unknown` means the invocation had no `REVIEW_REPORT` to assert either bucket from and is the real quiet degradation this signature exists to catch; a future edit must not simplify this back to a bare non-empty-`SKIPPED`-or-`FAILED-TO-FILE` check, which is exactly the bug being fixed here.

On the `MERGED` recovery path (Phase 1 step 2), `epic-update` returning `EPIC-UPDATE: already-recorded` is the idempotency check working correctly — **not** a partial update, and it is never logged.

Best-effort by construction — the skill never fails this run. A ticket with no epic is a no-op returning `EPIC-UPDATE: none`.

### 3.3 Update ticket

Append a separate `## Merged` section — do **not** touch the `## Implementation` section written by `/notion-dev:ticket`; the two are meant to coexist as a chronological record. This step runs **after** 3.2 deliberately: the "Deferred follow-ups" field below names actual follow-up ticket IDs, which do not exist until `epic-update` (3.2) files them. An earlier revision of this command wrote this section first and left that field promising links to tickets that were created only afterward, with nothing to ever backfill them — reordering closes that gap by writing the record once, after the data it needs exists.

Invoke `notion-dev:ticket-system`, `upsertSection(id, "Merged", { ... })` with these fields (order matters — the Notion adapter renders scalars as a table and narrative/lists below it, in this order):
- **PR** — the PR URL (same one written into `## Implementation` earlier; repeating it here makes the Merged record self-contained).
- **Merge commit** — SHA from the merge review-and-merge performed.
- **Merge strategy** — `squash`, `merge`, or `rebase`.
- **Base branch** — the branch merged into (from `git.baseBranch` or the PR's `baseRefName`).
- **Merged at** — ISO timestamp.
- **Review resolution** — 1-3 bullets summarizing how review feedback was handled, distilled from `REVIEW_REPORT` (e.g. "applied 4 comments, absorbed 2 findings, filed 1 follow-up, disagreed on 1").
- **Absorbed** — items from `REVIEW_REPORT`'s `ABSORBED` list, each with what was changed. Omit the field when the list is empty. These needed no ticket because the work is in this PR.
- **Deferred follow-ups** — items from `REVIEW_REPORT`'s `FILED` list, each with its blast-radius criterion number and its actual follow-up ticket ID/URL from `EPIC_REPORT`'s `FILED` ∪ `ALREADY_FILED` (both now known, since 3.2 already ran). `epic-update` remains best-effort: when `EPIC_REPORT` is `EPIC-UPDATE: none`, or a given item isn't in either list (e.g. `epic-update` failed partway, or the item is in `DROPPED` or `FAILED-TO-FILE`), list that item with no ID rather than inventing one — this section is still written with whatever is known, never blocked on 3.2's outcome.
- **Dropped** — items from `REVIEW_REPORT`'s `DROPPED` list, each with its rationale. Omit the field when the list is empty. A recorded drop is a decision, not an omission.

### 3.4 Post-merge hooks

Run `git.postMergeHooks` skills in order (empty default — no-op).

---

## Phase 4 — Clean up

Only start cleanup after confirming the merge landed: `gh pr view <pr> --json state` reports `MERGED`. **Never delete unmerged work.**

From `$REPO_ROOT`:

1. Checkout + pull the branch the PR merged into (its `baseRefName` — equals `git.baseBranch` in the simple flow): `git checkout <baseRefName> && git pull origin <baseRefName>`. Best-effort — on failure, do not stash or discard anything; continue with the remaining cleanup steps and report that the branch needs a manual checkout/pull.
2. If `<worktree-path>` is a registered worktree (`git worktree list` contains it — on the post-merge recovery path Phase 1 deliberately does not recreate a missing one, and a prior interrupted run may have already removed it), confirm it is the worktree resolved/created in Phase 1, then `git worktree remove <worktree-path>`. If it fails because of untracked leftovers (e.g. build artifacts), retry with `git worktree remove --force <worktree-path>`. Then `git worktree prune`. Absent → skip; only bookkeeping remains.
3. `git branch -D <headRefName>` using the branch name recorded in Phase 1 (`<slug>` is never defined in this command — use the actual `headRefName`) (`-D` required — squash merges aren't detected by `-d`; safe because the merge was verified above; skip silently when the local branch no longer exists).
4. Verify the remote branch is gone (`git ls-remote --heads origin <headRefName>`); if not, `git push origin --delete <headRefName>` (swallow "already deleted" errors).
5. Remove the worktrees parent directory if now empty: `rmdir` (not `rm -rf`).

### Ledger outcome

Append one outcome line to `$REPO_ROOT/.claude/notion-dev/ledger.jsonl` per the schema in `skills/flow-triage/references/ledger.md`:

```json
{"event":"outcome","run_id":"<KEY>-<id>","ts":"<UTC now>","result":"merged","review_rounds":N,"fix_commits":N,"files_changed":N,"insertions":N,"deletions":N,"duration_minutes":N}
```

Metrics come from `REVIEW_REPORT` (review rounds, fix commits) and `git show --shortstat` of the merge commit (files changed, insertions, deletions); duration from `RUN_START` to now. Any metric that cannot be determined is `null`. A ledger append failure never fails the run.

**Issue-log sweep.** Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`. Best-effort — a failure here never fails the run.

---

## Phase 5 — Report

Print a summary covering:
- Flow: `n/a — finalize entry point`, unless the ledger has a recorded `flow_chosen` for this `run_id`, in which case report that value instead.
- PR URL.
- Review summary — which loop ran (the configured code reviewer, Codex or Copilot, or the local fallback), rounds, applied vs. declined findings. When the local fallback ran, state prominently that no cross-model review validated the PR, and why.
- Ticket end state (`implemented`).
- Epic outcome, when the ticket had one: the epic's ID and URL, follow-ups absorbed, filed (with their IDs), and dropped, and whether the epic closed. Omit the line entirely when the ticket had no epic.
- Non-interactive decisions taken during the run, if any.
- Clean-workspace evidence (worktree removed, branch gone locally and remotely, base branch up to date).
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`. Omit the line entirely when the run logged nothing.

---

## Failure and stop conditions

- Verify suite fails after retries at any point (surfaced via the review loop) → stop; do not merge.
- Pre-merge check fails → stop; report which check and why.
- Merge conflict the user needs to resolve → hand control back with clear instructions.
- MCP / CLI unavailable for merge → fall back to `gh`; if that also fails, stop.
- **On any unrecoverable failure**: STOP without running cleanup. Leave the worktree, branch, and PR intact for inspection. Report the exact remaining state (worktree path, branch name, PR number) and the exact commands to resume or clean up manually. Best-effort, before stopping: append a ledger outcome line with `result` `"failed"` (unrecoverable failure) or `"stopped"` (user abort) and `null` metrics — never let ledger bookkeeping mask the real failure report. Also best-effort, before stopping: run the issue-log sweep from Phase 4 — this path skips Phase 4 entirely, and an unrecoverable failure is the single most valuable thing this log can record. A failure to write it never masks the real failure report. The Notion ticket stays "In Progress" — no failure status is ever written to Notion.
