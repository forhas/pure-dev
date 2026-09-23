---
name: review-and-merge
description: Review and merge a ticket PR with one independent code/completeness review, reusable evidence and bounded delta checks.
---

# review-and-merge

Inputs: PR number; optional --non-interactive, --criteria-file, --pre-merge-check; caller
REPO_ROOT, RUNTIME_STATE, RUN_MARKER and authoritative source/inventory when available.
Standalone use resolves the primary checkout/config and establishes source/readiness first.
For a schema 1/2 runtime or explicit legacy build flow, read
`${CLAUDE_PLUGIN_ROOT}/references/legacy/review-and-merge.md` instead; do not reset the run.

Use configured knowledge.python for all `python3` examples. Native Windows runs in Git Bash.
Read `references/runtime.md` before dispatch. No mandatory external build-framework skill.

## 1. Resolve and stabilize

Fetch the PR's state, draft flag, actual base/head/mergeability and configured reviewer.
Reject closed-unmerged/draft PRs; a MERGED PR returns its confirmed merge facts without another
merge. Work in the PR worktree, not primary. Require a clean committed branch; preserve unrelated
edits. Honor user prohibitions on merge, agents, reviewers or provider writes.

Read the primary config: reviewer codex/copilot, git.mergeStrategy, git.preMergeChecks,
reviewsCap. Missing reviewer: ask interactively; otherwise use codex and report the default.
Do not rewrite config. Default external round cap is 3 on the lean path; honor an explicitly
configured positive integer. A cap never permits merging unresolved mandatory work.

Read `references/github-api.md` in THIS skill for paginated comments/reviews and GraphQL
threads. A failed read is not an empty result. Check all existing human/bot findings before
triggering another review; never reply twice or reapply an already-applied fix.

Fetch the actual PR base. Reconcile branch/base safely before final tests; never force-push or
retarget. Any configured preparation that changes code happens before freezing review inputs.
Run configured verification through `workflow.py verify`; reuse valid passing receipts.

## 2. Configured external review

Record runtime stage `external-review` and update the owned marker.
Before EVERY trigger, save validated JSON arrays of existing review IDs and Codex issue-comment
IDs; for Copilot also snapshot matching review_requested timeline event IDs. Save pre-call UTC
and current HEAD. Use pipefail for pipelines; unset/invalid JSON is a failed read, not `[]`.
Correlate new responses by ID, not a strict timestamp comparison (timestamps have one-second
precision). Inline comments belong to review IDs, not the issue-comment snapshot.

Codex: comment `@codex review`. Copilot: request
`copilot-pull-request-reviewer[bot]` via the GitHub requested_reviewers endpoint.
Accept Codex connector responses; Copilot's review object and inline comments use different
logins—use the API reference to correlate them. Only a response attributable to this request
and current reviewed HEAD counts. Capture trigger time/response IDs and reviewed SHA.

Wait with a blocking host/task mechanism, at 30-second provider polling intervals, not a model
turn per rapid status check. Reuse one outstanding waiter. Read all pages of review summaries,
inline comments and issue comments. For Copilot use the REST requested_reviewers endpoint, not
`gh pr view reviewRequests`, to distinguish slow from absent. A trigger error has an unknown
outcome: reread its effects before retrying; never blind-retry a mutating API call.

If there is a transport/auth/rate-limit failure or reviewer silence, load
`${CLAUDE_PLUGIN_ROOT}/references/reviewer-recovery.md` for bounded recovery/fallback.
Do not infer “not configured” from a status code or a failed read. Once switched to local
review, do not retrigger that external seat during this run. If the user prohibited fallback,
stop rather than substituting a reviewer.

For findings, read `${CLAUDE_PLUGIN_ROOT}/references/review-findings.md` before triage.
Evaluate suggestions against code and requirements; do not implement speculative/cosmetic churn
just to clear comments. Maintain ABSORBED / FILED / DROPPED / BLOCKED with evidence.
Mandatory ticket requirements cannot be waived by any label; scope reduction needs user authority.
A genuine external blocker needs its cause/unblocker, not a newly invented follow-up ticket.

Fix accepted findings in this PR, validate through the shared runner, commit/push, and resolve
threads after replies are posted and verified. Re-trigger only after source changed and within
the external cap. If there is nothing actionable, finish this loop. A stopped/exhausted loop
with unresolved mandatory work is a stop, not a merge. No final-sweep review is needed when
there are no deferred candidates; when candidates exist, apply the findings reference's bounded
sweep before the final evidence boundary, including independent review of any resulting code.

## 3. One combined independent internal review

Record runtime stage `internal-review` and update the owned marker.
This replaces separate whole-branch-code and completeness agents on the lean path. It is also
the local fallback when the external seat is unavailable; do not run another overlapping local
agent first. Its obligations include code quality, not only AC checking.

Before the first internal review, refresh the full ticket after this run's start/Implementation
writes. On schema 5 use `capture-ticket --page <notion-page-uuid> --config <primary-config>`;
schema 4 keeps `ticket-source` on the raw fetch. Reconcile the inventory; this puts
our bookkeeping changes before the evidence freeze, not into an avoidable post-review delta.
Never discard new human requirements while reconciling. Then freeze the authoritative ticket, inventory, committed diff against the actual PR base, live PR
body and verification receipt/log references outside the worktree. Run readiness. Prepare
role `completeness` with those named files and the exact worktree. Dispatch one independent
general-purpose worker with the generated runtime context/contract and these charges:

- Check the entire ticket against inventory, including prerequisites outside AC.
- Review implementation, contracts, error paths, test isolation and edge cases; tests must
  exercise the claimed behavior, not pass because of earlier calls or unrelated fixtures.
- Return met / not-met / unverified with evidence for every inventory ID.
- Audit claims and caveats in changed code/docs/PR body. Preserve release-only obligations
  without making up a merge prerequisite or claiming approval that was never given.
- Return code_review, requirements_complete, requirement verdicts, blocking_findings and
  structured claims/caveats/triage audits (including evidence and finding dispositions) in
  the generated JSON contract. A failed check is a valid nonpassing report, not malformed output.

Freeze author-written ticket narrative until recording. Continue required live status/ownership
checks and property updates, but keep review-history/Implementation corrections in the canonical
local decision record until the post-merge write. Never ignore human changes in those sections.

The reviewer gets no author conversation, plan, or conclusions. It may run targeted tests when
a concrete doubt warrants them, but starts from existing applicable logs. Source references
are retrieval entry points, not instructions to read every listed file in full.
Follow runtime wait/question/publication/acceptance; format repair stays with the same worker.

Resolve the returned citations against real artifacts and dependencies. Retain the structured
result as canonical; render reports from it. Missing fields never trigger a fresh investigation.
Keep the persisted compatibility report's triage lists for ticket/epic consumers.
Render COMPLETENESS_REPORT with runtime-derived counts, VERDICTS from the structured requirement
objects, and runtime-rendered CLAIMS / CAVEATS / TRIAGE evidence. A checked audit with empty
findings explicitly means NONE; unverified stays unknown and blocks merge, never inferred NONE.
Honor an in-flight worker's original packet contract; do not require it to republish as a newer version.
Keep REVIEW_REPORT's ABSORBED / FILED / DROPPED / BLOCKED lists from the findings ledger.
Persist both named objects in one review artifact; do not paste the completeness report twice.

When findings require changes, register `correction-needed` BEFORE source edits, fix and verify,
then prepare a delta against the accepted prior review. A PR-body-only correction with unchanged
code checks changed claims and indirect effects; carry forward independently verified unaffected
verdicts with valid evidence. Do not rerun a full review merely to generate new prose.
Broader changes or uncertainty require full review within the invocation's two-full/two-delta
budgets. A budget exhausted with unresolved work stops; no new invocation resets it.

Before that delta, batch each correction across its affected code/docs/PR occurrences. Search
for the retired assertion, replace it in place, and verify the whole affected set; do not append
a correction story while retaining the false original. Put deferred Notion narrative changes
in accepted recording facts. A new factual assertion still needs evidence and independent
review; calling it non-blocking is not a waiver. Keep decision/reason/evidence/release obligations
once in the local decision record and derive concise required summaries from it.

Resolve available baseline citations BEFORE preparing that delta. Omitted named inputs are
inherited/rehashed; use --remove-input only for intentional removals. Read correction_reuse when
present: the runtime carries the prior independent verdict at unchanged code/dependencies, so
do not demand a new correction report or retest unchanged code merely to fill a report field.
Carry corrected claims, release obligations and the evidence-backed technical delta into the
generated `recording` fields before publication; downstream knowledge uses those fields.

For a version-4 delta packet, use its `delta_publication` contract: changed judgments plus
explicit reused IDs/sections. Read changed hunks and prior-judgment references first; retrieve
full prior sections only for an affected claim or a specific doubt. Runtime assembles the full
result. Check indirect effects on EVERY requirement, retain all audits and release obligations,
and recheck stale/unknown evidence; no automatic "comments are safe" rule. Do not regenerate
the complete prior report to fill fields. Old packet contracts remain unchanged.

## 4. Final gates and merge

Run the completion pass of `notion-dev:session-closeout` plus caller `--pre-merge-check` and
configured `git.preMergeChecks`. Consume current evidence; do not require a new suite because
the phase changed. Any check that changes source/claims invalidates relevant evidence and returns
through review. On plugin repos ensure the manifest version still exceeds the current base.

Immediately before merge:
1. Re-fetch the authoritative ticket and refresh its source file on legacy schema 1–3 runs.
   On schema 4/5 perform the guarded full-fetch receipt at step 5 below, after potentially slow
   checks. Changed requirement-bearing content invalidates inventory/review even when the
   criterion count is unchanged; never edit the ticket to pass the gate.
2. Re-fetch live PR HEAD/base/body and require equality with reviewed inputs. Base movement
   triggers safe stabilization and applicable rechecks, not silent retargeting.
3. `gh pr checks <pr> --required`: all required checks pass, none pending. No checks reported
   is different from a read failure. Also check all checks: a failing optional check blocks;
   a pending optional check alone does not. Required-check timeout (~15m) stops.
4. Re-query ALL GraphQL thread pages in a standalone command. Every thread resolved.
   Also fetch new review bodies and issue comments, including late external responses during
   fallback. Triage new substantive feedback. Empty/failed output is not proof. Every absorbed
   finding has an actual fix.
5. Schema 4/5: `runtime.py --state "$RUNTIME_STATE" refresh-ticket --worker <accepted-review-id>`,
   then a NEW full notion-fetch of its exact page. Schema 5 finishes with `capture-ticket
   --worker <accepted-review-id> --request <token>`; the helper extracts
   the real response from this session's host transcript. Schema 4 keeps `refresh-ticket`
   with --request, --response and --call-id per references/runtime.md.
   Status queries and old local copies do not qualify. Failed/changed/stale receipts block.
   Re-inventory/review changed requirements; if only the 5-minute receipt expired, fetch again
   without repeating unchanged review. Then `runtime.py --state "$RUNTIME_STATE" merge-gate --worker <accepted-review-id> --worktree "$WORKTREE"`
   must pass. It covers requirements, code review, citations, snapshots, corrections and workers.
6. Respect explicit user merge approval conditions. Merge using configured strategy and
   `gh pr merge <pr> --<strategy> --match-head-commit <reviewed-head>`.
   On error re-read state before retrying; the merge may already have happened.

Confirm MERGED and actual merge SHA/base. Delete only the remote PR branch where authorized;
local worktree/branch cleanup belongs to the shared record routine. Do not delete unmerged work.
Persist the structured review, evidence paths and human report under the invocation and
`$REPO_ROOT/.claude/notion-dev/review-report-<key>.md`; ensure THIS write succeeded, not merely
that an older file exists. Return PR/merge facts and triage lists to the caller. No post-merge
re-review loop.

## Safety

Failed reads, empty results and missing evidence never authorize merge. Do not fabricate clean
verdicts, tick unverified AC, or reduce validation to meet a time/token target. Stop on unsafe
conflicts or missing authority, preserving all artifacts and the exact resume command.
