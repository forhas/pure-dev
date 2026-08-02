---
name: ticket-system
description: Use when a notion-dev command needs to read or write a ticket in the configured Notion ticket database. Implements the logical ticket operations (fetchTicket, createTicket, updateStatus, …) over the Notion MCP, driven by .claude/notion-dev.config.json.
---

# ticket-system

Provides the ticket operations for the notion-dev commands over the configured Notion database. Commands invoke this skill by naming an operation; this file defines the operation contract and how each operation is fulfilled with the Notion MCP (`mcp__notion__*` tools).

If `.claude/notion-dev.config.json` is missing or has no `ticketSystem.databaseId`, fail clearly and tell the user to run `/notion-dev:init`. Resolve the config path against the **primary checkout**: use the caller's recorded `$REPO_ROOT` when provided, else the first path listed by `git worktree list` — never `git rev-parse --show-toplevel`, which returns the *worktree* root when run inside one. Callers often invoke this skill from inside a ticket worktree, which may not contain the config file.

## Logical operations

The caller names the operation and passes the arguments; the sections below describe how each is fulfilled.

| Operation | Arguments | Returns |
|---|---|---|
| `fetchTicket` | `id` (numeric or prefixed string, or a Notion page id/URL) | `{ title, key, body, status, type, url, metadata }` — `title` has the ID prefix stripped; `key` is the logical ticket key (`"STO-67"`) for display; `metadata` carries `rawTitle` (the literal Notion title), `pageId`, the `idProperty` value, `parentTaskProperty` (the raw related-page id from that Relation, or `""`), `epicProperty` (the raw Select value, or `""`), `epicMarkerProperty` (the raw Checkbox value, or `false`), and `assigneeProperty` (the raw People-column user id, or `""`) — each carries its type's empty default whenever the corresponding configured property is missing from the live DB, unset on the page, or (for `assigneeProperty`) not a People type, or (for `epicMarkerProperty`) not a Checkbox type; `type` is the logical key (`feature`/`bug`/…) when the DB has a mapped type property, else absent |
| `createTicket` | `{ title, body, type?, epic?, parent?, phase?, step?, assignee?, isEpic? }` | `{ id, url }` — `epic`/`parent`/`phase`/`step` are optional mission metadata; `parent` accepts either a logical ticket id or a Notion page id and is resolved to a page id via `fetchTicket`, same as `setParent`; `assignee` is a resolved Notion user id; `isEpic` (bool, default `false`) — when `true` and `epicMarkerProperty` exists on the live DB, sets it to `true` **in this same create call**; used only by `createEpic`. Each is absence-tolerant when the corresponding configured property is missing from the live DB |
| `resolveAssignee` | `value` (user id, email, or display name) | `{ id, name }` on a unique person match; `null` on no match or ambiguity. Read-only — never mutates config or the DB |
| `updateTicket` | `id`, `{ title?, body?, type? }` | `{ id, url }` — only the provided fields change |
| `updateStatus` | `id`, `logicalStatus` ∈ `{ inProgress, implemented }` (plugin-invoked set) plus any custom key present in the user's `statusMap` | `void` — the plugin never invokes `delivered` / `done` / shipped-style states; those are reserved for host-project commands |
| `setPullRequest` | `id`, `url` | `void` — persists the PR URL into the configured PR property. No-op when the live DB has no such property. Does not touch body sections. Record `missing-property:prProperty` per `notion-dev:issue-log`. |
| `setDependencies` | `id`, `[titleOrId, …]` | `void` — writes the configured `dependsOnProperty` relation. Resolves entries that look like titles to page IDs within the DB. No-op when the property is absent. Record `missing-property:dependsOnProperty` per `notion-dev:issue-log`. Pass-2 in mission creation. |
| `createEpic` | `{ name, overview, type?, assignee? }` | `{ id, key, url, pageId }` — creates an Epic container page with `epicMarkerProperty` already set to `true` in that same creation call (via `createTicket`'s `isEpic` argument) — the write that actually makes it an epic, with no unmarked intermediate state. No-op returning `null` when the DB lacks `parentTaskProperty` or `epicMarkerProperty`. Record `missing-property:parentTaskProperty` or `missing-property:epicMarkerProperty` per `notion-dev:issue-log`. |
| `findEpics` | — | `[{ id, key, pageId, name, title, url, overview }]` — pages where `epicMarkerProperty` is `true` and their own `parentTaskProperty` is empty (the same predicate `getEpicContext` step 2, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply), scoped by `staticProperties` when configured (see "Project scoping guardrail"). `null` when `epicMarkerProperty` is absent from the live DB — epics cannot be identified safely at all (mirrors `getSelectOptions`'s absent-property `null`); `[]` when the property exists but no page has it set yet — these are different states, not interchangeable. Record `missing-property:epicMarkerProperty` per `notion-dev:issue-log`. |
| `setParent` | `id`, `epicId` | `void` — writes the `parentTaskProperty` relation. No-op when the property is absent. Record `missing-property:parentTaskProperty` per `notion-dev:issue-log`. |
| `listEpicChildren` | `epicId` | `[{ id, key, title, status, url }]` — pages whose `parentTaskProperty` points at `epicId`, ordered by `id`. `[]` when the property is absent. Record `missing-property:parentTaskProperty` per `notion-dev:issue-log`. |
| `getEpicContext` | `epicId`, `currentTicketId` | bounded markdown context block, or `null` — epic identity, verbatim `## Overview`, **live** sibling status (via `listEpicChildren`, never the epic body's stale `## Tasks` snapshot) with the sibling whose `id` equals `currentTicketId` marked, and the most recent 3 `## Resolution Log` entries (with a count of any older entries omitted). `null` (no warning — routine) when `epicId` is empty, or `epicMarkerProperty` is absent from the live DB. When `currentTicketId` matches no sibling, mark nothing and continue — never an error. The sole owner of what "epic context" means — callers never assemble it themselves or parse `## Resolution Log`. **Background, not requirements**: callers must never treat its content as spec |
| `refreshEpicTasks` | `epicId` | `void` — re-renders the epic's `## Tasks` section from its live children. The single owner of that section's format |
| `appendToSection` | `id`, `sectionName`, `content` | `void` — **appends** to a named body section, creating it if absent. Never replaces, unlike `upsertSection` |
| `getSelectOptions` | `propertyName` | `[string]` or `null` — lists option names for a Select / Multi-Select / Status property. Returns `null` if the property is absent or not a selectable type. Read-only. |
| `addSelectOption` | `propertyName`, `optionName` | `void` — extends a Select's options list on the live DB. Should only be invoked after explicit user confirmation (adding options mutates shared DB schema). |
| `postComment` | `id`, `text` | `void` |
| `upsertSection` | `id`, `sectionName` (string), `content` (dict of labeled entries OR markdown) | `void` — appends a `## <sectionName>` block to the ticket body, or **overwrites** it if one already exists. Different section names are independent — e.g. `"Implementation"` and `"Merged"` coexist. |

`body` is markdown structured with sections: **Requirements**, **Acceptance Criteria**, **Context**, **Open Questions** (order may vary; missing sections are allowed).

`logicalStatus` is always the logical name. The adapter maps it to the concrete Notion status via `statusMap` in config, falling back to sensible defaults when a key is missing.

## ID normalization

Callers may pass an `id` as a **logical key** — `STO-285`, `STO285`, or `285`. Normalize by stripping the configured `project.key` prefix and any separator, then parsing the remainder as an integer, then resolving it through the `idProperty` lookup. A **Notion page id or page URL** is also accepted, resolving the page directly.

## Title prefix

Every ticket title carries its ticket ID as a leading tag: `[STO-67] Large-Wallet Stale-Index Incident`. The adapter owns this entirely — **callers pass and receive bare titles and never construct, parse, or strip the prefix themselves**. Applies to epics identically.

Format: `[<KEY>-<n>] ` — literal `[`, `project.key`, `-`, the numeric ID, `]`, one space.

Detection (case-insensitive on the key, tolerant of stray inner whitespace):

```
^\[\s*<KEY>-(\d+)\s*\]\s*
```

Only a prefix matching **this project's** `project.key` counts. On a DB shared between projects, a leading `[FOO-12] ` is part of the title, not a prefix — leave it alone.

**Writing.** `createTicket` and `updateTicket` write `[<KEY>-<n>] <bare title>`, stripping any already-matching prefix from the incoming value first. Idempotent: never double-prefixes, and a prefix carrying the wrong number is corrected to the page's real ID.

**Reading.** `fetchTicket` returns `title` with the prefix stripped, and `metadata.rawTitle` with the literal Notion title. This is what keeps callers correct without changes — `/notion-dev:ticket` kebab-cases the title into a branch slug, and a stripped title keeps branches as `ticket/STO-67-large-wallet-stale-index` rather than `ticket/STO-67-sto-67-large-wallet-stale-i`.

Callers that need to *show* the id alongside the title use the `key` field (`"STO-67"`) and render `[{key}] {title}` themselves. That is display formatting, not prefix construction — what the adapter owns is the title stored in Notion.

**`unique_id` prefix mismatch.** A Notion `unique_id` column carries its own prefix. When it differs from `project.key`, titles still use `project.key` — config is the source of truth for the plugin's naming, and branch names already depend on it. Log **one** warning per run: `"ID column prefix '<live>' differs from project.key '<KEY>'; titles use '<KEY>'"`. Record `prefix-mismatch:unique_id` per `notion-dev:issue-log`.

## Configuration

Config (from `.claude/notion-dev.config.json` → `ticketSystem`):
- `databaseId` — the Notion database
- `dataSourceId` — optional, preferred for queries when set
- `idProperty` — property name holding the numeric ticket ID (default `"ID"`). Works with both Notion `number` and `unique_id` (auto-increment) property types.
- `statusProperty` — property name holding the status select (default `"Status"`)
- `typeProperty` — property name holding the ticket type (default `"Type"`). The live property may be either Select or Multi-Select; the adapter normalizes both.
- `prProperty` — property name (URL) that `/notion-dev:ticket` writes the PR link to (default `"PR"`). When the property doesn't exist on the live DB, skip the write with a warning rather than aborting. Record `missing-property:prProperty` per `notion-dev:issue-log`.
- `assigneeProperty` — People property that `/notion-dev:create-task` assigns new tickets to (default `"Assignee"`). When the property doesn't exist on the live DB or isn't a People type, skip the write with a warning rather than aborting. Record `missing-property:assigneeProperty` when the property is absent, or `wrong-type:assigneeProperty` when it exists but is not a People property, per `notion-dev:issue-log`.
- `defaultAssignee` — default assignee as a Notion user id, email, or display name, resolved via `resolveAssignee` at create time. Empty string or absent → `/notion-dev:create-task` prompts interactively. `/notion-dev:init` writes it explicitly (including `""`).
- `statusMap` — logical → Notion option name; defaults below
- `typeMap` — logical type key → Notion option label; defaults below
- `staticProperties` — optional dict of extra properties to set on every new ticket (e.g. `{ "Project": "BTC-Gateway" }`). Set once at creation; never modified by `updateTicket` or `upsertSection`.
- `epicProperty` — Select property holding the Epic tag (default `"Epic"`). Used by mission-mode `createTicket`. Absence-tolerant.
- `phaseProperty` — Select property holding the Phase tag (default `"Phase"`). Absence-tolerant.
- `stepProperty` — Number property holding the Step position within a Phase (default `"Step"`). Absence-tolerant.
- `dependsOnProperty` — self-referential Relation property for blocking dependencies (default `"Depends on"`). Written in a second pass after all mission tickets exist. Absence-tolerant.
- `creationDateProperty` — property holding the ticket's creation timestamp (default `"Creation Date"`). Tolerates two live types: a `date` property (the adapter writes the timestamp at creation) or a `created_time` property (Notion auto-populates; the adapter never writes). Absence-tolerant.
- `parentTaskProperty` — self-referential Relation linking a ticket to its Epic container page (default `"Parent task"`). Distinct from `dependsOnProperty`: `Depends on` expresses blocking order between siblings, `Parent task` expresses containment. Absence-tolerant.
- `epicMarkerProperty` — Checkbox property marking a page as an Epic container (default `"Is Epic"`). This is the **sole** signal that identifies a page as an epic — carrying an `epicProperty` Select value is display metadata, not identity. Set to `true` by `createEpic`; read by `findEpics`, `getEpicContext`, `epic-update`, and `/notion-dev:ticket`'s epic guard, which all apply the same predicate. Absence-tolerant with a twist: when absent from the live DB, epics cannot be identified at all, so `findEpics` returns `null` and every guard/validation site treats the page as not an epic, rather than falling back to any structural guess.

Defaults for `statusMap` when keys are missing:
```
inProgress  → "In Progress"
implemented → "Implemented"
done        → "Done"
cancelled   → "Cancelled"
```

The plugin actively **writes** only `inProgress` (set by `/notion-dev:ticket` at worktree creation) and `implemented` (set by `/notion-dev:finalize` post-merge). `done` and `cancelled` are **read-only**: they exist so the epic-close check knows which of the DB's Status options mean resolved. No plugin command ever transitions a ticket into them — that is deliberately out of scope, and release/deployment semantics belong to the host project.

### Resolved set

The **resolved set** is the collection of live Notion option names produced by `statusMap.implemented`, `statusMap.done`, and `statusMap.cancelled`. A ticket counts as resolved when its status matches any member, case-insensitively.

Used by exactly two things: the epic-close check (in `/notion-dev:ticket` Phase 8 and `/notion-dev:finalize` Phase 3 — the same check, run from both entry points), and ticking the checkboxes in an epic's `## Tasks` section.

A missing `done` or `cancelled` key falls back to its default option name. If that option does not exist on the live DB it simply never matches — a status the plugin has not been told about is not resolved, so the epic does not auto-close. Wrong in the safe direction.

Defaults for `typeMap` when keys are missing:
```
feature     → "Feature"
bug         → "Bug"
improvement → "Improvement"
research    → "Research"
```

## Property type handling

The adapter normalizes the following shape differences between the canonical schema and real-world databases:

- **Title** — every Notion database has exactly one property whose type is `title` (the page title). The adapter discovers it dynamically by scanning the live schema for the `title`-typed property; its **name** is not fixed — common choices are `Name`, `Title`, `Task name`, etc. Callers pass the title value as a plain string; the adapter writes it to whichever property is the title type on this DB. Never hardcode a property name for the title. The value written is the caller's bare title with the ID prefix prepended, and the value read is stripped of it — see "Title prefix" above.
- **ID** — read/write as `number` or `unique_id` depending on the live property type. `unique_id` is read-only to the MCP; creation does not set it (Notion auto-assigns). Queries filter by numeric id regardless of type.
- **Type** — read: if the live property is `multi_select`, take the first value; if `select`, take the value. Write: if `multi_select`, send a single-item list; if `select`, send the scalar. Empty values round-trip as `null`.
- **PR** — read/write when `prProperty` exists on the live DB. When absent, skip writes and log a single warning per run (no abort). Record `missing-property:prProperty` per `notion-dev:issue-log`.
- **Epic / Phase** (Select) — write as the option name string. When the configured property is absent from the live DB, skip with a one-time warning. Record `missing-property:epicProperty` per `notion-dev:issue-log`. When the property exists but the option doesn't, raise a clear error telling the caller to add the option first (via `addSelectOption` or manually in Notion). Record `option-missing:<propertyName>` (substituting the real property name, e.g. `epicProperty` or `phaseProperty`) per `notion-dev:issue-log`. Never silently mutate the DB's option list from a write path — option creation is an explicit, user-confirmed action.
- **Step** (Number) — write as a number. Integers and floats both accepted; adapter passes through the caller's value.
- **Depends on** (Relation) — write as a list of page IDs. When the caller passes titles, resolve each to a page ID by DB-scoped title search (same mechanism `existing-ticket` uses on numeric IDs) before writing. Unresolved titles raise a clear error naming the offender. Absence-tolerant when the property is missing.
- **Assignee** (People) — write as a single-item list of `{ id }` user references to the `assigneeProperty` column. Read: `fetchTicket` returns the current value in `metadata.assigneeProperty` as the first person's user id when the property exists, is a `people` type, and has a value; `""` when absent, not People-typed, or unset. On a multi-assignee column only the first person is exposed — absence-tolerant, never an error. When the configured property is absent from the live DB or is not a `people` type, skip the write and log **one** warning per run (`"assigneeProperty '<name>' not found or not a People property on DB; skipping assignee write"`) — never abort. Record `missing-property:assigneeProperty` when the property is absent, or `wrong-type:assigneeProperty` when it exists but is not a People property, per `notion-dev:issue-log`. `assignee` is caller-supplied creation state, not a `staticProperty`: `updateTicket` and `upsertSection` never touch it.
- **Creation Date** (`date` or `created_time`) — read the live property type and branch. `date`: `createTicket` writes `{ "date": { "start": "<ISO 8601 UTC timestamp, with time>" } }`. `created_time`: never written — Notion populates it, and the API rejects writes to it. Any other type, or the property absent: skip the write and log **one** warning per run (`"creationDateProperty '<name>' not found or not a date/created_time property on DB; skipping creation date write"`). Record `missing-property:creationDateProperty` when the property is absent, or `wrong-type:creationDateProperty` when it exists but is neither `date` nor `created_time`, per `notion-dev:issue-log`. Creation-only, like `staticProperties` — `updateTicket` and `upsertSection` never touch it.
- **Parent task** (Relation, self-referential) — write as a **single-element** list of page IDs; a ticket has exactly one parent. Relation writes in Notion are replacement, not append, so writing one element is correct and no read-merge is needed (unlike `Depends on`). Reject a self-reference (`id == epicId`) with a clear error. When the configured property is absent from the live DB, skip the write and log **one** warning per run (`"parentTaskProperty '<name>' not found on DB; skipping parent write"`) — never abort. Record `missing-property:parentTaskProperty` per `notion-dev:issue-log`.
- **Is Epic** (Checkbox) — write as a boolean. Only `createEpic` writes it, and only `true`; no path ever writes `false` back over an existing epic. Read: `fetchTicket` returns the live value in `metadata.epicMarkerProperty` when the property exists and is a `checkbox` type; `false` when absent, unset, or not a Checkbox type — the same default whether the column doesn't exist or the box is simply unchecked, so every downstream reader treats "no marker property" and "marker is false" identically as "not an epic."

## Project scoping guardrail

When `staticProperties` is configured, those same properties act as a **fetch-side scope check**: a DB shared across projects will have tickets from other projects, and every per-ID operation starts from `fetchTicket`. After resolving a page, compare each `[name, expected]` in `staticProperties` against the fetched page's value for that property:

- **Match** (or property absent from the live DB) → proceed silently.
- **Mismatch** → abort with: *"`<PREFIX>-<id>` has `<prop>`=`<actual>`; this project is pinned to `<prop>`=`<expected>`. Refusing to operate on a ticket from a different project."* Record `abort:project-scope` per `notion-dev:issue-log`.

This is a hard abort — crossing project boundaries is always a user error in a multi-project DB setup. The guardrail applies to `fetchTicket` (and therefore to every operation that reaches a page through it: `updateTicket`, `updateStatus`, `setPullRequest`, `upsertSection`, `postComment`). `createTicket` is unaffected — it sets the pinned values, it doesn't verify them.

When `staticProperties` is empty or absent, the check is skipped — single-project DBs behave as before.

## Notion page heading parsing

When reading or updating a page, match headings by base text **ignoring trailing Notion attributes** like `{color="red"}`. Always fetch the current page state before mutating — don't rely on cached structure.

## Styling conventions

Tickets are first-class user-facing documents. The adapter applies a fixed visual palette when writing known sections so the three logical zones — **spec** (from `/notion-dev:create-task`), **resolution** (from `/notion-dev:ticket`), and **shipping** (from `/notion-dev:finalize`) — are immediately distinguishable at a glance. Callers pass plain content; the adapter renders it into styled Notion blocks.

### Palette per section

| Heading | Written by | Heading color | Intro callout | Icon |
|---|---|---|---|---|
| `Requirements` | `/notion-dev:create-task` | `orange` | `orange_background` | 📋 |
| `Acceptance Criteria` | `/notion-dev:create-task` | `orange` | — | — |
| `Context` | `/notion-dev:create-task` | `gray` | — | — |
| `Open Questions` | `/notion-dev:create-task` | `red` | `red_background` | ❓ |
| `Source` | `/notion-dev:create-task` | `gray` | — | — |
| `Implementation` | `/notion-dev:ticket` | `blue` | `blue_background` | 🔨 |
| `Merged` | `/notion-dev:finalize` | `green` | `green_background` | ✅ |
| `Overview` | `createEpic` | `gray` | — | — |
| `Tasks` | `createEpic` (empty at creation), create-task Pass 1.5 (populated when a mission is filed), and epic refresh (`/notion-dev:ticket` Phase 8, `/notion-dev:finalize` Phase 3) | `blue` | — | — |
| `Resolution Log` | epic update (same) | `purple` | — | — |

Unknown section names (including user-added ones) render with no color and no callout — the plugin only styles sections it owns. Match section names case-insensitively on base text; don't restyle sections a user has manually recolored (see "Heading attribute preservation" below).

The last three sections appear on **epic pages only**. None takes an intro callout — they are self-explanatory, and a callout on every one would be noise. `Tasks` renders as to-do blocks (same convention as `Acceptance Criteria`). The zone-divider rule below applies to `Implementation` / `Merged` on ticket pages only; epic pages use the per-entry divider described under `appendToSection`.

### Zone dividers

Before writing `## Implementation` or `## Merged`, insert a `divider` block **if the immediately preceding block on the page isn't already a divider**. This carves the page into three visual zones:

```
[Requirements · Acceptance Criteria · Context · Open Questions · Source]
───────────── divider ─────────────
[Implementation]
───────────── divider ─────────────
[Merged]
```

Dividers are idempotent — never add a second one.

### Intro callouts

For sections in the palette marked with a callout color, render it as the first block under the heading with the section's icon and background color:

- **Requirements** — one-sentence distillation of the goal (fallback: `"What this ticket covers."`).
- **Open Questions** — literal: `"Unresolved before implementation — resolve these before running /notion-dev:ticket."`
- **Implementation** — status line, e.g. `"Status: PR open · <PR URL>"` or `"Status: Plan authored"`.
- **Merged** — shipping summary, e.g. `"Shipped <YYYY-MM-DD> · <commit-hash> · merged to <base>"`.

Callouts are regenerated on each write — the upsert replaces the whole section body, so old callout text never lingers.

### Rich content inside sections

After the callout (if any), render section body:

- **Requirements / Context / Source** — paragraphs and bulleted lists. No checkboxes.
- **Acceptance Criteria** — always a **to-do list** (`- [ ]` → Notion to-do blocks). Never plain bullets; the checkability is the point.
- **Open Questions** — bulleted list; consider using **red** inline text for the actual question and neutral for surrounding framing.
- **Implementation** — a labeled block for `Plan`, `Implementation`, `Files Changed`, `PR`, `Branch`, `Notes`. Render labels as bold (`**Plan**`) followed by the value. For `Files Changed`, group by directory as a nested bulleted list. For `PR` and `Branch`, render as code-formatted text so they copy cleanly.
- **Merged** — mixed render: a 2-column (Field / Value) Notion **table** for the scalar fields in the order they appear in the content dict (e.g. `PR`, `Merge commit`, `Merge strategy`, `Base branch`, `Merged at`), followed by **labeled list sections** for narrative/list fields (`Review resolution` as bullets, `Deferred follow-ups` as a bulleted list with linked ticket IDs where present). The adapter decides per-field which side of the split a value goes:
  - **scalar** (string, URL, timestamp, short identifier) → table row.
  - **list or multi-line markdown** → labeled section below the table.
  
  Example rendering:
  ```
  🟢 ## Merged
  ┌────────────────┬──────────────────────────────┐
  │ PR             │ <PR URL>                     │
  │ Merge commit   │ `abc123def`                  │
  │ Merge strategy │ squash                       │
  │ Base branch    │ master                       │
  │ Merged at      │ 2026-04-24T14:32:00Z         │
  └────────────────┴──────────────────────────────┘
  
  **Review resolution**
  • Applied 4 comments across auth/session handling.
  • Deferred 1 as follow-up (see STO-42).
  • Disagreed on naming suggestion; left a reply.
  
  **Deferred follow-ups**
  • STO-42 — refactor session token storage
  ```

### Heading attribute preservation

When `updateTicket`'s body merge re-writes an existing section, **read the existing heading's trailing attribute block** (e.g. `{color="orange"}`) and preserve it verbatim in the rewritten heading. Do not override a user's manual color choice. Only when the existing heading has no attribute should the adapter apply the canonical palette color from the table above.

## fetchTicket(id)

`id` may arrive as a **Notion page id / URL** (e.g. `383fdf83c4178177beebd41a69bf47bc`, a dashed UUID, or a full `notion.so` / `notion.com` page URL) or as a **logical key** (`STO-285`, `STO285`, `285`). Resolve the page accordingly:

1. **Detect input shape and resolve the page:**
   - If `id` is a Notion page id (32 hex chars with or without dashes), a dashed UUID, or a Notion page URL: **fetch the page directly** with `mcp__notion__notion-fetch` — skip the database query entirely.
   - Otherwise treat `id` as a logical key: normalize it to numeric, then query the database (or data source if configured) for the page where `idProperty` equals the numeric id — use `mcp__notion__notion-query-data-sources` with an exact filter on `idProperty` (semantic `notion-search` is not reliable for numeric-ID equality, and `notion-fetch` only fetches by URL/ID; fall back to a DB-scoped `notion-search` only if the query tool is unavailable, verifying the hit's `idProperty` value before trusting it). When `idProperty` is a `unique_id` column, filter by its numeric component — ignore the textual prefix. Load the resolved page content with `mcp__notion__notion-fetch`.
2. **Apply the project scoping guardrail** (see section above) — abort here if any pinned `staticProperties` mismatch the live page. Fail before any further work.
3. Convert blocks to markdown, preserving **Requirements**, **Acceptance Criteria**, **Context**, **Open Questions** sections.
4. Read `typeProperty` (if present): normalize to a logical key via reverse lookup through `typeMap` (defaults above). For `multi_select`, the first option wins.
4a. Read the mission/epic-adjacent raw values, each absence-tolerant (missing or unset → that type's empty default, never a warning — these are routine, not exceptional):
   - `parentTaskProperty` (if present on the live DB): the related page id from that self-referential Relation, or `""` when unset or the property is absent.
   - `epicProperty` (if present): the Select's option value, or `""` when unset or the property is absent.
   - `epicMarkerProperty` (if present and Checkbox-typed): the live boolean, or `false` when unset, the property is absent, or it isn't a Checkbox type.
   - `assigneeProperty` (if present and People-typed): the first person's user id, or `""` when unset, the property is absent, or it isn't a People type.
5. Return `{ title, key, body, status, type, url, metadata: { pageId, idProperty value, rawTitle, parentTaskProperty, epicProperty, epicMarkerProperty, assigneeProperty } }`. `title` is the page title **with the ID prefix stripped** (see "Title prefix"); `key` is the logical ticket key (`"STO-67"`) for callers that need to *display* the id beside the title; `rawTitle` is the literal Notion title. The `idProperty value` (the numeric key) is read off the **resolved page** regardless of which branch resolved it — callers rely on it for branch/worktree naming. `parentTaskProperty`, `epicProperty`, `epicMarkerProperty`, and `assigneeProperty` are the raw values read in step 4a — callers such as the epic guard in `/notion-dev:ticket`, `getEpicContext`, and `epic-update`'s Step 1 read these directly rather than re-deriving them.

## resolveAssignee(value)

Read-only. Turns a human-supplied value into a concrete Notion user id. Used by `/notion-dev:create-task` to resolve a configured `defaultAssignee` before writing a ticket.

1. Fetch workspace users via `mcp__notion__notion-get-users`. Filter to entries whose `type` is `"person"` — skip bots and integrations.
2. Match `value` against the filtered list in this order, stopping at the first rule that yields matches:
   1. exact `id` equality
   2. exact email equality (case-insensitive), where the user exposes an email
   3. exact display-name equality (case-insensitive)
3. Resolve the result:
   - exactly one match → return `{ id, name }` (the canonical id and display name).
   - zero matches, or **more than one** match at the matching rule (ambiguous) → return `null`. The caller decides what to do (create-task falls back to the interactive picker with a warning).

Never writes config or the database. When `mcp__notion__notion-get-users` is unavailable, fail with the standard MCP-unavailability message (see "MCP unavailability"). Record `mcp-unavailable:notion-get-users` per `notion-dev:issue-log`.

## createTicket({ title, body, type?, epic?, parent?, phase?, step?, assignee?, isEpic? })

1. Determine the next ID: query the database ordered by `idProperty` desc; take `max + 1`. If `idProperty` is `unique_id`, skip this step — Notion auto-assigns on create; read the assigned id back from the created page.
1a. If `parent` is provided AND `parentTaskProperty` exists on the live DB, **resolve it to a page id now, before the create call** — it may arrive as a logical ticket id or already a Notion page id; resolve it exactly as `setParent` step 2 does (via `fetchTicket`). This is the only piece of mission metadata that needs work before creation; `epic`/`phase`/`step` are written as-is in step 2.
2. Create the page via `mcp__notion__notion-create-pages`:
   - Parent = configured database / data source.
   - Properties: `idProperty` = new id (omit when `unique_id`), the **title-typed property** (discovered from the live schema — see Property type handling above), `statusProperty` = `"Backlog"` (or the first option if Backlog not present). The title value depends on the ID column type — see the retitle rule in step 3.
   - If the live DB has `typeProperty` AND `type` was provided, set it: translate the logical key through `typeMap` to the Notion option label, then write it as a scalar (Select) or single-item list (Multi-Select) depending on the live property type.
   - For each `[name, value]` in `staticProperties` (if configured), set that property on the page. Property type is inferred from the live database schema (Select/Status → option name match; Multi-Select → single-item list unless the value is already a list; text → verbatim). Skip silently with a warning if the property doesn't exist on the DB.
   - **Assignee** (absence-tolerant): if `assignee` (a resolved user id) is provided AND the live DB has the `assigneeProperty` column AND it is a `people` type, set it to a single-item people list `[{ id: assignee }]`. If the column is absent or not People-typed, skip with the one-time warning from "Property type handling". `assignee` absent → set nothing.
   - **Creation Date** (absence-tolerant): if the live DB has the `creationDateProperty` column AND it is a `date` type, set it to the current UTC timestamp in ISO 8601 with time (e.g. `2026-08-01T14:32:00Z`). When it is a `created_time` type, set nothing — Notion fills it. When absent or any other type, skip with the one-time warning from "Property type handling". Record `missing-property:creationDateProperty` when the property is absent, or `wrong-type:creationDateProperty` when it exists but is neither `date` nor `created_time`, per `notion-dev:issue-log`.
   - **Mission metadata** (absence-tolerant, independent of each other):
     - If `epic` is provided AND `epicProperty` exists on the live DB, set that Select to `epic` (exact option-name match required; if the option doesn't exist, raise an error — the caller should have resolved it via `getSelectOptions` / `addSelectOption` first).
     - If `parent` was provided AND `parentTaskProperty` exists on the live DB, set that Relation **in this same create call** to a single-element list containing the page id resolved in step 1a. `epic` and `parent` are independent: the Epic select makes the grouping visible in DB views and filters, the Parent task relation makes it a container. Callers normally set both.
     - If `phase` is provided AND `phaseProperty` exists, set that Select to `phase` (same option-match rule).
     - If `step` is provided AND `stepProperty` exists, set that Number to `step`.
     - If `isEpic` is `true` AND `epicMarkerProperty` exists on the live DB, set that Checkbox to `true` **in this same create call** — this is the write that actually makes the page an epic (see "Epic containers" below). `isEpic` defaults to `false`; only `createEpic` ever passes `true`.
     - Any missing configured property emits a one-time warning (`"<name>Property '<n>' not found on DB; skipping"`) and continues.
   - Children blocks: render `body` markdown, **applying the Styling conventions above**. Each canonical heading (`Requirements`, `Acceptance Criteria`, `Context`, `Open Questions`, `Source`, `Overview`, `Tasks`) gets its palette color; intro callouts prepend sections that define one; `Acceptance Criteria` renders as to-do blocks. No divider appears yet at creation — only zone transitions add dividers. `Overview` and `Tasks` only appear when `createEpic` is the caller (see "Epic containers" below); this is the code path that colors them gray and blue respectively at creation time.

   **Setting `parent` here, rather than as a follow-up update, is deliberate and load-bearing.** The page, its body (including any caller-supplied provenance marker in `## Context`), and its parent relation are all written in this single `mcp__notion__notion-create-pages` call — there is no intermediate state where the page exists but is not yet a child of its epic, and therefore no window in which an interrupted run leaves an orphaned follow-up that `listEpicChildren(EPIC_ID)`-based dedup cannot see. Do not split `parent` back out into a separate write after creation: unlike the `unique_id` retitle in step 3 below, it does not need the new page's id — the relation points *from* the new page *to* the epic, and the epic's page id is already known (resolved in step 1a) before the create call is issued. Only the retitle genuinely has to wait, because that id does not exist until the page does.
3. Apply the title prefix (see "Title prefix"):
   - **`number` ID column** — the id was computed in step 1, so the create in step 2 already wrote `[<KEY>-<n>] <title>`. Nothing further.
   - **`unique_id` ID column** — the id does not exist until the page does. Step 2 created the page with the **bare** title; now read the assigned id off the created page and call `mcp__notion__notion-update-page` to set the title-typed property to `[<KEY>-<n>] <title>`. Two calls; unavoidable.

   If this retitle call fails, **do not roll back** — the page exists and is usable. Return normally and report that the prefix is missing. `updateTicket`'s backfill (below) repairs it on the next touch, and `fetchTicket`'s strip tolerates its absence.
4. Return `{ id: newId, url: pageUrl }`.

**`dependsOn` is never set here.** Mission callers run a second pass with `setDependencies` once all pages exist and their IDs are known.

`staticProperties` are **creation-only**. `updateTicket` and `upsertSection` must not touch them — they're user-owned after the ticket exists.

## updateTicket(id, patch)

`patch` may contain `title`, `body`, or `type` — any subset.

1. `fetchTicket(id)` → `pageId` and the current page content.
2. For each provided field:
   - `title` → strip any matching prefix from the incoming value (see "Title prefix"), then write `[<KEY>-<n>] <stripped>` to the page's title-typed property (whatever its name on the live DB) via `mcp__notion__notion-update-page`.
   - `type` → update the `typeProperty` if the database has one. Translate the logical key through `typeMap` and write as scalar (Select) or single-item list (Multi-Select) to match the live property type. Ignore when `typeProperty` is absent from the live DB.
   - `body` → **heading-scoped merge**, not wholesale replacement:
     1. Parse the existing page blocks and the new `body` markdown into `## <heading>` sections.
     2. For each `## <heading>` present in the **new** body: replace that section's children on the page. **Preserve the existing heading's trailing attribute block** (`{color="..."}`) verbatim — don't overwrite a user's manual color choice. If the existing heading has no attribute, apply the palette color from the Styling conventions table.
     3. Re-render the section's children with the Styling conventions applied (intro callouts, to-do blocks for Acceptance Criteria, etc.).
     4. For each `## <heading>` present **only** on the existing page: preserve it unchanged (content AND heading attributes).
     5. This guarantees that plugin-managed sections written by other commands — `## Implementation` (from `/notion-dev:ticket`), `## Merged` (from `/notion-dev:finalize`), and any future named sections added via `upsertSection` — are never wiped by a later `create-task` elaboration or any other call that supplies a partial body.

2a. **Prefix backfill.** Even when `patch` contains no `title`, inspect the live title. If it has no prefix, or a prefix whose number does not match this page's ID, rewrite it to `[<KEY>-<n>] <existing title, stripped>`. This is what lets `/notion-dev:create-task existing-ticket:<id>` repair a legacy title with no change to that command.

3. Return `{ id, url: pageUrl }`.

## updateStatus(id, logicalStatus)

1. Resolve the Notion option name from `statusMap[logicalStatus]` with the defaults above.
2. `fetchTicket(id)` to get the `pageId`.
3. Call `mcp__notion__notion-update-page` setting the `statusProperty` select to the resolved option.

## setPullRequest(id, url)

1. `fetchTicket(id)` to resolve `pageId`.
2. If the live DB has a property named by `prProperty` AND that property is a URL type, call `mcp__notion__notion-update-page` to set it to `url`.
3. If the property is absent or not URL-typed, log one warning (`"prProperty '<name>' not found on DB; skipping PR property write"`) and return — do not raise. Record `missing-property:prProperty` when the property is absent, or `wrong-type:prProperty` when it exists but is not a URL property, per `notion-dev:issue-log`. The PR URL is still recorded in the `## Implementation` section body by `/notion-dev:ticket`.

## setDependencies(id, references)

Writes the self-referential `dependsOnProperty` relation. `references` is a list whose entries are either numeric/prefixed IDs (e.g. `285`, `"STO-285"`) or ticket titles (any string that isn't a numeric or `<PREFIX>-N` form).

1. If `dependsOnProperty` is absent from the live DB → warn once and return. This mirrors the `prProperty` absence-tolerance. Record `missing-property:dependsOnProperty` per `notion-dev:issue-log`.
2. Resolve each entry to a Notion page ID:
   - Numeric / prefixed → normalize via `ID normalization` above, then run a DB-scoped `fetchTicket` to get the pageId. Skips the project-scoping guardrail for this lookup (we're within the same DB by construction).
   - Otherwise (title) → titles are stored as `[<KEY>-<n>] <bare title>` (see "Title prefix"), but a caller passing a title reference is expected to pass the bare form, same as every other caller in this file. First strip any leading `[<KEY>-<n>] ` from the caller's string too, so an already-prefixed string still matches — the adapter owns the prefix on both sides of the comparison, never the caller. Query the DB with a filter on the title-typed property **containing** the stripped string (a stored, prefixed title can never satisfy an equality filter against a bare candidate), then, in memory, strip the prefix from each returned page's live title — the same normalisation `fetchTicket` applies on read — and keep only the pages whose stripped title equals the caller's stripped string exactly. On zero matches raise: *"`setDependencies`: no ticket with title '<x>' in this DB"*. On multiple matches raise: *"`setDependencies`: title '<x>' is ambiguous (N matches); use a numeric ID instead"*.
3. `fetchTicket(id)` for the target ticket to resolve its `pageId`.
4. Call `mcp__notion__notion-update-page` setting `dependsOnProperty` to a Relation list of the resolved page IDs. Relation writes in Notion are **replacement**, not append — pass the full desired list. If you want to preserve pre-existing values, read them first and merge.

## getSelectOptions(propertyName)

Read-only. Used by callers (e.g. `/notion-dev:create-task`) to decide whether a proposed option name is new.

1. Fetch the data source schema via `mcp__notion__notion-fetch` on the configured `databaseId` (or `dataSourceId` if set).
2. Locate the property named `propertyName`.
3. If it's `select`, `multi_select`, or `status`, return the list of option names (`[string]`).
4. If it's any other type or missing, return `null`.

Never logs a warning on `null` — callers use the `null` return as a signal to skip downstream logic.

## addSelectOption(propertyName, optionName)

Mutates the live DB schema by appending an option to a Select property. **Only invoke after explicit user confirmation** — adding options alters shared state visible to everyone using the DB.

1. Fetch the data source schema; confirm `propertyName` exists and is `select` or `multi_select`. Raise if not.
2. If the option already exists (case-insensitive match), no-op and return.
3. Call `mcp__notion__notion-update-data-source` with a property update that extends the option list by one entry. Pick a default color deterministically (e.g. round-robin from the standard Notion palette) — don't leave it unset.
4. Return after the MCP confirms the update.

Never adds options to `status` properties — those are workflow-scoped and should be managed by an admin in Notion directly.

## postComment(id, text)

1. `fetchTicket(id)` to resolve `pageId`.
2. Call `mcp__notion__notion-create-comment` on the page with `text`.

## upsertSection(id, sectionName, content)

Writes (or overwrites) a single named section on the ticket page body.

`content` is either:
- A dict of labeled entries — rendered as labeled paragraphs or bulleted sub-sections under the heading.
- A markdown string — rendered verbatim under the heading.

Example dict:
```
{
  "Plan": "Short summary of the approach.",
  "PR": "<url>",
  "Files Changed": ["apps/api/...", ...],
  "Notes": "<markdown>"
}
```

Steps:
1. `fetchTicket(id)` → `pageId`.
2. Scan the page for an existing `## <sectionName>` heading (match base heading text, **ignoring** Notion trailing attributes like `{color="..."}`).
3. Resolve styling (see Styling conventions):
   - If `sectionName` is a palette entry (`Implementation`, `Merged`, `Overview`, `Tasks`), apply its heading color and prepend its intro callout (`Overview` and `Tasks` take none, per the palette table).
   - Render the content body following the palette's rich-content rules (labeled fields for Implementation; table for Merged).
   - If writing `Implementation` or `Merged`, ensure a `divider` block sits immediately before the heading — insert one if the preceding block isn't already a divider.
4. If the section already exists, call `mcp__notion__notion-update-page` to **replace** its children (from the heading down to the next top-level heading or end of page). Preserve the existing heading's trailing attribute block verbatim. Do not duplicate the heading. The divider, if present, is preserved; if absent, insert one.
5. If the section does not exist, append the blocks at the end of the page (divider, heading, callout, body).

Different section names (e.g. `"Implementation"` and `"Merged"`) coexist — `upsertSection` only touches the named section. Dividers between them are idempotent: each write checks for an adjacent divider before inserting one.

## Epic containers

An **epic** is a page in this same database where `epicMarkerProperty` (a Checkbox) is `true`, and its own `parentTaskProperty` is empty — the empty-parent check is a sanity check only (an epic has no parent of its own), not part of what makes it an epic. Children still typically carry the same `epicProperty` (Select) value as the epic page, for visual grouping in DB views, but that Select value is display metadata, not identity: a ticket carrying an `epicProperty` value, with no children or even with an ordinary Sub-items child, is **not** a container unless `epicMarkerProperty` is `true`. Epics are identified by this explicit marker, not by shape — shape alone is ambiguous: a legacy Epic-tagged *ticket* on a database upgraded to Notion's native Sub-items relation can pick up an ordinary sub-item and satisfy every structural signal an epic does (empty parent, Epic tag, a child); only the marker tells them apart, and there is no requirement on child count left to lean on instead — a freshly created epic with **zero** children is a perfectly valid epic.

`parentTaskProperty` and `epicMarkerProperty` are both required for epic containers to function, but they fail differently. When `epicMarkerProperty` is absent from the live DB, epics cannot be identified **at all**: every operation below degrades to a no-op with one warning, and the guard/validation sites (`findEpics`, `getEpicContext`, `epic-update`, `/notion-dev:ticket`'s epic guard) treat every page as **not an epic** rather than fall back to any structural guess — guessing from shape is exactly the bug this marker exists to close. Record `missing-property:epicMarkerProperty` per `notion-dev:issue-log`. When `parentTaskProperty` alone is absent, a marked epic can still be identified but can never gain children, and the plugin falls back to plain Epic-select tagging for containment purposes.

## createEpic({ name, overview, type?, assignee? })

1. If `parentTaskProperty` or `epicMarkerProperty` is absent from the live DB, warn once and return `null` — the caller degrades to Epic-select tagging.
2. Compose the body as two sections:
   - `## Overview` — the `overview` argument: a short statement of the initiative or incident.
   - `## Tasks` — empty at creation; the epic-refresh step populates it later.
3. Call `createTicket({ title: name, body, type, assignee, epic: name, isEpic: true })`. Reusing the normal creation path means the epic gets an ID, the title prefix, `Creation Date`, `staticProperties`, the assignee, and now `epicMarkerProperty` itself, all for free. Status is `"Backlog"` like any new ticket. `createTicket` returns only `{ id, url }` — it does not expose `pageId`. This also sets `epicProperty` to `name` when that property exists on the live DB, via `createTicket`'s own absence-tolerant Mission-metadata write — the Select tag stays useful for grouping in DB views, but per "Epic containers" above it is display metadata, not what makes this page an epic. **The page and `epicMarkerProperty` are written in this single `createTicket` call** — there is no intermediate state where the page exists but is not yet marked as an epic, so a create that fails partway, or a fetch/update failure afterward, can never leave an unmarked, complete-looking epic page for `findEpics()` to miss and a retry to duplicate. This is the same atomicity guarantee `createTicket`'s follow-up-creation path (see its `PROVENANCE` note, and its `parent`-relation note above) already documents for a page-identifying property — write it with the page, not after.
3a. Resolve `pageId`: call `fetchTicket(id)` on the id just created and read `metadata.pageId` off the result. This is the only source `createEpic` has for the Notion page id — one extra read, but unavoidable given `createTicket`'s return shape. This read is not load-bearing for the marker: `epicMarkerProperty` is already set by the time this runs, so a failure here only costs `createEpic` its `pageId` return value, never the page's epic status.
4. `parentTaskProperty` is left empty — an epic has no parent. `phase`, `step`, and `dependsOn` are never set on an epic.
5. `type` defaults to the dominant child type when the caller knows the children, else `feature`.
6. Return `{ id, key, url, pageId }` — `pageId` from step 3a; `key` is the logical ticket key (`"STO-67"`) derived the same way `fetchTicket` derives it (`project.key` + the numeric `id` from step 3), so callers can display `[{key}] {name}` without constructing the prefix themselves.

## findEpics()

Read-only.

1. If `epicMarkerProperty` is absent from the live DB, warn once and return **`null`** — mirrors `getSelectOptions`, which returns `null` for the same absent/unsuitable-property case. Epics cannot be identified safely at all without this property: falling back to a structural guess (an Epic-select tag, an empty parent, a child count) is exactly the bug this marker exists to close, so absence degrades to `null` rather than any such fallback. Distinct from step 3's `[]`: `null` means epic containers are unavailable on this DB at all; `[]` means the property exists but no page has it set yet. Callers must not conflate the two.
2. Query the database (or `dataSourceId` when configured) with `mcp__notion__notion-query-data-sources` for pages where `epicMarkerProperty` is `true` **and** (when `parentTaskProperty` also exists on the live DB) their own `parentTaskProperty` is empty — the same predicate `getEpicContext` step 2, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply (see "Epic containers" above), so "epic" means the same thing at all four sites. When `parentTaskProperty` is absent from the live DB entirely, its emptiness is vacuously true for every page, so the filter reduces to `epicMarkerProperty` alone in that case. When `staticProperties` is configured, add each `[name, expected]` pair as an additional equality filter on this same query — the same scoping the "Project scoping guardrail" applies per-page, applied here at query time so epic discovery never surfaces a foreign project's epic in a shared DB. When `staticProperties` is empty or absent, the query is unchanged.
3. For each hit return `{ id, key, pageId, name, title, url, overview }` — `key` is the logical ticket key (`"STO-67"`) for display, same meaning and format as in `fetchTicket` and `listEpicChildren`; `name` is the `epicProperty` Select value (display metadata — may be empty on a marker-only epic that was never given one), `title` is the page title with the ID prefix stripped, `overview` is the text of its `## Overview` section (empty string when absent). No hits → `[]`. There is no children-based filtering pass here: a page with zero children is returned exactly like any other epic, since the marker alone decides.

## setParent(id, epicId)

1. If `parentTaskProperty` is absent from the live DB, warn once and return.
2. Resolve `id` and `epicId` to page IDs via `fetchTicket`.
3. If they are the same page, raise: *"`setParent`: a ticket cannot be its own parent"*.
4. Call `mcp__notion__notion-update-page` setting `parentTaskProperty` to a single-element Relation list containing the epic's page id. Replacement semantics are correct here — a ticket has exactly one parent.

## listEpicChildren(epicId)

Read-only.

1. If `parentTaskProperty` is absent from the live DB, warn once and return `[]`.
2. Resolve `epicId` to a page ID via `fetchTicket`.
3. Query the DB for pages whose `parentTaskProperty` contains that page ID.
4. Return `[{ id, key, title, status, url }]` ordered ascending by `id` — `key` the logical ticket key (`"STO-67"`) for display, `title` prefix-stripped, `status` the live option name verbatim (not a logical key; callers compare it against the resolved set).

## getEpicContext(epicId, currentTicketId)

Read-only. Assembles the bounded context block that `/notion-dev:ticket` threads into its reasoning phases when a starting ticket belongs to an epic. `currentTicketId` is the id of the ticket being started — the same `id` `/notion-dev:ticket` Phase 1.1 resolved via its own `fetchTicket(id)` call; passed explicitly so this operation never depends on being invoked in any particular sequence. **The sole owner of what "epic context" means and how much of it is included** — callers must never assemble this themselves or parse `## Resolution Log` directly; that format belongs to `epic-update`, and a second copy of the parser in a command file is how the two drift apart.

1. If `epicId` is empty, or `epicMarkerProperty` is absent from the live DB, return `null`. Not a warning — this is the normal case for most tickets, which have no epic.
2. `fetchTicket(epicId)` → epic identity (`key`, `title`, `url`), `body`, and its own `metadata.parentTaskProperty` / `metadata.epicMarkerProperty`. **Validate before proceeding**: if the fetched page's own `parentTaskProperty` is non-empty, or its `epicMarkerProperty` is not `true` (`false` whether because the box is unchecked or `epicMarkerProperty` is absent from the live DB entirely — `fetchTicket` collapses both to the same default; see "Property type handling"), this is not a structurally valid epic — return `null`, the same signal as step 1's "no epic" case, and do nothing further. This is the same predicate `findEpics()`, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply; enforcing it here, inside the adapter, means every caller — present or future — inherits it rather than having to re-check at each call site. Without it, a `parentTaskProperty` value that merely points at an ordinary Notion Sub-items parent (not an epic) would be handed back as if it were one: a nonexistent `## Overview`, the parent's other children mislabeled as "siblings," and none of it flagged as anything other than epic context.
3. **Overview.** Extract the `## Overview` section verbatim from `body`. Omit the heading and body entirely from the output when the section is absent.
4. **Sibling status.** Call `listEpicChildren(epicId)` — a **live** call, never derived from the epic body's `## Tasks` section. That section is documented as "Snapshot as of the last resolution" and is only refreshed when a child resolves, so it is stale by construction; handing a starting ticket stale sibling status would be worse than handing it none. Render one line per child: `[{key}] {title} — {status}`. Mark the entry whose `id` equals `currentTicketId` with a trailing ` (this ticket)` so the reader can locate itself among its siblings. When `currentTicketId` matches no entry — e.g. the parent relation was just set but the epic's child query has not yet picked it up — mark nothing and continue; this is not an error.
5. **Recent resolution history.** Parse `## Resolution Log` from `body` into its `### [<KEY>-<n>] resolved — <datetime>` entries, in document order. `appendToSection` always appends at the end, so the **last 3** entries in document order are the most recent 3 resolutions — take those. When more than 3 entries exist, prepend a line stating how many older entries were omitted, so the reader knows there is more history and where to find it (the epic `url` from step 2).
6. Assemble and return one markdown block, in this order — identity, `## Overview` (when present), sibling status, recent resolution history:

```
## Epic context: [<KEY>-<n>] <epic title>
<epic url>

## Overview
<verbatim epic overview text>

### Siblings
- [<KEY>-67] Fix stale index — Implemented
- [<KEY>-68] Add cache metrics — In Progress (this ticket)
- [<KEY>-69] Backfill historic wallets — Backlog

### Recent resolution history
…2 older entries omitted — see the epic page for full history.
### [<KEY>-65] resolved — 2026-07-30 14:02 UTC
**Summary** — ...
### [<KEY>-66] resolved — 2026-07-31 09:15 UTC
**Summary** — ...
```

**Background, not requirements.** This block is context for the caller's reasoning, never a source of tasks or acceptance criteria — a resolution-log entry can describe an approach the current ticket now contradicts. Callers are responsible for stating that framing wherever they hand this block onward; see `/notion-dev:ticket` Phase 1.1.

## refreshEpicTasks(epicId)

Re-renders an epic's `## Tasks` section from its live children. **The single owner of that section's format** — callers never render it themselves, so `/notion-dev:create-task` and the epic-update flow cannot drift apart.

1. If `parentTaskProperty` is absent from the live DB, warn once and return.
2. `listEpicChildren(epicId)`.
3. Render one Notion to-do block per child, ordered by id:

```
- [x] [STO-67] Fix stale index — Implemented
- [ ] [STO-68] Add cache metrics — In Progress
- [ ] [STO-69] Backfill historic wallets — Backlog
```

   The box is ticked when the child's `status` is in the **resolved set**. Each line is `[{key}] {title} — {status}` from the `listEpicChildren` entry.
4. Prepend this note as the section's first paragraph: *"Snapshot as of the last resolution — see the Parent task column for live status."*
5. `upsertSection(epicId, "Tasks", <rendered blocks>)`.

Safe to call repeatedly. `upsertSection` replaces only up to the next top-level heading, so a `## Resolution Log` below it is never touched.

## appendToSection(id, sectionName, content)

The **append-only** counterpart to `upsertSection`. Where `upsertSection` replaces a section's children, this adds to the end of them. Use it wherever history must accumulate rather than be overwritten.

1. `fetchTicket(id)` → `pageId`.
2. Scan the page for an existing `## <sectionName>` heading — match base heading text, **ignoring** trailing Notion attributes like `{color="..."}`.
3. **Section absent** → append the heading at the end of the page, applying the palette color from the Styling conventions table, then write `content`'s blocks beneath it.
4. **Section present** → append `content`'s blocks immediately before the next top-level (`##`) heading, or at end of page when it is the last section. Existing children are never read back, rewritten, or reordered — that is the whole point of this operation.

`content` is markdown, rendered with the same block conventions `upsertSection` uses.

## MCP unavailability

There is no useful CLI fallback for Notion. If the MCP is unreachable, fail with: *"Notion MCP is unavailable. Re-check `.mcp.json`, confirm the `notion` server is listed, and retry."* Record `mcp-unavailable:notion` per `notion-dev:issue-log`.
