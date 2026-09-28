# Deterministic boundaries

New lean runs use schema 5 / result contract 5. Existing schema 1–4 runs and prepared workers
retain their protocols and budgets. No new agent, scheduler or provider-authentication stack.
Use configured knowledge.python on native Windows Git Bash and Ubuntu/WSL2.

Review consumption uses `references/review-accounting.md`: bounded index, lossless finding pages,
hash-bound dispositions before acceptance, and actual user authorization for one extra correction
review. Existing compact delta partitioning and all source/evidence freshness checks remain.

## Actual host captures

SessionStart exports NOTION_DEV_SESSION_ID and NOTION_DEV_TRANSCRIPT from the host's hook
payload. Restart Claude Code after updating. Custom Claude homes work without guessing paths.
An explicit --transcript/--session may name the actual parent log when the hook lacks the path;
never select another session or synthesize a log. Windows paths are decoded and shell-quoted.

After notion-fetch completes, select its actual exchange by the known Notion page UUID:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" capture-ticket --page <page-uuid> --config "$REPO_ROOT/.claude/notion-dev.config.json"
```
If the host exposes the tool ID, --call-id <actual-id> is also supported. Do not read the entire
transcript into model context to discover it. The helper selects the last matching call, then
requires its completed successful response; it never falls back past a failed/incomplete call.
This extracts the complete provider object and generates ticket.md. Foreign/child sessions,
conflicting IDs, failed responses, incomplete tails and unsupported shapes fail closed. If the
exchange is not yet flushed, wait for the existing delivery and retry capture, not the fetch.
No retyping, escaping, patching old captures, or replacing them with summaries.

Final freshness: `refresh-ticket --worker <accepted-id>`, NEW full notion-fetch, then
`capture-ticket --worker <accepted-id> --request <token>` (page comes from the challenge). The actual call
must follow this challenge, in the bound session, for the bound page. The 5-minute gate and
all-body comparison remain: human constraints under Implementation/Merged are never stripped.
Schema 4 retains its original raw-file refresh contract, not a relabeled stronger guarantee.
On an authorized schema-5 takeover, claim/resume-pr first transfers session ownership and clears
old freshness receipts. Refresh the source next, before implementation/review or any provider write.

The local host/log is trusted, not cryptographic provider attestation. Forging that log can
forge local evidence. Unsupported/missing host evidence stops explicitly; no fabricated fallback.

## One factual owner; freeze author-written ticket narrative

Keep decision, essential reason, evidence and release obligations in context.md during authoring.
Accepted recording facts own downstream summaries after review. Correct affected code/docs/PR
occurrences in one batch, in place, rather than appending a story while retaining the old claim.
A new factual claim requires evidence and review even when labeled non-blocking.

Freeze author-written Notion narrative before internal review. Live status/ownership still use
properties. Final Implementation/review history is written once during recording. If a required
pre-merge narrative edit cannot wait, include it before its source is independently reviewed.
Never ignore human changes under the same headings.

PR facts use `requirement` (string) and `behavior`, `validation`, `risks`, `mandatory` (objects
with stable semantic keys and fact-string values). Legacy lists remain readable; new corrections
replace a key, not a positional array element or an appended competing explanation. Duplicate
named paragraphs fail rendering. Review status stays outside these facts.
For numerical claims a value may be `{kind:"ratio",numerator:19,denominator:71,unit:"errors",
population:"retained tail only",source:"archive reference"}`, or `{kind:"comparison",
baseline:{p50:100,p95:200},observed:{p50:104,p95:190},nonincrease:false,unit:"ms",
population:"one run",source:"archive reference"}`. The renderer computes arithmetic and rejects
a requested nonincrease contradicted by any column. It does not validate invented input numbers.
Independent review must check source values and inference: a truncated tail sample cannot
establish whole-run proportions or rank of bias, nor does admission shedding alone prove latency
safety. Reuse immutable benchmark evidence when correcting prose; do not rerun merely to reword it.
Any other string fact carrying a figure (a unit, percentage or multiplier) must cite the artifact
that produced it — `(artifact: test_name)`, a verification receipt, an exported JSON/CSV or a
generated diff — or rendering fails. Restating a figure in a sentence is not evidence, and the
combined reviewer audits the artifact references, not the prose around them.

## Release obligations are one ledger

Every merged-but-unreleased obligation — a wire/contract change needing sign-off, a release note,
a config line, a measurement that gates the release — is one `## Release obligations` item in
the epic brief (epic-doc `format.md`), with its source ticket, whether sign-off is needed and the
automated gate (if any) that surfaces it. Request sign-off once per release from that list, not
per ticket. A deliverable promised to someone is a `commitment:` item; next-task warns when it
is merged but unreleased while later children keep adding obligations ahead of it.

## Compact delta publication

Use `workflow.py review-prepare` for new full/delta dispatches. It verifies the committed tree
before allocating a worker and provides `verification_receipts`. Generated reports declared via
`verify.steps[].outputs` or `--output STEP=PATH` are archived after the producing command; a
missing/not-regenerated output fails verification. Cite the archive with its receipt, not its
mutable source path. A later contradictory run blocks reuse and needs affected-claim review.
For independent targeted commands, `runtime.py verify --output PATH` also archives outputs.
Only named outputs are archived: never recursively collect build directories or secrets.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" review-inputs --state "$RUNTIME_STATE" --worktree "$WORKTREE" --pr <owner/repository#number>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" review-prepare --project "$REPO_ROOT" --state "$RUNTIME_STATE" --worktree "$WORKTREE" --inputs <returned-inputs-path>
```
The first helper reads the live PR with gh, verifies its HEAD, derives the actual base/head diff
and snapshots the authoritative ticket/inventory. Fetch missing base commits through the host,
then retry; never guess a base. For a Notion specification use live fetch → record-capture, then
`review-inputs --source spec=<capture-path>`; arbitrary coverage/log files cannot become a spec.
Do not dispatch with instructions to ignore stale inputs. New full/delta dispatches use this path;
already-issued legacy packets remain readable without invented provenance. Extra immutable
benchmark archives may use `--file <name>=<path>` under accurate labels.
For schema 3/4 resumptions without host-capture ownership, keep the existing `--file` preparation
adapter until the run finishes: regenerate diff/PR body from current git/gh, identify source
provenance as unknown where unavailable, and have the reviewer inspect the actual source.
Never present that adapter as a typed capture or mutate its schema/budget to opt in. Schema 1/2
continues through the legacy entrypoint. Once a run binds typed inputs it cannot downgrade.
For delta add `--previous <accepted-worker>` and changed named inputs. Refresh typed sources or
explicitly remove obsolete ones; no implicit stale inheritance. Prepare inputs BEFORE requesting
an extra correction-review allowance so its exact scope is authorized. `review-prepare` rechecks
the live PR and budget before verification. Before merge run `workflow.py review-check --state
<state> --worktree <path> --worker <accepted-review-id>`; changed body/base/head needs affected
review, not a prose override. Its local receipt is bound to that worker/session for five minutes
and required by merge-gate for typed packets. It performs no provider writes and does not
replace the ticket freshness gate. A race after observation remains a provider API boundary;
merge still uses --match-head-commit.
Keep declared `--depends` consistent. Logs are in the generated manifest: do not supply an old
test_log separately. Applicable inherited test-log inputs refresh to the new receipts.

Read delta.json, required paged sections, and delta_publication's prior index first. Prior
verdicts and references to audit/recording sections replace eager full-report loading. Retrieve
full sections only for affected claims or a specific doubt. Full evidence remains available.
Whole-file dependency checks remain conservative; no automatic "comment edits are safe" rule.

A version-4-or-later delta can publish the following alternative to the full result:
```json
{
 "report":"Concise changed-scope conclusion",
 "requirements_complete":true,
 "delta_review":{"previous":"<id>","manifest_sha256":"<hash>","checked_requirement_ids":["R1","AC1"],"disposition":"sufficient"},
 "delta_result":{
   "baseline_sha256":"<delta_publication hash>",
   "changed_requirements":[{"id":"R1","verdict":"met","citation":"<new evidence>"}],
   "reused_requirement_ids":["AC1"],
   "updated_sections":{"claims":{"status":"checked","evidence":"<claims examined>","findings":[]}},
   "reused_sections":["code_review","blocking_findings","caveats","triage","recording"]
 }
}
```
Partition every requirement and section exactly once. Include correction_review when required;
correction_reuse remains runtime-owned. requirements_complete/delta_review are current independent
attestations, not inherited. Check indirect effects on EVERY ID. Only current evidence may be
inherited; changed judgments still need resolved citations. Updated sections are complete
replacements, retaining applicable release obligations and accepted corrections. Explicit reuse
means the independent reviewer found that section still applicable. Runtime assembles the full
result and applies the existing publication/merge gates; full publication remains supported.
Version-4 reports render audit counts, not a second copy of their evidence; complete audit
objects remain in the same result. Older result rendering is unchanged.

## Canonical recording and execution

For attempted-but-landed Notion writes use `record-reconcile` with a fresh actual fetch ID.
The version-1 equivalence rule accepts only absent/false allow_async and one terminal insert
newline; all other arguments remain exact. Readback must establish the complete intended effect
exactly once. Nonliteral provider formatting returns `judge-effect`, not a confirming receipt;
only an explicit adapter judgment bound to the intent/call/readback hashes can continue. This
is host judgment, not provider attestation. It never dispatches or reverses a write. Read `references/record.md`'s recovery
and host-mediated-operation rules before handling mismatches; do not repair them with more writes.

An actual different-text create is NOT equivalent formatting. `record-receipt` quarantines
that operation against replay even if someone later labels it failed. For one already-created
page whose parent/properties/title match exactly, use `workflow.py record-discrepancy --state
<state> --operation <id> --call-id <actual-create> --readback-call-id <fresh-fetch> --explanation
"<complete difference and effect assessment>"`. It captures both texts and fresh readback,
returns an explicit user approval challenge, and performs no provider write. Show the evidence;
only an actual matching parent-user response allows `record-accept-discrepancy --state <state>
--operation <id>`. The five-minute decision window binds the observed page and session; if
expired, fetch and request again. It appends an **accepted discrepancy**, not a claim the
original intent matched. Report that distinction. Duplicate creates, retargeted properties,
unsupported responses or unapproved differences remain unresolved; no automatic normalization,
payload rewrite, synthetic receipt or retry. Other operation kinds retain their existing
explicit reconciliation contract. Recovery never grants authority to change the provider.
After an authorized session takeover, the original write may be captured with paired
`--write-transcript <original-log> --write-session <original-session>`; fresh readback and
approval still belong to the CURRENT owning session. Neither the old approval nor its page
snapshot transfers authority. Unsupported/missing original evidence remains unresolved.

Schema-5 record-facts holds observed merge/target/config facts, NOT requirements/review/verification.
Use `record-plan --state <state> --facts <facts.json> --review-worker <final-accepted-id>`.
It selects the actual result, inventory and runtime verification receipts; no consume wrapper,
older result or manual evidence copying. Unknown verification stays unknown. Full review archives
remain intact; only the redundant rendered narrative is omitted from the canonical view.
Exception: `resume-pr --merged` with no surviving completeness worker allows record-plan without
--review-worker. It records review/coverage as unknown and an explicit release-readiness warning;
neither the merge nor copied PR prose becomes an accepted verdict. Existing workers cannot be
bypassed by this recovery path.

`record-next --state <state> [--begin]` returns one operation in the existing plan order.
`plan-children` means declare the complete write set, not execute the parent. Use `record-view
--state <state> --name review --field recording` or names requirements/verification/
release_obligations/accepted_claim_corrections for complete scoped facts, never head/tail/cut.
`confirm-children` returns the receipt for already-confirmed children; confirm that parent through
record-outcome. `complete` means the plan is reconciled, not that closeout may be skipped.

New host-write children include exact authorized tool arguments:
```json
[{"name":"implementation","target":"<actual page>","data":{
 "host_call":{"name":"<actual tool name>","input":{"<provider key>":"<complete intended value>"}}
}}]
```
Declare with record-children, then `record-next --begin`. Invoke that exact tool/input once.
`record-receipt --state <state> --operation <id>` selects the exact frozen tool/input and binds it to
the session, frozen input and durable begin. Inspect the response/readback before record-outcome
confirmed with its actual receipt. Tool transport success alone is not successful provider work.
Skill hooks are host-mediated: bind their actual Skill call and confirm only after their effects
and commit/provider receipts are verified, not merely after loading skill instructions.

Local synchronous hooks instead declare `local_command: {"argv":["<interpreter>","<script>"],
"cwd":"<directory>"}`. Use record-run: it journals begin, executes without shell interpolation,
saves logs and confirms exit 0. The command's contract must mean completed work, not background
launch. Nonzero/timeout/interruption is unknown outcome because partial effects may exist.
Confirmed hooks never replay. Do not invent a script to replace a configured skill.

If an effect occurred before begin, use `record-observed --receipt <readback evidence>`, then
reconcile. This records the missing write-ahead boundary honestly, without retroactively inventing
it. Unknown outcomes never authorize blind retry. Use actual UTF-8 JSON files, not /dev/fd or
hand-escaped Python path literals. Schema 1–4 recording keeps its original contract.

## Measurement

### Common recording builders (0.39)

For ticket-status/ticket-resolution `plan-children`, use a NEW live notion-fetch of the target
page, then (configured `knowledge.python` for `python3`):
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" record-capture --state "$RUNTIME_STATE" --page <page-uuid>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" record-build --state "$RUNTIME_STATE" --parent <operation-id> --config "$REPO_ROOT/.claude/notion-dev.config.json" --snapshot <returned-snapshot>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" record-next --state "$RUNTIME_STATE" --begin
```
Dispatch the returned `data.host_call` exactly once. Existing record-receipt, provider-effect
verification, record-outcome and parent confirmation remain mandatory. No inline Python,
JSON envelope decoding, copied review report or handwritten child wrapper is required.
The capture is session-owned, immutable and at most five minutes old at planning. This does
not provide atomic provider revision locking: still validate live schema/ownership, and let
exact old_str anchors reject conflicting section edits. Reconcile lost responses; never retry
an unknown outcome blindly. A host timeout or unsupported provider shape is not success.
Large successful fetches persisted by Claude are read from the exact session's tool-results
directory (at most 4 MiB), not copied/decoded by the model. Other paths and failed/incomplete
results fail closed. For epic/adapter planning, `record-page --state <state> --snapshot <path>`
returns properties/heading index; add `--heading "Tasks"` (or another exact heading) for that
complete section. This is a scoped snapshot, not a new live status check or a claim that the
model read the whole epic. Authoritative ticket requirement extraction still reads the full ticket.

Implementation/Merged additions preserve existing section content and heading attributes.
Ambiguous headings, nonmatching criterion text, HTML code blocks, pre-existing identical entries
and unknown review coverage require the existing adapter's explicit reconciliation. The builder
does not paraphrase acceptance criteria, infer approval, or decide an epic is complete.

For epic/follow-up/Skill writes whose semantics require the existing adapter, `record-children`
also accepts flat recipes. Declare the complete set after live schema/child/scope checks and
approved filing decisions; this only removes wrapper construction, not those decisions:
```json
[{"name":"resolution","target":"<actual-page-url>","tool":"mcp__notion__notion-update-page",
  "input":{"page_id":"<actual-uuid>","command":"update_content","content_updates":[{"old_str":"<exact live anchor>","new_str":"<approved replacement>"}]}}]
```
Use the actual host tool and exact arguments for approved follow-up creation or configured Skill
hooks too. The helper normalizes into the original immutable child protocol. Local synchronous
hooks still use local_command/record-run; never replace a configured skill with an invented script.

### Performance checks

Regression fixtures are not proof of live savings. Track capture errors, self-induced full
reviews, stale-copy/induced findings, delta/full fresh-token ratio, report/view sizes, recording
requests and post-completion turns. Measure parent plus children; cache reads separately.
No omitted requirements, silent stale reuse, truncated evidence or weaker correctness gates.
