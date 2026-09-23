# Runtime protocol — small, explicit handoffs

Use configured `knowledge.python` for `python3` below, on Windows Git Bash and Ubuntu/WSL2.
State lives outside disposable worktrees: primary `.claude/notion-dev/runtime/<invocation>/state.json`.
One invocation per ticket, retained on resume. Never edit state JSON directly or reset budgets.

## Requirements and evidence

For new schema-5 runs use `capture-ticket --page <notion-page-uuid> --config <primary-config>`
after the real notion-fetch; SessionStart supplies the transcript path/session. Read the host
capture section of `references/boundaries.md`. Missing/foreign evidence stops; no manual JSON
assembly or schema downgrade.

For existing schema-4 runs, save the complete **raw notion-fetch response** (JSON, including page
metadata, properties and content, or its MCP content envelope) to a real UTF-8 file. Do not
construct a response from a status query, summarize it, or reuse a previous local capture.
Initialize the runtime, then bind the provider source:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" ticket-source --response <fetch.json> --config "$REPO_ROOT/.claude/notion-dev.config.json"
```

This returns canonical `ticket.md` and its hash. All body sections and unknown properties are
retained; only the configured status/PR properties and transport metadata are excluded.
Never strip a body section merely because it is called Implementation or Merged: it can hold
human requirements. Create the inventory against this generated source:
```json
{"source_sha256":"<ticket hash>","reviewed_whole_ticket":true,"items":[
 {"id":"R1","kind":"requirement","text":"<verbatim source requirement>","readiness":"ready","evidence":"<basis>"},
 {"id":"AC1","kind":"acceptance","text":"<verbatim AC>","readiness":"ready"},
 {"id":"P1","kind":"prerequisite","text":"<verbatim prerequisite>","readiness":"unknown","evidence":""}
]}
```
Kinds also include `constraint`. Read the whole ticket, not only AC. Inventory every mandatory
requirement/prerequisite; record release-only obligations distinctly without inventing an unmet
merge prerequisite. Missing authority is not ready. The independent reviewer checks extraction.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" init --run <invocation> --ticket <key>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" requirements --source <ticket.md> --inventory <requirements.json>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" ready
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" stage implementation
```

For configured verification use `workflow.py verify --project "$REPO_ROOT" --state "$RUNTIME_STATE"
--worktree "$WORKTREE"`. It uses the actual name/cmd config shape and `verify --reuse`.
For targeted checks use `runtime.py verify --worktree <path> --shell-command <command> [--reuse]
[--depends <input>]`. Keep full log output, especially named tests.
Reuse requires passing evidence at the same Git content, command, environment signature and
declared non-Git inputs. Ignored files, tool/service versions and relevant environment values
are NOT automatically covered; declare a non-secret fingerprint file or run without reuse.
Never infer success from an absent log or a pipeline's last command.

## Dispatch contract

`prepare --role <role> --worktree <path> --file ticket=<path> --file <label>=<path>`
returns a worker ID and a hash-bound `context.json`. Roles: scout, plan, implementation,
branch-review, local-review, completeness, record, probe. Default lean work is inline;
its one internal review uses **completeness**, which covers both code quality and requirements.

Pass the worker only this compact instruction:
> Read project instructions and the supplied context.json. Its result_contract is authoritative.
> Read the complete ticket/inventory; retrieve other sources as your role needs them. Complete
> the named task, validate your evidence, publish the structured result using runtime.py, and
> return only the result artifact reference. Repair rejected output in this same worker without
> repeating completed work. Use runtime question for missing input; chat is not reliable delivery.

Also pass runtime path, plugin root, configured interpreter, worktree, role objective and its
permissions (review workers are read-only except their owned runtime artifacts).
Do NOT inherit the author's conversation, rewrite the JSON contract in the parent prompt,
or paste a full manual. The generated contract includes delta/correction fields when applicable.
New packets also contain `publication`: an editable `submission.json` skeleton, the exact
command using the active configured interpreter, and the canonical result path. Use those;
do not read global state.json to discover worker metadata. The skeleton intentionally lacks
passing verdicts/evidence. A lean plan worker reports its required findings, evidence and risk
invariants in the current contract; it does not load the legacy plan-review formatting rubric.

After real host dispatch: `attach --worker <id> --agent <actual-host-id>`.
A dispatch acknowledgement is not a result. Do not invent an ID or launch a replacement while
the original can still run.

## Wait and questions

There is exactly one waiter for a worker:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" wait --worker <id> --seconds 60
```
Use a foreground blocking host call. If the host backgrounds that call, await that existing
task; do not launch another sleeper, status loop, file poll or waiter. On a pending return,
use the host's continuation mechanism. If mailbox delivery requires ending the parent turn:
`yield --worker <id> --marker "$RUN_MARKER" --session "$NOTION_DEV_SESSION_ID"`, then yield
without a completion report. This one-shot permission belongs to the current marker/session;
it does not disable Stop enforcement or reset counters. Continue on delivery.

A worker needing a decision calls `question --worker <id> --text <question>` BEFORE waiting.
The controller's wait returns `needs_input` with the question ID/text even if chat is delayed.
Resolve it from requirements/code, or ask the user when authority is missing; write
`answer --worker <id> --question <question-id> --text <answer>`. Notify/resume that SAME host
worker with the answer reference. It reads `inspect`, not the conversation history.
The worker must not keep editing while awaiting a decision. Question time is excluded from
the worker execution deadline. Answers are immutable and identify the exact question.

## Publication, acceptance and cancellation

Use the generated submission file/command when supplied. Older packets keep this form:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" publish --worker <id> --result <result.json>
```
New-run publication validates the generated role schema. Invalid output stays unpublished;
repair the FILE, then publish again from the same worker. No new reviewer or provider writes.
A published result is immutable. Runtime renders completeness counts and RECORD fields from
that structured object. Publish and consume return its actual `artifact.path` and hash; never
guess a result filename. Final chat is only its reference, never a different report.

**Host forbids worker report writes:** do not switch tools to evade the restriction. The
worker returns the complete contract JSON in its final host response instead. The parent waits
for that same host worker's completion, saves the unchanged object to its prepared submission
path, and publishes for that worker before consume/accept. Do not poll for runtime publication
after receiving this host-return result. Missing/rejected fields go back to the SAME reviewer;
the parent does not invent verdicts. This fallback pays host delivery latency but no new review.

Parent: `consume --worker <id>`, inspect the evidence, then `accept --worker <id>`.
Prefer `consume --worker <id> --summary` on new runs; `result-view --worker <id> --section
<requirements|recording|claims|...>` retrieves a needed full section. The immutable full result
remains at the returned artifact. Summary is routing, not permission to skip checking evidence.
**Consuming a result is not accepting it, and the difference is enforced.**
A valid nonpassing review may be accepted as an honest finding; acceptance is not permission
to merge. New-run acceptance repeats schema validation.

An expired deadline, idle display, failed chat delivery or malformed report does not prove
a process stopped. Consume a late available result first. Otherwise request host cancellation,
confirm termination with the host, then `end-worker --worker <id> --reason <why> --confirmed`.
Use `--invalid-result` for a consumed invalid legacy result, `--host-failed` for an actual
execution failure, or `--user-requested` for explicit cancellation. Without confirmation,
do not replace the worker or begin a second writer; preserve the primary lock if held.
The standard-library runtime cannot independently prove a host process terminated.

## Independent review and deltas

A full completeness worker receives authoritative source/inventory, current diff/PR claims,
test receipts and relevant source references—not the author's plan or conclusions.
It checks code quality, contracts, regression/edge cases, full-source coverage, every requirement,
unsupported claims and untriaged caveats. Generated output requires code_review, all requirement
verdicts/citations, requirements_complete and blocking_findings. Contract version 2 and later require
`claims`, `caveats` and `triage`, each with `status` (checked/unverified), nonempty `evidence`
and `findings`. An explicitly checked empty list means NONE; missing is invalid, not NONE.
Each finding carries finding/disposition/rationale/blocking. Unverified audits or a blocking
finding prevent merge even if the report says clean or its disposition is file/drop.
Publication may accept an honest nonpassing result; acceptance does not make it mergeable.
The runtime renders these three report headings from structured data, not separate prose.
Never mark a filed/dropped
mandatory requirement met. Release obligations remain explicit.

Version 3 additionally requires `recording`: `release_obligations` and `claim_corrections`
(lists of strings), plus `technical_delta` (fact/evidence objects). Use explicit [] for none.
Carry accepted fact corrections and release obligations here, not only in narrative or late
chat. Recording consumes these canonical facts; it does not synthesize them again.

Resolve citations with `resolve-citations --worker <id> --citations <citations.json>`:
each item has `id`, an existing `artifact`, a verbatim `quote`, and optional
`depends_on` paths. Include relevant implementation/test/config dependencies; a log alone
does not identify everything it exercised. Parent confirms quotes and test results, without
rerunning a passing applicable suite just to make a new report. Partial citation updates merge
by ID. `evidence --worker <id>` reports reusable/stale/blocked/unresolved records.

Before delta preparation, `resolve-citations` MUST have run on the accepted baseline; runtime
rejects a missing handoff. Resolve every available citation. An explicit [] is allowed only
when none resolves; it keeps every item unknown and grants no reuse or merge permission.

After a change prepare completeness with `--previous <accepted-worker>`. Supply only changed
named inputs: omitted names inherit their existing paths and are rehashed. Removal requires
`--remove-input <name>`; absence is not deletion. Content equality, not a new capture filename,
decides whether an input changed. Read its small delta
index first. Check changed paths/claims and indirect effects against the inventory. Carry forward
unchanged independently verified verdicts when their evidence still applies; do not re-derive
them from source merely because this is a fresh agent. Retrieve full sections with
`section --worker <id> --name <section> --page <n>` when the index marks them incomplete.
The result still covers EVERY ID and declares `delta_review` with the exact previous ID,
manifest hash, checked_requirement_ids, and disposition sufficient or full-review-required.
Uncertainty expands scope or escalates; it is not a fabricated clean verdict.

Version-4 delta packets offer `delta_publication`: changed judgments plus explicit unchanged
ID/section references. Read `references/boundaries.md` for its shape. Runtime assembles a full
result; do not regenerate the prior narrative. All-ID coverage and dependency checks remain.

At most two full and two delta attempts per invocation, including failed attempts.
Same-worker unpublished format repair consumes no new investigation attempt. Budget exhaustion
preserves work and stops with evidence; it never waives a requirement or starts a fresh run.

Before post-round corrective source edits use `correction-needed --worktree <path> --reason <why>`.
The next combined reviewer also checks the exact correction manifest and supplies its generated
correction_review fields; only a clean independently reviewed correction can pass.
Version 3's structured correction verdict is authoritative; runtime renders its header.
Declare `depends_on` paths for all external correction evidence (explicit [] only for code-only
review); code revision and requirement inventory are already bound. When code, obligation and
these dependencies are unchanged, the packet's `correction_reuse` carries the original verdict
and exact manifest. Do not manufacture a replacement verdict or rerun the correction tests.
Changed dependencies/source invalidate reuse. Version-1/2 packets retain their original rules.
`merge-gate --worker <id> --worktree <path>` must pass immediately before merge, after refreshing
live PR claims, HEAD, required checks and review threads. Changed source/inputs require recheck.

## Recording and measurement

Before recording, schema-4 merge requires the fresh-ticket procedure below.

`workflow.py record-plan` snapshots named evidence into immutable versioned payloads.
`workflow.py record-input --state <state> --operation <id> --begin` verifies and returns frozen
provider input, journaling attempted before an execute. Consume that returned data, not the
original source paths. Confirm with `workflow.py record-outcome` only after a successful response/readback.
A lost response is unknown-outcome, never a blind retry. Confirmed operations skip only when
their identity and payload match. `record-child` registers stable, parent-scoped suboperations.
Read `references/record.md` only at recording time.

`summary` reports stages, attempts, outstanding workers, verification reuse and record outcomes.
Import raw parent/child JSONL with telemetry.py for token counts. Unknown telemetry is not zero.
Schema 1/2 resumes retain original contracts; do not rewrite them to obtain new attempt budgets.
Already-prepared version-1/2 workers also retain their packet/validation contract.
Schema-5 workers use version 4; schema-3/4 workers keep version 3. No budget or invocation reset.
New lean invocations use schema 5 and require the host-captured full-source refresh receipt. Never use
`init --legacy` on this path; it belongs only to an explicitly selected legacy build flow.
Never downgrade state
to bypass it. Old frozen version-2 recording payloads remain readable without rebinding.

## Fresh authoritative ticket at the merge boundary

After the final accepted review and other live merge checks, begin:
`refresh-ticket --worker <id>`. It returns a request token bound to this run, reviewed source,
worker and provider page. NOW call notion-fetch for that exact page and retain its actual ID.
On schema 5 finish with `capture-ticket --worker <id> --request <token>`;
it extracts the real host exchange. Do not assemble a response JSON yourself.
Only on schema 4 save the full raw response to a NEW real JSON file and finish with
`refresh-ticket --worker <id> --request <token> --response <new-fetch.json> --call-id <actual-id>`.
Do not use the provider's `as of` text as fetch time: it may describe last page editing.

Only an unchanged full source permits merge-gate. Changed content means bind this new response,
refresh the whole inventory/readiness and obtain independent review. This includes constraints
outside AC, regardless of whether the criterion count changed. A status-only projection, wrong
page, old capture, failed fetch, changed receipt, foreign worker/run or >5-minute-old refresh
blocks. Begin again if the boundary expires; do not rerun unchanged reviews. A new begin
invalidates any older successful receipt. Schema 1–3 resumes retain their existing rules.

This is a host/provider integration receipt, not cryptographic provider attestation. The helper
cannot establish network truth or prevent a host forging a new call ID and copying old bytes.
The adapter must preserve the actual tool response and call identity; unavailable evidence stops
merge rather than filling fields with assertions. No credentials or provider SDK are added.
That is a trust boundary, not pending implementation work; see `references/boundaries.md`.
