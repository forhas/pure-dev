# notion-dev: Ticket Assignee Support — Design

**Date:** 2026-07-24
**Status:** Approved (brainstorming)
**Scope:** Assign a Notion user to tickets created by `/notion-dev:create-task`.

## Goal

When creating a ticket, assign it to a Notion user. If the plugin config declares a
default assignee, use it silently. Otherwise, ask the user who to assign it to and
present the list of workspace users to pick from.

## Config (schema + `ticketSystem`)

Two new **optional**, absence-tolerant keys under `ticketSystem` (same tolerance model
as `prProperty` / `epicProperty`):

- `assigneeProperty` — the Notion **People** column name. Default `"Assignee"`.
- `defaultAssignee` — a user **id, email, or display name**. Resolved to a concrete
  user id at ticket-creation time via `notion-get-users`. When **absent OR an empty
  string** (`""`), the create-task flow prompts interactively — `""` and "key missing"
  are treated identically by the runtime.

Neither key is required by the schema. A project that sets neither behaves exactly as
today (no assignment prompt is still shown at create time; see the flow below).

**Init writes `defaultAssignee` explicitly**, including `""` when the user declines a
default — a deliberate exception to init's "omit when equal to default" convention, so
the knob is discoverable in the config file. `assigneeProperty` still follows the
omit-when-default rule (written only when the live People column name differs from
`"Assignee"`).

## New `ticket-system` operation: `resolveAssignee(value)`

Single place that turns a human-supplied value into a Notion user id.

- **Input:** a string that may be a user id, an email, or a display name.
- **Behavior:** fetch workspace users via `mcp__notion__notion-get-users`, filter to
  `type == "person"` (skip bots/integrations). Match in this order:
  1. exact id
  2. exact email (case-insensitive)
  3. exact display name (case-insensitive)
- **Returns:** `{ id, name }` on a unique match; `null` when there is **no match** or
  the value is **ambiguous** (more than one person matches). The caller decides how to
  handle `null` (the command falls back to the interactive picker with a warning).
- Read-only. Never mutates config or the DB.

## `createTicket` gains an optional `assignee` arg (resolved user id)

`createTicket({ title, body, type?, epic?, phase?, step?, assignee? })`

- `assignee` is a **resolved Notion user id** (not a name) — resolution happens in the
  command layer, keeping `createTicket` dumb about lookup.
- Write rule: if `assigneeProperty` exists on the live DB **and** is a `people`-typed
  property **and** `assignee` was provided → write it as a single-item people list.
- If the column is **absent** or **not people-typed** → skip the write and emit a
  **one-time warning** (mirrors `prProperty` absence handling). Never aborts.
- `assignee` is **creation-only** state passed by the caller; it is not a
  `staticProperty` and is not re-applied by `updateTicket` / `upsertSection`.

## `/notion-dev:create-task` flow — new Phase 2.75 "Resolve assignee"

Runs **after** the Phase 2.2 confirm gate and **before** Phase 3 write.

1. If `defaultAssignee` is configured → `resolveAssignee(defaultAssignee)`.
   - Unique match → use its id silently.
   - `null` (no match / ambiguous) → warn (`"defaultAssignee '<v>' did not resolve to a
     unique user; falling back to manual selection"`) and continue to step 2.
2. If no `defaultAssignee` (or step 1 fell through) → `AskUserQuestion` listing
   `type == "person"` users by display name, **plus a "Leave unassigned" option**.
   - A named pick → resolve to id, use it.
   - "Leave unassigned" → pass no `assignee` (ticket created without assignment).
3. **Missions (multi-task):** prompt **once**; apply the same resolved assignee (or
   "leave unassigned") to **every** ticket in the mission by passing `assignee` into each
   `createTicket` call in Pass 1.
4. The interactively chosen assignee is used **for this run only** — the config is
   **never** written.

### Absence / edge behavior summary

| Situation | Behavior |
|---|---|
| No `defaultAssignee`, no `assigneeProperty` on DB | Prompt still runs; write skipped with one-time warning |
| `defaultAssignee` is `""` or key absent | Prompt interactively (identical handling) |
| `defaultAssignee` resolves uniquely | Silent assignment |
| `defaultAssignee` no/ambiguous match | Warn, fall back to picker |
| User picks "Leave unassigned" | No assignment; no warning |
| `assigneeProperty` absent / not people-typed | One-time warning, ticket still created |
| `notion-get-users` unavailable | Same MCP-unavailable failure path as the rest of the skill |

## `/notion-dev:init` — default assignee setup

Init both provisions the People column and offers to record a default.

**Create-new DB (3a-i):** add an `Assignee` (People) property to the created schema.
Since the name matches the default, `assigneeProperty` is not written to config.

**Use-existing DB (3a-ii):** detect a People-typed property for the assignee slot —
prefer one named `"Assignee"` (case-insensitive); otherwise, if exactly one `people`
property exists, offer it via `AskUserQuestion`. Record `assigneeProperty` only when the
resolved name differs from `"Assignee"`. If no People property exists, offer to add an
`Assignee` (People) column, or skip (assignment writes will warn-and-skip at runtime).

**New step 3b — Default assignee (both paths):** ask `AskUserQuestion`:
"Set a default assignee for new tickets?" Options:
- **Pick a user** — list `type == "person"` users (via `notion-get-users`) as
  sub-choices; the chosen user's **id** is written to `defaultAssignee`.
- **No default** — write `defaultAssignee: ""`; create-task will prompt each run.

Skip step 3b silently only when the assignee slot was skipped entirely (no People
column and the user declined to add one) — in that case write neither key.

**Reconfigure mode:** prefill the 3b question with the current `defaultAssignee` (or
"No default" when it is `""`/absent).

**Schema-drift check:** treat the assignee slot as **informational only** (like PR): if
`assigneeProperty` is configured but missing or not `people`-typed on the live DB, report
it; never a hard drift.

## Files touched

- `plugins/notion-dev/schema/notion-dev.config.schema.json` — add `assigneeProperty`,
  `defaultAssignee`.
- `plugins/notion-dev/skills/ticket-system/SKILL.md` — document `resolveAssignee`,
  the `assignee` arg on `createTicket`, People property-type handling, config keys.
- `plugins/notion-dev/commands/create-task.md` — add Phase 2.75, thread `assignee`
  into single-ticket and mission write paths.
- `plugins/notion-dev/commands/init.md` — add `Assignee` (People) to the create-new
  schema, detect the People slot for use-existing, add step 3b (default assignee), and
  the drift-check line.
- `plugins/notion-dev/README.md` — mention the two config keys.

## Out of scope (YAGNI)

- Persisting an interactively chosen assignee back to config (explicitly declined).
- Multi-assignee (People columns can hold many; we write a single user).
- Reassigning existing tickets / an assignee arg on `updateTicket`.
