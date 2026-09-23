## `read(<epic-id>, <current-ticket-id>?, KNOWLEDGE_CONTEXT?)` → `EPIC_CONTEXT` or `null`

Read-only. Runs before any worktree exists, so it **writes nothing** — not the brief, not a bootstrap, nothing in the primary checkout. `read` is now a thin parse over a `retrieve` result: the fetch itself lives in `notion-dev:knowledge`, and `read` never runs `iwe` or `git` on its own.

1. `KNOWLEDGE_CONTEXT` supplied by the caller → use it, **no fetch of any kind — not Notion, not git.** Otherwise invoke the `notion-dev:knowledge` skill, operation `retrieve(<epic-id>, <ticket-title>?, <current-ticket-id>)` once — the id goes in the **third** argument; `read` is given no title, so the lexical seed is simply omitted, whereas passing the id where the title belongs makes `--lexical "<ticket id>"` a seed that matches nothing — this applies the epic predicate itself, exactly as `findEpics()`, `getEpicContext` step 2, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply it; not an epic → return `null` — and take its result as `KNOWLEDGE_CONTEXT`.
2. Return `EPIC_CONTEXT` — the root document (`KNOWLEDGE_CONTEXT`'s first fenced document, frontmatter stripped) — plus the fields already parsed from it: `NEXT` (the ordered list from `## Next`, each item's `<KEY>-<n>` and its reason text), `BLOCKED` (the `Blocked:` line's keys), `STATUS` (`open` or `closed` from the header line), `CHILDREN` (one `listEpicChildren(<epic-id>)` call inside `retrieve`, `[{ id, key, title, status, url }]`, for the caller's validation — when `<current-ticket-id>` is given, marked `(this ticket)` as `getEpicContext` does), and `BOOTSTRAP`
   — and `DRIFT`. `read` writes the root document to a temp file, assembles the state JSON
   `refresh` shows from `CHILDREN` and the epic's live status (`status_class` = `resolved` when the status is in
   the resolved set, `in_progress` when it equals `statusMap.inProgress`, else `open`; every
   unresolved child's `## Blocked by` keys, `metadata.phaseProperty`, `metadata.stepProperty`
   from one `fetchTicket` each — the same fetches `record` step 2 makes), and `thread_blocked` — from the current `## Open threads`, for each bullet the keys it says it blocks or holds (`blocks STO-22, STO-23`, `holds STO-x`), never a key after `Unblocked by:`, never a key a bullet merely informs (`revisit in STO-71`), and never a stop bullet (the script adds those from the bullets themselves) — the same judgment `record` step 2 applies when it writes `Blocked:`. Then runs the derivation
   command `refresh` names with no `--reason`, and reads only its stderr: `DRIFT: 0` → `DRIFT:
   false`; otherwise `DRIFT: true` with the `drift:` lines verbatim (the findings now also include a listed child whose title differs from its live title, and cases where the numbered order differs from the derived order). `read` still writes nothing —
   not the brief, not a lock, nothing in the primary checkout: it runs before any worktree exists.
   Whoever writes next repairs the drift — `/notion-dev:ticket` through its Phase 2 `start`,
   `/notion-dev:next-task` through `refresh drift`. `BOOTSTRAP: true` (with `SEED: <path>` or `SEED: notion`) means the brief does not exist yet — `retrieve` bootstrapped it **in memory**; the file is created later by the first `record` — a resolution's, or `/notion-dev:next-task`'s `record --bootstrap`.

Callers treat `EPIC_CONTEXT` as **background, not requirements** — the ticket body remains the single source of truth for what to build, exactly as it was when this context came from Notion.
