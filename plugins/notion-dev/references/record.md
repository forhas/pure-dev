# Shared post-merge record routine

Ticket and finalize execute this routine inline, once per merged ticket, using the existing
runtime journal. No generic record agent, new investigation, or duplicated finalize path.
`python3` denotes configured `knowledge.python`, on Windows Git Bash and Ubuntu/WSL2.

## 1. Establish facts and authority before writes

Record runtime stage `record` and update the owned marker. At completion, use stage `closeout`
for the workspace pass so provider/cleanup time is not charged to implementation or review.
Confirm the PR is MERGED using GitHub; capture full merge SHA, actual base, strategy, merged
timestamp and URL. Load the retained ticket metadata, structured independent review,
verification receipts and compact technical decisions. Do not reconstruct them from chat.
A missing review on merged-PR recovery remains unknown; do not infer all AC met from MERGED.

Resolve any interactive FILED follow-up decisions BEFORE acquiring the primary lock. Pass only
approved FILED items to creation; ABSORBED, DROPPED and externally BLOCKED items are not new tickets.
Missing/unknown filing history cannot mean no follow-ups. Preserve it and reconcile the PR record.

Save immutable `record-facts.json` beside runtime state with:
```json
{
 "ticket":"<key>","ticket_url":"<url>","pr_url":"<url>","merge_sha":"<full SHA>",
 "base":"<actual base>","strategy":"<strategy>","merged_at":"<timestamp>",
 "requirements":"<structured review path, or explicit unknown on merged recovery>",
 "verification":"<receipt index path>","review":"<structured result path>",
 "epic":"<page id or null>","followups":[],
 "knowledge_delta":[{"fact":"<new durable fact>","evidence":"<source/commit reference>"}],
 "worktree":"<owned worktree>","branch":"<owned branch>","hooks":["<configured skills in order>"]
}
```
Requirements, verification and review may be embedded structured objects instead of paths.
A path-valued one is recorded in the payload as `{"path":…,"sha256":…}` — its **content**, not
its name, is the operation's identity, so repairing or re-running the artifact it points at
forces reconciliation instead of a silent `skip`. Read the payload's `path` to load it. A
string that is neither a readable file nor exactly `unknown` is **refused at planning**:
recording the path text as though it were embedded evidence would confirm — and then skip —
a resolution with no evidence bound to it at all.
An empty knowledge delta is legitimate; do not invent a knowledge change to fill a field.
Store additional approved filing decisions and existing outcome reports by reference.
Fields describe observed facts, not fabricated placeholders.

Acquire `knowledge.py lock take --run <invocation> --section record --wait 3600`.
On failure stop with the actual lock owner/cause. Report stale-lock recovery.
Pass `LOCK_HELD: true` to invoked skills; they must not take/release it again.
Remain in the primary checkout for recording/cleanup. Always release after the routine unless
an unconfirmed live writer could still perform side effects; then preserve the lock and report.

## 2. Plan, execute and reconcile operations

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" record-plan --state "$RUNTIME_STATE" --facts <record-facts.json>
```

The helper emits immutable payload files and stable operation IDs. For each operation:
- **skip:** the same payload is already confirmed; consume the receipt.
- **execute:** journal `record-op --operation <id> --target <target> --outcome attempted
  --digest <data_sha256>` BEFORE the authorized write.
- **reconcile:** a previous response was lost or execution interrupted. Read the affected
  Notion section, merge/hook receipt or Git state. Confirm only when the intended effect exists.
  Record failed only after proving no effect occurred; then a retry may execute. Unknown stays
  unknown-outcome and requires resolution, never a blind retry.

After a response/readback confirms the effect, journal confirmed with the same operation,
target/digest and actual provider ID or durable receipt path. Use distinct child operations
for multi-write steps and EACH configured hook so a partial step cannot repeat completed
side effects. The parent operation confirms only after all children are confirmed or explicitly
not applicable. Keep payloads stable on resume; changed intent needs explicit reconciliation and
a new operation revision. A report-format problem does not change any operation's outcome.

## 3. Operation meanings and order

1. **ticket-status:** ticket-system `updateStatus(id, "implemented")`. Never advance to deployed/
   released. Re-read status to confirm; use the configured status map.
2. **ticket-resolution:** reuse the adapter operation references already loaded. Preserve
   `Implementation`; append its Completeness evidence once, refresh AC only from matching
   independently verified verdicts, and upsert `Merged` with merge/PR/base/test/review facts.
   Check existing sections for this exact PR/SHA before appending. Retain unmet/unknown verdicts,
   release obligations and approved scope decisions. Batch compatible provider updates where
   the adapter supports it, without replacing unrelated/user-edited content.
3. **epic-record:** invoke epic-update with retained ticket/epic identity, REVIEW_REPORT,
   approved FILING_DECISIONS, REPO_ROOT and LOCK_HELD. With no FILED items, take its short
   resolution-only path; do not load follow-up interview/creation instructions. Capture
   EPIC_REPORT and actual created ticket URLs. Missing epic is an explicit no-op.
4. **cleanup:** first confirm MERGED and check the exact owned worktree/branch. Preserve a
   surviving PLAN/context artifact outside it. Do not force-remove dirty work or another
   session's checkout. Remove the owned clean worktree, then the merged local ticket branch;
   verify/delete only its authorized remote branch. From primary, checkout the actual base and
   pull --ff-only. If pull fails, inspect and report primary changes before doing anything else;
   never stash/discard someone else's work. Remove only the empty worktrees container with rmdir,
   never a recursive deletion of the parent. The run marker remains live through recording.
5. **knowledge-delta:** the supplied delta is already the technical synthesis. Preserve it as
   the input to the configured knowledge hook; this step itself performs no duplicate capture.
   Empty or hook-not-configured is stated explicitly, not passed off as a capture.
6. **post-merge-hooks:** run configured skills in order, with one journal child operation each.
   Before EACH hook require primary branch == base, merge SHA ancestor of HEAD, and HEAD ==
   origin/base after fetch. Missing prerequisites skip/record the failure, never run on an
   assumed checkout. Supply ticket metadata/body, merge facts and knowledge_delta. For
   notion-dev:knowledge call capture once with that delta; validate it against the merge and
   affected concepts, without synthesizing it again. Honor existing hook checkpoints on legacy
   recovery; an arbitrary hook with unknown external outcome must not be rerun automatically.
7. **epic-brief:** invoke epic-doc record with EPIC_REPORT, REVIEW_REPORT, completeness report,
   completion-closeout and a small facts-based DRAFT_REPORT, LOCK_HELD, base and merge SHA.
   Pass every required name explicitly, including absent/unknown signals. It owns the brief,
   live child/dependency refresh, concurrency-safe commit/push and meaningful NEXT output.
   Never copy the full review narrative into knowledge and then again into the brief.

Before each provider write read the current target revision where needed. Preserve concurrent
edits; a stale full-page replacement is not a valid batch optimization. All knowledge/epic commits
use their existing safe write path, exact pathspecs and bounded rejected-push convergence.
Never force-push. A confirmed merge does not imply successful recording.

## 4. Close the record

Save one `record-result.json` with these eight outcomes:
`EPIC-REPORT`, `TICKET-RECORD`, `CLEANUP`, `CLEANUP-STEPS`, `HOOKS`,
`EPIC-DOC-RECORD`, `EPIC-DOC-NEXT`, `ISSUES`.
Generate `workflow.py record-summary --state "$RUNTIME_STATE"` from the operation journal
first; use its facts and attach the actual epic/knowledge output references. A missing field
is repaired from receipts, not by repeating the operation. Preserve failures and skip reasons.

Append the existing ledger's outcome once per invocation (read prior event/session first),
with real plan-review metrics only if that review ran. Sweep unexpected issues once.
Runtime summary is the canonical operational measurement; do not ask another model to tally it.

Release the lock. Caller performs workspace closeout over the finished report and owned
artifacts. Report merge success separately from partial recording, preserving exact unknown/
failed operations and recovery command. Only fully reconciled required record operations permit
`OUTCOME: resolved`; best-effort knowledge/brief failures remain explicit in their outcome fields,
never hidden by that label. Do not load old code-review history to make the final report longer.
