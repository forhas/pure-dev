Read `format.md`, `write-path.md` and `output.md` before writing. Load `bootstrap.md` only if the brief is missing. Cross-references to other operations name sibling files here.

## `refresh(<epic-id>, <reason>)` — the derived writer

Recomputes the derived parts of the brief from live state and nothing else: the header's
`Status:` and `Updated:`, the whole `## Next` region, and — for two reasons — one stop bullet
under `## Open threads`.
`<reason>` is one of `start <KEY>-<n>`, `stop <KEY>-<n> <phase> <cause> <worktree-path>`, `create <KEY>-<n>`, `drift`.

| reason | caller | effect beyond `## Next` |
|---|---|---|
| `start <KEY>-<n>` | `/notion-dev:ticket` Phase 2, after `updateStatus(id, "inProgress")` | removes that key's stop bullet when one exists |
| `stop <KEY>-<n> <phase> <cause> <worktree-path>` | `/notion-dev:ticket`'s failure-and-stop path | adds (or replaces) that key's stop bullet |
| `create <KEY>-<n>` | `/notion-dev:create-task` after a ticket gets an epic parent | none |
| `drift` | `/notion-dev:next-task` step 1 on `DRIFT: true` | none |

**Inputs, all live:** `fetchTicket(<epic-id>).status`, `listEpicChildren(<epic-id>)`, and one
`fetchTicket` per unresolved child for its `## Blocked by` keys, `metadata.phaseProperty` and
`metadata.stepProperty` — exactly what `record` step 2 fetches. `refresh` never reads the Notion
epic page body and never runs `iwe`.

**Derivation.** `python3` in every `knowledge.py` line below stands for `knowledge.python` from `$REPO_ROOT/.claude/notion-dev.config.json` (default `python3`; `python` or `py -3` on Windows, as `/notion-dev:init` recorded). Write the current brief (loaded from `origin/<epicBranch>` by the write path's
step 2) to a temp file, assemble the state JSON (plus `stop: { key, phase,
cause, worktree }` on a `stop`), and run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" next --brief <tmp brief> --state <tmp state.json> --today <YYYY-MM-DD>
```

```json
{
  "epic": { "key": "STO-60", "status_class": "open" },
  "children": [
    { "key": "STO-71", "id": 71, "title": "Cache metrics", "status_class": "open",
      "blocked_by": ["STO-70"], "phase": 2, "step": 1 }
  ],
  "thread_blocked": ["STO-22"],
  "stop": { "key": "STO-70", "phase": "Phase 7", "cause": "review loop stalled",
            "worktree": "../btc-worktrees/btc-STO-70" }
}
```

`status_class` is `resolved | in_progress | open` (resolved set, `statusMap.inProgress`, else); `id` is the numeric `idProperty` value as an integer; `phase` and `step` are integers or `null`; `blocked_by` lists `<KEY>-<n>` strings; `thread_blocked` is assembled as `read` states; `stop` is present only on a `stop` reason.

`` exit 0 = the brief was already true (`unchanged`); exit 1 = the rendered brief differs (the ordinary success path — write stdout over the brief); exit 2 = malformed brief or JSON (`failed`, `CAUSE:` the stderr line). ``

with `--reason <word> <key>` for `start`, `stop` and `create`, and no `--reason` for `drift`. Its
stdout is the new brief in full — the `## Next` region, the header and the stop bullet rewritten,
every other byte preserved; its stderr lists the drift it repaired.

**Never diff the rendered brief against the old one to see what changed — that stderr listing is
the change list.** It names every repair the script made, which is the whole of what `refresh`
rewrites, so a diff adds nothing; on Windows it adds nothing loudly. Git for Windows checks the
brief out with CRLF (`core.autocrlf=true`) while `knowledge.py` forces LF on its stdout, so a
line-based `diff` of the two reports **every** line as changed regardless of the repair: measured
in a client run as `1,137c1,137` — both copies of a 137-line brief, ~5k tokens, to report a
two-line drift, and misleading as well as wasteful. Write stdout over the brief and report the
`drift:` lines; on the `read` path, which writes nothing, discard stdout rather than diffing it.

The script partitions the unresolved children, orders the numbered list by phase, step, then numeric id, puts the first
child whose every `## Blocked by` key is resolved at item 1 with its reason preserved when item 1
did not change (else `unblocked; <dep> landed` or `first in phase order`), writes `In progress:`
with each key's `since` preserved, and `Blocked:` from the threads' keys plus every stop bullet's
key. `stop` adds the bullet; `start` removes it. `Status: closed` and `epic complete` exactly when
the epic's live status is in the resolved set. Exit 0 means the brief was already true.

**Outcome.** Byte-identical brief → `unchanged`, no commit, `COMMIT: none`. Otherwise commit
through `
