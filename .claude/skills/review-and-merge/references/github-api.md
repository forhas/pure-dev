# GitHub API reference for the review loop

Exact commands for reading, replying to, and resolving PR review threads. `<pr>` is the PR number; `{owner}`/`{repo}` placeholders are expanded automatically by `gh api`.

## Reading review state (always paginate)

REST reads return at most one page (30 items) by default — later comments are silently missed without `--paginate`:

```bash
gh api --paginate repos/{owner}/{repo}/pulls/<pr>/comments   # inline review comments
gh api --paginate repos/{owner}/{repo}/pulls/<pr>/reviews    # review summaries
gh api --paginate repos/{owner}/{repo}/issues/<pr>/comments  # PR-level (issue) comments
```

**`--paginate` applies `--jq` per page, not to the combined result.** This is the trap: an
aggregating filter (`last`, `first`, `length`, `add`, `max_by`) runs once per page and prints
one result per page. Capturing that in a shell variable yields a multi-line value — and
interpolating it into another jq expression produces invalid syntax, so the command fails or,
worse, silently matches nothing:

```bash
# WRONG — one line of output per page; $ID becomes "null\n123\n456"
ID=$(gh api --paginate repos/{owner}/{repo}/pulls/<pr>/reviews --jq '[.[]|select(...)]|last|.id')
```

`--slurp` wraps all pages into one outer array, but **`--slurp` cannot be combined with
`--jq`** (`gh` rejects it: *"the `--slurp` option is not supported with `--jq`"*). So slurp
first, then filter with external `jq`, flattening pages with `.[][]`:

```bash
# RIGHT — single value, all pages considered
ID=$(gh api --paginate --slurp repos/{owner}/{repo}/pulls/<pr>/reviews \
  | jq -r '[.[][] | select(...)] | last | .id')
```

Per-item filters that print one line each (no aggregation) are unaffected — `--paginate --jq`
is fine for those.

## Thread resolution state (GraphQL only)

Thread **resolution state is not in the REST payload**. Query it via GraphQL to know which threads to skip (already resolved), to get each thread's node `id` (needed to resolve it), and to verify the merge gate:

```bash
gh api graphql -f query='
  query($owner:String!,$repo:String!,$pr:Int!,$cursor:String){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$pr){
        reviewThreads(first:100, after:$cursor){
          pageInfo{ hasNextPage endCursor }
          nodes{ id isResolved comments(first:100){ nodes{ databaseId } } }
        }
      }
    }
  }' -F owner={owner} -F repo={repo} -F pr=<pr> -F cursor=null
```

Rules that are easy to get wrong:

- **GraphQL is not covered by REST `--paginate`.** `reviewThreads(first:100)` returns one page. If `pageInfo.hasNextPage` is true, re-run with `-F cursor=<endCursor>` and accumulate ALL pages before deciding anything (both when processing and when verifying the merge gate).
- **Map every comment in a thread, not just the root.** A thread can contain replies; map every comment `databaseId` back to that thread's `id`/`isResolved`. Otherwise a reply's REST `comment_id` won't resolve to a thread and its state is lost.
- **Re-run this query after each review round.** The REST polling reads do not return thread node ids, and new comments create new threads. Without a refresh, new threads have no `threadId` and the merge gate can never clear.

## Copilot pending-review check

`gh pr view <pr> --json reviewRequests` is **not a reliable source for a pending Copilot
request** — it has been observed returning empty while the bot's request was genuinely live
(confirmed via the REST endpoint below and the PR timeline). Use the REST endpoint instead
everywhere this skill needs to know whether Copilot's review request is still outstanding:

```bash
if RESULT=$(gh api repos/{owner}/{repo}/pulls/<pr>/requested_reviewers --jq '.users[].login'); then
  echo "$RESULT" | grep -qx 'copilot-pull-request-reviewer\[bot\]' && echo PENDING || echo NOT_PENDING
else
  echo "READ_FAILED"   # gh itself errored — retry the read, per SKILL.md's rule that a
                        # failed read is never evidence; do not treat this as "not pending"
fi
```

**Capture `gh api`'s own exit status before piping into `grep`, and never fall through past a
failed read.** A pending list that is legitimately empty (nobody outstanding) makes `gh api --jq`
print zero bytes and exit `0` — the *same* zero-byte output a failed call can also produce.
Piping the raw command straight into `grep -q <login>` loses the distinction: `grep` finds no
match either way, so its own exit code (`1`) can't tell "the call failed" from "the call
succeeded and nobody is pending." Nesting the membership test **inside** the `if`'s success
branch, as above, is what actually enforces the separation — an `||` handler that only prints
`READ_FAILED` without an `exit`/`return`/`continue` still falls through to the membership test
on the next line, emitting both `READ_FAILED` and `NOT_PENDING` with an overall zero exit status,
which is exactly the ambiguity this check exists to remove. With the `if`/`else` form, a non-zero
`gh api` exit can never reach the membership test at all — it always means retry, never a
verdict; a zero exit with `NOT_PENDING` is a legitimate, definite absence, distinct from an
unread state, and safe to treat as "check for a submitted review" per the (b) branch in step 3
of SKILL.md.

Bot login present (`PENDING`) → the request is live. `NOT_PENDING` → either it was never made,
or Copilot already submitted and was auto-removed — absence alone is ambiguous (see the
"response landed" check in step 3 of SKILL.md, which also checks for a submitted review).

## Replying

In-thread reply to an inline review comment (use the REST `comment_id` / `databaseId`):

```bash
gh api repos/{owner}/{repo}/pulls/<pr>/comments/<comment_id>/replies -f body="..."
```

Reply to non-inline review notes or PR-level comments:

```bash
gh pr comment <pr> --body "..."
```

## Resolving a thread

Replying does **not** resolve a thread — resolution is separate state. After replying (Agree, Partially agree, and Disagree alike), resolve using the thread's GraphQL node `id`:

```bash
gh api graphql -f query='mutation($id:ID!){ resolveReviewThread(input:{threadId:$id}){ thread{ isResolved } } }' -F id=<thread-node-id>
```

## Merge-gate verification

Before merging:

```bash
gh pr checks <pr> --required            # every required check passing
gh pr checks <pr>                       # nothing failing anywhere; pending optional checks don't block
# + full paginated reviewThreads query → every thread isResolved: true
```

**Exit-code caveat (cli/cli#9682)**: both commands exit non-zero with the message `no checks reported on the '<branch>' branch` when the PR has no checks (or no *required* checks with `--required`). That outcome satisfies the corresponding gate — distinguish it from real failures by the message, not the exit code.

Merge and confirm:

```bash
gh pr merge <pr> --squash
gh pr view <pr> --json state             # must report MERGED before deleting anything
gh pr view <pr> --json headRepositoryOwner,headRepository,headRefName
gh api --method DELETE "repos/<headOwner>/<headRepo>/git/refs/heads/<head-branch-encoded>"
```

**Percent-encode the ref.** `gh api` takes a URL path, so a `#` — legal in a git ref, special in a URL — is parsed as a fragment and silently dropped: `…/heads/feature/foo#bar` is sent as `…/heads/feature/foo`, deleting an unrelated branch. Encode `%` first (it is the escape character), then `#`; leave `/` as-is. `?` needs no handling — `git check-ref-format` rejects it, so it cannot appear in a branch name.

```
%  →  %25        #  →  %23
```

**Delete from the head repository, not `origin`.** On a fork-based PR the head branch lives in the fork while `origin` is the base repo, so `git push origin --delete <head-branch>` either fails or deletes a same-named base branch instead. Resolve the head repo from the PR and target it. A `403` on a fork you cannot write to is expected — report it and continue.

**Order matters — never delete before `state` reads `MERGED`.** With a merge queue on the base branch, `gh pr merge` exits 0 having only *enqueued* the PR (`gh pr merge --help`: "If required checks have passed, the pull request will be added to the merge queue"), and `state` still reads `OPEN`. Deleting the head branch then destroys the ref the queue is building from. Poll at 30s intervals to a ~15-minute bound, then stop and report rather than deleting.

**Never `--delete-branch`**: its local-cleanup step has to move the worktree holding the head branch onto the base branch, which the primary checkout already holds, so git refuses (`fatal: '<base>' is already used by worktree at '<primary>'`) and the command exits non-zero *after* the remote merge has already succeeded (cli/cli#13380). Deleting the remote branch explicitly avoids the whole path. A `--delete` that fails because the branch is already gone (auto-delete-on-merge) is not an error.

On a non-zero exit from `gh pr merge`, check state before anything else — never re-run the merge:

```bash
gh pr view <pr> --json state   # MERGED → merge succeeded; do NOT re-run gh pr merge
```

Only if state is still `OPEN` treat it as a real merge failure and diagnose.
