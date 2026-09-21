# Runtime protocol — lifecycle, readiness, and evidence gates

Read this reference once when `ticket`, `finalize`, or a standalone reviewing skill
starts. It replaces synchronous-dispatch assumptions, relative-age timeout guesses,
and automatic control probes in notion-dev. It does not grant permission to spawn
an agent, mutate a provider, or merge; the caller's authority and safety rules remain.

`python3` below means the configured `knowledge.python` interpreter (default
`python3`, possibly `python` or `py -3`). All commands work through Git Bash on
Windows and through Bash on WSL. The runtime uses only Python's standard library.

## Invocation and telemetry

After loading config and resolving the ticket, create one invocation directory under
`$REPO_ROOT/.claude/notion-dev/runtime/<invocation>/`, inside the existing self-ignored
directory. Ensure its self-ignoring `.gitignore` exists first using the directory setup
in `skills/flow-triage/references/ledger.md`, including on a standalone first run.
Otherwise writing telemetry changes the reviewed tree's untracked fingerprint.
Use the preflight token, or a new UUID for an interactive/direct invocation.
Set `RUNTIME_STATE` to its absolute `state.json` path. Initialize:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" init --run <invocation> --ticket <key>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" stage intake
```

Persist `runtime_state` in the existing run marker; preserve it on marker rewrites,
claim handover, and resume. Never reuse another invocation's state by ticket ID.
Legacy runs without it get a new state and re-established evidence, never assumed
verdicts. Pass `RUNTIME_STATE` to invoked notion-dev skills and the record unit.
At each phase boundary call `stage <name>` (selection, intake, plan, implementation,
validation, review, merge, record, complete, or stopped). Calls close the previous
span using a real clock. A repeated identical name does not restart its timer.
On resuming a stopped run, call the actual resumed stage before doing work; never
leave review, merge, or record charged to `stopped`. Resuming does not reset review
budgets, deadlines, accepted results, or the worker registry.

Run configured validation commands through the measured runner, without changing
which checks/retries the existing workflow requires:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" verify --worktree <absolute-worktree> --shell-command '<configured command>'
```

The Bash runner enables `errexit` and `pipefail`. The result carries real exit status, elapsed seconds, revision/fingerprint and log
path; use that log as verification evidence. Exit 1 means failed or modified-during-
verification, never success. This milestone measures duplicate runs; it does not
cache or skip them. Read relevant failure output from the log; do not pipe the runner
through a success-masking command. Missing state/invalid input returns exit 2 and
must be repaired, not interpreted as a passed gate.

## Readiness: the whole requirement, not just its checkboxes

Save the full authoritative ticket body as `ticket.md` next to state, unchanged.
Keep the original criteria file too. Before planning, inspect every section for
requirements, prerequisites, ordering/sign-off conditions, constraints, and AC.
Write `requirements.json` with this structure (calculate the source hash, never guess):

```json
{
  "source_sha256": "<SHA-256 of ticket.md bytes>",
  "reviewed_whole_ticket": true,
  "items": [
    {"id": "P1", "kind": "prerequisite", "text": "<verbatim source quote>",
     "readiness": "blocked", "evidence": "Customer decision not received"},
    {"id": "AC1", "kind": "acceptance", "text": "<criterion verbatim>",
     "readiness": "ready"}
  ]
}
```

Kinds are `requirement`, `acceptance`, `prerequisite`, `constraint`; readiness is
`ready`, `unknown`, or `blocked`. Every inventoried item is mandatory. `ready` means
understood/buildable, not implemented; a prerequisite is ready only when its actual
condition is satisfied with cited evidence. Non-interactive interpretation is not
customer consent, permission to ignore ordering, or authorization to narrow a bound.
"Useful regardless of the answer" does not satisfy "settle this first."

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" requirements --source <ticket.md> --inventory <requirements.json>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" ready
```

Exit 1 blocks planning/implementation. Name the unresolved item and evidence needed;
use the existing truthful stop path, including retiring the preflight marker. Do not
wait until *every* criterion is impossible. Unknown authority or ambiguity requires
clarification; do not choose a weaker reading solely to reach ready. Code cannot
prove extraction completeness: the independent verifier must compare the inventory
with the full source, not just trust this list. Actual approved scope changes require
an updated authoritative source and fresh inventory/review, not a local waiver.

On resume, before preparing completeness, and immediately before the merge gate, re-fetch the authoritative ticket
and refresh the source file. Changed bytes invalidate the old inventory and review,
even when criterion count is unchanged. Do not modify Notion to make the gate pass.
A standalone PR review uses its supplied authoritative intent/spec as the source;
if none exists, stop and request it rather than inventing requirements. A previously
merged `finalize` recovery records unresolved evidence honestly but does not attempt
to retroactively merge or bypass a gate.

## Workers: prepare → attach → result_ready → consumed → accepted

Before each actual dispatch, prepare a distinct worker with role `scout`, `plan`,
`implementation`, `branch-review`, `local-review`, `completeness`, or `record`. Supply the necessary input files (not a
whole conversational history). Review roles also require the worktree. For example:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" prepare --role completeness --worktree <worktree> --file ticket=<ticket.md> --file inventory=<requirements.json> --file criteria=<criteria-file> --file diff=<diff-file> --file pr=<PR-body-file> --file verify=<verification-log>
```

Omit genuinely absent optional artifacts, never fabricate paths. `prepare` records
file hashes, the code revision including dirty/untracked changes, the requirement
inventory and the deadline. Use its returned worker ID. Default deadline: 900 seconds;
record with configured hooks may use `--timeout 2700`, still within the existing
primary-lock safety margin. Preparation belongs immediately before dispatch.

`prepare` returns a **packet path**, not another copy of the inventory. The packet
indexes immutable UTF-8 JSON requirement metadata and byte-preserving input snapshots
beside state; it does not replace the authoritative sources or waive freshness checks.
Give the child this path and a narrow objective. Read the ticket/inventory and applicable
project instructions first, then relevant input snapshots and code. Retrieve referenced
architecture/history only for a named question. Missing/contradictory evidence expands
retrieval; no token budget permits omitting a requirement. Do not load the entire runtime
state (which includes all historical reports) or send the whole transcript to each worker.

This protocol covers **third-party flow agents too**, including a whole-branch reviewer
launched by feature-dev or superpowers. Pass the prepare/publish contract through the flow
adapter before dispatch, not after a delayed reply. Use `branch-review` for the whole-branch
seat and `local-review` for task reviews. Build-flow workers may use `--slot <task-or-seat-id>`
for disjoint parallel implementation, scouting, architecture or review tasks. A slot is
stable across retries and never an escape from waiting for its previous worker. An unscoped
worker excludes other workers in its role; `record` and `completeness` never permit slots.
Every actual agent has one worker ID and real host ID. A host that cannot provide this
contract must be handled as an explicit unsupported dispatch, not an untracked agent
or a second reviewer launched while the first is pending. Existing authority rules apply.

Give the child the resolved interpreter command, absolute `runtime.py` path,
`RUNTIME_STATE`, worker ID, input paths, and the result contract below. Pass literal
values; do not assume parent shell variables exist in the child's environment.
Also pass the packet path; do not paste its input file contents into the dispatch.
The Agent tool may be asynchronous: a launch acknowledgement is **pending work**,
not zero-byte output. Attach the actual returned host agent ID:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" attach --worker <worker> --agent <actual-agent-id>
```

The child writes a UTF-8 `worker-<worker-id>-result.json` next to state, then calls `publish` with it
**before** its final chat response. Publishing this owned result is the sole file-write
exception for a review-only worker; it may not modify project files, commit, or push.
Do no work or side effects after publication. Return the same verdict in the final
response too, so hosts with immediate delivery remain supported.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" publish --worker <worker> --result <result.json>
```

All results contain `{"report":"<the existing full keyed report>"}`. Completeness
also includes `requirements_complete: true` only after checking the entire source
against the inventory, `requirements: [{"id":"P1","verdict":"met","citation":"<actual evidence>"}, ...]`
for every inventory ID, and `blocking_findings: []` only when no unresolved required
code/claim/caveat finding remains. If extraction omitted a prerequisite, set
`requirements_complete: false` and name it in blocking findings. Never declare a
mandatory item met because it was filed, dropped, or relabelled as a known limitation.
Existing AC/claim/caveat contracts and citation validation still apply. The parent
cannot author or substitute the independent worker's verdict.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" wait --worker <worker> --seconds 30
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" consume --worker <worker>
```

Waits are bounded to 60 seconds per call. Pending wait exits 1 and means continue
waiting or doing independent useful work—not failure. Inspect the returned state.
Consume only `result_ready`, then validate/triage the report under the caller's rubric.
Consumption is idempotent. A malformed completed report takes the existing bounded
replacement path, not a clean verdict. No unconditional PONG control probe is run.

**Consuming a result is not accepting it, and the difference is enforced.** A report
must be consumed before its contract can be judged, so `consumed` says only that the
parent has read it — never that the worker is finished with. Record the judgement:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" accept --worker <worker>
```

`accept` and `end-worker --invalid-result` are the only two exits from `consumed`, and
`prepare` refuses another worker in the same role until one of them has been taken. That
gate fails closed on purpose: without it, a contract-invalid report that had to be
consumed to be judged would leave its worker `consumed`, unterminated and possibly still
running, while a replacement started alongside it — for `record`, two live workers with
provider side effects and duplicate writes. A caller that forgets is stopped and told
which exit to record, rather than silently permitted. `merge-gate` counts a consumed but
unjudged worker as an outstanding outcome for the same reason.

For completeness, the parent must also resolve each citation under the existing
citation rules. Write a list of `{id, artifact, quote}` objects: a real evidence/log
path and the exact supporting text for each requirement, not the deliverable's own
unsupported claims. Run `resolve-citations --worker <worker> --citations <file.json>`.
The runtime checks quotes against files, records their hashes, and rejects missing or
changed evidence at merge. Semantic sufficiency still requires independent judgment.
A citation that cannot be resolved stops merge; neither consumption nor a child saying
`met` substitutes for this check. Never rewrite the child's immutable verdict to pass.

If mailbox delivery needs a parent-turn yield, `yield --worker <worker> --marker
<owned-run-marker> --session "$NOTION_DEV_SESSION_ID"` grants the Stop hook one
60-second, session-owned permission to hand back. State remains unfinished and the
existing block counter is preserved. Announce waiting, never completion. Resume the
same state when notified; a host without notification/resume support must use the
durable-result wait path instead. No marker (standalone skill) means no Stop-hook
permit is necessary. Do not claim the host automatically resumes until tested there.

**Timeout is not termination.** `inspect` uses elapsed monotonic time, not an agent
list's relative age; repeated `started <1m ago` labels prove neither a restart nor a
failure. Result-ready wins over delayed mailbox delivery. A clock discontinuity is
reported as uncertain, never used to kill working agents: stop the run with that
cause and retain any active-writer lock until host/clock state is reconciled; do not
repeat pending waits indefinitely. At a true timeout, call
`end-worker --worker <worker> --reason <cause>` before requesting host cancellation.
After the host confirms it is no longer running, repeat with `--confirmed`. Until
then no replacement or inline writer may run. A real host execution failure may use
`--host-failed`; only an explicit user cancellation may use `--user-requested`.
Missing notification, inactivity labels, or a model's estimate of minutes are neither.
For a consumed report rejected by the actual output contract, use `--invalid-result`
with its concrete defect and still confirm termination before replacement/replay.
An available result must be consumed before deciding how to recover. Preserve the
record-unit lock/unknown-hook-outcome rules if termination cannot be confirmed.

## Final merge guard

### Independent correction receipts

Finish branch/base synchronization, version fixes, configured checks, and mutating
closeout work **before** full completeness dispatch. Freeze the factual PR body and
verification logs. Do not keep adding adjacent explanations or provisional counts;
unsupported new prose creates new review work. Never advance the base with this run's
brief bookkeeping during the final evidence window.

For a bounded correction after an accepted full report, refresh all current input files
and prepare an independent worker with the same role and the latest baseline:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" prepare --role completeness --previous <latest-accepted-worker> --worktree <worktree> --file ticket=<ticket.md> --file inventory=<requirements.json> --file criteria=<criteria-file> --file diff=<current-full-diff> --file pr=<current-PR-body> --file verify=<current-verification-log>
```

The delta manifest references a separate, byte-preserving before/after committed-tree patch, lists changed
input names, prior immutable report and citation hashes, and old/new input references.
It requires clean trees, unchanged requirements, a complete accepted baseline, and
**at most two delta attempts per invocation**, including failed attempts. The two full
passes remain the workflow's separate bound. Older states without clean-tree/snapshot
metadata require a full review, not an inferred baseline. Failure/rejection never resets
either budget. If full review is needed and its budget is spent, stop.

Read the manifest first to assess scope; inspect the patch/code by relevant section rather
than dumping a large patch into the parent context. The patch hash is verified at publication
and merge. A large/broad patch calls for honest escalation, never silent truncation.

The fresh reviewer checks the source/inventory, corrected code for defects, current
claims/caveats, all changed dependencies, and indirect effects on every requirement.
Unchanged citation bytes only identify reuse candidates; they never prove behavior is
unchanged. Retrieve the original diff/code where needed. Return the usual full current
verdict set and this additional object (including when reporting an honest escalation):

```json
{"delta_review": {
  "previous": "<baseline worker ID>",
  "manifest_sha256": "<packet's delta sha256>",
  "disposition": "sufficient",
  "checked_requirement_ids": ["P1", "AC1"]
}}
```

`full-review-required` is the other disposition; it publishes successfully but blocks
merge. The host must not author the review, rewrite `not-met`, or copy forward a verdict
without independent applicability checks. Resolve every current citation, consume/accept
the report, and use the new worker ID at merge. Any subsequent code/input mutation still
invalidates this receipt. Missing history/coverage, new requirements, or broad changes
use a full independent review within budget, not an ever-growing “delta”.

After citation resolution, the existing checks/thread/rebase gates and pre-merge
closeout, refresh the ticket source and validate the consumed completeness receipt:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" merge-gate --worker <completeness-worker> --worktree <worktree>
```

Run this as its own command immediately before the merge command. Exit 1 or 2 means
**stop before merging**, leaving the branch/worktree/PR for recovery. No degraded,
pending, stale or unconsumed result passes; all mandatory items need cited `met`
verdicts, and all worker results/termination outcomes must be accounted for. A rebase,
code/input change, or repaired requirement needs a new applicable completeness result
within the bounded full/delta passes; exhaustion stops rather than waiving the gate.
This guard takes precedence over legacy prose that allowed filing an unmet criterion
or merging with degraded completeness. Non-required follow-ups remain permissible.

## Usage snapshot and final reporting

At completion/stopping call `stage complete` or `stage stopped`, then `summary`.
Report measured stage times, worker states/delivery lag, validation runs and repeated
signatures. Token counters are not inferred from text length. When the host exposes
the raw session path, run `scripts/telemetry.py <parent.jsonl> --runtime "$RUNTIME_STATE"`;
it includes available sibling subagent logs, deduplicates streamed messages, separates
cache reads/writes/uncached input/output, and counts actual compaction boundaries.
Report unavailable/missing child logs and the last observed request cutoff. The final
response may not yet be in the live log; refresh the snapshot afterward for benchmark
comparison. Do not call a live partial snapshot a complete invoice.
