Diagnose which live Notion columns this project's notion-dev config actually bound.
Read-only. Do not change the config, the plugin, or anything in Notion. Report only.

## Why

A previously reported bug — "writing a dependency also created the reverse edge on the
target page" — was blamed on Notion self-referential relations being symmetric. That has
since been disproven by direct test: an API-created one-way self-relation is directional,
and a two-way one splits across two columns. So the reverse edge had some other cause.

The leading hypothesis is a **mis-binding**. Notion's native Sub-items is a PAIR of columns
(here: `Parent-task` + `Sub-tasks`). If `dependsOnProperty` was bound to `Sub-tasks`, then
writing `A.Sub-tasks = [B]` puts `[A]` into `B.Parent-task` — a reverse edge appearing on
the target instantly, and immune to retyping or recreating the unrelated `Depends on` column.

There is a second, still-live concern. This DB's column is named `Parent-task` with a
**hyphen**, but the plugin's default is `"Parent task"` with a **space**. A hyphen is not a
space, so the exact-name match may have missed and fallen through to a more ambiguous rule.
If `parentTaskProperty` bound to `Sub-tasks`, epic containment is inverted.

Answer both questions with evidence.

## Hard rules

- **Strictly read-only.** No writes to Notion, no edits to config or plugin files.
- Report exact names and ids verbatim. Do not normalize, correct, or tidy them — a hyphen
  vs a space is precisely what is being tested.
- If something is absent, say "absent" rather than reporting the default as if it were set.

---

## 1 — Config, verbatim

Read `.claude/notion-dev.config.json` and report, exactly as written:

- `ticketSystem.parentTaskProperty` — value, or **absent** (default `"Parent task"` applies)
- `ticketSystem.dependsOnProperty` — value, or **absent** (removed in plugin 0.10.0, but an
  older config may still carry it)
- `ticketSystem.epicMarkerProperty`, `ticketSystem.databaseId`, `ticketSystem.dataSourceId`

## 2 — Config history (strong evidence if available)

If the project is a git repo and the config is tracked:

```
git log --oneline -- .claude/notion-dev.config.json
git log -p -- .claude/notion-dev.config.json
```

Report every value `parentTaskProperty` and `dependsOnProperty` have ever held, and when they
changed. This shows what `/notion-dev:init` originally bound, which is the single most direct
evidence available. If the file is untracked or the repo has no history for it, say so.

## 3 — Live schema

Fetch the tickets database schema. List **every** relation property, and for each:

- exact name (verbatim, including hyphens/spacing/case)
- whether it is self-referential
- its property id
- whether it is one half of Notion's native Sub-items pair

To identify native Sub-items: base64-decode the property id. Native ones decode to the
internal `notion://tasks/parent_task_relation` or `notion://tasks/sub_task_relation`
namespace, which the public API cannot create. Anything else was made by a user or the API.

## 4 — Resolution check

For each of `parentTaskProperty` and `dependsOnProperty`, state which live column the
configured-or-default name resolves to, matching the way the plugin does (exact name,
case-insensitive). Flag explicitly if a configured name resolves to **nothing** live, or if
the default would have failed to match because of the hyphen.

## 5 — Evidence in the data

The mis-binding, if real, left fingerprints. Check for them.

1. **Dependency edges in containment columns.** For the mission tasks under epic STO-333
   (STO-334 … STO-344), report any task whose `Sub-tasks` or `Parent-task` references a
   **sibling task** rather than the epic. Sibling references in a containment column are
   dependency writes that landed in the wrong place — the smoking gun.
2. **`Depends on` population.** Count rows where `Depends on` is non-empty. (A prior check
   found zero. Confirm, and note that the reporter said they cleared edges by hand, so zero
   is consistent with both explanations and is not decisive on its own.)
3. **Epic integrity.** Confirm STO-333's own `Parent-task` is empty and its `Sub-tasks` holds
   exactly the 11 children — i.e. containment is currently correct whatever the binding says.

---

## Report format

```
CONFIG (verbatim)
  parentTaskProperty:   <value | absent → default "Parent task">
  dependsOnProperty:    <value | absent>
  epicMarkerProperty:   <value | absent>

CONFIG HISTORY
  <values over time, with commits | untracked/no history>

LIVE RELATION COLUMNS
  <name> | self-ref? | property id | native Sub-items half? <parent|sub|no>
  ...

RESOLUTION
  parentTaskProperty → <live column | NO MATCH>
  dependsOnProperty  → <live column | NO MATCH | n/a>
  hyphen/space mismatch affected the match: <YES | NO>

EVIDENCE
  sibling refs in containment columns: <none | list them>
  "Depends on" non-empty rows:         <n>
  STO-333 containment correct:         <YES | NO>

VERDICT
  <mis-binding confirmed / refuted / inconclusive — and which column
   dependsOnProperty actually pointed at>
```

State only what you observed. If the evidence is ambiguous or the history is gone, say
inconclusive rather than picking the tidier story — "we cannot tell" is a valid and useful
result here.
