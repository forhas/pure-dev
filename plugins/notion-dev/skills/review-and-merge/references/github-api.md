# GitHub API reference for the review loop

Exact commands for reading, replying to, and resolving PR review threads. `<pr>` is the PR number; `{owner}`/`{repo}` placeholders are expanded automatically by `gh api`.

## Reading review state (always paginate)

REST reads return at most one page (30 items) by default — later comments are silently missed without `--paginate`:

```bash
gh api --paginate repos/{owner}/{repo}/pulls/<pr>/comments   # inline review comments
gh api --paginate repos/{owner}/{repo}/pulls/<pr>/reviews    # review summaries
gh api --paginate repos/{owner}/{repo}/issues/<pr>/comments  # PR-level (issue) comments
```

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
gh pr merge <pr> --<strategy> --delete-branch   # <strategy> = git.mergeStrategy from .claude/notion-dev.config.json, default squash
gh pr view <pr> --json state            # must report MERGED
```

On a non-zero exit from the merge command, check state before anything else — `--delete-branch` can fail on local cleanup after the remote merge already succeeded (branch checked out in a worktree; cli/cli#13380):

```bash
gh pr view <pr> --json state   # MERGED → merge succeeded; do NOT re-run gh pr merge
git push origin --delete <head-branch>   # finish the remote deletion, continue cleanup
```

Only if state is still `OPEN` treat it as a real merge failure and diagnose.
