# notion-dev genericity audit — current-source recheck

Date: 2026-09-29. Baseline: `36717f6`, PR #88, notion-dev **0.45.0**.
Implementation: **0.45.1**. [Implementation plan](../superpowers/plans/2026-09-29-notion-dev-genericity-recheck.md).

## Conclusion and scope

The supplied 2026-09-28 prompt describes 0.44.0. Most proposed extension points already
shipped in 0.45.0: do not implement them again. The useful remaining work is repairing their
boundaries and removing two decomposition inefficiencies, not introducing another workflow.

Only pure-dev is changed. The prompt explicitly makes BTC-Gateway and
smart-contracts-foundry read-only and their transfers report-only. Neither client repository
nor any Notion page was changed. The recommendations below are not evidence of installed
plugin versions or applied client configuration.

The old prompt's automatic absorption language is unsafe as written: `land before X` is an
ordering constraint, not permission to merge tickets. A fold declaration also cannot replace
the absorbed ticket's requirements or user authority. The implementation retains single-ticket
runtime inventories and the existing approved re-scope path, not the multi-ticket runtime
proposed in #86.

## Evidence and classification

Paths in the table are relative to `plugins/notion-dev/`, unless prefixed `scripts/`.
Classification describes the assumption, not whether the entire file should move.

| Assumption / source | Classification | Current evidence and disposition |
| --- | --- | --- |
| Web-service-only failure classes, `references/scope.md`, `scripts/scope.py` | **Move** domain classes to clients | Already replaced in 0.45.0 by `failureModeClasses` / `failureModeReference` and neutral fallback. Keep. Repair malformed list handling and reference paths escaping the project, including symlinks. |
| Fixed units and artifact-only numerical claims, `scripts/scope.py`, `references/boundaries.md` | **Move** domain units; **generic** evidence rule | Configurable `figureUnits` and spec citations already work. Update stale artifact-only prose: a spec citation proves a parameter, not an observed performance gain. |
| Generated lines count toward filing size, `scripts/workflow.py:changed_lines` | **Move** generated-path selection | `generatedPaths` exists. Reproduction: a 900-line generated Unicode file was counted because Git quoted its name. Use NUL-delimited literal paths; keep `--no-renames`. Handwritten lines still count. |
| Non-goal findings always go to backlog, `scripts/scope.py:route_followup` | **Move** severity meaning / destination | Ordered label rules already exist. Keep project labels and gating epic IDs outside plugin defaults. Closure now preserves label/meta routing rather than re-homing every child to `nonGoalDestination`. |
| Meta work can return to its product epic through an override | **Generic** invariant | Reject `epic` or `epic:<source_epic>` for meta packets, including explicit routing rules. Match `META` consistently with other case-insensitive labels. A different known gating epic remains valid. |
| Brief lines approximate context, `scripts/knowledge.py:epic_goal` | **Generic** budgeting | 0.45.0 already checks byte-estimated tokens against `briefRetrieveShare * knowledge.retrieveBudget`. Align format documentation; never discard unresolved obligations to meet the budget. This is not a tokenizer guarantee. |
| `release` implies a customer version, boundaries / epic format / recording | **Generic** delivery ledger | Already defined to include deployment and activation. Keep ledger field names and sign-off semantics; do not invent a per-ticket sign-off. |
| `endpoint`, DTO, wire/error codes in schema failure-class examples | **Example (keep)** | Explicit examples alongside contract-system examples; not required domains. |
| `/balance/:chain`, authentication tasks and pipeline examples, task-breakdown | **Example (keep)** | Worked task/title illustrations, not a required project architecture. Remove the claim that the decision rules inherit BTC-Gateway's heuristics. |
| Customer-deployment fact in `commands/new-info.md`; example ticket IDs / seed filenames in epic-doc | **Example (keep)** | Illustrative facts and formats. No client identifier is used as a routing default or runtime condition. |
| `endpoint` in review GitHub API instructions and Notion connection diagnostics | **Generic** integration detail | Actual provider endpoints, not an assumption about the software being developed. Keep. |
| `release` in locks, runtime state, release notes and version history | **Generic** or historical description | Lock release and plugin version history are not project delivery assumptions. Keep; do not bulk-rewrite historical protocols. |
| Domain-shaped evaluation fixture / tests | **Example (keep)** | Existing `GenericityTests` exercise HTTP-service, contract-system and unconfigured neutral cases, configurable units/spec citations, generated paths, routing, dependencies and budget. Add synthetic boundary tests rather than copying either client's code or IDs into fixtures. |
| One key search discovers all sibling body declarations, scope / lean intake | **Generic** retrieval, broken coverage claim | Reuse known packets, brief and fetched-source leads. Only use body search when the actual provider supports it. Otherwise report partial coverage; never compensate by fetching all sibling bodies. |
| All fold phrases mean auto-absorb, including unattended | **Generic** intent / authority boundary | Parse escaped Notion brackets; distinguish prerequisite (`before`) from merge proposal (`with`); flag contradictory declarations. Verify live ownership/dependencies, scoped approval and consolidated authoritative requirements before implementation. |
| Follow-ups lack dependencies/surface | **Generic**, already solved | `dependencies`, `surface`, `lands_with` are validated/rendered by 0.45.0. Keep canonical `## Blocked by` body representation. Do not add a second dependency model. |
| A spec pivot should trigger re-scope | **Generic**, partially solved | The pending marker and recommendation exist. Fix stale-goal output supplying a re-home batch while pending; ensure current-resolution spec changes veto closure before recording persists them, on both filing paths. Ordinary recording cannot clear this marker. |
| More than eight files means more tickets, task-breakdown | **Generic** but inefficient heuristic | Remove file-count trigger. Independently deliverable outcomes justify splitting; coupled code/tests/docs/generated changes stay together. Review size alone can use stacked PRs under one ticket. |
| Every child needs all shared context, task-breakdown | **Generic** but redundant transport | Keep all applicable requirements/constraints/AC inline; link shared history/architecture by source and section. Never replace an actionable criterion with a link. |

Vocabulary review grouped occurrences of `endpoint`, `DTO`, `error code`, `wire`, `customer`,
`release`, BTC/Electrum and Solidity/ABI-related words across the plugin. Rows above account
for the functional families: domain configuration examples, worked examples, actual provider
APIs, delivery semantics, lock release and historical/legacy documentation. No domain-specific
default list is introduced by this patch.

### Two proposals deliberately not implemented verbatim

1. **Complete body discovery through title search.** Notion's REST search filters page/data
   source titles; that is not body search. An installed MCP provider may offer more, so inspect
   its real capability rather than assuming either capability exists. The scanner reports
   `coverage: supplied pages only`; unseen declarations remain unknown. This is an explicit
   retrieval boundary, not a claim of exhaustive discovery. See the
   [official Search reference](https://developers.notion.com/reference/post-search).
2. **Native dependency relation writes.** Neither inspected client config maps such a
   relation. `skills/ticket-system/references/create-ops.md` deliberately excludes native
   dependency writes because inferred property support does not establish writable relations
   through every supported provider. The SFC plan naming `Depends on` does not establish an
   adapter/config mapping. Retain supported body dependencies; do not make speculative writes
   or add an unused config key. Reconsider only with an explicit provider capability contract.

## Transfers — recommendations only

Evidence read: each client's `CLAUDE.md`, `.claude/notion-dev.config.json`, the two
2026-09-28 plans named in the supplied prompt, and SFC's security-gate skill. These are current
repository rules and historical analyses, not a fresh analysis of every underlying session.

### BTC-Gateway ← plugin

| Transfer | Evidence / exact destination | Dependency |
| --- | --- | --- |
| BTC failure classes, not generic defaults | BTC plan Part B; `CLAUDE.md` **Scope and Decomposition** and **Client/Server Contract Changes**. Put the short list below in `.claude/notion-dev.config.json` → `convergence.failureModeClasses`, or a dedicated reference. | Extension exists in 0.45.0; 0.45.1 validates references safely. |
| Domain figure units and generated paths | BTC wire amount/fee units, generated `openapi.json`, lockfile. Set `convergence.figureUnits` and `generatedPaths`; exclusions affect filing size only, never validation/review scope. | Exists in 0.45.0; 0.45.1 fixes Git-quoted names. |
| Off-product meta routing | Tooling/knowledge work is not the product goal. Set `metaDestination: backlog`, label such findings `meta` in **Scope and Decomposition**. | 0.45.1 rejects conflicting source-epic overrides. |
| Correct fold/dependency interpretation | Add a short reference to plugin re-scope in **Scope and Decomposition**, not a second copied procedure. Preserve current ownership/approval; `land before` remains a prerequisite. | Use repaired 0.45.1 intake. |

### BTC-Gateway ← smart-contracts-foundry

| Candidate | Evidence and recommendation | Exact target / dependency |
| --- | --- | --- |
| Spec gap is an owner decision | SFC rule 1 records an invented parameter and repeated follow-ups; BTC plan's timeout/client-budget ambiguity is a relevant counterpart. Ask for an undefined external contract parameter before implementing it; do not ask about every internal coding choice. | BTC `CLAUDE.md` **Scope and Decomposition** / **Client/Server Contract Changes**. No plugin change required. |
| Origin-aware gate warnings | SFC security-gate distinguishes own-change defects from pre-existing warnings. BTC currently has `preMergeChecks: []`; copying a new gate has no evidence-backed benefit. Retain existing own-feature absorb rules, and adopt origin routing if a real pre-merge gate is added. | No current BTC edit recommended; future gate's own skill, not generic plugin defaults. |
| Gated destination for release blockers | SFC rule 7 uses a dedicated mainnet readiness epic. BTC rule 2 already treats fund-loss/data-leak as serious. Keep such labels on a goal/gating parent rather than silently unparenting them. | BTC convergence destinations below; `epic` conservatively retains source parent until an owner designates a suitable separate gating epic. No guessed epic ID. |
| Meta stays off product epic | SFC rule 7 already says this. | BTC config + rule reference as above, after 0.45.1. |
| Hot-file bundling | Both projects already have same-surface/grouping rules (BTC rule 4, SFC rule 6). Do not add another scan or blanket same-file merge. | Retain rules; use existing approved re-scope when relevant. |
| Fold declarations / spec-change re-scope | SFC rule 2 and its review name missed declarations after spec pivots. | BTC rules should defer to repaired generic intake and pending re-scope, not add an automatic ticket-closure policy. |

### smart-contracts-foundry ← BTC-Gateway

| Candidate | Judgment / exact destination | Dependency |
| --- | --- | --- |
| Committed delivery before another round of polish | BTC rule 6 makes delivery commitments explicit. SFC rule 8 already has deployment obligations, but can name promised testnet/mainnet deliverables in the same ledger. Add only actual commitments in the epic brief's `## Release obligations`; do not create a second tracker. | Existing 0.44+ ledger supports this; actual provider/brief edits require a separate client task. |
| Incident-grouping window | Do not copy a fixed half-day batching delay. SFC's plan identifies spec decisions/pivots as its major driver, not BTC's incident timing. Keep SFC's existing surface grouping and re-scope on changed decisions. | No new client rule required. |
| Reviewer absorb/filing discipline, generated-size exemption | SFC own-feature rule 5 and rule 6 already cover the first part. Populate generated paths below to use the existing size mechanism. | 0.45.0 extension, 0.45.1 path repair. |

### Suggested convergence additions

Merge these into the existing `convergence` objects; do not replace the six existing settings.
These are suggested project policy, not settings applied by this PR. Config routing matches
explicit finding labels; it does not infer severity from prose. Retain any stricter owner
decisions or review gates.

**BTC-Gateway:**

```json
{
  "failureModeClasses": [
    "Client-acted verdict correctness, including address-pruning decisions",
    "Timeout and concurrency bounds relative to caller budgets",
    "Electrum active/standby connection and subscription lifetime",
    "Upstream outage, failover and error classification",
    "Wire compatibility: authentication bytes, DTO meaning, error precedence and amount units",
    "Sensitive-data masking in logs and error messages"
  ],
  "figureUnits": ["sat", "sats", "satoshis", "vB", "vbytes", "BTC", "tests", "subscriptions"],
  "generatedPaths": ["openapi.json", "package-lock.json"],
  "destinations": [{"match": "fund-loss|data-leak", "to": "epic"}],
  "metaDestination": "backlog",
  "briefRetrieveShare": 0.5
}
```

The BTC destination intentionally retains the product parent until a suitable gating epic is
designated. It can prevent closure, which is preferable to hiding release blockers. A `meta`
finding also carrying a label routed to `epic` needs an explicit different destination; it
fails closed in 0.45.1 rather than dropping either policy silently.

**smart-contracts-foundry:**

```json
{
  "failureModeClasses": [
    "Access control and first-caller-wins",
    "CEI and re-entrancy",
    "Parameter bounds: zero, maximum and overflow",
    "Irreversible or one-shot phase transitions",
    "Value conservation, rounding and donation",
    "Front-running",
    "Oracle, WETH or Uniswap failure",
    "ABI, selector, event, enum-ordinal and storage-layout compatibility",
    "Gas bounds",
    "Test-only code in mainnet bytecode"
  ],
  "figureUnits": ["bps", "ETH", "wei", "gwei", "gas", "e18", "tests"],
  "generatedPaths": ["abi/", "src/generated/"],
  "destinations": [{"match": "severity:(critical|high)|security|fund-loss|mainnet", "to": "epic:STO-390"}],
  "metaDestination": "backlog",
  "briefRetrieveShare": 0.35
}
```

SFC's current rule names STO-390. Revalidate its live status/ownership when applying; this audit
did not query Notion. Ensure the security-gate's **Routing warnings and notes** uses the same
labels on legitimate pre-existing findings; do not turn own-change warnings into filed work.
If the source epic itself is STO-390, a meta finding cannot be routed back there.

The proposed 0.35 share is a **trial**, motivated by the SFC plan's 12.7 KB brief and exhausted
retrieval headroom, not measured proof of an optimal setting. At an 8000-token retrieval budget
it assigns a 2800 estimated-token share to the brief. Protected constraints remain intact even
if over budget. BTC's 0.5 simply retains the default; there is no evidence to tune it further.

Instead of the inline lists, either client may place only these bullets in
`.claude/references/notion-failure-modes.md` and set `failureModeReference` to that path.
Choose one representation: the list wins if both are present. Do not point the parser at all
of `CLAUDE.md`, where unrelated bullet lists would become failure classes. Keep domain detail
project-owned and load it only for the design stage.

## Efficiency and quality impact

No new config keys, init questions, agents, reviewer seats, review rounds, base-branch commits
or mandatory provider calls are introduced. The single-ticket inventory and review/merge gates
are unchanged. Existing entry-point context is byte-for-byte unchanged; the intake pointer is
slightly shorter. New wording lives in stage references/skills, not an always-loaded preamble.

| Mechanism | Cost and benefit |
| --- | --- |
| Failure-class validation | Local path/list validation only; no extra model call. Stops wrong-file context before reading it. |
| Generated-path repair | Same one Git call, NUL-delimited. Prevents generated bulk from falsely justifying another ticket. |
| Meta routing / pending re-scope | Local checks on existing packets/briefs. Correctness prevents misplaced work and stale-goal closure; no extra review pass. |
| Fold handling | Reuses available leads; at most the existing search intent where body search is supported. Candidate-only fetches; no sibling full scan. Approval can require human input only when actually changing scope. |
| Child context / split rules | Saves duplicated shared context and artificial ticket boundaries. Per-ticket savings depend on actual decomposition; no numerical savings claimed. |
| Brief/evidence documentation | Aligns instructions with existing helpers, retaining all active constraints and direct evidence. No extra tool round trip. |

Measured UTF-8 sizes against 0.45.0 (not model tokens):

| File / group | Baseline bytes | Change |
| --- | ---: | ---: |
| `commands/ticket.md` | 8382 | 0 |
| `commands/next-task.md` | 3911 | 0 |
| `commands/finalize.md` | 4402 | 0 |
| `skills/review-and-merge/SKILL.md` | 13279 | 0 |
| `references/scope.md` | 8228 | +1049 |
| `references/boundaries.md` | 19598 | +175 |
| `skills/epic-update/SKILL.md` | 5618 | +460 |
| `skills/task-breakdown/SKILL.md` | 9910 | +493 |

The four entry points remain **29,974 bytes** combined. Stage-specific instructions increase;
this is not advertised as a prompt-shrinking patch. Their additional words replace unsafe or
ambiguous behavior. Token/time savings require subsequent real-ticket measurements and are
not a pre-merge claim of this correctness-focused audit. Compare parent peak context separately
from cumulative input/cache-read/output tokens, and track extra tickets, repeated exploration,
body fetches and late requirements as well as wall-clock time.

## Validation evidence

- Before fixes, the seven new synthetic regressions produced 14 assertion failures and two
  expected-validation errors against 0.45.0. All seven pass with the fixes. Existing 42
  decomposition tests pass too.
- An isolated `/tmp` copy removed the code safeguards and nine new instruction anchors.
  Every new regression test failed; the nine matching instruction checks each reported FAIL.
  The production checkout was never reset/restored for mutation testing.
- `bash scripts/run-verifications.sh`: all **27 harnesses pass** locally on Ubuntu/WSL2.
- No new config keys: existing cross-domain config tests remain in the same harness. New tests
  cover invalid/reference-escape paths, symlink escapes, Unicode generated paths, meta overrides,
  escaped/conflicting/order declarations and stale-goal re-home suppression.
- Native Windows Python cannot launch from this WSL host. Native Windows Git Bash and Python
  3.8 execution are validated by the existing PR CI jobs; their result is recorded on the PR,
  not inferred from local Linux passes. The symlink-only test explicitly skips on hosts without
  symlink creation privileges; ordinary absolute/parent/host-specific path tests still run.

Review boundary: prompt/skill ordering assertions prove instructions are present, not that
every host/model will follow them. Synthetic helpers likewise do not establish live provider
search coverage. The next normal client run should confirm scope approval, pending-spec
closure veto and compact retrieval behavior without changing review quality.
