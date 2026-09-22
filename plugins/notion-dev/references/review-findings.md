# Review findings — load only when findings or deferred candidates exist

Use the caller's runtime, reviewed HEAD and remaining budgets. This reference does not start
another loop or require an external build-framework skill.

## Judge and preserve

Read all inline, review-body and PR-comment findings. Correlate inline comments by
pull_request_review_id; track body comments by ID. Ignore boilerplate, not substantive requests.
Check code and authoritative requirements before agreeing. Record agree / partially agree /
disagree, with evidence. Declining an incorrect suggestion is not dropping a valid defect.

Maintain one compact ledger beside runtime state: finding ID, source/URL, reviewed SHA,
path/scope, mandatory-or-separate, judgment, disposition, rationale, fix commit or blocker.
Reuse it across rounds and resume. Never reconstruct it from the whole conversation.

Dispositions for agreed findings:

- **absorb:** fix here; default for defects in this PR, especially requirements, regressions
  and safety guarantees. A protocol/API change may size the fix but never excuses deferring
  a defect in this PR's own guarantee.
- **file:** genuinely separate work only. Cite one criterion: (1) a new public interface,
  dependency/config or migration outside the requirement; (2) an unsettled design decision
  outside the ticket; (3) work large enough to obscure the ticket's review. Touching another
  file is not a criterion. Preserve the approved packet and criterion for epic-update.
- **drop:** insignificant/speculative/low-value work, with a concrete rationale. Never hide
  a real requirement defect, failed test or unverified mandatory claim under this label.
- **blocked:** an actual external cause (authority, credentials, unreachable required service),
  naming cause and unblocker. Length, complexity and needing a protocol change are not external.
  Do not turn a blocker into a follow-up ticket; required blocked work stops the merge.

A label never waives mandatory ticket work. A user-approved scope change must update the
authoritative source/inventory and receive appropriate fresh review; it is not a bookkeeping fix.

## Fix in coherent batches

Fix failing CI first; failed reads are not green CI. For each accepted batch, make the smallest
complete correction, including necessary callers/tests/docs. Avoid cleanup unrelated to the
finding. Batch coupled fixes in one commit and record the mapping; do not require a complete
test suite and commit for each comment. Run applicable configured verification once for the
completed batch through workflow.py verify. Reuse valid receipts; changed inputs invalidate them.
Commit explicit owned paths, push, then post/verify replies and resolve corresponding threads.

If a correction creates another defect, identify the chain and either repair it within the
remaining review budget or safely revert an optional improvement. Never revert a mandatory fix
into a known unsafe state or file a correctness regression merely to end the loop.
From round three onward do not introduce optional cosmetic churn. No round limit makes
unfinished mandatory work mergeable. Empty/no-actionable feedback on unchanged code ends the
external loop; do not retrigger merely for a new report or reply.

## One bounded deferred-work sweep

Skip entirely when no FILED or termination-deferred candidates exist. Otherwise, once before
the final combined review, recheck whether each candidate really meets its filing criterion.
Absorb small same-scope work now; retain genuinely separate items with their criterion.
This sweep adds no extra external review round: the combined independent code/completeness
worker reviews the final batch. Record correction-needed before edits following any independent
review, and preserve the correction obligation through the delta/full review protocol.

After that review, only bounded corrections of its findings are allowed. No second sweep,
new optional scope, reset budget or second overlapping local reviewer. Exhausted mandatory
work stops with the exact evidence and resume command.

## Return durable dispositions

Persist ABSORBED, FILED, DROPPED and BLOCKED lists, plus declined suggestions separately.
Every absorbed item names a real fix; every filed item retains criterion and packet; blocked
items retain cause/unblocker. Empty lists explicitly say none. Include reviewed SHAs, rounds,
fix commits and runtime result references. Ticket/epic consumers use these facts directly.
