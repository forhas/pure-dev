---
name: session-closeout
description: This skill should be used before reporting a session, run, or task as finished — when about to write a final summary, say the work is done, or hand it back. Enumerates every loose end from named sources rather than from memory, forces each into resolved / tracked / blocked, and refuses a report that leaves an actionable item in none of the three.
---

# session-closeout — finish with zero tails

A **tail** is an actionable item a session leaves behind that it could have finished. Tails are
resolved, not reported. This skill runs **before** the final report is written, because a tail
discovered while writing the report is one that gets written down instead of fixed.

## The rule

**Every tail ends in exactly one of three states. There is no fourth.**

| state | meaning | what it requires |
|---|---|---|
| `resolved` | done in this session | the evidence — a commit sha, a passing command, a merged PR |
| `tracked: <url>` | genuinely separate work | a **ticket that exists right now**, with its URL. "I will file it" is not this state |
| `blocked: <cause>` | cannot be finished from here | the **external** cause, named, plus what would unblock it |

"Left for later", "nice to have", "worth flagging", "out of scope for now" are **not states**.
They are the absence of one, phrased so it reads like a decision.

**`blocked` is for external causes only** — a credential the session does not have, a third-party
outage, a service it cannot reach, a decision only the user can make, an approval only a human
can give. It is **not** for work that is merely long, tedious, or unreviewed.
**Time is not a blocker**: if there was time to describe the work, there was time to start it.
A `blocked` item with an internal cause is a tail wearing a label, and it is the single most
common way this rule is defeated.

## When to run — two passes

**A tail whose fix belongs in the pull request has to be found before the merge, not after it.**
The sources in step 1 are ordered by kind, not by timing, and a caller that merges has two
distinct moments to use them:

- **Completion pass — before the merge.** Sources 1, 2, 5, 6 and 7: uncommitted and unpushed
  work, `FILED` items carried forward, deferred trailers, and a fresh verification run. Every one
  of these has a fix that belongs *in the pull request*. **Source 8 is deliberately not here** —
  the finished report does not exist before the merge, so listing it would make this pass an
  impossible gate. Run it
  while the branch is still open — a caller driving `review-and-merge` passes it as a
  `--pre-merge-check` requirement, which is precisely the hook for a condition that must hold
  immediately before the merge command runs.
- **Workspace pass — after cleanup.** Sources 3, 4 and 8: leftover worktrees and branches, open
  pull requests, and the finished draft report — plus the *second half* of source 5, the `FILED`
  items' ticket URLs, which do not exist until the filing step has run. Source 8 is here rather
  than in the completion pass for the same reason: at completion time there is no report to read. These are only *answerable* once the merge and cleanup have
  happened, and none of them is fixed by changing code.

**Running only the workspace pass is the failure this split exists to prevent.** The completion
sources would then be read after the branch was deleted, so a defect the fresh test run turned up
could no longer enter the reviewed pull request — it would need the very second pull request this
whole design exists to avoid, or it would be left sitting on the base branch.

## 1. Enumerate — from sources, never from memory

Do not recall what is outstanding; **query it**. Recall is what produces "one thing left".

1. *(completion)* **Uncommitted work** — `git status --porcelain` in the primary checkout and in
   every worktree (`git worktree list --porcelain`). Non-empty is a tail, with **two exclusions
   that are not exceptions to the rule but a correction of what "this session's tail" means**:

   - **Changes the run recorded as pre-existing** — a flow that was permitted to start against a
     dirty checkout (`develop`'s `PREEXISTING_DIRTY`) holds that exact status output. Those lines
     predate the session, are not the session's to resolve, and cannot safely be committed onto a
     feature branch. Subtract them and judge only what remains. Without this, every such run stops
     dead at the completion pass over changes it was explicitly allowed to proceed past.
   - **Worktrees this session does not own.** Another checkout's uncommitted work belongs to
     whoever is editing it.

   Both exclusions are *reported*, never silently dropped: say which lines were set aside and why,
   so a genuine tail cannot hide behind the word "pre-existing".
2. *(completion)* **Unpushed work** — in every worktree **this run owns**, not just the current
   one, and a branch with *no* upstream is a tail too. `@{upstream}` **fails** rather than
   reporting that case, so an unguarded `rev-list` reads as an error, not as zero — handle it
   explicitly:

   ```bash
   git worktree list --porcelain | awk '/^worktree /{print $2}' | while read -r w; do
     b=$(git -C "$w" symbolic-ref --quiet --short HEAD) || continue   # detached HEAD: skip
     if git -C "$w" rev-parse --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
       n=$(git -C "$w" rev-list --count '@{upstream}..HEAD')
       [ "$n" -gt 0 ] && echo "$w ($b): $n unpushed commit(s)"
       continue
     fi
     # No remote-tracking ref is not the same as never pushed. `gh pr checkout` on a
     # FORK pull request sets branch.<b>.remote to the fork's URL and branch.<b>.merge
     # to the ref, and creates no tracking ref at all — so `@{upstream}` fails on a
     # branch that is pushed and in sync. Verified live: this branch reported "never
     # pushed" while `git ls-remote` showed the fork's ref at exactly local HEAD.
     # Ask the configured push target directly before concluding anything.
     r=$(git -C "$w" config --get "branch.$b.remote") || r=""
     m=$(git -C "$w" config --get "branch.$b.merge") || m=""
     if [ -n "$r" ] && [ -n "$m" ]; then
       remote_sha=$(git -C "$w" ls-remote "$r" "$m" | cut -f1)
       if [ -z "$remote_sha" ]; then
         echo "$w ($b): pushes to $r but the ref is absent there — unpushed"
       elif [ "$remote_sha" != "$(git -C "$w" rev-parse HEAD)" ]; then
         echo "$w ($b): differs from $r $m — unpushed"
       fi
     else
       echo "$w ($b): no upstream — never pushed"
     fi
   done
   ```

   **Ownership scopes this exactly as it scopes source 1, and for a sharper reason.** Another
   session's ahead-or-never-pushed branch is not this run's tail, and treating it as one is worse
   than noise: the callers' pre-merge gate blocks the merge until every tail is resolved, and the
   only way to "resolve" someone else's unpushed branch is to push it — this pass reaching into
   another session's work to unblock its own merge. Enumerate every worktree, but **judge** only
   the ones this run owns; report the rest as observed-and-not-judged, so they are visible without
   being actionable.

   **A branch with no upstream is a tail only where pushing is part of the flow.** In a repository
   with no `origin` remote — or on any run whose flow deliberately does not push, which is what
   `quick-dev:develop`'s **local mode** is — every branch reports `no upstream — never pushed`,
   including the primary checkout's own base branch, and none of them is resolvable: pushing is
   precisely the thing that mode does not do. Left unqualified this source hands local mode's
   pre-squash gate (`develop` Phase 4 step 5) two tails it cannot clear on every run, and a gate
   that can never be satisfied is one every caller learns to skip. Verified against a live
   local-mode run, where it fired on both worktrees. So: probe the remote first
   (`git remote get-url origin`); when there is none, report every branch as
   observed-and-not-judged with `no remote — nothing to push to`, and judge nothing under this
   source. When a remote does exist, a no-upstream branch this run owns is a tail as stated.
3. *(workspace)* **Leftover worktrees and branches** — a worktree, or a local branch whose work has landed, is
   a tail. **Do not reach for `git branch --merged`.** Where the project squash-merges, a
   squashed branch's commits are not ancestors of the squash commit, so `--merged` lists nothing
   and the check silently passes on exactly the branch it exists to catch. (`develop`'s own
   cleanup uses `git branch -D`, not `-d`, for this reason.) Ask whether the branch's pull
   request landed instead:

   ```bash
   git worktree list
   git for-each-ref --format='%(refname:short)' refs/heads | while read -r b; do
     [ "$b" = "<base>" ] && continue
     s=$(gh pr list --head "$b" --state all --limit 1 --json state --jq '.[0].state')
     case "$s" in
       MERGED) echo "$b: PR merged — stale branch" ;;
       CLOSED) echo "$b: PR CLOSED WITHOUT MERGING — unfinished work, do not delete" ;;
     esac
   done
   ```

   **Only `MERGED` is evidence the work landed.** A `CLOSED` pull request usually means abandoned,
   not merged, and this pass's resolution for a stale branch is deletion — so treating the two
   alike would delete the only copy of unfinished work. A closed-unmerged branch is a tail of its
   own kind: it takes `tracked:` or `blocked:` and its resolution is a **decision**, never a
   deletion. When this pass is unsure, it keeps the branch; nothing here is worth losing work over.

   **With no pull-request backend there is no reliable ancestry test for a squashed branch** —
   say that rather than substituting one that looks like an answer. `git cherry` does not rescue
   it either: a squash of N commits has one patch-id, which matches none of the N. What a *flow*
   has instead is better than any inference: it knows the branch it created, so it checks that
   branch by name. Only a session cleaning up after someone else is left guessing, and that case
   needs a human, not a command.
4. *(workspace)* **Open pull requests this run opened or pushed to** — correlate by head branch,
   not by listing everything:

   ```bash
   gh pr list --state open --json number,headRefName,url \
     --jq '.[] | select(.headRefName as $h | $OWNED | index($h)) | "\(.number) \(.url)"'
   ```

   where `$OWNED` is the set of branches this run created or pushed to. **A bare
   `gh pr list --state open` is wrong here**, and wrong in the same way source 2 was before it
   was scoped: in any repository with other contributors it returns their pull requests, and the
   sentence below would make each one this session's tail — so the pass could demand that work it
   neither created nor touched be tracked, closed, or otherwise resolved.

   An owned PR is a tail **unless leaving it open for human review was the session's stated
   deliverable**, in which case it is `resolved` and the report says so. One nobody asked to be
   left open is unfinished work.
5. *(completion, then workspace)* **Issues this session filed**, plus every item in a review
   report's `FILED` list. **Query the set this run recorded, not the repository's open issues** —
   `gh issue list` filters only by explicit flags and nothing in a bare invocation identifies what
   this run created, so listing everything would make every pre-existing issue in the repository
   this session's tail:

   ```bash
   # $FILED_IDS: issue numbers this run created; empty is normal and means nothing was filed.
   for n in $FILED_IDS; do
     gh issue view "$n" --json number,state,url --jq '"\(.number) \(.state) \(.url)"'
   done
   ```

   Each needs `tracked:` with its URL — **or the durable record its flow actually uses.**
   `quick-dev` has no ticket backend by design: it persists `FILED` work as `Deferred:` trailers
   on the squash commit, and in GitHub mode as the PR's own comment record. Demanding a ticket URL
   there would force an ad-hoc issue that the flow neither creates nor reads, or leave the closeout
   permanently unsatisfiable. A trailer or PR record that a later `git log --grep` can find **is**
   durable tracking; what is never acceptable is the item existing only in a report.

   **This one source spans both passes, because filing often happens after the merge.**
   `notion-dev`'s `epic-update` creates follow-up tickets in the record phase, and `quick-dev`'s
   `Deferred:` trailers are written by the squash commit itself — so at completion time the URL
   does not exist yet. The **completion pass** therefore requires only that every `FILED` item is
   carried forward with its criterion number into the list the filing step consumes; the
   **workspace pass** requires the URL, once the filing has actually happened. Demanding the URL
   before the filing step runs would either deadlock the pre-merge gate or force ad-hoc ticket
   creation outside the filing skill, bypassing its epic association and idempotency bookkeeping.
6. *(completion)* **Work already recorded as deferred** — `git log --grep '^Deferred:' --grep '^Unmet:'` across
   this session's commits.
7. *(completion)* **Verification** — run the project's full test / build / lint suite *now*. A failing check is
   a tail; so is never having run it. Do not report a session as done on the strength of a suite
   that last passed several commits ago.
8. *(workspace, on the finished draft)* **Your own draft report.** Every caveat, limitation,
   "note that", and unverified claim in it is a tail that has not been assigned a state.

   **This source is worthless unless the draft it reads already exists in final form.** It cannot
   run at completion time — the report does not exist yet — and it cannot run before the workspace
   pass, because the merge, record, cleanup, hook and workspace outcomes are written after that.
   So the order is: **compose the full draft, then run this source and step 2 over it, then send.**
   Inspecting a draft that predates the outcomes, and never re-reading the one actually sent, is a
   zero-tails gate that never sees the artifact it exists to check.

## 2. The phrase check

Search the draft report for these before it goes out — over the **finished** draft, the one that
already carries the merge, cleanup and workspace outcomes, not an earlier version of it:

> "one thing left" · "one honest note" · "worth flagging" · "remaining open"
> "the only remaining item" · "for a follow-up" · "should probably" · "left for later"
> "in a future session" · "not addressed" · "nice to have" · "TODO"

Each hit is a tail that reached the report without a state. **Do not soften the sentence.**
Resolve the item or give it one of the three states. Rewording is the exact failure this check
exists to catch: the phrase is the symptom and the unstated item is the defect, so deleting the
phrase while leaving the item is strictly worse than leaving both.

## 3. Resolve

Work the list. **`resolved` is the default; the other two must be argued for.** Wherever the work
is possible from here — a fix, a cleanup, a validation, a documentation correction, a version
bump, a re-run, a deletion — do it now. The question is never "is this worth another session?"
but "can this be finished in this one?"

Two bounds keep the closeout from running away:

- **Each lifecycle pass runs at most twice.** This is a *retry* bound, and it is counted
  **per pass** — completion may scan twice, and workspace may scan twice. It is not a budget of
  two scans that the two lifecycle passes above consume between them; reading it that way would
  mean a completion tail whose fix surfaced another tail could never be rechecked, since the
  workspace pass would have spent the remaining scan. Resolving items surfaces new ones, and the
  second scan of *that* pass is what covers them. Anything still open after a pass's second scan
  takes `tracked:` with a real URL, or `blocked:` with a named external cause. There is no third
  scan of either pass, and that is what keeps the closeout from becoming the thing that prevents
  the session from ending.
- **Do not start new scope.** A tail is something this session created, touched, or promised. An
  improvement merely *noticed* along the way is not a tail — at most it is a `tracked:` item, and
  usually it is nothing at all. Widening the session to fix everything observed is the opposite
  failure and costs just as much.

## 4. Report

End the final report with a closeout block. Every key appears on every run; a key with nothing to
report takes `0`, never absence:

```
CLOSEOUT:
TAILS-FOUND: <n>
RESOLVED: <n>
TRACKED: <n>
BLOCKED: <n>
PASSES: <1|2>
```

then one line per item that is not `resolved`:

```
- tracked: <item> — <url>
- blocked: <item> — <external cause>; unblocked by <what>
```

`TAILS-FOUND: 0` is a legitimate and common result: step 1's queries came back empty and the
draft passed step 2. It is not the same as omitting the block, which says only that the closeout
never ran.

**A session with `TRACKED: 0` and `BLOCKED: 0` is finished.** Say so plainly, with no hedge and
no closing caveat — the block above is the caveat, and it is empty. Making that the ordinary
outcome is what this skill is for.
