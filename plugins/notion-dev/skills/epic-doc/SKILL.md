---
name: epic-doc
description: Use when a ticket that belongs to an epic starts (read the epic's markdown brief from origin/<base> as context), when a ticket resolves (rewrite that brief and commit it to the base branch), when /notion-dev:next-task needs the epic's recommended next ticket, and when /notion-dev:new-info routes a fact to the brief (`note`). The single owner of the epic brief — see "The file" below for its path.
---

# epic-doc — operation router

One brief per epic at `<knowledge.dir>/epic/<KEY>-<n>-<slug>.md`; lookup by key, never slug.
Read/write branch: `git.prTargetBranch` or `git.baseBranch`, from the primary config.
Background only: full ticket requirements and live provider status remain authoritative.
Operations are best-effort, but never select from a known failed drift repair. Report failures.

Load ONLY the requested operation under `${CLAUDE_PLUGIN_ROOT}/skills/epic-doc/references/`:

| Operation | Reference |
|---|---|
| schedule (lean next-task) | `schedule.md` |
| parse (already-retrieved root) | `parse.md` |
| read (legacy full drift audit) | `read.md` |
| refresh start/stop/create/drift | `refresh.md` |
| record / record --bootstrap | `record.md` |
| note / note --apply | `note.md` |

Writers additionally load `format.md`, `write-path.md`, `output.md`; bootstrap loads
`bootstrap.md` only when missing. `record` and `note` use `refresh.md` for derived Next.
`note --apply` also reads record's preconditions. Readers do not load any writer manual.
Use configured `knowledge.python` (`python` on native Windows Git Bash; `python3` on WSL
unless configured otherwise). Reuse unchanged read-only config/instructions in this invocation.
