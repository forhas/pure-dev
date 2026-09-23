## The write path` below with the subject
`docs(epic): <KEY>-<n> start <key>`,
`docs(epic): <KEY>-<n> stop <key>`,
`docs(epic): <KEY>-<n> create <key>` or
`docs(epic): <KEY>-<n> refresh`,
by the pathspec `-- <brief path> <knowledge.dir>/index.md` (the catalog bullet rule of "The file"
applies here too), and return `refreshed`.

**Best-effort**, like every operation here: `failed` is recorded by the caller as
`partial:epic-doc` and never stops a run — except that `/notion-dev:next-task` does not select
from a brief whose drift refresh failed.

## The write path — every commit from the primary checkout

`refresh`, `record`, `record --bootstrap`, `note --apply` and `notion-dev:knowledge` `capture`
(both forms) commit and push from `$REPO_ROOT` through these five steps and no others. Stated
once here; the others cite it.

1. **Lock.** Unless the caller passed `LOCK_HELD`, take the primary lock:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock take --run <run id> --section <name> --wait <seconds>` — `LOCK_HELD` means an enclosing section already holds it. Run ids: a ticket run uses `<KEY>-<id>`, finalize `finalize <pr>`, next-task `next-task <KEY>-<n>`; every other command generates a per-invocation token at its start (its preconditions or, for create-task, its `create` paragraph say how). On Windows, renaming the lock directory can fail while another process holds a handle inside it; `lock take` treats that as a lost race and retries, so no extra handling is needed.
   Exit 1 → `failed`, `CAUSE: primary lock held by <run> (<section>) since <time>`; a printed
   `stale:` line → record `lock-stale:primary` per `notion-dev:issue-log` and name the old owner
   in the report. Read-only checks of the primary and `git worktree add` never take it.
2. **Establish the base.** `git -C $REPO_ROOT fetch origin <epicBranch>`. The primary must be on
   `<epicBranch>`; the operations whose contract allows a checkout — `refresh` (all reasons) and
   `record --bootstrap` — run `git -C $REPO_ROOT checkout <epicBranch>` when the primary is clean
   outside the exempt paths; when it is not clean, the existing branch assertion applies instead —
   the primary must already be on `<epicBranch>` or the operation is `failed` with `CAUSE: primary
   checkout is dirty and not on <epicBranch>`; the others assert the branch as before. Then
   `git -C $REPO_ROOT pull --ff-only origin <epicBranch>`. A `--ff-only` failure → `failed`,
   `CAUSE: <epicBranch> has diverged from origin` — never stash, never reset a diverged base.
   After this step the three ref assertions of `/notion-dev:ticket` Phase 9 hold by
   construction, and the porcelain check on the operation's pathspec must be empty, as before.
   Under `--branch <noteBranch>` (`/notion-dev:new-info --pr`) the fetch still runs, but in
   place of the on-branch check and the `--ff-only` pull: HEAD's branch must be `<noteBranch>`
   and `git -C $REPO_ROOT merge-base --is-ancestor origin/<epicBranch> HEAD` must exit 0 — the
   branch was cut from the epic branch and still contains it.
3. **Derive and commit.** Write the files, `git add` them, then, if
   `git diff --cached --quiet -- <pathspec>` succeeds → `unchanged`, `COMMIT: none`, go to 5.
   Otherwise `git commit --only -m "<subject>" -- <pathspec>`.
4. **Push, converge on rejection.** `git push origin <epicBranch>`. On a non-fast-forward
   rejection: `git -C $REPO_ROOT fetch origin <epicBranch>`, then assert
   `git rev-list origin/<epicBranch>..HEAD` names **exactly one** commit — this attempt's own.
   Anything else → `failed`, commit left in place, `CAUSE: push rejected — <git's message>`,
   as before. One commit → **put the primary on the fetched tree without discarding the permitted
   dirt.** When `git -C $REPO_ROOT status --porcelain` shows any of the three exempt setup files
   dirty — `.claude/notion-dev.config.json`, `.mcp.json`, `.claude/settings.local.json`, the
   exhaustive list the preconditions exempt and the only tracked dirt that can legally be here —
   `git -C $REPO_ROOT stash push --include-untracked --quiet --` those paths first — untracked,
   because init's commit step is optional and this operation must stay usable when it was
   declined, and a plain `stash push -- <path>` errors on a path git does not know; then
   `git -C $REPO_ROOT reset --hard origin/<epicBranch>`; then
   `git -C $REPO_ROOT stash pop --index --quiet` when one was pushed.
   `--index` is not optional there: the preconditions exempt *staged* edits to those files as
   well as unstaged ones, and a plain pop restores the bytes while silently discarding the
   user's index selection. Re-derive against the fresh files, and go back to step 3.
   **Both halves are load-bearing.** The reset is `--hard` because every path outside this
   operation's pathspec must become the commit just fetched: a `--soft` reset moves HEAD only, so
   the index keeps the pre-fetch tree and every file an upstream commit changed sits there as a
   staged reversion — which fails the next clean-tree check and can republish stale content. The
   stash is what stops that hard reset taking the user's permitted edits with this attempt's
   commit, which is all the `rev-list` proof licenses discarding. This is **not** the
   diverged-base case of step 2, where stashing is still forbidden. A `stash pop` that conflicts
   — upstream changed an exempt file too — is `failed` with `CAUSE: <path> conflicts with
   <epicBranch>; your edits are in <stash ref>`, never a discard. **Three attempts.** `record` and `note --apply`
   re-apply their diff *semantically* — the bullets they add and remove, the sentence they
   restate — to the fresh brief; `refresh` and `capture` simply re-derive. The third rejection
   is `failed` with the local commit left in place and the caller's `blocked:` closeout line, as
   before. Under `--branch <noteBranch>` there is no push and no retry.
5. **Unlock.** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" lock release --run <run id>` — skipped when the caller passed `LOCK_HELD`. Report `ATTEMPTS: <n>`, the number of times step 3 ran.
