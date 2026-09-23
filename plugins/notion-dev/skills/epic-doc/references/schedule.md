# schedule(<epic-id>) — selection before knowledge expansion

Read-only. Resolve the epic identity/marker with ticket-system and read `listEpicChildren`
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

Resume an owned unresolved worktree first. Otherwise visit NEXT in order, then remaining live
children in configured phase/step/numeric order. Candidates must be live unresolved children,
not claimed elsewhere, not held by BLOCKED or an Open thread. Fetch the full candidate ticket
and verify every `## Blocked by` key against live resolved statuses. A dependency may be outside
this epic; resolve it explicitly. Unavailable/unknown is blocked, not permission to proceed.
Keep selection reasons and retained full ticket/source identity by reference.

Only AFTER selecting a candidate invoke knowledge `retrieve(epic, ticket-title, ticket-key)`.
That targeted retrieval must retain the complete epic root's relevant constraints/history and
release obligations, including sibling-path constraints; the entire selected ticket is still
mandatory. Reuse identity/child metadata from this same selection boundary, but check live
ownership/status again before a claim or write. Do not transport the previous ticket's history.
