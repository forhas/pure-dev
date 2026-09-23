# Efficient handoffs: implementation and measurement

The lean owner/reviewer/record architecture is unchanged. This release fixes observed contract
and handoff failures and limits which supporting manuals enter each stage. It does not claim a
measured token reduction, a <200K ticket, or a guaranteed runtime.

## Boundaries

```text
brief + live children → select + check full candidate → ticket-title-seeded knowledge
    → full authoritative inventory → cohesive implementation + applicable verification
    → configured external review → one combined independent review
    → resolve evidence → delta only for real changes
    → fresh full-ticket receipt + current PR/check/thread gates → merge
    → shared frozen recording → declared child writes → validated completion
```

| Boundary | Mechanism | Safety retained |
|---|---|---|
| Correction publication/gate | Result contract 3 uses one structured verdict; header is rendered | Exact manifest/obligation, independent author, nonclean/blocking findings still gate |
| Delta handoff | resolve-citations before prepare; named inputs inherited unless explicitly removed | Missing/stale evidence stays unknown; full inventory and two-full/two-delta budgets remain |
| Correction reuse | Same revision, obligation, inventory and declared external evidence | Changed dependencies invalidate; never author a substitute verdict |
| Intake | Operation routers, schedule before retrieve, title-seeded bounded knowledge | Full selected ticket, epic constraints/history, live status/ownership and dependency checks |
| Merge freshness | Schema-4 refresh challenge, captured full response, page/run/review identity, 5-minute boundary | New requirements outside AC stop merge; unknown/failed/status-only evidence fails closed |
| Recording | Payload 3 deduplicates archives and exposes canonical complete provider views | Full evidence stays local; unknown fields remain; no recursive file collection or truncation |
| Recovery | record-children and record-outcome use the existing journal | Unknown needs readback; confirmed children never replay; actual targets and frozen digests |
| Completion | complete validates journal/workers/ownership/owned lock and sets phase + state | Stop protection stays on until this boundary; explicit resume preserves budgets |

The freshness helper accepts the Notion MCP page-fetch JSON format, including its text-content
envelope. It is not a general Notion SDK. An unrecognized/incomplete response stops with an
actionable error rather than guessing. The host must supply the actual provider response and
call ID: standard-library code cannot attest a network request or detect deliberate forged
capture. All body text is retained, even in plugin-named sections. Only configured status/PR
properties and transport metadata are excluded from requirement comparison. Own pre-review
bookkeeping is captured before freezing the first internal review.

**Disposition: `blocked`.** Attestation is an external limit: the Notion MCP fetch returns no
signed response, so no local helper can prove a request happened. A provider-signed fetch
response would unblock it; until then the receipt fails closed on missing or incomplete capture.

Version boundaries are explicit: schema 1/2 legacy workflows (new explicit legacy flows use
`init --legacy`, never on a lean invocation), schema 3 existing lean invocations,
and already-prepared result contracts 1/2 keep their original obligations. New lean workers get
contract 3; new invocations get schema 4. Version-2 recording payloads remain consumable. Do not
reset state, edit published evidence, or create a new invocation to replenish review budgets.

## Verification and next live comparison

`test_handoffs.py` exercises punctuation-independent correction verdicts, stale dependency
invalidation, stable input identities, explicit evidence handoff, full-source refresh failures,
out-of-AC requirement drift, immutable deduplicated recording, partial child recovery, native
stdin Unicode, and terminal-state safety. It also checks router targets/read-set size and runs
the real iwe retrieval on a generic sibling/history/release-constraint fixture when installed.
The full CI jobs install iwe, so this fixture runs on Windows and Ubuntu. Existing historical
instruction assertions read test-only assembled views of the moved owners; the plugin never
loads these assembled views.

After merge, update the plugin and resolve one comparable real ticket. Keep parent/child JSONL
and its runtime directory, then run telemetry.py. Compare separately:

- Fresh input/output, cache reads, request count and parent peak context.
- Selection/intake time, first-edit context, and actual instruction/source read set.
- Full/delta counts; reusable/stale/unresolved evidence at delta preparation; changed input names.
- Format-only redispatches (target zero); source-unchanged correction retests (only for concrete doubt).
- Fresh-ticket receipts and requirements discovered after implementation began.
- Recording size, child retries/reconciliation, and turns after completion.
- PR-ready/end-to-end time, separating external review/provider waits from active work.

Use the same accounting conventions and record ticket scope/risk. Confirm quality through full
requirement evidence, configured checks and defect findings; a smaller context alone is not
success. No live savings are inferred from character counts or offline checks. A multi-ticket
sample is needed before attributing an aggregate improvement to this release.

**Disposition: `blocked`.** External cause: savings exist only in a live Claude Code run against
a client repository, which no offline test can substitute for. The real-ticket comparison above,
then the multi-ticket sample, is what unblocks it.
