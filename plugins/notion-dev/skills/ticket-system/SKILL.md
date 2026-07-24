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
| `fetchTicket` | `id` (numeric or prefixed string, or a Notion page id/URL) | `{ title, body, status, type, url, metadata }` — `type` is the logical key (`feature`/`bug`/…) when the DB has a mapped type property, else absent |
| `createTicket` | `{ title, body, type?, epic?, phase?, step?, assignee? }` | `{ id, url }` — `epic`/`phase`/`step` are optional mission metadata; `assignee` is a resolved Notion user id. Each is absence-tolerant when the corresponding configured property is missing from the live DB |
| `resolveAssignee` | `value` (user id, email, or display name) | `{ id, name }` on a unique person match; `null` on no match or ambiguity. Read-only — never mutates config or the DB |
| `updateTicket` | `id`, `{ title?, body?, type? }` | `{ id, url }` — only the provided fields change |
| `updateStatus` | `id`, `logicalStatus` ∈ `{ inProgress, implemented }` (plugin-invoked set) plus any custom key present in the user's `statusMap` | `void` — the plugin never invokes `delivered` / `done` / shipped-style states; those are reserved for host-project commands |
| `setPullRequest` | `id`, `url` | `void` — persists the PR URL into the configured PR property. No-op when the live DB has no such property. Does not touch body sections. |
| `setDependencies` | `id`, `[titleOrId, …]` | `void` — writes the configured `dependsOnProperty` relation. Resolves entries that look like titles to page IDs within the DB. No-op when the property is absent. Pass-2 in mission creation. |
| `getSelectOptions` | `propertyName` | `[string]` or `null` — lists option names for a Select / Multi-Select / Status property. Returns `null` if the property is absent or not a selectable type. Read-only. |
| `addSelectOption` | `propertyName`, `optionName` | `void` — extends a Select's options list on the live DB. Should only be invoked after explicit user confirmation (adding options mutates shared DB schema). |
| `postComment` | `id`, `text` | `void` |
| `upsertSection` | `id`, `sectionName` (string), `content` (dict of labeled entries OR markdown) | `void` — appends a `## <sectionName>` block to the ticket body, or **overwrites** it if one already exists. Different section names are independent — e.g. `"Implementation"` and `"Merged"` coexist. |

`body` is markdown structured with sections: **Requirements**, **Acceptance Criteria**, **Context**, **Open Questions** (order may vary; missing sections are allowed).

`logicalStatus` is always the logical name. The adapter maps it to the concrete Notion status via `statusMap` in config, falling back to sensible defaults when a key is missing.

## ID normalization

Callers may pass an `id` as a **logical key** — `STO-285`, `STO285`, or `285`. Normalize by stripping the configured `project.key` prefix and any separator, then parsing the remainder as an integer, then resolving it through the `idProperty` lookup. A **Notion page id or page URL** is also accepted, resolving the page directly.

## Configuration

Config (from `.claude/notion-dev.config.json` → `ticketSystem`):
- `databaseId` — the Notion database
- `dataSourceId` — optional, preferred for queries when set
- `idProperty` — property name holding the numeric ticket ID (default `"ID"`). Works with both Notion `number` and `unique_id` (auto-increment) property types.
- `statusProperty` — property name holding the status select (default `"Status"`)
- `typeProperty` — property name holding the ticket type (default `"Type"`). The live property may be either Select or Multi-Select; the adapter normalizes both.
- `prProperty` — property name (URL) that `/notion-dev:ticket` writes the PR link to (default `"PR"`). When the property doesn't exist on the live DB, skip the write with a warning rather than aborting.
- `assigneeProperty` — People property that `/notion-dev:create-task` assigns new tickets to (default `"Assignee"`). When the property doesn't exist on the live DB or isn't a People type, skip the write with a warning rather than aborting.
- `defaultAssignee` — default assignee as a Notion user id, email, or display name, resolved via `resolveAssignee` at create time. Empty string or absent → `/notion-dev:create-task` prompts interactively. `/notion-dev:init` writes it explicitly (including `""`).
- `statusMap` — logical → Notion option name; defaults below
- `typeMap` — logical type key → Notion option label; defaults below
- `staticProperties` — optional dict of extra properties to set on every new ticket (e.g. `{ "Project": "BTC-Gateway" }`). Set once at creation; never modified by `updateTicket` or `upsertSection`.
- `epicProperty` — Select property holding the Epic tag (default `"Epic"`). Used by mission-mode `createTicket`. Absence-tolerant.
- `phaseProperty` — Select property holding the Phase tag (default `"Phase"`). Absence-tolerant.
- `stepProperty` — Number property holding the Step position within a Phase (default `"Step"`). Absence-tolerant.
- `dependsOnProperty` — self-referential Relation property for blocking dependencies (default `"Depends on"`). Written in a second pass after all mission tickets exist. Absence-tolerant.

Defaults for `statusMap` when keys are missing:
```
inProgress  → "In Progress"
implemented → "Implemented"
```

The plugin actively invokes only `inProgress` (set by `/notion-dev:ticket` at worktree creation) and `implemented` (set by `/notion-dev:finalize` post-merge). Additional logical keys (`delivered`, `done`, etc.) may appear in a user's `statusMap` to support custom commands like a separate `/release` flow, but **no plugin command transitions a ticket to those states** — that is deliberately out of scope. Release and deployment semantics belong to the host project.

Defaults for `typeMap` when keys are missing:
```
feature     → "Feature"
bug         → "Bug"
improvement → "Improvement"
research    → "Research"
```

## Property type handling

The adapter normalizes the following shape differences between the canonical schema and real-world databases:

- **Title** — every Notion database has exactly one property whose type is `title` (the page title). The adapter discovers it dynamically by scanning the live schema for the `title`-typed property; its **name** is not fixed — common choices are `Name`, `Title`, `Task name`, etc. Callers pass the title value as a plain string; the adapter writes it to whichever property is the title type on this DB. Never hardcode a property name for the title.
- **ID** — read/write as `number` or `unique_id` depending on the live property type. `unique_id` is read-only to the MCP; creation does not set it (Notion auto-assigns). Queries filter by numeric id regardless of type.
- **Type** — read: if the live property is `multi_select`, take the first value; if `select`, take the value. Write: if `multi_select`, send a single-item list; if `select`, send the scalar. Empty values round-trip as `null`.
- **PR** — read/write when `prProperty` exists on the live DB. When absent, skip writes and log a single warning per run (no abort).
- **Epic / Phase** (Select) — write as the option name string. When the configured property is absent from the live DB, skip with a one-time warning. When the property exists but the option doesn't, raise a clear error telling the caller to add the option first (via `addSelectOption` or manually in Notion). Never silently mutate the DB's option list from a write path — option creation is an explicit, user-confirmed action.
- **Step** (Number) — write as a number. Integers and floats both accepted; adapter passes through the caller's value.
- **Depends on** (Relation) — write as a list of page IDs. When the caller passes titles, resolve each to a page ID by DB-scoped title search (same mechanism `existing-ticket` uses on numeric IDs) before writing. Unresolved titles raise a clear error naming the offender. Absence-tolerant when the property is missing.
- **Assignee** (People) — write as a single-item list of `{ id }` user references to the `assigneeProperty` column. Read is not implemented (the plugin never reads assignee back). When the configured property is absent from the live DB or is not a `people` type, skip the write and log **one** warning per run (`"assigneeProperty '<name>' not found or not a People property on DB; skipping assignee write"`) — never abort. `assignee` is caller-supplied creation state, not a `staticProperty`: `updateTicket` and `upsertSection` never touch it.

## Project scoping guardrail

When `staticProperties` is configured, those same properties act as a **fetch-side scope check**: a DB shared across projects will have tickets from other projects, and every per-ID operation starts from `fetchTicket`. After resolving a page, compare each `[name, expected]` in `staticProperties` against the fetched page's value for that property:

- **Match** (or property absent from the live DB) → proceed silently.
- **Mismatch** → abort with: *"`<PREFIX>-<id>` has `<prop>`=`<actual>`; this project is pinned to `<prop>`=`<expected>`. Refusing to operate on a ticket from a different project."*

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

Unknown section names (including user-added ones) render with no color and no callout — the plugin only styles sections it owns. Match section names case-insensitively on base text; don't restyle sections a user has manually recolored (see "Heading attribute preservation" below).

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
5. Return `{ title, body, status, type, url, metadata: { pageId, idProperty value } }`. The `idProperty value` (the numeric key) is read off the **resolved page** regardless of which branch resolved it — callers rely on it for branch/worktree naming.

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

Never writes config or the database. When `mcp__notion__notion-get-users` is unavailable, fail with the standard MCP-unavailability message (see "MCP unavailability").

## createTicket({ title, body, type?, epic?, phase?, step?, assignee? })

1. Determine the next ID: query the database ordered by `idProperty` desc; take `max + 1`. If `idProperty` is `unique_id`, skip this step — Notion auto-assigns on create; read the assigned id back from the created page.
2. Create the page via `mcp__notion__notion-create-pages`:
   - Parent = configured database / data source.
   - Properties: `idProperty` = new id (omit when `unique_id`), the **title-typed property** (discovered from the live schema — see Property type handling above) = `title`, `statusProperty` = `"Backlog"` (or the first option if Backlog not present).
   - If the live DB has `typeProperty` AND `type` was provided, set it: translate the logical key through `typeMap` to the Notion option label, then write it as a scalar (Select) or single-item list (Multi-Select) depending on the live property type.
   - For each `[name, value]` in `staticProperties` (if configured), set that property on the page. Property type is inferred from the live database schema (Select/Status → option name match; Multi-Select → single-item list unless the value is already a list; text → verbatim). Skip silently with a warning if the property doesn't exist on the DB.
   - **Assignee** (absence-tolerant): if `assignee` (a resolved user id) is provided AND the live DB has the `assigneeProperty` column AND it is a `people` type, set it to a single-item people list `[{ id: assignee }]`. If the column is absent or not People-typed, skip with the one-time warning from "Property type handling". `assignee` absent → set nothing.
   - **Mission metadata** (absence-tolerant, independent of each other):
     - If `epic` is provided AND `epicProperty` exists on the live DB, set that Select to `epic` (exact option-name match required; if the option doesn't exist, raise an error — the caller should have resolved it via `getSelectOptions` / `addSelectOption` first).
     - If `phase` is provided AND `phaseProperty` exists, set that Select to `phase` (same option-match rule).
     - If `step` is provided AND `stepProperty` exists, set that Number to `step`.
     - Any missing configured property emits a one-time warning (`"<name>Property '<n>' not found on DB; skipping"`) and continues.
   - Children blocks: render `body` markdown, **applying the Styling conventions above**. Each canonical heading (`Requirements`, `Acceptance Criteria`, `Context`, `Open Questions`, `Source`) gets its palette color; intro callouts prepend sections that define one; `Acceptance Criteria` renders as to-do blocks. No divider appears yet at creation — only zone transitions add dividers.
3. Return `{ id: newId, url: pageUrl }`.

**`dependsOn` is never set here.** Mission callers run a second pass with `setDependencies` once all pages exist and their IDs are known.

`staticProperties` are **creation-only**. `updateTicket` and `upsertSection` must not touch them — they're user-owned after the ticket exists.

## updateTicket(id, patch)

`patch` may contain `title`, `body`, or `type` — any subset.

1. `fetchTicket(id)` → `pageId` and the current page content.
2. For each provided field:
   - `title` → update the page's title-typed property (whatever its name on the live DB) via `mcp__notion__notion-update-page`.
   - `type` → update the `typeProperty` if the database has one. Translate the logical key through `typeMap` and write as scalar (Select) or single-item list (Multi-Select) to match the live property type. Ignore when `typeProperty` is absent from the live DB.
   - `body` → **heading-scoped merge**, not wholesale replacement:
     1. Parse the existing page blocks and the new `body` markdown into `## <heading>` sections.
     2. For each `## <heading>` present in the **new** body: replace that section's children on the page. **Preserve the existing heading's trailing attribute block** (`{color="..."}`) verbatim — don't overwrite a user's manual color choice. If the existing heading has no attribute, apply the palette color from the Styling conventions table.
     3. Re-render the section's children with the Styling conventions applied (intro callouts, to-do blocks for Acceptance Criteria, etc.).
     4. For each `## <heading>` present **only** on the existing page: preserve it unchanged (content AND heading attributes).
     5. This guarantees that plugin-managed sections written by other commands — `## Implementation` (from `/notion-dev:ticket`), `## Merged` (from `/notion-dev:finalize`), and any future named sections added via `upsertSection` — are never wiped by a later `create-task` elaboration or any other call that supplies a partial body.
3. Return `{ id, url: pageUrl }`.

## updateStatus(id, logicalStatus)

1. Resolve the Notion option name from `statusMap[logicalStatus]` with the defaults above.
2. `fetchTicket(id)` to get the `pageId`.
3. Call `mcp__notion__notion-update-page` setting the `statusProperty` select to the resolved option.

## setPullRequest(id, url)

1. `fetchTicket(id)` to resolve `pageId`.
2. If the live DB has a property named by `prProperty` AND that property is a URL type, call `mcp__notion__notion-update-page` to set it to `url`.
3. If the property is absent or not URL-typed, log one warning (`"prProperty '<name>' not found on DB; skipping PR property write"`) and return — do not raise. The PR URL is still recorded in the `## Implementation` section body by `/notion-dev:ticket`.

## setDependencies(id, references)

Writes the self-referential `dependsOnProperty` relation. `references` is a list whose entries are either numeric/prefixed IDs (e.g. `285`, `"STO-285"`) or ticket titles (any string that isn't a numeric or `<PREFIX>-N` form).

1. If `dependsOnProperty` is absent from the live DB → warn once and return. This mirrors the `prProperty` absence-tolerance.
2. Resolve each entry to a Notion page ID:
   - Numeric / prefixed → normalize via `ID normalization` above, then run a DB-scoped `fetchTicket` to get the pageId. Skips the project-scoping guardrail for this lookup (we're within the same DB by construction).
   - Otherwise (title) → query the DB with a filter on the title-typed property equaling the string. Exact match required. On zero matches raise: *"`setDependencies`: no ticket with title '<x>' in this DB"*. On multiple matches raise: *"`setDependencies`: title '<x>' is ambiguous (N matches); use a numeric ID instead"*.
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
   - If `sectionName` is a palette entry (`Implementation`, `Merged`), apply its heading color and prepend its intro callout.
   - Render the content body following the palette's rich-content rules (labeled fields for Implementation; table for Merged).
   - If writing `Implementation` or `Merged`, ensure a `divider` block sits immediately before the heading — insert one if the preceding block isn't already a divider.
4. If the section already exists, call `mcp__notion__notion-update-page` to **replace** its children (from the heading down to the next top-level heading or end of page). Preserve the existing heading's trailing attribute block verbatim. Do not duplicate the heading. The divider, if present, is preserved; if absent, insert one.
5. If the section does not exist, append the blocks at the end of the page (divider, heading, callout, body).

Different section names (e.g. `"Implementation"` and `"Merged"`) coexist — `upsertSection` only touches the named section. Dividers between them are idempotent: each write checks for an adjacent divider before inserting one.

## MCP unavailability

There is no useful CLI fallback for Notion. If the MCP is unreachable, fail with: *"Notion MCP is unavailable. Re-check `.mcp.json`, confirm the `notion` server is listed, and retry."*
