---
name: knowledge
description: Use when a run needs the repo's knowledge bundle — `retrieve` assembles one budgeted context block from the epic's root concept, `capture` writes what a merge or a new fact taught, `curate` resolves near-duplicate concepts, and `migrate` moves a client's existing bundle onto this schema; besides `scripts/knowledge.py` this skill is the only part of the plugin that invokes `iwe`.
---

# knowledge — operation router

Load `${CLAUDE_PLUGIN_ROOT}/skills/knowledge/references/common.md` once, then ONLY the
requested operation below. Reuse already-loaded instructions and read-only config within the
invocation; invalidate config/schema caches on file/revision change or provider schema errors.
Never cache live ownership/status checks across a write or assume a cached source is current.

| Operation | Required reference |
|---|---|
| retrieve | `references/retrieve.md` |
| capture / capture --fact | `references/capture.md` |
| curate | `references/curate.md`, then capture's write rules when actually writing |
| migrate | `references/migrate.md` |

Paths are relative to this skill. Read a cross-referenced operation only when that branch runs.
The ticket is authoritative; the bundle is background. Fail closed on writes, degrade visibly
on reads. `next-task` selects through epic-doc **schedule** before ticket-title-seeded retrieve.
