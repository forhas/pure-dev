# Live plugin execution — 2026-09-01

Closes the behavioural gap issue #31 named: until this run, **nothing in this
repository had ever executed a skill**. The `scripts/verify-*.sh` harnesses assert
structure — that the right command strings, orderings and assertions are present
in the markdown — and structure is all they can assert, because a skill is
instructions for a model, not code.

This is the record of what happened when the flows were run for real. It is kept
because the next session will otherwise have to take "it was verified" on trust,
which is the same currency #31 was filed to stop spending.

## What was run, and against what

| flow | target | outcome |
|---|---|---|
| `/notion-dev:ticket PDS-1` | `forhas/pure-dev-scratch`, live Notion DB | merged as [#1](https://github.com/forhas/pure-dev-scratch/pull/1), squash `580a987` |
| `/notion-dev:finalize 2` | fork PR from `oinc-network/pure-dev-scratch` | merged as [#2](https://github.com/forhas/pure-dev-scratch/pull/2), squash `dd65c57` |
| `/quick-dev:develop --flow=feature-dev` | `pure-dev-scratch-local`, **local mode** | squash-merged locally, `01e24a7` |

The Notion database was a scratch database created for the run, with the full
canonical schema: a `unique_id` ID column with prefix `PDS`, Select `Status` /
`Type` / `Epic` / `Phase`, `Number` `Step`, `Date` `Creation Date`, `URL` `PR`,
`People` `Assignee`, `Checkbox` `Is Epic`, and a self-referential `Parent task`
relation.

Local mode was entered the way a user reaches it — a repository with no `origin`
remote — not by forcing a flag.

## What worked, first time

- **The configured reviewer really ran.** `@codex review` drew a real Codex review
  on both pull requests, within ~2 minutes each, reporting no major issues. The
  local fresh-agent fallback was exercised separately as local mode's reviewer;
  it returned `VERDICT: CLEAN` on a clean diff without manufacturing findings.
- **The Completeness gate caught a real false claim.** On PR #1 the verifier
  reported that the PR body's "the suite was green-by-accident" did not hold:
  `npm test` on `origin/main` exited 1 with `# fail 1`. Independently confirmed by
  extracting `origin/main` and running it. Triaged `absorb`, corrected before the
  merge. This is the gate doing exactly what it is for, on a claim written in good
  faith.
- **Every acceptance criterion was settled by a resolved citation**, not by an
  agent's say-so: commands re-run by the gate, a named test matched in the
  retained verification output, a code span content-matched in the diff.
- **The percent-encoding and singular-`ref`/plural-`refs` distinction** in the
  branch-deletion path behaved as documented, on both a same-repo and a fork PR.
- **The fork head-repository deletion path worked**: the head repo was resolved
  before any delete, the fork's ref was checked (`git/ref/heads/…`, singular) and
  then deleted (`git/refs/heads/…`, plural), and `origin` was never touched.
- **The "never re-run the merge" rule paid for itself.** `gh pr merge 2` returned
  `error connecting to api.github.com`; the merge had in fact succeeded. Checking
  state first, as the skill requires, found `MERGED` rather than merging twice.
- **The self-ignored `.claude/<plugin>/` directories** kept every ledger, criteria
  file and persisted report out of `git status` throughout.

## What did not — eight divergences, all fixed in the same pull request

Every one of these is a defect in the instructions, and none of them is visible by
reading the documents: each was internally consistent and simply did not match how
the MCP surface, GitHub, or git actually behaves.

1. **`unique_id` reads back prefixed.** `notion-fetch` returns the ID property as
   `"PDS-1"`; `notion-query-data-sources` returns `1`. Callers are told to derive
   "the numeric `<id>`" from it, which unnormalized yields
   `ticket/PDS-PDS-1-<slug>`. `fetchTicket` now normalizes what it read.
2. **Notion escapes brackets.** A title arrives as `\[PDS-1\] …`, which the
   title-prefix regex never matched — silently keeping the prefix in the branch
   slug (the exact shape the rule promises not to produce) and breaking
   `updateTicket`'s never-double-prefix idempotence.
3. **notion-dev worktrees had no container.** Cleanup's
   `rmdir "$(dirname <worktree-path>)"` therefore named the directory holding the
   primary checkout: a step that could never succeed, safe only because `rmdir`
   refuses a non-empty directory. Now `<repo>-worktrees/`, matching quick-dev.
4. **The closeout deadlocked local mode.** Source 2 treats a branch with no
   upstream as a tail; local mode has no remote, so every branch — including the
   primary's base branch — reported one, and pushing is precisely what that mode
   does not do.
5. **`finalize` could not recreate a fork PR's worktree.**
   `origin/<headRefName>` is not a valid object when the head branch lives in the
   fork: `fatal: Not a valid object name`. This was the one case step 3's deletion
   path goes out of its way to handle.
6. **The closeout misread a fork-PR worktree as never pushed.**
   `gh pr checkout` sets `branch.<b>.remote`/`.merge` but no tracking ref, so
   `@{upstream}` fails on a branch that is pushed and in sync.
7. **A Codex summary comment is not yet a review.** It appears within seconds,
   from the same bot login as the review, with its status reading `Running`. A
   loop watching only for a new comment from that author reaches the merge gates
   before the review exists.
8. **The scratch project's own test script** (`node --test test/`) resolved `test/`
   as a module on Node 22 and aborted before running anything. Not a plugin
   defect — recorded because it is what the Completeness gate's claim finding was
   about, and because it is a reminder that a suite can be red without saying so.

`scripts/verify-ticket-system.sh` guards 1, 2, 3 and 7 as standing invariants;
`scripts/verify-session-convergence.sh` guards 4 and 6;
`scripts/verify-post-merge-ordering.sh` guards 5. Every check was mutation-proven
against the file it guards.

## What this does not cover

Stated so the next reader does not over-read the table above. These are facts
about the run's scope, not open work:

- The `superpowers` build path (`writing-plans` → `plan-review` →
  `subagent-driven-development`) was not exercised: triage scored PDS-1 at 5/24
  and chose `feature-dev`, and the local-mode run forced `feature-dev` too.
- No epic container was created, so `epic-update`, `findEpics`, `createEpic` and
  `getEpicContext` ran only on their no-epic paths.
- No review round produced a code change, so the multi-round loop, the severity
  ratchet, the oscillation guard and the round cap were not driven — those are
  covered instead by this repository's own PRs #23, #24, #28 and #29, which drove
  them through the `.claude/` mirror.
- `/notion-dev:create-task` and `/notion-dev:init` were not run as commands; the
  ticket and the config were produced by following their documented output shapes.
