# Runtime protocol — small, explicit handoffs

Use configured `knowledge.python` for `python3` below, on Windows Git Bash and Ubuntu/WSL2.
State lives outside disposable worktrees: primary `.claude/notion-dev/runtime/<invocation>/state.json`.
One invocation per ticket, retained on resume. Never edit state JSON directly or reset budgets.

## Requirements and evidence

Save the full authoritative source as `ticket.md`, then an inventory:
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

The worker writes the complete JSON object to an owned result file and runs:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" publish --worker <id> --result <result.json>
```
New-run publication validates the generated role schema. Invalid output stays unpublished;
repair the FILE, then publish again from the same worker. No new reviewer or provider writes.
A published result is immutable. Runtime renders completeness counts and RECORD fields from
that structured object. Final chat is only its reference, never a different report.

Parent: `consume --worker <id>`, inspect the evidence, then `accept --worker <id>`.
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
verdicts/citations, requirements_complete and blocking_findings. Never mark a filed/dropped
mandatory requirement met. Release obligations remain explicit.

Resolve citations with `resolve-citations --worker <id> --citations <citations.json>`:
each item has `id`, an existing `artifact`, a verbatim `quote`, and optional
`depends_on` paths. Include relevant implementation/test/config dependencies; a log alone
does not identify everything it exercised. Parent confirms quotes and test results, without
rerunning a passing applicable suite just to make a new report. Partial citation updates merge
by ID. `evidence --worker <id>` reports reusable/stale/blocked/unresolved records.

After a change prepare completeness with `--previous <accepted-worker>`. Read its small delta
index first. Check changed paths/claims and indirect effects against the inventory. Carry forward
unchanged independently verified verdicts when their evidence still applies; do not re-derive
them from source merely because this is a fresh agent. Retrieve full sections with
`section --worker <id> --name <section> --page <n>` when the index marks them incomplete.
The result still covers EVERY ID and declares `delta_review` with the exact previous ID,
manifest hash, checked_requirement_ids, and disposition sufficient or full-review-required.
Uncertainty expands scope or escalates; it is not a fabricated clean verdict.

At most two full and two delta attempts per invocation, including failed attempts.
Same-worker unpublished format repair consumes no new investigation attempt. Budget exhaustion
preserves work and stops with evidence; it never waives a requirement or starts a fresh run.

Before post-round corrective source edits use `correction-needed --worktree <path> --reason <why>`.
The next combined reviewer also checks the exact correction manifest and supplies its generated
correction_review fields; only a clean independently reviewed correction can pass.
`merge-gate --worker <id> --worktree <path>` must pass immediately before merge, after refreshing
live PR claims, HEAD, required checks and review threads. Changed source/inputs require recheck.

## Recording and measurement

`record-check --operation <stable-id> --target <target> --payload <file>` returns execute, skip
or reconcile plus data_sha256. Before an authorized provider write, record `record-op` with
outcome attempted and that digest; confirm only after a successful response/readback. A lost
response is unknown-outcome, never a blind retry. Confirmed operations skip only when their
identity and payload match. `workflow.py record-plan` generates the normal operation list.
Read `references/record.md` only at recording time.

`summary` reports stages, attempts, outstanding workers, verification reuse and record outcomes.
Import raw parent/child JSONL with telemetry.py for token counts. Unknown telemetry is not zero.
Schema 1/2 resumes retain original contracts; do not rewrite them to obtain new attempt budgets.
