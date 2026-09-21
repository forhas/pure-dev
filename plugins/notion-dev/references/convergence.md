# Convergence slice: rollout and measurement

This slice targets repeated completeness work after branch/body mutations, unregistered
flow reviewers, and repeated context transport. It does not replace the knowledge graph,
change Notion schemas, relax requirements, or skip configured validation. All changes
belong to notion-dev; use synthetic projects to exercise them.

```text
next-task: select + artifact references
  ticket: validate source → claim → start brief → synchronize fresh worktree
    scout/plan → scoped implementation workers → registered branch reviewer
      review loop → stabilize base/version + mutating closeout/checks
        freeze inputs → full completeness → resolve citations
          small correction? → validate → independent delta (max 2)
            read-only freshness + runtime gate → merge → record
```

## Contracts

- `prepare` now returns a context packet path instead of inline inventory/files.
  The packet indexes full source/inventory and byte-preserving input snapshots.
  This reduces transport, not the reviewer's responsibility to read relevant evidence.
- A delta requires the latest accepted complete inventory review and clean committed
  revisions in the same worktree. It compares entire trees, not only this PR's commits;
  incoming base changes and deleted files are included. Hashes identify change, never
  infer semantic safety. The fresh reviewer checks all requirements' indirect effects,
  code correctness, claims and caveats, or requests full review.
- Changed requirements or insufficient scope need a full review. Two full passes are
  a workflow limit; two delta preparations (including failed ones) are enforced in code.
  Termination/invalid-report recovery does not replenish them. Never initialize a fresh
  invocation to bypass a stopped run's budget.
- Selected reviewers remain independent; build-flow slots permit disjoint tasks/seats,
  not parallel replacements for the same task. Pending branch reviewers block merging.
- Snapshot/state directories must be outside disposable worktrees and self-ignored.
  They contain ticket/code data; keep existing local access controls and do not upload
  them as PR attachments. Historical snapshots deliberately use disk to save context.
- No host API is invented here: the prompt adapter supplies the lifecycle contract to
  actual agents. An adapter that cannot publish/attach is unsupported and stops honestly.
  Offline tests do not establish live adapter support. **Disposition: `blocked`** —
  external cause: establishing it needs a live Claude Code host session, which offline
  tests structurally cannot provide. Unblocked by the canary run below, which also
  discharges the unmeasured savings targets; no release is claimed until it runs.

## Acceptance and canary

Offline regressions must cover stale-head rejection, exact delta binding, full inventory
coverage, bounded attempts, honest escalation, changed/deleted/Unicode paths, snapshot
integrity, claim corrections, pending whole-branch review, stable implementation slots,
and the ordering of mutation versus completeness. Run every `scripts/verify-*.sh`.
Both CI legs must pass (Windows Git Bash and Ubuntu); no native Windows result should
be inferred from a Linux test run.

Before release, run a real Claude Code canary on explicitly designated disposable
resources with synthetic requirements and mocked providers, once on native Windows
and once on Ubuntu/WSL2. This document grants no provider-write permission. Exercise:

1. A base advance caused by start bookkeeping is synchronized before implementation.
2. Both build-flow adapters register every actual agent, including the whole-branch
   reviewer. Delay its mailbox; consume the durable result without replacing it.
3. A clean full review followed by a small comment/claim correction produces a delta
   receipt, not another whole investigation. All mandatory verdicts still resolve.
4. A late base change affecting behavior requests broader review or blocks; unchanged
   citation bytes must not manufacture a pass. Changed requirements require full review.
5. Resume from `stopped` retains worker IDs/budgets and records the actual resumed stage.

Record full and delta attempts separately (`runtime summary`), actual dispatch count
versus registered worker count (coverage must be 100%), delivery lag, time to first
implementation/PR-ready, late requirement defects, repeated verification signatures,
and authoritative source refreshes. Use raw parent + child JSONL for per-stage fresh
input/cache creation/output/cache reads and peak context. Report missing logs as unknown.

Compare at least three normal tickets against the measured baseline; one synthetic
canary validates behavior, not savings. Success: no correctness regressions, no stale
receipt accepted, no redundant full review caused solely by run-owned bookkeeping,
and reduced median total tokens/time. Keep <200K peak context and roughly <1h as goals,
not achieved measurements. If parent context still dominates, the next measured slice
is knowledge retrieval and command/stage separation, not weaker completeness checks.

## Reliability follow-through (0.33.1)

Issues #61, #64 and #66 add live dependency diagnostics, OS-released state locks, and
an explicit code-review obligation for terminal-sweep corrections. The first full
completeness worker can review that patch without an earlier completeness baseline;
the runtime gate requires a separate exact-manifest code verdict. No extra worker
round is introduced. Use `references/runtime.md` for lock migration and host boundaries.

Offline coverage includes local disablement over project enablement, stale hints in
both directions, real killed/live lock holders, and sweep-correction rejection when
the independent code verdict is absent, not clean, stale, or mismatched. Extend the
synthetic canary with those three cases on each host; offline tests cannot establish
host prompt compliance or measured token savings. The existing release validation
boundary above remains; these fixes do not claim a new measured token/time baseline.
