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
verification, never success. Read relevant failure output from the log; do not pipe the runner
through a success-masking command. Missing state/invalid input returns exit 2 and
must be repaired, not interpreted as a passed gate.

### The verification index

Every run appends a receipt: command hash, exit status, log path and log hash, elapsed
seconds, the revision it ran against, and an **environment signature** over the four
toolchain facts the outcome depends on (`os.name`, platform, Python minor version, shell
basename). The signature is those facts and nothing else — never a copy of the
environment, which would put credentials into durable state and invalidate every receipt
on an unrelated variable.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" verifications --worktree <absolute-worktree>
```

Each entry carries `applicable` and, when false, the reasons: the revision moved, the
toolchain signature differs, the log is missing or was edited after the run, or the
command modified the tree it verified. Read this index before rerunning a command.

`verify --reuse` returns an applicable passing receipt instead of running again, and
records a `verification_reused` event. It reuses nothing else: a failure, a receipt
whose log changed, a moved revision, a changed signature and a tree-modifying command
are all rerun. Reuse is a stated choice at the call site, never a silent cache — omit
the flag and the command always runs. A reviewer may still run its own independent
probes when the evidence or the risk warrants it; a receipt is a floor, not a ceiling.

### State-lock recovery

Transactions use an OS-managed lock on the persistent `state.lock` **file**: `flock`
on Ubuntu/WSL2 and a nonblocking `msvcrt` byte-range lock on native Windows Python.
Process exit or termination releases the lock automatically; retry the same command
against the same state after the host confirms the holder ended. An interrupted atomic
write leaves the previous committed state intact. An unused file is normal, not a stale
lock. **Never delete or replace this file**: that can let two processes lock different
files and write the same state concurrently. A live holder makes contenders time out
after five seconds with an OS-lock message, not a guessed stale-PID diagnosis.

Legacy releases used a directory at `state.lock`, without owner metadata. The runtime
refuses to guess whether that directory is abandoned. Stop/confirm termination of all
old runtime processes for this invocation, then remove **only that exact empty legacy
directory** with `rmdir` and retry. Never recursively delete it, edit `state.json`,
reset the invocation, or remove it merely because it is old. If ownership cannot be
established, stop and ask the operator rather than breaking a possible live lock.
Upgrading while an old binary owns a directory fails closed; use one runtime version
per invocation.

Scope: local filesystem and one OS host per invocation. Simultaneous native-Windows
and WSL processes sharing one state, and network filesystem lock interoperability,
are not guaranteed; do not share an invocation across those boundaries. This lock
protects state transactions, not the lifetime of an agent or provider operation.
Worker cancellation still requires host confirmation under the protocol below.
See [Python locking](https://docs.python.org/3/library/fcntl.html) and
[Windows byte-range locking](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking?view=msvc-170).

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
`implementation`, `branch-review`, `local-review`, `completeness`, `record`, or `probe`.
Supply the necessary input files (not a
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
citation rules. Write a list of `{id, artifact, quote, depends_on}` objects: a real
evidence/log path, the exact supporting text for each requirement, and the source files
that receipt's conclusion rests on — not the deliverable's own unsupported claims. Run
`resolve-citations --worker <worker> --citations <file.json>`.
The runtime checks quotes against files, records their hashes, and rejects missing or
changed evidence at merge. Semantic sufficiency still requires independent judgment.
A citation that cannot be resolved stops merge; neither consumption nor a child saying
`met` substitutes for this check. Never rewrite the child's immutable verdict to pass.

**Resolve immediately after consuming a result, with whatever the report supports.**
Ingestion is per item: a call may cover a subset, later calls add the rest, and
re-resolving an ID replaces that one entry rather than duplicating it. The call returns
`resolved`, `unresolved` and `complete`, and **exits 1 while anything is unresolved** —
the evidence is durable, the gap is named, and neither is mistakable for the other.
Partial ingestion relaxes *when* evidence becomes durable, never whether it is complete:
`merge-gate` still requires every requirement resolved. An ID outside the inventory is
rejected rather than stored. Do not defer resolution until the end of a review round —
that is what left a following delta with an empty evidence set and no basis for reuse.

`depends_on` is how a receipt goes stale without its own bytes changing. A cited test
log does not change when the helper it exercised does, so the sources a verdict rests
on are named explicitly; `merge-gate` blocks on a changed or missing dependency exactly
as it does on changed evidence. Declaring nothing means claiming the receipt depends on
nothing, so declare the files a rechecking reviewer would have to read.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" evidence --worker <worker>
```

The evidence index classifies every requirement into one of four states, never two:
`current` (artifact and dependencies intact), `stale` (something it rests on changed,
is missing, or is inside the pending change), `blocked` (the reviewer's own verdict was
not `met`, however intact the bytes are), and `unresolved` (no evidence recorded). It
exits 1 while anything is unresolved. `current` marks a **reuse candidate**, not a
verdict: unchanged bytes identify what need not be re-derived, and never establish that
behavior is unchanged.

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

### Corrective code before the first completeness receipt

Before post-round sweep edits/reverts, on the clean committed worktree, register:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" correction-needed --worktree <worktree> --reason "<what made this necessary>"
```

This records the pre-edit revision, not a review verdict. `--reason` is recorded, never
inferred; `summary` reports the causes. A repeat registration keeps the original
baseline and only adds a new cause — and adding one invalidates an existing completeness
receipt, because a new cause means new corrective code is coming. Register before editing,
never after committing the fix. Repeated registration preserves the original baseline;
it cannot clear an obligation. All terminal sweep branches that change code use it.
If registration was missed, stop and recover the true baseline through independent
review; do not pretend that an empty post-fix diff proves the edit was checked.

Commit and validate the correction, then prepare the first **full** completeness
worker normally (no `--previous` required). Its packet includes `correction_manifest`,
a hash-bound path indexing the entire pre-edit/current committed-tree diff, including
incoming base changes and deleted files. Patch bytes live in a separate file; do not
copy them into the parent prompt. The manifest and patch are checked at publication
and merge. Subsequent full/delta workers retain this explicit obligation too.

The independent verifier additionally applies the `notion-dev:local-code-review`
rubric to the correction and its indirect effects, without spawning another worker.
It returns this object alongside (not instead of) the full completeness result:

```json
{"correction_review": {
  "id": "<correction manifest id>",
  "manifest_sha256": "<packet's correction_manifest sha256>",
  "verdict": "clean",
  "blocking_findings": [],
  "report": "VERDICT: CLEAN\n<code review evidence and scope>"
}}
```

Use `not-clean` with `VERDICT: NOT-CLEAN` for defects, or `unverified` with
`VERDICT: UNVERIFIED` for insufficient scope/evidence; report findings honestly.
Only one exact `VERDICT: CLEAN` header, a clean structured verdict, no blocking
findings and the matching manifest can pass. Missing or mismatched code review blocks
merge even if all requirements are met. It is legal to publish/consume a nonpassing
report so the parent can triage it; acceptance does not turn it into a passing gate.
Completeness alone is not code review. This adds a task to the existing independent
worker, not another reviewer round or a reset of the two-full/two-delta budgets.
If the patch requires broader review than the remaining budget supports, stop.

### Independent correction receipts

Finish branch/base synchronization, version fixes, configured checks, and mutating
closeout work **before** full completeness dispatch. Freeze the factual PR body and
verification logs. Do not keep adding adjacent explanations or provisional counts;
unsupported new prose creates new review work. Never advance the base with this run's
brief bookkeeping during the final evidence window.

Before a corrective code edit or rebase after an accepted report, register
`correction-needed` on the clean pre-edit tree too; any existing baseline is retained.
For a bounded correction after an accepted full report, refresh all current input files
and prepare an independent worker with the same role and the latest baseline:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" prepare --role completeness --previous <latest-accepted-worker> --worktree <worktree> --file ticket=<ticket.md> --file inventory=<requirements.json> --file criteria=<criteria-file> --file diff=<current-full-diff> --file pr=<current-PR-body> --file verify=<current-verification-log>
```

It requires clean trees, unchanged requirements, a complete accepted baseline, and
**at most two delta attempts per invocation**, including failed attempts. The two full
passes remain the workflow's separate bound. Older states without clean-tree/snapshot
metadata require a full review, not an inferred baseline. Failure/rejection never resets
either budget. If full review is needed and its budget is spent, stop.

#### The delta index is a table of contents, not the material

`delta.json` is a **bounded index**, kept at or under 2KB of content. It names one
`directory` and one `worktree`, and every artifact it references is a `{file, sha256,
bytes}` triple **relative to that directory** — join the two to open one. It carries:

| Key | What it references |
|---|---|
| `patch` | The byte-preserving before/after committed-tree diff, in its own file |
| `inputs` | Before/after input names, hashes and snapshot paths |
| `previous_report` | The prior immutable report, **by reference** — never inlined |
| `evidence` | Per-requirement applicability counts plus the full evidence index file |
| `sections_file` | The complete lists, whole, for paged retrieval |
| `reuse_applicable` / `recheck_needed` / `blocked` / `unresolved` | Requirement IDs by state |
| `changed_paths` / `changed_inputs` | What moved since the baseline |

Lists are inlined while they fit the budget; the largest is shortened first, and every
shortened list is named in `sections.incomplete` with its true count in
`sections.counts`. `complete` and `within_budget` say so at the top level. An inlined
list is always a **prefix of page 1**, never a sample, and a short one is never the
whole section. Retrieve the rest a page at a time:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" section --worker <worker> --name changed_paths --page 2
```

**No truncated section and no unread page is complete input.** A reviewer that reasons
from a shortened list as though it were whole has not bounded its scope; say so and
escalate instead. Read the index first to assess scope, then only what it references,
by relevant section rather than dumping a large patch into the parent context. Every
referenced artifact's hash is verified at publication and at merge. A large or broad
patch calls for honest escalation, never silent truncation.

Classify each requirement before investigating: `reuse_applicable` is the candidate
set, `recheck_needed` and `unresolved` are the work, `blocked` needs the baseline's own
unmet verdict resolved. Deeply investigate the affected and unresolved subset, and widen
the dependency closure the moment an indirect effect appears. Every current verdict is
tied to the current reviewed state even where its evidence came from an earlier receipt.

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

## Host publication probe

Before trusting the durable-result path on a host for the first time, prove it on that
host. Prepare a worker with role `probe`, dispatch a disposable agent, have it publish
a result carrying the exact bytes it was given as `payload`, and check what landed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" probe --worker <worker> --expect <payload-file>
```

The finding is `delivered`, `truncated`, `mangled` or `missing`, with both hashes and
the delivery lag; exit 1 for anything but `delivered`. Use a payload with non-ASCII
text and enough length to cross the host's own limits — a short ASCII round trip proves
nothing about the case that fails. **Write the expectation file as UTF-8 with LF**: the
probe compares bytes on purpose, so a CRLF expectation makes every delivery `mangled` on
Windows against a host that is working correctly. A schema test that only shows a valid result object
exists cannot distinguish these four outcomes, which is why this compares bytes.

An unsupported host stops honestly. Do not route around a refused write by asking the
worker to perform the same prohibited action through shell commands, and do not claim
a notification or resume API the probe has not exercised on that host.

## Recording provider operation outcomes

The runtime performs no provider call and holds no credential; the host's authorized
tools do that. What it records is the outcome, so an interrupted operation is visible
to whoever resumes rather than retried blind:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" record-op --operation <stable-logical-id> --target <what> --outcome attempted
```

Outcomes are `planned`, `attempted`, `confirmed`, `unknown-outcome` and `failed` —
there is no sixth, and an unacknowledged create is `unknown-outcome`, never `failed`
and never omitted. Reconcile an `unknown-outcome` create by provenance or readback
**before** any retry. `summary` lists every operation that is not `confirmed`, so a
provider outage cannot end a run as "fully recorded".

## Usage snapshot and final reporting

At completion/stopping call `stage complete` or `stage stopped`, then `summary`.
Report measured stage times, worker states/delivery lag, validation runs and repeated
signatures. Token counters are not inferred from text length.

`summary`'s `end_to_end` block adds worker counts by role, workers still neither
accepted nor confirmed terminated, verification reuses, per-worker evidence
applicability, record-operation outcomes and correction causes. Its `scope` field is
part of the report: these counters cover **what this runtime observed** — registered
workers, measured stages, commands run through `verify`. A command run outside the
runner and an agent never registered as a worker are unknown, not zero. The older
narrow counters are unchanged and still present; they were never whole-run totals.

When the host exposes
the raw session path, run `scripts/telemetry.py <parent.jsonl> --runtime "$RUNTIME_STATE"`;
it includes available sibling subagent logs, deduplicates streamed messages, separates
cache reads/writes/uncached input/output, and counts actual compaction boundaries.
With `--runtime` it also **correlates each child log to its worker** by host agent ID,
labelling every child with its role, slot and the stage it was prepared in, and
aggregating usage per role. `correlation` reports both directions: workers whose log is
absent (unknown cost, never zero), workers never attached, and logs that match no
worker (real cost this run cannot attribute). `peak_context` reports the parent's peak
and the largest child's peak separately, because peaks are concurrent scopes and adding
them would describe a context window no single request ever held.
Report unavailable/missing child logs and the last observed request cutoff. The final
response may not yet be in the live log; refresh the snapshot afterward for benchmark
comparison. Do not call a live partial snapshot a complete invoice.
