# notion-dev 0.36: lean ticket execution

This release implements the three changes identified after the STO-156 investigation.
The implementation is project-independent; it neither changes BTC-Gateway nor performs live
Notion, deployment or GitHub provider writes during its offline tests.

## Default ownership

```text
next-task: live selection + retained source references
  → ticket: full-source readiness → owned worktree → cohesive implementation → validation
  → review-and-merge: configured external review → one independent code/completeness worker
  → shared inline record: immutable operation plan → provider writes/readback → journal
  → closeout
finalize: resume the original invocation at review or recording (including after cleanup)
```

The controller implements a cohesive ticket rather than producing a code-transcription plan
and repeatedly briefing task, specification and quality agents. A bounded design reviewer or
scout remains appropriate for concrete architectural risk or unanswered questions. The combined
independent reviewer retains full-ticket coverage, code quality, claims/caveats and evidence checks.

## Three changes

1. **Reliable handoffs and evidence reuse.** Runtime schema 3 generates and validates worker
   result contracts. Malformed unpublished output is repaired by the same worker; an honest
   nonpassing review remains valid output. Questions and answers are durable, visible before
   chat delivery, and excluded from execution deadlines. Only one shell waiter owns a worker.
   The configured verification runner consumes current passing receipts and reruns stale/failed
   checks. Telemetry correlates decorated host agent filenames without guessing ambiguous names.
2. **Lean default orchestration.** The four main entrypoints load only their current stage's
   references. Build frameworks are optional legacy overrides. Review fixes are batched by
   cohesive change, not one full suite per comment. External review defaults to three rounds;
   existing explicit configuration wins. An unavailable/slow external reviewer uses the same
   internal seat, subject to user authority and required provider approvals. Late feedback is
   still checked before merge. Runtime enforces two full/two delta internal attempts, including
   failed attempts; exhausting a budget does not waive required work.
3. **Shared recording.** Ticket and finalize run one inline routine. Stable operation IDs and
   payload hashes distinguish execute, skip and reconcile. Confirmed effects cannot be reset
   to replay; uncertain effects cannot be blindly retried. Per-mutation/per-hook child receipts
   protect partial recovery. No-follow-up epic updates avoid loading ticket-creation machinery.
   Knowledge capture uses the retained technical delta, not a second investigation.

## Safety and compatibility

- Authoritative requirements, prerequisite readiness, independent review, real evidence,
  current HEAD/base/body, CI, thread resolution and explicit merge authorization remain gates.
- Git and provider actions retain existing ownership, exact-target, primary-lock and readback
  requirements. The local helper cannot establish a remote effect or prove a host process stopped;
  it records evidence supplied by the authorized host. Unknown stays unknown.
- Ignored inputs, tool/service versions and relevant environment values must be declared for
  verification reuse. Otherwise run that check without reuse. A log alone is not complete evidence.
- Python 3.8+, UTF-8/LF, Windows-native Git Bash and Ubuntu/WSL2 are supported. Helpers use the
  configured interpreter, standard-library locks and Git; no POSIX-only locking API is added.
- Existing schema 1/2 invocations retain their contracts and budgets. Explicit legacy build flows
  and old-run recovery load references/legacy; new lean runs do not. Historical prompt harnesses
  test those retained contracts. verify-lean-workflow.sh tests the actual new default, including
  negative cases and isolated prompt mutations. Shared executable runtime tests remain active.

## Live evaluation after merge

Update the plugin and start a fresh Claude Code session for one representative real ticket using
next-task with the same reviewer/config as the baseline. Do not add a --flow legacy override.
No disposable project is required. Preserve the raw parent/child JSONL and invocation artifacts.

Compare fresh input/output, cache reads/writes and peak parent input separately; also compare
wall time, time to first implementation/PR-ready, requests, workers, review attempts, wait calls,
question delay, verification executions/reuses, record operations/reconciliations and compactions.
Check quality separately: all mandatory requirements, regression checks, late-discovered
requirements, unresolved findings, and correct Notion/knowledge/epic outcomes.

**Disposition: `blocked`.** Do not claim ticket-level token/time savings from reduced prompt
bytes or passing unit tests. External cause: a real token/time figure needs a representative
live ticket run against a client repository, which no offline test can substitute for. The
real-ticket run below is what unblocks it, and it determines whether this structural change
improves the baseline. Stop and
diagnose unexpected repeated reviews, stale-evidence reuse or replayed provider effects; preserve
the existing invocation rather than resetting its budget.
