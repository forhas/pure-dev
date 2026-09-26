---
description: Resume an existing ticket PR at its first incomplete review or recording stage.
argument-hint: "[<pr-number>] [--non-interactive]"
---

# /notion-dev:finalize

This is a resume entrypoint, not a second implementation of ticket/review/record.
It does not change requirements, skip review, or authorize deployment.
Invoke only at the user's request or as recovery within an authorized ticket/next-task run.

1. Resolve the primary checkout (first `git worktree list --porcelain` entry), load its config,
   and use configured `knowledge.python` for `python3` examples. Probe `gh auth status`.
   Infer an **open** PR from the current branch only when no number was supplied. With an explicit
   number accept OPEN or MERGED; reject drafts and CLOSED-without-merge.
2. Fetch PR identity/head/base/state, derive the configured ticket key from its branch, and
   fetch the full ticket with ticket-system. Find the matching owned run marker/runtime in the
   primary `.claude/notion-dev/`. Resume that invocation, preserving review budgets and completed
   operations. Exhaustion uses `references/review-accounting.md`, never a fresh budget.
   A legacy flow marker or schema 1/2 runtime uses `references/legacy/finalize.md` instead.
3. For a lean run, follow `references/lean-intake.md`'s resume/ownership rules. Stop before
   any write if another session owns it or an earlier worker is unaccounted for. Adopt the
   marker for this host session only after ownership is resolved. Create a preflight marker
   with `workflow.py preflight`; never hand-edit runtime or ownership state.
   If no prior runtime exists, create one with `workflow.py preflight` and `runtime.py init`,
   save the full source and inventory, and establish requirements readiness for an OPEN PR.
   A MERGED PR can enter recording recovery without pretending unmet requirements are met.
4. **OPEN:** use the actual PR worktree and branch. If missing, fetch and create a detached
   worktree, then `gh pr checkout <pr>` there; this supports fork PRs without assuming
   `origin/<headRefName>` exists. Confirm it matches the PR's current HEAD.
   Recover retained context/evidence, register changed requirements honestly, and invoke
   `notion-dev:review-and-merge`. Never rebuild a completed plan.
5. **MERGED:** skip review and merge entirely. Confirm merge SHA/base from GitHub. Recover the
   persisted structured review result and requirement evidence; if unavailable, inspect PR
   records and source. Missing verdicts remain unknown—do not tick AC from a merge alone.
6. In either case read `references/record.md` and run that exact shared routine inline, using
   the existing journal to reconcile or skip completed operations. No copied cleanup/status
   implementation and no replacement record agent.
7. Run the workspace closeout pass, report actual outcomes and evidence paths, then mark the
   owned marker complete through `workflow.py complete --state "$RUNTIME_STATE" --marker "$RUN_MARKER"`.
   On failure preserve work, mark stopped with cause, and report the
   exact resume path. No requirement to create a disposable test project.

Before invoking review in step 4 or recording in step 6, bind the verified PR using:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" resume-pr --project "$REPO_ROOT" --preflight <preflight-marker> --ticket <key> --state "$RUNTIME_STATE" --worktree <pr-worktree> --branch <pr-branch>
```
Add `--merged` only after GitHub confirmed MERGED; this allows recording after the worktree
has already been removed. Save the returned marker as RUN_MARKER. A running foreign owner
or unaccounted worker blocks adoption. Preserve the original runtime and invocation identity.

Non-interactive follows authorized work through completion. Worker waits/questions follow
`references/runtime.md`; safe yield is not abandonment. Never repeat provider writes because
a human-readable report is malformed. Never override a user's no-agent or no-merge instruction.
