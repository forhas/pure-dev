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

## 1. Enumerate — from sources, never from memory

Do not recall what is outstanding; **query it**. Recall is what produces "one thing left".

1. **Uncommitted work** — `git status --porcelain` in the primary checkout and in every worktree
   (`git worktree list --porcelain`). Non-empty is a tail.
2. **Unpushed work** — `git rev-list --count @{upstream}..HEAD` non-zero is a tail.
3. **Leftover worktrees and branches** — a worktree or local branch whose work has merged is a
   tail. `git worktree list`, then `git branch --merged <base>`.
4. **Open pull requests** — `gh pr list --state open`. Each is a tail **unless leaving it open
   for human review was the session's stated deliverable**, in which case it is `resolved` and
   the report says so. An open PR nobody asked to be left open is unfinished work.
5. **Open issues this session filed**, plus every item in a review report's `FILED` list —
   `gh issue list --state open`. Each needs `tracked:` with its URL at minimum.
6. **Work already recorded as deferred** — `git log --grep '^Deferred:' --grep '^Unmet:'` across
   this session's commits.
7. **Verification** — run the project's full test / build / lint suite *now*. A failing check is
   a tail; so is never having run it. Do not report a session as done on the strength of a suite
   that last passed several commits ago.
8. **Your own draft report.** Read it before sending. Every caveat, limitation, "note that", and
   unverified claim in it is a tail that has not been assigned a state.

## 2. The phrase check

Search the draft report for these before it goes out:

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

- **It runs at most twice.** Resolving items can surface new ones and the second pass covers
  those. Anything still open after pass 2 takes `tracked:` with a real URL, or `blocked:` with a
  named external cause. There is no pass 3, and this is what keeps the closeout from becoming
  the thing that prevents the session from ending.
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
