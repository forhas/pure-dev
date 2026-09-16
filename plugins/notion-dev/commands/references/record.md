# /notion-dev:ticket — the record unit (Phases 8-10)

Read by the agent dispatched from `../ticket.md` Phase 8, or by the orchestrator
itself on the inline-recovery path when that dispatch fails.

The caller has already resolved the interactive filing gate (`FILING_DECISIONS`),
taken the primary lock (`LOCK_HELD: true`), and left the worktree (`cd $REPO_ROOT`).
Do not take the lock again, do not ask the user anything, and do not release the
lock — the caller does that after this unit returns.

### 8.1 Update status

`updateStatus(id, "implemented")` — marks the ticket as merged-and-code-complete. The plugin **never** transitions beyond this; release/deployment status is out of scope.

The invocations below pass `LOCK_HELD` so none of them takes it again.

Invoke the `notion-dev:epic-update` skill via the Skill tool with args `<id>`, plus `--non-interactive` when set. Pass `REVIEW_REPORT` (Phase 7), `$REPO_ROOT` and `LOCK_HELD` as context. Pass **only the `FILED` list** from `REVIEW_REPORT` (Phase 7 states the contract in full). `ABSORBED` items are already merged, `DROPPED` items are already decided, and `BLOCKED` items are externally impossible for anyone — filing any of them recreates the unbounded ticket growth this split exists to stop.

It owns the whole epic-side record: filing deferred follow-ups as tickets under the epic, refreshing the epic's `## Tasks`, appending a dated log entry, and closing the epic when every child is resolved. Record its `EPIC-UPDATE:` output block as `EPIC_REPORT` for Phase 10 and for 8.3 below.

**Assert the packet count against the filed count.** `epic-update` writes one `followup-<KEY>-<id>-<n>.md` context packet per item it actually files (`epic-update/SKILL.md` step 2 — the path carries this ticket's `<id>`, and omitting it is the difference between counting this run's packets and counting the project's), and both the write and the whole skill are best-effort — so a skipped filing step and a completed one are indistinguishable from here unless this command checks. Compare `EPIC_REPORT`'s `FILED` length against the packets for **this ticket**, matched by exact identity — the `<n>` each filed item was assigned — not by a glob. **`followup-<KEY>-*.md` is the wrong pattern and silently reads the whole project**: `<KEY>` is the project key, shared by every ticket in the repository, so that glob counts every follow-up packet any prior ticket ever wrote and reports a wild excess against this run's `FILED` on almost every invocation. Scope it to `followup-<KEY>-<id>-*.md`, and count only the identities this invocation reports in `FILED`. Two cases are **not** mismatches and must not be logged as one: an `ALREADY_FILED` item legitimately has no new packet at all; and a **successful retry** of a historical `FAILED` item deliberately reuses the packet the original attempt wrote — `epic-update` step 1a persists that packet *before* calling `create-task`, so it exists whether or not the call succeeded, and step 1a reuses it by its recorded `<n>` rather than writing a new one. Such an item lands in this invocation's `FILED` with a packet older than this invocation, and that is the producer's contract working, not a missing packet. Assert that each filed item **has** its own packet at the identity recorded for it — never that the packet was created by this run. On a mismatch — including a filed item whose own packet is absent — record `unexpected:followup-packet-missing` per `notion-dev:issue-log`, naming both counts and the missing identities, and say it in Phase 10's epic line. Without the packet there is no local record of what a follow-up ticket was generated from, and `epic-update`'s `PROVENANCE` dedup has nothing to retry against. Measured on `notion-dev` 0.20.2: BTC-Gateway STO-77 filed three tickets and wrote zero packets and no persisted review report, and nothing in the run noticed or reported it. When `EPIC_REPORT`'s `FAILED-TO-FILE` bucket is non-empty, or either `DROPPED` or `FAILED-TO-FILE` carries `epic-update`'s `unknown` sentinel, record `partial:epic-update` per `notion-dev:issue-log`. Never merely because `DROPPED` holds concrete items — per `epic-update/SKILL.md`, a `DROPPED` item there is a user decision (the interactive gate offered File/Drop and the user chose Drop, with a rationale), the routine kind of interaction this log must never record. `unknown` means the invocation had no `REVIEW_REPORT` to assert either bucket from and is the real quiet degradation this signature exists to catch; a future edit must not simplify this back to a bare non-empty-`DROPPED`-or-`FAILED-TO-FILE` check, which is exactly the bug being fixed here.

Best-effort by construction — the skill never fails this run. A ticket with no epic is a no-op returning `EPIC-UPDATE: none`.

### 8.3 Update ticket

**Update the Completeness record.** Skip this whole subsection only when `COMPLETENESS_REPORT` is absent — with no report there is nothing to record. **An unset `CRITERIA_FILE` is not that case.** The gate still runs its claim and caveat charges without a criteria file and reports `CRITERIA-TOTAL: 0` (see `notion-dev:review-and-merge`'s `## Input`), so `CLAIMS` / `CAVEATS` / `TRIAGE` can carry real findings for a ticket that simply stated no acceptance criteria. Skipping on `CRITERIA_FILE` alone would drop them from the ticket's only durable record.

Otherwise, `appendToSection(id, "Implementation", …)` with a **Completeness** block — never `upsertSection`: Phase 6.5 wrote `## Implementation` before the merge, and a replacing write here would clobber its Plan / Implementation / Files Changed / PR / Branch / Plan review / Notes fields; this append is the only addition made to it. Three cases:

- **`CRITERIA_FILE` was unset** (the ticket has no `## Acceptance Criteria` section): there are no boxes, so do **not** call `refreshAcceptanceCriteria` — there is nothing to tick and ticking nothing is not a verdict. Append the block only when at least one of `CLAIMS` / `CAVEATS` / `TRIAGE` is not `NONE`, carrying those entries and stating that this ticket declared no acceptance criteria, so `CRITERIA-TOTAL: 0` is a fact about the ticket rather than a verdict about the work. When all three are `NONE`, write nothing: an empty record is noise, not evidence.
- **`COMPLETENESS_REPORT` is absent, or its `CRITERIA-TOTAL` does not equal `CRITERIA_FILE`'s line count** (the gate's `VERDICTS` no longer line up one-to-one with today's criteria): the Completeness block states plainly that verdicts were unavailable this run — and why (report absent, or a criteria/verdict count mismatch) — and that the unticked boxes are **not** a verdict. Do **not** call `refreshAcceptanceCriteria` in this case: leave every box exactly as it already reads, since ticking one now would assert a verdict this run cannot actually support.
- **Otherwise** (`COMPLETENESS_REPORT` present and its `CRITERIA-TOTAL` matches `CRITERIA_FILE`'s line count): from `COMPLETENESS_REPORT`'s `VERDICTS` block, build `verdicts` — one entry per criteria-file line, in file order, `{ criterion, verdict }` — and call `refreshAcceptanceCriteria(id, verdicts)` via `notion-dev:ticket-system`. Take each `criterion` from `CRITERIA_FILE`, **not** from the verdict line's echo of it: the file is the verbatim copy fetched from Notion, and a paraphrase written back would silently rewrite the ticket's own definition of done. The Completeness block records each criterion, its verdict (`met` / `not-met` / `unverified`), the gate's resolved citation, and — for any criterion escaped to `file` or `drop` — its label and rationale from `COMPLETENESS_REPORT`'s `TRIAGE`.

For an acceptance criterion, `file` and `drop` are **scope reductions**, not deferrals of extra work — which is why they land on the ticket rather than only in the PR. Someone tracking this work must be able to see that its stated definition of done shrank.

Append a separate `## Merged` section — do **not** replace the `## Implementation` section written in Phase 6.5 (the Completeness block appended above is the only addition made to it); the two are meant to coexist as a chronological record. This step runs **after** 8.2 deliberately: the "Deferred follow-ups" field below names actual follow-up ticket IDs, which do not exist until `epic-update` (8.2) files them. An earlier revision of this command wrote this section first and left that field promising links to tickets that were created only afterward, with nothing to ever backfill them — reordering closes that gap by writing the record once, after the data it needs exists.

Invoke `notion-dev:ticket-system`, `upsertSection(id, "Merged", { ... })` with these fields (order matters — the Notion adapter renders scalars as a table and narrative/lists below it, in this order):
- **PR** — the PR URL (same one written into `## Implementation` earlier; repeating it here makes the Merged record self-contained).
- **Merge commit** — SHA from the merge review-and-merge performed.
- **Merge strategy** — `squash`, `merge`, or `rebase`.
- **Base branch** — the branch merged into (from `git.baseBranch` or the PR's `baseRefName`).
- **Merged at** — ISO timestamp.
- **Review resolution** — 1-3 bullets summarizing how review feedback was handled, distilled from `REVIEW_REPORT` (e.g. "applied 4 comments, absorbed 2 findings, filed 1 follow-up, disagreed on 1").
- **Absorbed** — items from `REVIEW_REPORT`'s `ABSORBED` list, each with what was changed. Omit the field when the list is empty. These needed no ticket because the work is in this PR.
- **Deferred follow-ups** — items from `REVIEW_REPORT`'s `FILED` list, each with its blast-radius criterion number and its actual follow-up ticket ID/URL from `EPIC_REPORT`'s `FILED` ∪ `ALREADY_FILED` (both now known, since 8.2 already ran). `epic-update` remains best-effort: when `EPIC_REPORT` is `EPIC-UPDATE: none`, or a given item isn't in either list (e.g. `epic-update` failed partway, or the item is in `DROPPED` or `FAILED-TO-FILE`), list that item with no ID rather than inventing one — this section is still written with whatever is known, never blocked on 8.2's outcome.
- **Dropped** — items from `REVIEW_REPORT`'s `DROPPED` list, each with its rationale. Omit the field when the list is empty. A recorded drop is a decision, not an omission.
- **Blocked** — items from `REVIEW_REPORT`'s `BLOCKED` list, each with its external cause and what would unblock it. Omit the field when the list is empty. These carry no ticket ID and must never be given one: a `blocked` item is real work nobody can start, not deferred work somebody can. **This field is the only durable record an ordinary review finding's block ever gets** — the Completeness record above covers acceptance criteria, not review findings, so without it the cause and the unblocker exist solely in a terminal summary that scrolls away.
---

## Phase 9 — Clean up

Touch the run marker: `phase` = "Phase 9", `heartbeat` = now.

Only start cleanup after confirming the merge landed: `gh pr view <pr> --json state` reports `MERGED`. **Never delete unmerged work.**

From `$REPO_ROOT` — `cd $REPO_ROOT` first if the run is still inside the worktree, since step 1 removes it out from under the current directory. **The worktree goes first and the primary checkout's `checkout` goes last** — nothing in worktree removal or branch deletion needs the primary to be on the base branch, and doing the primary's checkout while a worktree may still be sitting on that branch is what produced `fatal: '<baseRefName>' is already used by worktree at '<primary>'`:

1. Confirm `<worktree-path>` is the worktree this flow created (the path computed in Phase 1.2/2.1), then `git worktree remove <worktree-path>`. If it fails, retry with `git worktree remove --force <worktree-path>`. **Two causes reach that retry, and only the first is incidental**: untracked leftovers (e.g. build artifacts — PLAN.md itself is already gone per 6.6), and `fatal: working trees containing submodules cannot be moved or removed`. The second is **deterministic, not an anomaly** — a repo that vendors dependencies as git submodules puts them in every worktree it creates, so `--force` is the norm there rather than the exception, and a watcher should not read it as a fault. Measured: 3 consecutive ticket runs in one submodule-bearing client, 3 for 3. Then `git worktree prune`.

Then `rm -f "$REPO_ROOT/.claude/notion-dev/runs/<KEY>-<id>.json"` — the claim is gone with the worktree.
2. `git branch -D <branch>` using the branch name recorded in 2.1 (`ticket/<project.key>-<id>-<slug>`) — do not re-spell the template here (`-D` required — squash merges aren't detected by `-d`; safe because the merge was verified above). If it fails because `<branch>` is checked out in the primary checkout, run step 4 first and retry this step after it.
3. Verify the remote branch is gone (`git ls-remote --heads origin <branch>`); if not, `git push origin --delete <branch>` (swallow "already deleted" errors). `notion-dev:review-and-merge` deletes the remote branch itself as its own command after the merge, so this is normally a no-op confirmation — it stays because that deletion is not guaranteed to have been reached. Targeting `origin` directly is correct **here specifically**, and the asymmetry with `/notion-dev:finalize` step 3 is deliberate rather than an oversight: this flow created `<branch>` and pushed it to `origin` itself in Phase 5, so the head repository is `origin` by construction and no fork case exists. `finalize` takes an arbitrary PR number and must resolve the head repository first.
4. Checkout + pull the branch the PR merged into (its `baseRefName` — equals `git.baseBranch` in the simple flow): `git checkout <baseRefName> && git pull --ff-only origin <baseRefName>`. **`--ff-only` is required, not stylistic**: a primary whose base branch carries local-only commits has diverged, and a default `pull` would silently manufacture a merge commit to reconcile it — the exact unintended merge commit this whole ordering exists to prevent. `--ff-only` aborts instead, which is what "do not stash or discard anything" means for a diverged branch. Best-effort — on failure, do not stash or discard anything; continue with the remaining cleanup steps and report that the branch needs a manual checkout/pull.

**A failed pull must be diagnosed, not merely reported — the evidence is gone one step later.**
`--ff-only` covers a *diverged* base, but the other cause is a **dirty primary checkout**, which
surfaces as `Your local changes to the following files would be overwritten by merge` and means
something wrote outside the worktree during the run. Before continuing, capture and report
`git -C "$REPO_ROOT" status --porcelain`, naming the offending paths. Do not stash or discard
anything — but do not let the run end with only "the branch needs a manual pull" either.

The ordering makes this urgent rather than optional: the worktree and the branch are removed
**before** this step, so by the time the pull fails, the only record of where a stray edit came
from is already deleted. A run that follows "continue with the remaining cleanup steps and report"
literally, with no diagnosis, leaves the edit sitting in the primary checkout indefinitely and
unattributable.

Measured in a client: a build-flow implementer subagent, dispatched with the worktree as its
working directory and an absolute worktree path in its brief, **also** wrote its edit to the same
relative path under the primary checkout. Both copies got the change; the worktree copy was
committed and merged normally while the primary copy sat as an uncommitted modification —
invisible to every gate in the flow, because each of them inspects the worktree and none inspects
the primary. It was recovered only by diffing the stray copy against the merged base, which showed
it to be an older intermediate state of the same edit, and discarding it.
5. Remove the worktrees parent directory if now empty: `rmdir "$(dirname <worktree-path>)"` — derived from the path Phase 1.2/2.1 computed, so the target is checkable without introducing a second name for it. `rmdir`, never `rm -rf`: it refuses on a non-empty directory, which is the whole safety property here.

### Post-merge hooks

Run `git.postMergeHooks` skills in order (empty default — no-op). These run **after** cleanup, not before it: a hook such as `notion-dev:knowledge` commits and pushes from the primary checkout, and only here is the primary guaranteed to be on a freshly pulled `<baseRefName>` containing the merge commit the hook reads. Running them earlier meant committing and pushing to whatever branch the primary happened to be on. The hook receives `<ticket-id>`, `<merge-sha>`, the ticket body, `KNOWLEDGE_CONTEXT`, this run's review report, and `LOCK_HELD` — nothing from Notion.

Assert that before invoking anything:

```bash
git -C $REPO_ROOT rev-parse --abbrev-ref HEAD                    # must equal <baseRefName>
git -C $REPO_ROOT merge-base --is-ancestor <merge-commit> HEAD   # must exit 0
test "$(git -C $REPO_ROOT rev-parse HEAD)" = \
     "$(git -C $REPO_ROOT rev-parse origin/<baseRefName>)"       # must be equal
```

**All three lines, and each catches something the others do not.** Step 4 chains `checkout && pull`, so a `checkout` that succeeds and a `pull` that then fails (network, a dirty primary) leaves HEAD on the right branch but *behind* — a name-only assertion passes on that stale checkout, handing the hook exactly the state this ordering promised to prevent. Line 2 makes "contains the merge" checkable: `<merge-commit>` is the SHA `review-and-merge` returned and the run already records, and its being an ancestor of HEAD proves the merge is present whatever the pull did — including when the local `origin/<baseRefName>` ref is itself stale, which is why line 3 does not replace it.

Line 3 is what makes it *only* the merge. A primary carrying local-only commits satisfies both earlier lines — the branch name is right and the merge commit is an ancestor — while HEAD also holds commits that were never pushed and never reviewed. A hook is free to commit and push — the contract constrains *when* hooks run, not what they do, and `notion-dev:knowledge`, the consumer-repo hook that motivated this ordering, does exactly that — so a hook running on a diverged primary publishes that unreviewed local work to the base branch as a side effect of a ticket run. Requiring HEAD to equal `origin/<baseRefName>` exactly rejects divergence rather than reconciling it, which is also why step 4 pulls `--ff-only`.

If **any** assertion fails, **skip the hook step entirely** and report that hooks were skipped, which assertion failed, the branch and HEAD the primary was found on, and that they need a manual re-run after a successful checkout and fast-forward pull. Never run a configured hook on an unasserted branch: the ordering makes the right state overwhelmingly likely, and these assertions make it certain.

The cost of this ordering is stated deliberately: by the time hooks run, the worktree is gone, so a hook cannot inspect the branch's working tree. That is consistent with the documented hook contract — `git.postMergeHooks` is specified as "skills invoked after merging", the merge is a squash by default so the branch's tree is not the merged tree anyway, and the flow already deleted the remote branch. A hook needing the pre-merge working tree must read it from git history instead.

### Ledger outcome

Append one outcome line to `$REPO_ROOT/.claude/notion-dev/ledger.jsonl` per the schema in `skills/flow-triage/references/ledger.md`:

```json
{"event":"outcome","run_id":"<KEY>-<id>","ts":"<UTC now>","result":"merged","review_rounds":N,"fix_commits":N,"files_changed":N,"insertions":N,"deletions":N,"duration_minutes":N,"plan_review_findings":N,"plan_review_accepted":N,"plan_review_declined":N,"plan_review_unresolved":N,"triage_absorbed":N,"triage_filed":N,"triage_dropped":N,"triage_blocked":N,"triage_reclassified":N,"completeness_criteria":N,"completeness_met":N,"completeness_unverified":N,"completeness_items":N}
```

Metrics come from `REVIEW_REPORT` (review rounds, fix commits) and `git show --shortstat` of the merge commit (files changed, insertions, deletions); duration from `RUN_START` to now. Plan-review metrics come from `PLAN_REVIEW_REPORT` (Phase 4.2 step (b)); all four are `null` wherever there is no review signal to record — the `feature-dev` path, which has no plan to review, a `degraded` review, where the reviewer never ran, and a resume that skipped the review. On a degraded review write `null`, **not** the zeros its output block carries: `0` findings would be indistinguishable from a review that ran and found nothing, and that is exactly the distinction this ledger exists to preserve. The five `triage_*` counts come from `REVIEW_REPORT`'s `ABSORBED` / `FILED` / `DROPPED` / `BLOCKED` lists, with `triage_reclassified` counting the `FILED` entries marked as reclassified from `absorb`. `triage_blocked` is never folded into `triage_filed`: a blocked item is unreachable, not deferred, and merging the two is what made a reachability limit read as a filing habit. Write `null` for all five — never `0` — when no review produced a triage. The four `completeness_*` counts come from `COMPLETENESS_REPORT`'s `CRITERIA-TOTAL` / `CRITERIA-MET` / `CRITERIA-UNVERIFIED` keys, with `completeness_items` counting its `TRIAGE` entries. Write `null` for all four — never `0` — when no completeness check ran: no criteria file and no changed prose, or a run that stopped before the gate. That is distinct from `CRITERIA-TOTAL: 0`, which `COMPLETENESS_REPORT` carries whenever the gate ran its claim and caveat charges but had no criteria file to check — a check that ran and found nothing, not one that never ran; that `0` belongs in `completeness_criteria` as a real `0`. Any metric that cannot be determined is `null`. A ledger append failure never fails the run.

**Issue-log sweep.** Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`. Best-effort — a failure here never fails the run.

**Epic doc — record the resolution.** Runs after the draft report is composed and before the closeout workspace pass below, so the closeout can see the commit it makes. Compose the full draft report (the summary list below) first. Then, when `EPIC_REPORT` is anything but `EPIC-UPDATE: none`, invoke the `notion-dev:epic-doc` skill, operation `record(<id>)`, from `$REPO_ROOT`, passing as context: `REPO_ROOT`, `LOCK_HELD`, `<baseRefName>` and `<merge-commit>` (the same two Phase 9's hook assertions used), `EPIC_REPORT` (8.2), `REVIEW_REPORT` and `COMPLETENESS_REPORT` (Phase 7), the completion pass's `CLOSEOUT:` block from Phase 7's pre-merge check as `COMPLETION_CLOSEOUT`, the run's non-interactive decisions as `DECISIONS`, and the draft report as `DRAFT_REPORT`. Record its output block as `EPIC_DOC_REPORT`. It rewrites the epic's brief and commits it straight to `<baseRefName>` — the same slot and the same three assertions as the post-merge hooks. When the block reads `EPIC-DOC: failed`, record `partial:epic-doc` per `notion-dev:issue-log`; a local commit its `CAUSE:` names is a tail the closeout below forces into `blocked:` with that cause. Skip silently when the ticket had no epic.

## Output block

Return exactly this block and nothing else after it:

```
RECORD:
EPIC-REPORT: <the epic-update EPIC-UPDATE: block verbatim, or `none`>
TICKET-RECORD: <ok | partial: <what was not written> | failed: <cause>>
CLEANUP: <ok | partial: <which step> | failed: <cause>>
EPIC-DOC-RECORD: <ok | skipped: <why> | failed: <cause>>
ISSUES: <comma-separated issue-log signatures recorded in this unit, or `none`>
```

Every key appears on every run. A key with nothing to report takes its `ok` or `none` value, never
absence — an omitted key is indistinguishable from a step that never ran.
