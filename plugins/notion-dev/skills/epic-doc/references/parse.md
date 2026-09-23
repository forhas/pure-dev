# Parse an already-retrieved brief

No provider fetch, Git call, writer instructions or sibling-body reads. The caller supplies
the root document (first fenced markdown document in an iwe result, frontmatter stripped)
and the live child list, if already read at this selection boundary.

Return EPIC_CONTEXT unchanged, NEXT (ordered keys and reasons from `## Next`), BLOCKED (keys
on `Blocked:`), STATUS (header open/closed), CHILDREN, BOOTSTRAP and SEED. Preserve all
constraints, historical decisions and release obligations in the root; do not summarize them
away. Requirements still come from the selected full ticket, never this background.

Set DRIFT true for a known mismatch between live child membership/status and the Next partition.
Do not claim a full dependency/order audit happened: otherwise DRIFT is `unknown`, not false.
Legacy callers requiring that audit load `read.md`; writers derive against live data with
`refresh.md`. Missing or failed reads remain unavailable, never an empty or completed epic.
