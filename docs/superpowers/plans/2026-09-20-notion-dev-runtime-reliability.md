# notion-dev milestone 1: runtime reliability and measurement

Implemented locally for version 0.32.0. This is the first slice recommended by the
STO-153 investigation, not the complete context/controller redesign.

## Delivered

- `scripts/runtime.py`: per-invocation durable state; measured stages and validation;
  prepare/attach/publish/wait/consume worker lifecycle; real elapsed deadlines;
  confirmed cancellation before replacement; immutable results; restart recovery.
- Full-source requirement inventory before implementation, including prerequisites
  outside Acceptance Criteria. Unknown/blocked mandatory conditions stop readiness.
- Independent completeness must cover the full source and every inventory ID.
  Parent-resolved evidence, source/input hashes, and the actual code revision must
  still match immediately before merge. Pending, degraded, stale or unmet results
  cannot pass. Labels and round caps cannot waive mandatory requirements.
- `ticket`, `next-task`, `finalize`, plan/scout/local-review/completeness and record
  prompts use the protocol. Stop-hook yields are one-shot and session-owned; they do
  not complete the ticket or reset/spend the normal stop-block counter.
- `scripts/telemetry.py`: read-only raw JSONL accounting, deduplicating streamed
  message IDs and distinguishing uncached input, cache creation, cache reads, output,
  peak input context, actual compactions, tool calls and available child logs.

Paths above are relative to `plugins/notion-dev`. The operational contract and CLI
examples are in [runtime.md](../../../plugins/notion-dev/references/runtime.md).
Runtime files live in the primary checkout's ignored `.claude/notion-dev/runtime/`
directory, outside disposable worktrees. Workers receive explicit paths and their
own result contract, not inherited shell-variable assumptions.

## Validation

- All 22 `scripts/verify-*.sh` harnesses pass on this Linux/WSL environment.
- 37 offline runtime/telemetry tests cover STO-153 timing, pending/late results,
  premature cancellation, whole-source prerequisites, stale evidence, changed code,
  second-pass current-head coverage, restart, real failure exit codes, one-shot yields
  and usage deduplication. Three in-memory mutations prove the tests detect a false
  merge pass, premature worker cancellation and streamed usage double-counting.
- Python sources parse against Python 3.8's grammar. UTF-8/LF output and configured
  interpreter selection are checked. The existing Windows CI job discovers the new
  harness; the windows-latest leg has since run on this PR. It first failed -- a bare
  `bash` resolves to the System32 WSL stub there, not Git for Windows -- and passes
  once `runtime.py` resolves the interpreter explicitly.
- New telemetry reconciles the available STO-153 parent/child logs: 293 requests;
  586 uncached input, 969,796 cache creation, 116,132,372 cache read and 254,065 output
  tokens. New-input-plus-output is 1,224,447; parent peak input context is 718,327.
  These are transcript counters, not an invoice or an optimized-run benchmark.

## Boundaries and next validation step

This helper is not a replacement agent host: prompts must invoke its CLI, host agent
IDs and cancellation confirmations come from actual host results, and a child must
publish before its final chat response. It cannot independently prove the semantics
of a requirement inventory, a citation, or a host cancellation. Those remain explicit
parent/independent-review obligations. The merge guard is a required command in the
workflow, not a server-side GitHub branch protection or an interception of all tools.

No test is cached/skipped. No knowledge bundle, epic brief, provider adapter or
third-party build-plugin internals were redesigned. quick-dev and its repo-local
mirrors retain their existing semantics. Historical audit artifacts under `optimize/`
were retained outside version control and are deliberately not part of this change. No
live Notion/GitHub mutation or plugin installation was performed.

A real Claude Code canary has since been run on this PR's head, in a disposable local
git repository with synthetic ticket data and mocked provider operations -- no live
Notion writes, GitHub mutations, deployments or BTC-Gateway changes. It exercised a
real dispatched agent publishing before its final reply (result available to the
parent 47s before delivery), delayed consumption (61.676s lag, measured), Stop-hook
yield/resume (one-shot, session-owned, counter neither reset nor spent) and a blocked
prerequisite refusing both `ready` and `prepare`. Results and the retained event trace
are recorded on the pull request. Actual host termination remains unexercised: the
runtime records `confirmed=True` on the parent's assertion, and nothing there verified
the host had really stopped the process.

Before using the new version on a production ticket, repeat the canary against
explicitly designated *provider* test resources, which the synthetic run deliberately
did not touch; confirm no merge or Done transition can precede consumption.
Then run one ready, representative ticket and collect the complete parent/child logs
plus runtime state. Compare stage times, cancellation waste, delivery lag, validation
repetition and the four usage counters against the baseline while independently
checking requirement coverage. No performance reduction is claimed until measured.

The canary needs the user's chosen test resources and permission for its intended
provider writes. The larger optimization milestones remain the roadmap in the audit,
not additional changes silently included in this implementation.
