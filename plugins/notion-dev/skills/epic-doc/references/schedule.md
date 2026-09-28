# schedule(<epic-id>) — selection before knowledge expansion

Read-only. Reuse the caller's verified epic identity/marker from this selection boundary (else
resolve it with ticket-system) and read `listEpicChildren`
once at this selection boundary. These are live statuses; do not infer ownership from a brief.
Fetch origin and locate only `<knowledge.dir>/epic/<KEY>-<n>-*.md` on
`origin/<epicBranch>` (`git.prTargetBranch` or `git.baseBranch`). Read that brief with `git show`.
Do not retrieve the knowledge bundle, expand concept links or fetch all sibling bodies yet.
Return the brief path, blob identity, NEXT/BLOCKED/STATUS and live CHILDREN via `parse.md`.

A missing brief takes `bootstrap.md`'s in-memory path, preserving every actionable seed
constraint; a failed fetch is unavailable, not missing. A known partition drift uses `refresh`
under its normal lock/write path. Unknown dependency-order drift alone is not a reason to
fetch every sibling: validate the candidate below. Disk bootstrap is the existing
`record --bootstrap` path, not an ad-hoc write.

Also run `knowledge.py epic-goal --brief <brief> --state <live-state.json> [--log <resolution
log>]` over the same boundary and return its GOAL, FOLLOWUP_RATE, GENERATION, `rehome`,
`brief.over_budget` and `release.warnings`. A `goal: met` epic passes `goal_met: true` into the
select plan, which then returns no candidate.
Return these references/fields to next-task; schedule does not select or fetch a candidate.
The caller owns the following selection checks, once: resume an owned unresolved worktree first.
For new selection run `knowledge.py retrieval-plan --purpose select --state <live-state.json>`
(configured `knowledge.python`). Supply the brief's ordered keys as `candidate_order`, stop keys
as `stopped_keys`, threads as `thread_blocked`, and a unique fresh-read `boundary`. Fetch only the
returned `fetch` entries, annotate the checked candidate's `checked_boundary` and explicit
`dependencies_known: true`, and repeat the planner until candidate or blocked. External status
reads populate `external_statuses`; failed reads remain unknown and enter `unavailable_keys`
for this boundary so the planner cannot request them indefinitely. If no candidate remains,
report blocked with those failures, not epic complete. A changed content revision
invalidates dependency content. Never reuse a boundary/status list after a write. The helper
does not claim tickets: full requirements and live ownership remain mandatory below.
Otherwise visit NEXT in order, then remaining live
children in configured phase/step/numeric order. Candidates must be live unresolved children,
not claimed elsewhere, not held by BLOCKED or an Open thread. Fetch the full candidate ticket
and verify every `## Blocked by` key against live resolved statuses. A dependency may be outside
this epic; resolve it explicitly. Unavailable/unknown is blocked, not permission to proceed.
Keep selection reasons and retained full ticket/source identity by reference.
`dependency check pending` in a brief is an unexamined candidate, not ready and not permanently
blocked. Fetch candidates progressively in the established order until one is proven eligible;
never dispatch a gatherer to fetch every sibling simply to select one. Preserve unknowns for
the unexamined tail. Reuse cached dependency content only with a trustworthy unchanged provider
revision; statuses and ownership still need current checks. Outside-epic dependencies require
explicit live resolution; absence from CHILDREN is not proof of completion.

Only AFTER selecting a candidate the caller invokes knowledge `retrieve(epic, ticket-title, ticket-key)` once.
That targeted retrieval must retain the complete epic root's relevant constraints/history and
release obligations, including sibling-path constraints; the entire selected ticket is still
mandatory. Reuse identity/child metadata from this same selection boundary, but check live
ownership/status again before a claim or write. Do not transport the previous ticket's history.
