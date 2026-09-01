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

   Skipping Phase 2 also means `REVIEW_REPORT` was never produced by *this* run — but 3.3's "Review resolution" field and, critically, 3.2's `notion-dev:epic-update` invocation both depend on it: epic-update reads it as the source of deferred follow-ups, and files none of them (its `DROPPED` and `FAILED` both fall back to the **unknown** sentinel, per its step 2) if it never receives a report. Recover it, in order, once step 3 below has derived `<KEY>-<id>`: (a) read `$REPO_ROOT/.claude/notion-dev/review-report-<KEY>-<id>.md` — the file Phase 2 persists whenever it actually runs. **Split its contents at the `## Completeness` heading Phase 2 appends: everything above that heading is `REVIEW_REPORT`; everything from the heading onward, with the heading stripped, is `COMPLETENESS_REPORT`.** A file written before this change (or one whose completeness append never happened) carries no `## Completeness` heading at all, so the split degrades to exactly today's behavior — the whole file becomes `REVIEW_REPORT`, unchanged, and `COMPLETENESS_REPORT` is simply absent. That backward-compatible degradation is what makes adding the split safe. Use these when present; (b) when the file itself is absent (this recovery sub-case: the merge landed but the run died *before* Phase 2 ever wrote that file, or before it existed at all in an older run), reconstruct `REVIEW_REPORT` from the PR's review history instead of only "n/a — recovered post-merge": the review comments, threads, and replies on the PR carry both the applied/declined summary for 3.3 *and* the deferred-follow-ups list 3.2 needs — decline/defer rationale lives in the reply text on each thread, so pull it from there rather than treating the merge as evidence of nothing outstanding. There is no comparable source to reconstruct `COMPLETENESS_REPORT` from, so it stays absent on this sub-case — 3.3's criteria-ticking step is skipped precisely when `COMPLETENESS_REPORT` is absent, which already covers it. When reconstruction still yields nothing usable (no review history to read, e.g. a manually opened and merged PR), pass `REVIEW_REPORT` to 3.2 as explicitly **absent**, not as an empty report — the two mean different things to `epic-update`'s close check (see its fourth close condition). A persisted `REVIEW_REPORT` written before this change has no `ABSORBED`/`FILED`/`DROPPED` split — it carries one undifferentiated deferred list. Treat that list as `FILED`: this reproduces the old behavior exactly for in-flight work rather than silently dropping it.
3. Extract the **numeric ticket id** from the head branch name (pattern `ticket/<project.key>-<n>-*`, `<KEY>` = `project.key` from the config). This `<id>` is what every downstream `notion-dev:ticket-system` call uses.
4. Resolve the worktree path from the config's `worktree.prefix` template using that numeric `<id>`. If it's absent **and the PR is open**, recreate it (on the `MERGED` recovery path, never recreate — per step 2 — and when the worktree is absent there, skip the rest of this step including the `cd`; run Phases 3–4 from `$REPO_ROOT`):
   ```
   git fetch origin
   ```
   If a local branch `<headRefName>` exists: verify it matches `origin/<headRefName>` (fast-forward it if behind), then `git worktree add <worktree-path> <headRefName>`. If no local branch exists: `git worktree add <worktree-path> -b <headRefName> origin/<headRefName>`.
   Once the worktree is resolved (whether pre-existing or just created), if `PLAN.md` exists at its root, move it aside to `$REPO_ROOT/.claude/notion-dev/PLAN-<KEY>-<id>.md` rather than deleting it — first ensuring that self-ignored directory exists (`mkdir -p` + `.gitignore`, commands in `skills/flow-triage/references/ledger.md`; it survives worktree removal but may be absent when finalize is the first notion-dev command to run, e.g. on a manually opened PR) — the review loop's clean-tree gate requires the worktree clean, but if the interrupted run died before ticket.md 6.5 wrote the `## Implementation` section, this file is the only surviving plan record.
   `cd` into the worktree — work from there so review fixes land on the branch.
5. `fetchTicket(id)` via `notion-dev:ticket-system` — gives the ticket URL/title used in the Merged section.

   **Write the criteria file.** Write the ticket body's `## Acceptance Criteria` list — one criterion per line, verbatim, with the leading list marker stripped: `- [ ]`, `- [x]`, **or a bare `- ` bullet**. All three are reachable and stripping only the first corrupts the ticket. `refreshAcceptanceCriteria` (3.3, and `/notion-dev:ticket` Phase 8) renders `- [x]` for every `met` criterion, so any ticket a completeness gate has already run against carries ticked boxes — and this command is explicitly idempotent and accepts any PR, including a hand-authored ticket whose criteria are plain bullets. A criterion line that keeps its old marker still counts as one line, so 3.3's `CRITERIA-TOTAL` mismatch guard does not fire, and the next `refreshAcceptanceCriteria` writes back `- [ ] - [x] <criterion>` — accumulating a marker per run and silently rewriting the ticket's own definition of done, the exact failure this whole path is built to prevent. Write it to `$REPO_ROOT/.claude/notion-dev/criteria-<KEY>-<id>.md`, in the self-ignored directory the ledger, the rescued `PLAN.md`, and the persisted review report already share (`mkdir -p` plus its `.gitignore`, commands in `skills/flow-triage/references/ledger.md`). Record the path as `CRITERIA_FILE`. Runs on **both** paths — the normal review and the `MERGED` recovery — since 3.3's criteria-ticking step needs it either way.

   **Nothing is authored here.** The criteria come from Notion, which no part of this run can weaken — that is what makes them worth gating on.

   When the body has no `## Acceptance Criteria` section, or it is empty, write no file and leave `CRITERIA_FILE` unset. `/notion-dev:create-task` guards against that state, but this command accepts any ticket and must not invent a definition of done for one that has none.

---

## Phase 2 — Review and merge

Reached only when Phase 1 did **not** take the `MERGED` recovery path (that path skips this
phase entirely). Probe `jq --version` here — abort with install instructions if missing:
`winget install jqlang.jq` (or `choco install jq` / `scoop install jq`) on Windows, where it is
commonly absent; `brew install jq` / `apt install jq` otherwise.

Invoke the `notion-dev:review-and-merge` skill via the Skill tool with args:
`<pr-number>`, plus `--non-interactive` when set, plus — when `CRITERIA_FILE` is set —
`--criteria-file "<CRITERIA_FILE>"`, plus — when the target repo is a
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

Record the report's `COMPLETENESS-REPORT` section — `COMPLETENESS`, the four `CRITERIA-*` counts, `VERDICTS`, `CLAIMS`, `CAVEATS`, `TRIAGE` — as `COMPLETENESS_REPORT`, alongside `REVIEW_REPORT`. It is present regardless of whether `CRITERIA_FILE` was set — with no criteria file it reads `COMPLETENESS` as `clean`, `blocked`, or `degraded`, with `CRITERIA-TOTAL: 0`.

Persist it: write `REVIEW_REPORT` to `$REPO_ROOT/.claude/notion-dev/review-report-<KEY>-<id>.md` (`mkdir -p` + self-ignoring `.gitignore` first — same self-ignored directory the ledger and the rescued `PLAN.md` live in, per `skills/flow-triage/references/ledger.md`, so it never appears in `git status`) **as the skill returned it, unedited — it already carries its own inline `COMPLETENESS-REPORT` section, and that is not a reason to strip it out first** — then **append** `COMPLETENESS_REPORT` a second time, under a `## Completeness` heading, purely so it is separately locatable: Phase 1 step 2's recovery path reads everything at or after that heading back out as its own `COMPLETENESS_REPORT`; everything before the heading is read back as `REVIEW_REPORT` regardless of whatever completeness content it already carries inline. This is what lets a *later* recovery run of this same command find both the review report and the completeness verdicts if this run dies between Phase 2 and Phase 3 completing. Best-effort, exactly like the existing write — a failure here never fails the run.

---

## Phase 3 — Record

### 3.1 Update status

`updateStatus(id, "implemented")` — marks the ticket as merged-and-code-complete. The plugin **never** transitions beyond this; release/deployment status is out of scope.

### 3.2 Update the epic

Invoke the `notion-dev:epic-update` skill via the Skill tool with args `<id>`, plus `--non-interactive` when set. Pass `REVIEW_REPORT` (Phase 2, or — on the `MERGED` recovery path — the persisted-file/reconstructed-history recovery in Phase 1 step 2, absent when neither yielded anything usable) and `$REPO_ROOT` as context.

**Only the `FILED` list** from `REVIEW_REPORT` is passed to `epic-update`. `ABSORBED` items are already merged and `DROPPED` items are already decided; filing either would recreate the non-convergence this split exists to stop.

It owns the whole epic-side record: filing deferred follow-ups as tickets under the epic, refreshing the epic's `## Tasks`, appending a dated log entry, and closing the epic when every child is resolved. Record its `EPIC-UPDATE:` output block as `EPIC_REPORT` for Phase 5 and for 3.3 below. When `EPIC_REPORT`'s `FAILED-TO-FILE` bucket is non-empty, or either `DROPPED` or `FAILED-TO-FILE` carries `epic-update`'s `unknown` sentinel, record `partial:epic-update` per `notion-dev:issue-log`. Never merely because `DROPPED` holds concrete items — per `epic-update/SKILL.md`, a `DROPPED` item there is a user decision (the interactive gate offered File/Drop and the user chose Drop, with a rationale), the routine kind of interaction this log must never record. `unknown` means the invocation had no `REVIEW_REPORT` to assert either bucket from and is the real quiet degradation this signature exists to catch; a future edit must not simplify this back to a bare non-empty-`DROPPED`-or-`FAILED-TO-FILE` check, which is exactly the bug being fixed here.

On the `MERGED` recovery path (Phase 1 step 2), `epic-update` returning `EPIC-UPDATE: already-recorded` is the idempotency check working correctly — **not** a partial update, and it is never logged.

Best-effort by construction — the skill never fails this run. A ticket with no epic is a no-op returning `EPIC-UPDATE: none`.

### 3.3 Update ticket

**Update the Completeness record.** Skip this whole subsection only when `COMPLETENESS_REPORT` is absent — with no report there is nothing to record. **An unset `CRITERIA_FILE` is not that case.** The gate still runs its claim and caveat charges without a criteria file and reports `CRITERIA-TOTAL: 0` (see `notion-dev:review-and-merge`'s `## Input`), so `CLAIMS` / `CAVEATS` / `TRIAGE` can carry real findings for a ticket that simply stated no acceptance criteria. Skipping on `CRITERIA_FILE` alone would drop them from the ticket's only durable record.

Otherwise, `appendToSection(id, "Implementation", …)` with a **Completeness** block — never `upsertSection`: `/notion-dev:ticket` Phase 6.5 wrote `## Implementation` before the merge, and a replacing write here would clobber its Plan / Implementation / Files Changed / PR / Branch / Plan review / Notes fields; this append is the only addition made to it. Three cases:

- **`CRITERIA_FILE` was unset** (the ticket has no `## Acceptance Criteria` section): there are no boxes, so do **not** call `refreshAcceptanceCriteria` — there is nothing to tick and ticking nothing is not a verdict. Append the block only when at least one of `CLAIMS` / `CAVEATS` / `TRIAGE` is not `NONE`, carrying those entries and stating that this ticket declared no acceptance criteria, so `CRITERIA-TOTAL: 0` is a fact about the ticket rather than a verdict about the work. When all three are `NONE`, write nothing: an empty record is noise, not evidence.
- **`COMPLETENESS_REPORT` is absent, or its `CRITERIA-TOTAL` does not equal `CRITERIA_FILE`'s line count** (the gate's `VERDICTS` no longer line up one-to-one with today's criteria — the case the `MERGED` recovery path can hit, since Phase 1 step 2 may recover `COMPLETENESS_REPORT` from an earlier run's persisted file while step 5 wrote `CRITERIA_FILE` fresh from today's Notion body): the Completeness block states plainly that verdicts were unavailable this run — and why (report absent, or a criteria/verdict count mismatch) — and that the unticked boxes are **not** a verdict. Do **not** call `refreshAcceptanceCriteria` in this case: leave every box exactly as it already reads — ticking one now could pair a stale verdict with the wrong criterion, silently rewriting a box's meaning, which is exactly what taking criterion text from `CRITERIA_FILE` rather than the verdict's echo exists to prevent.
- **Otherwise** (`COMPLETENESS_REPORT` present and its `CRITERIA-TOTAL` matches `CRITERIA_FILE`'s line count): from `COMPLETENESS_REPORT`'s `VERDICTS` block, build `verdicts` — one entry per criteria-file line, in file order, `{ criterion, verdict }` — and call `refreshAcceptanceCriteria(id, verdicts)` via `notion-dev:ticket-system`. Take each `criterion` from `CRITERIA_FILE`, **not** from the verdict line's echo of it: the file is the verbatim copy fetched from Notion, and a paraphrase written back would silently rewrite the ticket's own definition of done. The Completeness block records each criterion, its verdict (`met` / `not-met` / `unverified`), the gate's resolved citation, and — for any criterion escaped to `file` or `drop` — its label and rationale from `COMPLETENESS_REPORT`'s `TRIAGE`.

For an acceptance criterion, `file` and `drop` are **scope reductions**, not deferrals of extra work — which is why they land on the ticket rather than only in the PR. Someone tracking this work must be able to see that its stated definition of done shrank.

Append a separate `## Merged` section — do **not** replace the `## Implementation` section written by `/notion-dev:ticket` (the Completeness block appended above is the only addition made to it); the two are meant to coexist as a chronological record. This step runs **after** 3.2 deliberately: the "Deferred follow-ups" field below names actual follow-up ticket IDs, which do not exist until `epic-update` (3.2) files them. An earlier revision of this command wrote this section first and left that field promising links to tickets that were created only afterward, with nothing to ever backfill them — reordering closes that gap by writing the record once, after the data it needs exists.

Invoke `notion-dev:ticket-system`, `upsertSection(id, "Merged", { ... })` with these fields (order matters — the Notion adapter renders scalars as a table and narrative/lists below it, in this order):
- **PR** — the PR URL (same one written into `## Implementation` earlier; repeating it here makes the Merged record self-contained).
- **Merge commit** — the merge SHA: from the merge `review-and-merge` performed, or, on the `MERGED` recovery path, from `gh pr view <pr> --json mergeCommit` (Phase 1 step 2), where the review loop never ran.
- **Merge strategy** — `squash`, `merge`, or `rebase`.
- **Base branch** — the branch merged into (from `git.baseBranch` or the PR's `baseRefName`).
- **Merged at** — ISO timestamp.
- **Review resolution** — 1-3 bullets summarizing how review feedback was handled, distilled from `REVIEW_REPORT` (e.g. "applied 4 comments, absorbed 2 findings, filed 1 follow-up, disagreed on 1").
- **Absorbed** — items from `REVIEW_REPORT`'s `ABSORBED` list, each with what was changed. Omit the field when the list is empty. These needed no ticket because the work is in this PR.
- **Deferred follow-ups** — items from `REVIEW_REPORT`'s `FILED` list, each with its blast-radius criterion number and its actual follow-up ticket ID/URL from `EPIC_REPORT`'s `FILED` ∪ `ALREADY_FILED` (both now known, since 3.2 already ran). `epic-update` remains best-effort: when `EPIC_REPORT` is `EPIC-UPDATE: none`, or a given item isn't in either list (e.g. `epic-update` failed partway, or the item is in `DROPPED` or `FAILED-TO-FILE`), list that item with no ID rather than inventing one — this section is still written with whatever is known, never blocked on 3.2's outcome.
- **Dropped** — items from `REVIEW_REPORT`'s `DROPPED` list, each with its rationale. Omit the field when the list is empty. A recorded drop is a decision, not an omission.

---

## Phase 4 — Clean up

Only start cleanup after confirming the merge landed: `gh pr view <pr> --json state` reports `MERGED`. **Never delete unmerged work.**

From `$REPO_ROOT` — `cd $REPO_ROOT` first if the run is still inside the worktree, since step 1 removes it out from under the current directory. **The worktree goes first and the primary checkout's `checkout` goes last** — nothing in worktree removal or branch deletion needs the primary to be on the base branch, and doing the primary's checkout while a worktree may still be sitting on that branch is what produced `fatal: '<baseRefName>' is already used by worktree at '<primary>'`. Every step below stays independently skippable, which is what the `MERGED` recovery path (where the worktree may already be absent, and the remote branch already deleted) depends on:

1. If `<worktree-path>` is a registered worktree (`git worktree list` contains it — on the post-merge recovery path Phase 1 deliberately does not recreate a missing one, and a prior interrupted run may have already removed it), confirm it is the worktree resolved/created in Phase 1, then `git worktree remove <worktree-path>`. If it fails because of untracked leftovers (e.g. build artifacts), retry with `git worktree remove --force <worktree-path>`. Then `git worktree prune`. Absent → skip; only bookkeeping remains.
2. `git branch -D <headRefName>` using the branch name recorded in Phase 1 (`<slug>` is never defined in this command — use the actual `headRefName`) (`-D` required — squash merges aren't detected by `-d`; safe because the merge was verified above; skip silently when the local branch no longer exists). If it fails because `<headRefName>` is checked out in the primary checkout — reachable on the recovery path, where no worktree was holding it — run step 4 first and retry this step after it.
3. Verify the remote branch is gone, **in the repository that owns it**. Resolve that first — `gh pr view <pr> --json headRepositoryOwner,headRepository,headRefName` — because this command takes an arbitrary PR number and can therefore be handed a fork PR, where the head branch lives in the fork and `origin` is the base repository. When the head repository **is** `origin`, `git ls-remote --heads origin <headRefName>` and, if it is still there, `git push origin --delete <headRefName>` (swallow "already deleted" errors). When it is **not**, check the fork the same way before deleting: `gh api "repos/<headOwner>/<headRepo>/git/ref/heads/<head-branch-encoded>"` — note the singular `ref` for a single-reference lookup — where a `404` means it is already gone and this step is done. Only if it is still there, `gh api --method DELETE "repos/<headOwner>/<headRepo>/git/refs/heads/<head-branch-encoded>"` (plural `refs` on the delete), with the same percent-encoding rule the skill documents. Swallow a `422 Reference does not exist` on that delete exactly as the `origin` path swallows "already deleted" — it means the ref went away between the check and the call. Both halves matter: on the normal path `notion-dev:review-and-merge` has already deleted the branch, so a delete issued without the check ahead of it would fail on every fork PR that came through the skill, which is the common case rather than the exotic one. Treat a `403` as the expected outcome rather than a failure — the branch is the contributor's to delete. Never delete from `origin` on the strength of a name match alone: the base repository can carry an unrelated branch of the same name, and deleting *that* is the failure this step exists to avoid. `notion-dev:review-and-merge` deletes the remote branch itself as its own command after the merge, so on the normal path this is a no-op confirmation; on the `MERGED` recovery path it is the step that actually does it.
4. Checkout + pull the branch the PR merged into (its `baseRefName` — equals `git.baseBranch` in the simple flow): `git checkout <baseRefName> && git pull --ff-only origin <baseRefName>`. **`--ff-only` is required, not stylistic**: a primary whose base branch carries local-only commits has diverged, and a default `pull` would silently manufacture a merge commit to reconcile it — the exact unintended merge commit this whole ordering exists to prevent. `--ff-only` aborts instead, which is what "do not stash or discard anything" means for a diverged branch. Best-effort — on failure, do not stash or discard anything; continue with the remaining cleanup steps and report that the branch needs a manual checkout/pull.
5. Remove the worktrees parent directory if now empty: `rmdir "$(dirname <worktree-path>)"` — derived from the path Phase 1 resolved, so the target is checkable without introducing a second name for it. `rmdir`, never `rm -rf`: it refuses on a non-empty directory, which is the whole safety property here.

### Post-merge hooks

Run `git.postMergeHooks` skills in order (empty default — no-op). These run **after** cleanup, not before it: a hook such as `knowledge-capture` commits and pushes from the primary checkout, and only here is the primary guaranteed to be on a freshly pulled `<baseRefName>` containing the merge commit the hook reads. Running them earlier meant committing and pushing to whatever branch the primary happened to be on — and this command in particular can be invoked from inside the worktree, so the primary's branch was never asserted at all.

Assert that before invoking anything:

```bash
git -C $REPO_ROOT rev-parse --abbrev-ref HEAD                    # must equal <baseRefName>
git -C $REPO_ROOT merge-base --is-ancestor <merge-commit> HEAD   # must exit 0
test "$(git -C $REPO_ROOT rev-parse HEAD)" = \
     "$(git -C $REPO_ROOT rev-parse origin/<baseRefName>)"       # must be equal
```

**All three lines, and each catches something the others do not.** Step 4 chains `checkout && pull`, so a `checkout` that succeeds and a `pull` that then fails (network, a dirty primary) leaves HEAD on the right branch but *behind* — a name-only assertion passes on that stale checkout, handing the hook exactly the state this ordering promised to prevent. Line 2 makes "contains the merge" checkable: `<merge-commit>` is the merge SHA this run already records — from `review-and-merge` on the normal path, or from `gh pr view <pr> --json mergeCommit` on the `MERGED` recovery path, where Phase 2 never ran and there is no skill return value to take it from — and its being an ancestor of HEAD proves the merge is present whatever the pull did — including when the local `origin/<baseRefName>` ref is itself stale, which is why line 3 does not replace it.

Line 3 is what makes it *only* the merge. A primary carrying local-only commits satisfies both earlier lines — the branch name is right and the merge commit is an ancestor — while HEAD also holds commits that were never pushed and never reviewed. A hook is free to commit and push — the contract constrains *when* hooks run, not what they do, and `knowledge-capture`, the consumer-repo hook that motivated this ordering, does exactly that — so a hook running on a diverged primary publishes that unreviewed local work to the base branch as a side effect of a ticket run. Requiring HEAD to equal `origin/<baseRefName>` exactly rejects divergence rather than reconciling it, which is also why step 4 pulls `--ff-only`.

If **any** assertion fails, **skip the hook step entirely** and report that hooks were skipped, which assertion failed, the branch and HEAD the primary was found on, and that they need a manual re-run after a successful checkout and fast-forward pull. Never run a configured hook on an unasserted branch: the ordering makes the right state overwhelmingly likely, and these assertions make it certain.

The cost of this ordering is stated deliberately: by the time hooks run, the worktree is gone, so a hook cannot inspect the branch's working tree. That is consistent with the documented hook contract — `git.postMergeHooks` is specified as "skills invoked after merging", the merge is a squash by default so the branch's tree is not the merged tree anyway, and on the `MERGED` recovery path the worktree is frequently absent before this command even starts. A hook needing the pre-merge working tree must read it from git history instead.

### Ledger outcome

Append one outcome line to `$REPO_ROOT/.claude/notion-dev/ledger.jsonl` per the schema in `skills/flow-triage/references/ledger.md`:

```json
{"event":"outcome","run_id":"<KEY>-<id>","ts":"<UTC now>","result":"merged","review_rounds":N,"fix_commits":N,"files_changed":N,"insertions":N,"deletions":N,"duration_minutes":N,"triage_absorbed":N,"triage_filed":N,"triage_dropped":N,"triage_reclassified":N,"completeness_criteria":N,"completeness_met":N,"completeness_unverified":N,"completeness_items":N}
```

Metrics come from `REVIEW_REPORT` (review rounds, fix commits) and `git show --shortstat` of the merge commit (files changed, insertions, deletions); duration from `RUN_START` to now. The four `triage_*` counts come from `REVIEW_REPORT`'s `ABSORBED` / `FILED` / `DROPPED` lists, with `triage_reclassified` counting the `FILED` entries marked as reclassified from `absorb`. Write `null` for all four — never `0` — when no review produced a triage. The four `completeness_*` counts come from `COMPLETENESS_REPORT`'s `CRITERIA-TOTAL` / `CRITERIA-MET` / `CRITERIA-UNVERIFIED` keys, with `completeness_items` counting its `TRIAGE` entries. Write `null` for all four — never `0` — when no completeness check ran: no criteria file and no changed prose, or a run that stopped before the gate. That is distinct from `CRITERIA-TOTAL: 0`, which `COMPLETENESS_REPORT` carries whenever the gate ran its claim and caveat charges but had no criteria file to check — a check that ran and found nothing, not one that never ran; that `0` belongs in `completeness_criteria` as a real `0`. Any metric that cannot be determined is `null`. A ledger append failure never fails the run.

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
- Post-merge hooks: which ran, or — when a Phase 4 hook assertion failed — that they were **skipped**, the branch the primary was actually on, and that they need a manual re-run. Omit the line entirely when `git.postMergeHooks` is empty.
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`. Omit the line entirely when the run logged nothing.
- **Completeness** — say nothing when `CRITERIA_FILE` was unset (the ticket had no criteria to check). Otherwise: when `COMPLETENESS_REPORT` was absent or its `CRITERIA-TOTAL` didn't match `CRITERIA_FILE`'s line count, state that explicitly — the completeness gate produced no usable verdict for this record, and the unticked boxes are not a verdict — rather than saying nothing; an unchecked run and a clean `met` result must never render the same. Otherwise, when any criterion is not `met`: "<n> of <m> acceptance criteria were not met at the completeness gate" — `<n>` counts `not-met` criteria only — then each with its verdict, triage label, and rationale. State `CRITERIA-UNVERIFIED` separately whenever it is non-zero, as a third state never folded into `<n>`: `unverified` means the gate could not check, which is not the same as finding the work undone. Say nothing only when every criterion is `met`.

When `triage_reclassified` is greater than zero, state it in the report: "<n> of <m> `absorb` items were reclassified to `file` at the merge gate (criteria <list>)". This is worth surfacing every time it happens — an `absorb` item became a `file` item only because a criterion turned out true that the earlier triage missed, and a run doing that repeatedly is the signal the blast-radius test is miscalibrated. Say nothing when the count is zero.

---

## Failure and stop conditions

- Verify suite fails after retries at any point (surfaced via the review loop) → stop; do not merge.
- Pre-merge check fails → stop; report which check and why.
- Merge conflict the user needs to resolve → hand control back with clear instructions.
- MCP / CLI unavailable for merge → fall back to `gh`; if that also fails, stop.
- **On any unrecoverable failure**: STOP without running cleanup. Leave the worktree, branch, and PR intact for inspection. Report the exact remaining state (worktree path, branch name, PR number) and the exact commands to resume or clean up manually. Best-effort, before stopping: append a ledger outcome line with `result` `"failed"` (unrecoverable failure) or `"stopped"` (user abort) and `null` metrics — never let ledger bookkeeping mask the real failure report. Also best-effort, before stopping: run the issue-log sweep from Phase 4 — this path skips Phase 4 entirely, and an unrecoverable failure is the single most valuable thing this log can record. A failure to write it never masks the real failure report. The Notion ticket stays "In Progress" — no failure status is ever written to Notion.
