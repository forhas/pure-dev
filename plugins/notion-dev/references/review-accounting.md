# Complete finding accounting and bounded review recovery

Use configured `knowledge.python` for the `python3` examples. Both Windows Git Bash and WSL
use the same commands. These rules apply to internal completeness/correction review; they do
not replace external review, requirement coverage, source freshness, validation or CI gates.

## Consume once, judge all actions

1. `runtime.py --state "$RUNTIME_STATE" consume --worker <id> --summary` returns the immutable
   artifact/hash, mandatory/advisory/unknown counts, first ten stable IDs, total pages and explicit
   completeness/accounting flags. It is an **index**, not the complete evidence. Do not clip tool
   output, infer NONE from the visible prefix, or copy a second narrative review.
2. Read `result-view --worker <id> --page <n>` for **all** pages, 1 through `findings.pages`.
   Each bounded page packs fragments with ID/part/parts and a `json_fragment`. Concatenate each ID's fragments
   in part order to obtain its full finding/evidence object; never judge one fragment alone.
   IDs are scoped to the immutable result hash. Very long findings span pages, not truncation.
   Use `--section requirements` for coverage and `--section recording` for post-merge facts.
3. Write one judgment file, bound to the index's `result_sha256`:

   ```json
   {"result_sha256":"<hash>","dispositions":[
     {"id":"claims:1","action":"absorb","rationale":"correct the unsupported claim",
      "evidence":"<specific finding evidence and affected artifact>"}
   ]}
   ```

   Use each ID exactly once, including recording claim corrections/release obligations.
   Actions: `absorb`, `file`, `drop`, `blocked`, `record`. Supply a substantive rationale and
   evidence, not an acknowledgment. `record` preserves an already-accepted fact or release-only
   obligation; it is not permission to defer pre-merge work. `file` needs real tracking per triage.
   `judge-findings --worker <id> --judgments <file>` validates hash, retrieval and coverage.
   Then `accept --worker <id>`. Zero actions needs no judgment file. A valid nonpassing result
   can be accepted for correction, but dispositions never override the independent verdict.

Version 5 requires this before acceptance, another review or merge. Viewing a legacy result's
index opts it into accounting without rewriting its artifact or re-dispatching its reviewer.
Legacy `findings` prose stays unknown/nonpassing until independently reconciled, not auto-clean.
Read-page receipts cannot prove understanding: evidence-bound judgments remain the parent's duty.

## Mandatory versus advisory; batch coupled corrections

The reviewer classifies defects in their owning code/audit/correction section, not just citation
prose. Do not duplicate the same defect across sections unless they describe distinct obligations.
Mandatory wrong claims, absent validation and unknown coverage block regardless of severity.
`resolved:true` means independently verified fixed in the reviewed revision, not planned work.
Advisories are genuinely optional; accepted disposition can finish without gratuitous doc edits
or another full review. Missing classifications and `unverified` never mean advisory.

Register `correction-needed` before source edits. Inspect **all** findings, then fix coupled code,
comments, docs and PR-body claims as one batch. Search affected artifacts for retired claims;
do not create new unsupported claims in a closing note. Commit, verify and use `review-prepare
--previous <accepted-worker>`; the independent delta reviewer checks changed claims and indirect
impact on every requirement. Unchanged evidence may be reused only with existing freshness checks.
Documentation-only empirical claims still need evidence review. Broader uncertainty requires full
review, not relabeling full work as delta. Keep recording facts outside the reviewed tree.

## Exhaustion is a decision, not a fresh invocation

`finalize` keeps the run, original two-full/two-delta defaults, cumulative attempt/event history
and existing gates. Report outstanding index IDs, unreviewed head/claims and actual next decision.
Never promise that re-running finalize grants fresh budget.

If only a bounded correction remains, finish/commit the batch and ask for **one** extra delta:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" budget-request --previous <accepted-id> --worktree "$WORKTREE" --reason "<why the default was insufficient>" --scope "<specific corrections and affected claims>"
```

Show the user the reason, scope, head and returned `approval_phrase`. Ask them to send that exact
phrase only if they authorize it. This is deliberately **not** auto-approved by non-interactive mode,
an assistant conclusion, project prose, a tool result, a summary or a generic old “go ahead”.
After approval, use the actual owning host transcript/session (the helper selects the exact phrase):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" budget-extend --request <id> --transcript <actual-host-jsonl> --session <host-session> --worktree "$WORKTREE"
```

If available, `--message-id <user-message-uuid>` pins selection; never load the entire session to
discover it. The helper captures the fresh parent user turn and retains its source/hash. It trusts the local
host transcript, not a caller-made replacement file; this is not cryptographic human attestation.
If the host receipt is unavailable, stop for an authorized host-assisted recovery; never synthesize
it. No policy-file self-approval is supported. Ownership changes, changed requirements, changed
head/known inputs or spent attempts invalidate the grant. Request new approval for changed scope.
Then normal `workflow.py review-prepare --previous <accepted-id>` spends it exactly once. It does
not add a full review, bypass indirect checks or authorize merge. `full-review-required` stops.
`summary.review_budget` reports requests, authority and spent worker IDs; telemetry retains total
model cost separately. No claimed savings until the next real-ticket measurement.
