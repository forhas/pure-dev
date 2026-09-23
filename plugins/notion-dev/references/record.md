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
 "worktree":"<owned worktree>","branch":"<owned branch>","hooks":["<configured skills in order>"],
 "epic_url":"<actual epic URL or null>","brief_path":"<actual brief path or null>",
 "project_root":"<primary checkout>","knowledge_dir":"<configured bundle path>"
}
```
Requirements, verification and review may be embedded structured objects instead of paths.
On schema 5 OMIT those three fields from record-facts; record-plan --review-worker selects
them from the final accepted runtime worker and verification receipts. The field/path rules
below are for existing schema 1–4 resumptions.
Paths resolve relative to this facts file. Each must exist; only requirements accepts the
literal `unknown` on merged recovery. For other unavailable evidence use an explicit object
such as `{"status":"unknown","reason":"<observed cause>"}`, never a pretend file path.
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
Schema 5 adds `--review-worker <final-accepted-id>` (omit only for verified MERGED recovery
without a surviving review; the helper records unknown coverage). Read the recording section of
`references/boundaries.md` for record-next, record-view, record-receipt and record-run.
They reuse this journal; no new scheduler or provider authority.

Schema-4/5 runs emit version-3 immutable payloads and stable operation IDs. The helper
archives full named evidence by content identity, deduplicating identical requirements/review
files. Provider views retain every structured requirement verdict, audit, evidence reference,
release obligation and accepted claim correction; only a structured review with canonical
recording facts can omit its redundant report narrative from the view. Unknown formats/fields
remain complete. The original report stays in the hash-bound local archive. It does not
recursively open paths inside receipts. Each source file is limited to 4 MiB: larger
inputs require scoped evidence, never silent truncation. Plan output contains references,
not the evidence text. Keep these private artifacts outside commits; do not copy entire logs
or secrets into provider pages.

On new runs the final accepted review's `recording` fields supply the canonical technical delta,
claim corrections and release obligations. Reconcile them before planning, not after delayed
chat arrives. Do not substitute a stale author summary for those accepted corrections.
Old schema-3/version-2 plans resume unchanged through the same interface.

For each operation consume the frozen data, not the original evidence paths:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" record-input --state "$RUNTIME_STATE" --operation <id> --begin
```
This verifies the saved payload against the plan/journal, reads and hashes it once, and returns
that same data. With `--begin`, execute is durably journaled as `--outcome attempted` BEFORE
the provider call. Use the returned data for the authorized write; never reopen the source
files to construct it. Changed sources cannot alter this operation's intended evidence.

Schema 5 normally uses `record-next --state <state> --begin` for one complete scoped operation.
For parent planning use record-view, never a truncated evidence pool. Declare exact host_call
or local_command per child. Ticket status and epic writes also use children on schema 5.
Capture the actual host exchange with record-receipt before confirmation; synchronous local
hooks use record-run, which journals before executing. Skills remain host-mediated. If an
effect preceded begin, record-observed and reconcile; never fabricate a historical begin.

- **skip:** the same payload is already confirmed; consume the receipt.
- **execute:** perform the authorized write using the returned data, target and digest.
- **reconcile:** a previous response was lost or execution interrupted. Read the affected
  Notion section, merge/hook receipt or Git state. Confirm only when the intended effect exists.
  Record failed only after proving no effect occurred; then a retry may execute. Unknown stays
  unknown-outcome and requires resolution, never a blind retry.

After a response/readback confirms the effect, use the SAME command surface:
`workflow.py record-outcome --state "$RUNTIME_STATE" --operation <id> --outcome confirmed
--provider-id <receipt>`. It looks up the frozen target and digest; do not copy them by hand.
Use failed or unknown-outcome with the observed cause/readback when appropriate. The low-level
runtime record-op remains for legacy callers only. Without `--begin`, record-input
is read-only; `--field <name>` retrieves one top-level field for inspection/reconciliation,
including after confirmation. Downstream epic/brief steps use these frozen review/requirements
fields from ticket-resolution, never reopen the original evidence. Do not combine --field
with --begin: an attempt must receive its complete input.
Never pipe provider input through head/tail or a character limit. If the view is too large,
inspect its scoped fields first and plan smaller complete write payloads; never truncate evidence.
On resume consume existing frozen payloads without regenerating them. Replanning changed
evidence fails closed, including after confirmation. Legacy path-only payloads are refused:
reconcile their existing effects and preserve their journal; do not reset or silently rebind
an attempted/confirmed identity. Changed intent needs an explicitly reconciled new operation
revision, not a report-format repair.

Use distinct child operations for multi-write steps and EACH configured hook:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" record-child --state "$RUNTIME_STATE" --parent <planned-id> --name <stable-name> --target <actual-target> --payload <literal-input.json>
```
For new schema-4 multi-write parents, declare the COMPLETE set first with
`workflow.py record-children --state "$RUNTIME_STATE" --parent <id> --writes <writes.json>`.
The JSON is `[{"name":"merged-section","target":"<real target>","data":{...}}, ...]`.
Declare completeness append, AC update and merged section separately unless the adapter truly
performs one atomic provider call (then one atomic-batch child is appropriate). Hooks each get
their own child. All children must exist and be confirmed before their required parent can
confirm; a partial interruption resumes only unfinished children. `record-input --begin` on
such a parent returns `action: children`, never permission to perform a second parent write.

Use actual epic/local targets, not the ticket URL for every kind. Use real UTF-8 JSON files or
`--payload -` / `--writes -` with stdin. Native Windows Python cannot open Bash process
substitution paths such as /dev/fd or /proc/fd. No shell-specific provider-payload tricks.
The child ID is `<planned-id>:child:<stable-name>`. Names match
`[A-Za-z0-9][A-Za-z0-9._-]{0,79}`; choose semantic names (e.g. `merged-section`, `hook-01`)
once and retain them on resume. No nested children or IDs invented from display names.
The helper freezes a self-contained JSON object; derive it from frozen record-input data,
not live evidence paths. Execute it through record-input exactly like its parent. Disk names
are hashes, so IDs containing colons work on Windows too. Children inherit their parent's
required/best-effort policy: only knowledge-delta and epic-brief are best-effort. Unknown IDs
remain required. Failed optional children stay visible in ISSUES and unresolved operations,
but do not block resolution. The parent confirms only after all children are confirmed or
explicitly not applicable; never hide partial effects behind a confirmed parent.

## 3. Operation meanings and order

On schema 5 write the final Notion Implementation/review narrative here from accepted facts.
Preserve unrelated content and human edits. The review phase deliberately deferred these writes
to avoid invalidating its own frozen source. Keep required explanations concise and consistent
with the corrected code/docs/PR claims; do not invent new rationale during recording.

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

After workspace closeout, run `workflow.py complete --state "$RUNTIME_STATE" --marker
"$RUN_MARKER"`. It verifies required recording outcomes, worker accounting, invocation/session
ownership and release of this run's primary writer lock, then sets BOTH phase and state to
complete. Do not use a phase-only marker update or disable the Stop hook. A stopped run must
be explicitly resumed first. Foreign locks are never released by this helper.
