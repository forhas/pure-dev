# notion-dev Epics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `Creation Date` support, ID-prefixed ticket titles, Epic container pages, and epic resolution logs to the notion-dev plugin.

**Architecture:** All behavior lives in prompt-markdown. `skills/ticket-system/SKILL.md` is the adapter layer that owns every Notion interaction — new operations and the title-prefix logic go there, and the four command files consume them by name. `schema/notion-dev.config.schema.json` declares the three new config keys. Commands never construct a title prefix or touch a Notion property directly.

**Tech Stack:** Markdown prompt files, JSON Schema draft-07, Notion hosted MCP (`mcp__notion__*`).

**Spec:** `docs/superpowers/specs/2026-08-01-notion-dev-epics-design.md` — section references below (`§3`, `§6.4`, …) point at it. Read the referenced section before editing; this plan gives the exact edits, the spec gives the reasoning.

## Why there are no tests

This repo contains no executable code and no test harness (`find . -type d -name "test*"` returns nothing). Every task therefore ends with **verification commands that check cross-file contracts** — that an operation named in a command exists in the skill that implements it, that a config key referenced in prose exists in the schema, that the schema still parses. These are real, runnable checks with stated expected output; run them and read the output before committing. The spec's §11 live smoke run against a scratch Notion DB is a manual step for the user after merge, not part of any task.

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include these.

- **Absence tolerance.** Every new Notion property (`creationDateProperty`, `parentTaskProperty`) is absence-tolerant: when missing from the live DB, skip the operation and log **one** warning per run. Never abort. (§1, §4.3, §4.4, §4.5)
- **One warning per run.** Warnings for a missing property are emitted once per run, not once per call. Matches the existing `prProperty` / `assigneeProperty` convention.
- **Omit-when-default.** `/notion-dev:init` writes a config key only when the resolved live name differs from the schema default. Exceptions already in the codebase (`reviewer`, `defaultAssignee`) are not extended by this work.
- **The adapter owns the title prefix.** No command file ever **writes a title** carrying a constructed prefix, and none parses or strips one. Callers pass and receive bare titles, and get the ticket key as a separate `key` field (`"STO-67"`) when they need to *display* it. Rendering `[{key}] {title}` for human-readable output is fine; building a prefix to write back is not. (§3)
- **`statusMap.done` / `statusMap.cancelled` are read-only.** The plugin reads them for the epic-close check and never transitions a ticket into them. (§1.2)
- **Epic bookkeeping is best-effort.** Every step in §6 logs a warning and continues on failure; it never fails a run whose merge already landed. (§6.6)
- **`quick-dev` is untouched.** No file under `plugins/quick-dev/` changes.
- **One version bump.** `plugins/notion-dev/.claude-plugin/plugin.json` goes `0.7.0` → `0.8.0` exactly once, in Task 9.

---

### Task 1: `Creation Date` support

Adds the config key and the adapter's write path. Self-contained: nothing else in the plan depends on it, and it depends on nothing.

**Files:**
- Modify: `plugins/notion-dev/schema/notion-dev.config.schema.json:84-88` (insert after the `dependsOnProperty` block)
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md:55` (Configuration list), `:84` (Property type handling), `:212` (createTicket step 2)

**Interfaces:**
- Produces: config key `ticketSystem.creationDateProperty`, default `"Creation Date"`. Consumed by Task 4 (init detection) and Task 9 (README).
- Produces: `createTicket` sets the creation timestamp when the live property is `date`-typed.

- [ ] **Step 1: Add the schema property**

In `plugins/notion-dev/schema/notion-dev.config.schema.json`, immediately after the `dependsOnProperty` block (which closes at line 88 with `}`) and before the closing `}` of `ticketSystem.properties`, insert:

```json
        "creationDateProperty": {
          "type": "string",
          "default": "Creation Date",
          "description": "Property holding the ticket's creation timestamp. The live property may be either a Date property (the plugin writes the creation timestamp) or a Created time property (Notion auto-populates; the plugin never writes). Absence-tolerant — when missing or of any other type, the write is skipped with a warning rather than aborting."
        }
```

Add a `,` to the end of the preceding `dependsOnProperty` block's closing `}` so the JSON stays valid.

- [ ] **Step 2: Document the config key in the adapter**

In `plugins/notion-dev/skills/ticket-system/SKILL.md`, in the `## Configuration` bullet list, immediately after the `dependsOnProperty` bullet (line 55), add:

```markdown
- `creationDateProperty` — property holding the ticket's creation timestamp (default `"Creation Date"`). Tolerates two live types: a `date` property (the adapter writes the timestamp at creation) or a `created_time` property (Notion auto-populates; the adapter never writes). Absence-tolerant.
```

- [ ] **Step 3: Add the property-type handling rule**

In the same file, in the `## Property type handling` bullet list, immediately after the `**Assignee** (People)` bullet (line 84), add:

```markdown
- **Creation Date** (`date` or `created_time`) — read the live property type and branch. `date`: `createTicket` writes `{ "date": { "start": "<ISO 8601 UTC timestamp, with time>" } }`. `created_time`: never written — Notion populates it, and the API rejects writes to it. Any other type, or the property absent: skip the write and log **one** warning per run (`"creationDateProperty '<name>' not found or not a date/created_time property on DB; skipping creation date write"`). Creation-only, like `staticProperties` — `updateTicket` and `upsertSection` never touch it.
```

- [ ] **Step 4: Wire it into `createTicket`**

In the same file, in `## createTicket(...)` step 2's bullet list, immediately after the `**Assignee** (absence-tolerant)` bullet (line 215) and before the `**Mission metadata**` bullet, add:

```markdown
   - **Creation Date** (absence-tolerant): if the live DB has the `creationDateProperty` column AND it is a `date` type, set it to the current UTC timestamp in ISO 8601 with time (e.g. `2026-08-01T14:32:00Z`). When it is a `created_time` type, set nothing — Notion fills it. When absent or any other type, skip with the one-time warning from "Property type handling".
```

- [ ] **Step 5: Verify the schema still parses and the key is wired end to end**

```bash
cd /home/forhas/dev/pure-dev
python3 -c "import json; d=json.load(open('plugins/notion-dev/schema/notion-dev.config.schema.json')); p=d['properties']['ticketSystem']['properties']['creationDateProperty']; print('default:', p['default'])"
grep -c 'creationDateProperty' plugins/notion-dev/skills/ticket-system/SKILL.md
```

Expected: first command prints `default: Creation Date` and exits 0 (a parse error means Step 1 broke the JSON — most likely the missing comma). Second command prints `3` (Configuration bullet, Property type handling bullet, createTicket bullet).

- [ ] **Step 6: Commit**

```bash
git add plugins/notion-dev/schema/notion-dev.config.schema.json plugins/notion-dev/skills/ticket-system/SKILL.md
git commit -m "feat(notion-dev): support a Creation Date property on new tickets"
```

---

### Task 2: Adapter-owned ticket ID title prefix

Makes `ticket-system` add `[<KEY>-<n>] ` on write and strip it on read, so no command file changes. Depends on nothing; Task 3's `createEpic` relies on it.

**Files:**
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md:36` (new section after `## ID normalization`), `:77` (Title bullet in Property type handling), `:190` (fetchTicket step 5), `:210-222` (createTicket steps 2-3), `:234` (updateTicket step 2)

**Interfaces:**
- Consumes: nothing.
- Produces: `fetchTicket` returns a **stripped** `title` plus `metadata.rawTitle`. `createTicket` and `updateTicket` write prefixed titles. Task 3's `createEpic` and Task 8's log rendering both rely on titles being stripped on read.

- [ ] **Step 1: Add the title-prefix section**

In `plugins/notion-dev/skills/ticket-system/SKILL.md`, insert a new section between the end of `## ID normalization` (line 36) and `## Configuration` (line 38):

````markdown
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

**`unique_id` prefix mismatch.** A Notion `unique_id` column carries its own prefix. When it differs from `project.key`, titles still use `project.key` — config is the source of truth for the plugin's naming, and branch names already depend on it. Log **one** warning per run: `"ID column prefix '<live>' differs from project.key '<KEY>'; titles use '<KEY>'"`.
````

- [ ] **Step 2: Note the prefix on the Title property-handling bullet**

In `## Property type handling`, append to the end of the `**Title**` bullet (line 77), after "Never hardcode a property name for the title.":

```markdown
The value written is the caller's bare title with the ID prefix prepended, and the value read is stripped of it — see "Title prefix" above.
```

- [ ] **Step 3: Strip on read in `fetchTicket`**

Replace `fetchTicket` step 5 (line 190) with:

```markdown
5. Return `{ title, key, body, status, type, url, metadata: { pageId, idProperty value, rawTitle } }`. `title` is the page title **with the ID prefix stripped** (see "Title prefix"); `key` is the logical ticket key (`"STO-67"`) for callers that need to *display* the id beside the title; `rawTitle` is the literal Notion title. The `idProperty value` (the numeric key) is read off the **resolved page** regardless of which branch resolved it — callers rely on it for branch/worktree naming.
```

Then append to the "Reading" paragraph of the `## Title prefix` section added in Step 1:

```markdown
Callers that need to *show* the id alongside the title use the `key` field (`"STO-67"`) and render `[{key}] {title}` themselves. That is display formatting, not prefix construction — what the adapter owns is the title stored in Notion.
```

- [ ] **Step 4: Prefix on create**

In `## createTicket(...)`, replace step 2's first properties bullet (line 212) with:

```markdown
   - Properties: `idProperty` = new id (omit when `unique_id`), the **title-typed property** (discovered from the live schema — see Property type handling above), `statusProperty` = `"Backlog"` (or the first option if Backlog not present). The title value depends on the ID column type — see the retitle rule in step 3.
```

Then replace step 3 (line 222, currently `3. Return { id: newId, url: pageUrl }.`) with:

````markdown
3. Apply the title prefix (see "Title prefix"):
   - **`number` ID column** — the id was computed in step 1, so the create in step 2 already wrote `[<KEY>-<n>] <title>`. Nothing further.
   - **`unique_id` ID column** — the id does not exist until the page does. Step 2 created the page with the **bare** title; now read the assigned id off the created page and call `mcp__notion__notion-update-page` to set the title-typed property to `[<KEY>-<n>] <title>`. Two calls; unavoidable.

   If this retitle call fails, **do not roll back** — the page exists and is usable. Return normally and report that the prefix is missing. `updateTicket`'s backfill (below) repairs it on the next touch, and `fetchTicket`'s strip tolerates its absence.
4. Return `{ id: newId, url: pageUrl }`.
````

- [ ] **Step 5: Prefix and backfill on update**

In `## updateTicket(id, patch)`, replace the `title` bullet in step 2 (line 234) with:

```markdown
   - `title` → strip any matching prefix from the incoming value (see "Title prefix"), then write `[<KEY>-<n>] <stripped>` to the page's title-typed property (whatever its name on the live DB) via `mcp__notion__notion-update-page`.
```

Then, immediately after step 2's bullet list and before step 3 (`3. Return { id, url: pageUrl }.`), insert:

```markdown
2a. **Prefix backfill.** Even when `patch` contains no `title`, inspect the live title. If it has no prefix, or a prefix whose number does not match this page's ID, rewrite it to `[<KEY>-<n>] <existing title, stripped>`. This is what lets `/notion-dev:create-task existing-ticket:<id>` repair a legacy title with no change to that command.
```

- [ ] **Step 6: Verify the prefix contract is stated in every place that writes or reads a title**

```bash
cd /home/forhas/dev/pure-dev
grep -n 'Title prefix' plugins/notion-dev/skills/ticket-system/SKILL.md
grep -c 'rawTitle\|`key`' plugins/notion-dev/skills/ticket-system/SKILL.md
grep -rn 'title.*=.*\[<KEY>-\|title.*\[\$\?{\?KEY' plugins/notion-dev/commands/ | wc -l
```

Expected: first prints 5 lines (the section heading plus 4 cross-references). Second prints ≥ 3. Third prints `0` — **no command file may write a title carrying a constructed prefix**. Display rendering such as `[{key}] {title}` in an epic's task list is explicitly allowed and does not match this pattern.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/skills/ticket-system/SKILL.md
git commit -m "feat(notion-dev): prefix ticket titles with their ID in the adapter"
```

---

### Task 3: Epic primitives in `ticket-system`

The five new operations plus `parentTaskProperty`, the resolved set, and the epic-page palette. Everything from Task 4 onward consumes this.

**Files:**
- Modify: `plugins/notion-dev/schema/notion-dev.config.schema.json:54-58` (`statusMap` description), `:88` (insert `parentTaskProperty`)
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md:16-28` (operations table), `:55` (Configuration), `:57-63` (statusMap defaults), `:84` (Property type handling), `:107-116` (palette), `:215` (createTicket `parent`), end of file (new operation sections)

**Interfaces:**
- Consumes: Task 2's title prefix (`createEpic` gets it via `createTicket`); Task 1's `createTicket` shape.
- Produces, for Tasks 4-9:
  - `createEpic({ name, overview, type?, assignee? })` → `{ id, url, pageId }`
  - `findEpics()` → `[{ id, pageId, name, title, url, overview }]`
  - `setParent(id, epicId)` → `void`
  - `listEpicChildren(epicId)` → `[{ id, key, title, status, url }]`
  - `refreshEpicTasks(epicId)` → `void` — sole owner of the `## Tasks` render format
  - `appendToSection(id, sectionName, content)` → `void`
  - `createTicket` gains `parent?`
  - config key `ticketSystem.parentTaskProperty`, default `"Parent task"`
  - the **resolved set** = the live option names from `statusMap.implemented` / `.done` / `.cancelled`

- [ ] **Step 1: Add `parentTaskProperty` to the schema**

In `plugins/notion-dev/schema/notion-dev.config.schema.json`, after the `creationDateProperty` block added in Task 1, insert (adding a comma to the preceding block):

```json
        "parentTaskProperty": {
          "type": "string",
          "default": "Parent task",
          "description": "Self-referential Relation property linking a ticket to its Epic container page. Distinct from dependsOnProperty. Absence-tolerant — without it, Epic grouping degrades to Epic-select tagging only and no epic pages are created or matched."
        }
```

- [ ] **Step 2: Document the read-only status entries in the schema**

Replace the `statusMap` `description` (line 57) with:

```json
          "description": "Maps logical statuses to Notion option names. The plugin WRITES inProgress and implemented. It only READS done and cancelled — these exist so the epic-close check knows which of your Status options mean resolved, and no plugin command ever transitions a ticket into them. Defaults: inProgress→In Progress, implemented→Implemented, done→Done, cancelled→Cancelled."
```

- [ ] **Step 3: Add the five operations to the operations table**

In `plugins/notion-dev/skills/ticket-system/SKILL.md`, in the `## Logical operations` table, insert these rows after the `setDependencies` row (line 24):

```markdown
| `createEpic` | `{ name, overview, type?, assignee? }` | `{ id, url, pageId }` — creates an Epic container page. No-op returning `null` when the DB lacks `epicProperty` or `parentTaskProperty` |
| `findEpics` | — | `[{ id, pageId, name, title, url, overview }]` — pages with `epicProperty` set and `parentTaskProperty` empty. `[]` when either property is absent |
| `setParent` | `id`, `epicId` | `void` — writes the `parentTaskProperty` relation. No-op when the property is absent |
| `listEpicChildren` | `epicId` | `[{ id, key, title, status, url }]` — pages whose `parentTaskProperty` points at `epicId`, ordered by `id`. `[]` when the property is absent |
| `refreshEpicTasks` | `epicId` | `void` — re-renders the epic's `## Tasks` section from its live children. The single owner of that section's format |
| `appendToSection` | `id`, `sectionName`, `content` | `void` — **appends** to a named body section, creating it if absent. Never replaces, unlike `upsertSection` |
```

Also update the `createTicket` row (line 19) to add `parent`:

```markdown
| `createTicket` | `{ title, body, type?, epic?, parent?, phase?, step?, assignee? }` | `{ id, url }` — `epic`/`parent`/`phase`/`step` are optional mission metadata; `assignee` is a resolved Notion user id. Each is absence-tolerant when the corresponding configured property is missing from the live DB |
```

- [ ] **Step 4: Add the config bullet and the resolved-set definition**

In `## Configuration`, after the `creationDateProperty` bullet added in Task 1, add:

```markdown
- `parentTaskProperty` — self-referential Relation linking a ticket to its Epic container page (default `"Parent task"`). Distinct from `dependsOnProperty`: `Depends on` expresses blocking order between siblings, `Parent task` expresses containment. Absence-tolerant.
```

Then replace the `statusMap` defaults block (lines 57-63) with:

````markdown
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

Used by exactly one thing: the epic-close check in `/notion-dev:ticket` Phase 8 and `/notion-dev:finalize` Phase 3, and for ticking the checkboxes in an epic's `## Tasks` section.

A missing `done` or `cancelled` key falls back to its default option name. If that option does not exist on the live DB it simply never matches — a status the plugin has not been told about is not resolved, so the epic does not auto-close. Wrong in the safe direction.
````

- [ ] **Step 5: Add the Parent task property-handling rule**

In `## Property type handling`, after the `**Creation Date**` bullet added in Task 1, add:

```markdown
- **Parent task** (Relation, self-referential) — write as a **single-element** list of page IDs; a ticket has exactly one parent. Relation writes in Notion are replacement, not append, so writing one element is correct and no read-merge is needed (unlike `Depends on`). Reject a self-reference (`id == epicId`) with a clear error. When the configured property is absent from the live DB, skip the write and log **one** warning per run (`"parentTaskProperty '<name>' not found on DB; skipping parent write"`) — never abort.
```

- [ ] **Step 6: Add `parent` to `createTicket`**

In `## createTicket(...)` step 2, in the `**Mission metadata**` bullet's sub-list, after the `epic` sub-bullet (line 217), add:

```markdown
     - If `parent` is provided AND `parentTaskProperty` exists on the live DB, set that Relation to a single-element list containing the epic page's id. Applied **after** the page is created and retitled, since it needs the new page's id. `epic` and `parent` are independent: the Epic select makes the grouping visible in DB views and filters, the Parent task relation makes it a container. Callers normally set both.
```

- [ ] **Step 7: Add the epic-page palette entries**

In `### Palette per section`, add three rows to the table after the `Merged` row (line 115):

```markdown
| `Overview` | `createEpic` | `gray` | — | — |
| `Tasks` | epic refresh (`/notion-dev:ticket` Phase 8, `/notion-dev:finalize` Phase 3) | `blue` | — | — |
| `Resolution Log` | epic update (same) | `purple` | — | — |
```

Then, immediately after the "Unknown section names…" paragraph (line 117), add:

```markdown
The last three sections appear on **epic pages only**. None takes an intro callout — they are self-explanatory, and a callout on every one would be noise. `Tasks` renders as to-do blocks (same convention as `Acceptance Criteria`). The zone-divider rule below applies to `Implementation` / `Merged` on ticket pages only; epic pages use the per-entry divider described under `appendToSection`.
```

- [ ] **Step 8: Write the five operation sections**

Append to the end of `plugins/notion-dev/skills/ticket-system/SKILL.md`, immediately before the final `## MCP unavailability` section:

````markdown
## Epic containers

An **epic** is a page in this same database where `parentTaskProperty` is empty, `epicProperty` (Select) is set, and one or more other pages point at it via `parentTaskProperty`. Children carry the same `epicProperty` value as the epic page. Epics are identified structurally, not by a dedicated property.

A page with an Epic select and an empty parent but **no** children is an *epic-in-waiting* — `findEpics` still returns it so a first child can attach.

Both properties are required for epic containers. When either is absent from the live DB, every operation below degrades to a no-op with one warning, and the plugin falls back to plain Epic-select tagging.

## createEpic({ name, overview, type?, assignee? })

1. If `epicProperty` or `parentTaskProperty` is absent from the live DB, warn once and return `null` — the caller degrades to Epic-select tagging.
2. Compose the body as two sections:
   - `## Overview` — the `overview` argument: a short statement of the initiative or incident.
   - `## Tasks` — empty at creation; the epic-refresh step populates it later.
3. Call `createTicket({ title: name, body, type, assignee, epic: name })`. Reusing the normal creation path means the epic gets an ID, the title prefix, `Creation Date`, `staticProperties`, and the assignee for free. Status is `"Backlog"` like any new ticket.
4. `parentTaskProperty` is left empty — an epic has no parent. `phase`, `step`, and `dependsOn` are never set on an epic.
5. `type` defaults to the dominant child type when the caller knows the children, else `feature`.
6. Return `{ id, url, pageId }`.

## findEpics()

Read-only.

1. If `epicProperty` or `parentTaskProperty` is absent from the live DB, warn once and return `[]`.
2. Query the database (or `dataSourceId` when configured) with `mcp__notion__notion-query-data-sources` for pages where `epicProperty` is not empty **and** `parentTaskProperty` is empty.
3. For each hit return `{ id, pageId, name, title, url, overview }` — `name` is the `epicProperty` Select value, `title` is the page title with the ID prefix stripped, `overview` is the text of its `## Overview` section (empty string when absent).

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
````

- [ ] **Step 9: Verify the schema parses and every operation is defined**

```bash
cd /home/forhas/dev/pure-dev
python3 -c "import json; d=json.load(open('plugins/notion-dev/schema/notion-dev.config.schema.json')); print('parentTaskProperty default:', d['properties']['ticketSystem']['properties']['parentTaskProperty']['default'])"
for op in createEpic findEpics setParent listEpicChildren refreshEpicTasks appendToSection; do
  printf '%s: table=%s section=%s\n' "$op" \
    "$(grep -c "^| \`$op\`" plugins/notion-dev/skills/ticket-system/SKILL.md)" \
    "$(grep -c "^## $op" plugins/notion-dev/skills/ticket-system/SKILL.md)"
done
```

Expected: the first prints `parentTaskProperty default: Parent task`. The loop prints `table=1 section=1` for all five — every operation is both listed in the contract table and given a full section. Any `table=0` or `section=0` is a missing edit.

- [ ] **Step 10: Commit**

```bash
git add plugins/notion-dev/schema/notion-dev.config.schema.json plugins/notion-dev/skills/ticket-system/SKILL.md
git commit -m "feat(notion-dev): add Epic container operations to the ticket-system adapter"
```

---

### Task 4: `/notion-dev:init` — detect and create the new properties

**Files:**
- Modify: `plugins/notion-dev/commands/init.md:78-93` (3a-i schema table), `:101-114` (3a-ii detection), `:298-306` (report), `:319-334` (drift check)

**Interfaces:**
- Consumes: Task 1's `creationDateProperty`, Task 3's `parentTaskProperty` and `statusMap.done`/`.cancelled`.
- Produces: configs that carry the new keys. No later task consumes init's output directly.

- [ ] **Step 1: Add the two properties to the create-new schema table**

In `plugins/notion-dev/commands/init.md`, in the 3a-i property table, add two rows after the `Depends on` row (line 89):

```markdown
  | `Creation Date` | Date | set by `createTicket` at ticket creation |
  | `Parent task` | Relation (self-referential) | links a ticket to its Epic container page; distinct from `Depends on` |
```

Then extend the paragraph that follows the table (line 93, beginning "The last four are the structural-mission properties") by appending:

```markdown
`Parent task` carries the same creation caveat as `Depends on`: if the create API cannot declare a self-referential relation before the database's own ID exists, add it immediately afterward via `mcp__notion__notion-update-data-source` pointing at the new database. `Creation Date` is a plain Date property — the plugin writes the timestamp itself rather than using a `Created time` property, so the value stays editable and backfillable.
```

- [ ] **Step 2: Add detection for both properties in 3a-ii**

In the `**Detect structural-mission properties**` bullet list (lines 110-113), after the `dependsOnProperty` sub-bullet, add:

```markdown
  - `parentTaskProperty` (default `"Parent task"`) — scan for a self-referential `relation` **other than** the one bound to `dependsOnProperty`. Prefer the name `"Parent task"` (case-insensitive), then `"Parent item"`, then `"Parent"`. If none is found, ask `AskUserQuestion`: **Create `Parent task` (Relation)** / **Bind to `<found>`** (only when a candidate exists) / **Skip**. The Create option's prompt must state the limitation plainly: *"The API creates a plain self-referential relation, not Notion's native Sub-items feature — grouping and every plugin feature work identically, but rows render as a normal relation column rather than nested sub-rows. To get the native rendering, enable Sub-items in the Notion UI first and re-run init to bind to it."* On **Skip**, epic containers are unavailable and Epic grouping degrades to Select-tagging only.
```

Then, immediately after that bullet list and before the `**Detect extra Select/Status/Multi-Select properties**` bullet (line 114), add:

```markdown
- **Detect the Creation Date property** — prefer a property named `"Creation Date"` (case-insensitive) of type `date` or `created_time`. If missing under that name, scan for a single `created_time` property and offer it. If still unresolved, ask `AskUserQuestion`: **Add `Creation Date` (Date)** / **Bind to `<found>`** (only when a candidate exists) / **Skip** (creation-date writes are skipped at runtime with a warning). Record `creationDateProperty` only when the resolved live name differs from the default.
```

- [ ] **Step 3: Add the resolved-status prompt**

In 3a-ii, immediately after the `**Type options**` bullet (line 108) and before the `**Detect structural-mission properties**` bullet, add:

```markdown
- **Resolved statuses** — ask `AskUserQuestion` (multi-select) over the resolved Status property's live option list: *"Which of these mean a ticket is resolved?"* Pre-check any option matching `Implemented` / `Done` / `Cancelled` case-insensitively. Write the picks to `statusMap.done` and `statusMap.cancelled`, following the omit-when-default convention — when the picks are exactly the defaults, write nothing. This set is read-only to the plugin: it decides when an Epic auto-closes, and no command ever transitions a ticket into these statuses. Skip this question on the **create-new** path (3a-i), where the Status options are the plugin's own three and the defaults already apply.
```

- [ ] **Step 4: Add both slots to the drift check**

In `#### Notion drift items` step 2's bullet list, after the `**Assignee slot**` bullet (line 327), add:

```markdown
   - **Creation Date slot** (`creationDateProperty`): if config has the key, it should exist and be `date` or `created_time`; **informational only**, not a hard drift (mirrors the PR and Assignee slots). Skip the check when the key is absent from config.
   - **Parent task slot** (`parentTaskProperty`): if config has the key, it should exist and be a self-referential `relation`; **informational only**. Skip the check when the key is absent from config.
```

- [ ] **Step 5: Report which optional slots resolved**

In `### 11. Report`, after the `- Code reviewer: <codex|copilot>.` line (line 304), add:

```markdown
- Optional slots resolved: `Creation Date`, `Parent task` — and whether **Epic containers are available** (both `epicProperty` and `parentTaskProperty` present). When either is missing, say so plainly: "Epic containers unavailable — Epic grouping will use the Select tag only."
```

- [ ] **Step 6: Verify init covers all three new config surfaces**

```bash
cd /home/forhas/dev/pure-dev
for k in creationDateProperty parentTaskProperty; do
  printf '%s: init=%s schema=%s\n' "$k" \
    "$(grep -c "$k" plugins/notion-dev/commands/init.md)" \
    "$(python3 -c "import json;print(int('$k' in json.load(open('plugins/notion-dev/schema/notion-dev.config.schema.json'))['properties']['ticketSystem']['properties']))")"
done
grep -c 'statusMap.done' plugins/notion-dev/commands/init.md
```

Expected: both keys show `init` ≥ 2 (detection bullet + drift bullet) and `schema=1`. The last command prints `1` (the resolved-status prompt). A `schema=0` means Task 1 or 3 was skipped; an `init=0` means this task's edit is missing.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/commands/init.md
git commit -m "feat(notion-dev): detect and create Creation Date and Parent task in init"
```

---

### Task 5: `/notion-dev:create-task` — attach tickets to epics

**Files:**
- Modify: `plugins/notion-dev/commands/create-task.md:66-77` (Phase 2.5.2), `:95` (new Phase 2.6), `:141-186` (Phase 3.2), `:190-220` (Phase 4 report)

**Interfaces:**
- Consumes: Task 3's `findEpics`, `createEpic`, `createTicket({parent})`, `listEpicChildren`, `upsertSection`.
- Produces: `EPIC_ID` and the epic name on both the mission and single-ticket paths; the `## Tasks` render format reused verbatim by Task 8.

- [ ] **Step 1: Resolve the Epic page in the mission path**

In `plugins/notion-dev/commands/create-task.md`, at the end of `### 2.5.2 Reconcile the proposed Epic` (after line 77), add:

````markdown
Once the Epic **select value** is reconciled, resolve the Epic **page** — the container the tasks will hang from:

1. Invoke `notion-dev:ticket-system` operation `findEpics()`.
2. A returned epic whose `name` matches the reconciled Epic value (case-insensitive) → reuse it. Record its id as `EPIC_ID`.
3. No match → invoke `createEpic({ name: <reconciled Epic value>, overview: <2-4 sentence distillation of the mission's goal from the source body>, type: <the dominant task type across the mission>, assignee: <resolved in Phase 2.75> })`. Record `EPIC_ID`.
4. `findEpics()` returned `[]` (the DB lacks `epicProperty` or `parentTaskProperty`) → `EPIC_ID = undefined`. Continue with Epic-select tagging only; do not prompt.

`EPIC_ID` is `undefined` on the "Collapse to single ticket" branch — a collapsed mission is a single ticket and goes through Phase 2.6 like any other.
````

- [ ] **Step 2: Add Phase 2.6 for the single-ticket path**

Insert a new phase between Phase 2.5's closing `---` (line 95) and `## Phase 2.75 — Resolve assignee` (line 97):

````markdown
## Phase 2.6 — Attach to an epic (single-ticket path only)

Runs only when Phase 2.5 returned `kind: "single"`. Skipped entirely for missions (2.5.2 already resolved the epic) and for the `existing-ticket` source mode, which never re-parents a ticket — the same rule that makes it skip Phase 2.5.

1. Invoke `notion-dev:ticket-system` operation `findEpics()`. Empty → **skip silently, no prompt**.
2. Judge the ticket's title and `## Requirements` against each epic's `name` and `## Overview`. This is a semantic judgment, not string matching: an epic is a plausible candidate when this ticket is work on the same incident, feature, or investigation. A shared word is not a match.
3. **Zero plausible candidates → skip silently.** No prompt. This is the common case, and routine single-ticket runs must stay as quiet as they are today.
4. **One or more plausible candidates** → ask `AskUserQuestion`: *"This looks related to an existing epic. Attach it?"*
   - **Attach to `[<KEY>-<n>] <name>`** — the best candidate first, further candidates as additional options. Record `EPIC_ID` and the epic name.
   - **Pick another** — show the full `findEpics()` list as sub-choices.
   - **No epic** — proceed unattached; `EPIC_ID = undefined`.

**Non-interactive mode** never prompts here: use `--epic` / `--parent` when supplied, else attach to nothing.
````

- [ ] **Step 3: Pass `epic` and `parent` on the single-ticket create**

In `#### Single-ticket path`, replace the second bullet (line 147) with:

```markdown
- Otherwise, operation is `createTicket({ title, body, type, assignee, epic, parent })` — new ticket. Omit `assignee` when Phase 2.75 chose "Leave unassigned"; omit `epic` and `parent` when Phase 2.6 attached to no epic (`epic` = the epic name, `parent` = `EPIC_ID`). `existing-ticket` `updateTicket` never sets an assignee or a parent — both are creation-only.
```

- [ ] **Step 4: Pass `parent` in the mission path and add Pass 1.5**

In `#### Mission path (two-pass)`, in the Pass 1 pseudocode, add a `parent` line after `epic:` (line 164):

```
    parent:   EPIC_ID,          // epic page from 2.5.2; omitted when undefined
```

Then insert a new pass between Pass 1 and Pass 2 (after line 170):

````markdown
**Pass 1.5 — populate the epic's task list** (skip when `EPIC_ID` is undefined):

Invoke `notion-dev:ticket-system` operation `refreshEpicTasks(EPIC_ID)`. That operation owns the `## Tasks` render format entirely — do **not** render the list here, or this command and the epic-update flow will drift apart.

This runs even though nothing has resolved yet, so the epic reads as a real plan the moment it exists. A failure here is non-fatal — warn and continue to Pass 2.
````

- [ ] **Step 5: Name the epic in both report shapes**

In `### Single-ticket result`, after the "New (or updated) ticket ID and URL." bullet (line 195), add:

```markdown
- The epic it was attached to, when Phase 2.6 attached one: `Epic: [<KEY>-<n>] <name> · <url>`. Omit the line entirely when unattached.
```

In `### Mission result`, replace the first line of the code block (line 204, `Mission created under Epic: <epic name>`) with:

```
Mission created under Epic: [<KEY>-<n>] <epic name> · <epic url>
```

- [ ] **Step 6: Verify every operation create-task names exists in the adapter**

```bash
cd /home/forhas/dev/pure-dev
for op in findEpics createEpic listEpicChildren upsertSection createTicket; do
  printf '%s: used=%s defined=%s\n' "$op" \
    "$(grep -c "$op" plugins/notion-dev/commands/create-task.md)" \
    "$(grep -c "^## $op" plugins/notion-dev/skills/ticket-system/SKILL.md)"
done
grep -n 'Phase 2.6' plugins/notion-dev/commands/create-task.md | head -3
```

Expected: every operation shows `used` ≥ 1 and `defined=1` — anything create-task calls must have a section in the adapter. `Phase 2.6` prints at least the heading line plus its reference in the phase flow.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/commands/create-task.md
git commit -m "feat(notion-dev): attach new tickets to Epic containers in create-task"
```

---

### Task 6: `/notion-dev:create-task` — non-interactive mode

Needed by Task 8's follow-up filing. Kept separate from Task 5 because a reviewer could reasonably accept epic attachment while rejecting the proxy-respondent design.

**Files:**
- Modify: `plugins/notion-dev/commands/create-task.md:1-20` (frontmatter + arg parsing), `:32-52` (Phase 2), `:56-93` (Phase 2.5), `:97-121` (Phase 2.75), `:127-139` (Phase 3.1)

**Interfaces:**
- Consumes: Task 5's Phase 2.6 and `EPIC_ID`.
- Produces: the invocation contract Task 8 depends on —
  `/notion-dev:create-task --non-interactive --context-file=<path> --epic="<name>" --parent=<id> --assignee=<id> prompt:<text>`

- [ ] **Step 1: Document the flags**

In `plugins/notion-dev/commands/create-task.md`, update the frontmatter `argument-hint` (line 3) to:

```yaml
argument-hint: "[--non-interactive] [--context-file=<path>] [--epic=<name>] [--parent=<id>] [--assignee=<id>] [prompt:|existing-ticket:|notion-page:]<text-or-ref>"
```

Then, immediately after the **Parsing rule** paragraph (line 15) and before `## Preconditions`, add:

````markdown
**Flags.** Five optional flags are parsed off the front of the argument string **before** the source-selector parsing rule runs, so they never interfere with free-prompt text:

| Flag | Effect |
|---|---|
| `--non-interactive` | Never pause for user input; see the phase table below. |
| `--context-file=<path>` | Path to a markdown context packet. Seeds the interviewer, and is the proxy respondent's evidence base. Valid with or without `--non-interactive`. |
| `--epic=<name>` | Skip Phase 2.6's matching; use this Epic select value verbatim. |
| `--parent=<id>` | Epic page ticket id for the `parentTaskProperty` relation. Normally passed with `--epic`. |
| `--assignee=<id>` | Skip Phase 2.75's resolution; use this Notion user id. |

`--epic`, `--parent`, and `--assignee` are what let `/notion-dev:finalize` file a review follow-up as a sibling under the resolving ticket's epic with no prompting.

**`--non-interactive` phase behavior:**

| Phase | Interactive | Non-interactive |
|---|---|---|
| 2.1 interview | Questions go to the user | Questions go to a **proxy-respondent subagent** (below) |
| 2.2 confirm | `create` / `revise` / `cancel` | Auto-`create` |
| 2.5 breakdown | May return a mission | Auto-collapse to `single` |
| 2.6 epic attach | Prompt on candidates | Use `--epic` / `--parent`, or attach to none |
| 2.75 assignee | Prompt when unresolved | Use `--assignee`, else `defaultAssignee`, else leave unassigned |
| 3.1 type | Prompt when unclear | Infer from the body; default `improvement` |

**Proxy-respondent subagent.** The interviewer still runs in full — depth calibration, clarity audit, all of it — but its questions are answered by a **fresh subagent**, not by the main loop.

This is deliberate. When `/notion-dev:finalize` files a deferred review item, the main loop is the agent that *wrote* that item during review. Having it answer its own interview restates its own assumptions and produces a ticket that looks elaborated but carries no new information. A fresh agent, handed the ticket, the merge diff, and the review thread, has to actually read them.

Dispatch the subagent with the context packet and this instruction: *answer the interviewer's questions as the requester would, grounding every answer in the packet; when the packet does not support an answer, reply "unknown — needs human input" rather than inventing detail.* Answers of that form flow into the ticket's `## Open Questions`, so the gap stays visible instead of becoming a confident-sounding fabrication.
````

- [ ] **Step 2: Route the interview and confirm gate**

In `### 2.1 Run the interview`, after the "No `confidence`-branching lives in this command" line (line 44), add:

```markdown
In **non-interactive mode**, the interviewer's questions go to the proxy-respondent subagent described above instead of to the user. Everything else about the interview is unchanged.
```

In `### 2.2 Confirm`, after the `- `create` — proceed to Phase 2.5.` line (line 51), add:

```markdown

In **non-interactive mode**, skip this gate: proceed as if the user chose `create`, and log the auto-decision for the Phase 4 report.
```

- [ ] **Step 3: Auto-collapse the breakdown**

In `## Phase 2.5 — Breakdown assessment`, after the sentence ending "elaborating an existing ticket never splits it." (line 57), add:

```markdown

In **non-interactive mode**, instruct `notion-dev:task-breakdown` to return `single` and skip 2.5.2 and 2.5.3 entirely. This mode exists to file one deferred review finding, which is one item by construction; running the breakdown and then discarding a mission result would be wasted work.
```

- [ ] **Step 4: Honor `--assignee`**

In `## Phase 2.75 — Resolve assignee`, insert a new step before the current step 1 (line 103), renumbering the existing steps 1-3 to 2-4:

```markdown
1. **`--assignee` supplied** → `assignee = <that id>`; skip the rest of this phase. In non-interactive mode without the flag, fall through to `defaultAssignee` resolution below, and if that fails, `assignee = unassigned` — never prompt.
```

- [ ] **Step 5: Default the type**

In `### 3.1 Classify the type`, after "If still unclear, ask `AskUserQuestion` with the four options." (line 135), add:

```markdown

In **non-interactive mode**, never ask: infer from the body, and when genuinely unclear default to `improvement` — the least-committal of the four, and the easiest to correct later.
```

- [ ] **Step 6: Verify the flags are consistently documented**

```bash
cd /home/forhas/dev/pure-dev
for f in non-interactive context-file epic parent assignee; do
  printf -- '--%s: %s\n' "$f" "$(grep -c -- "--$f" plugins/notion-dev/commands/create-task.md)"
done
grep -c 'proxy-respondent' plugins/notion-dev/commands/create-task.md
grep -c 'argument-hint.*non-interactive' plugins/notion-dev/commands/create-task.md
```

Expected: every flag ≥ 2 (the flag table plus at least one phase that honors it). `proxy-respondent` ≥ 2 (definition plus the 2.1 reference). The last prints `1` — the frontmatter hint must advertise the flags or callers will not discover them.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/commands/create-task.md
git commit -m "feat(notion-dev): add non-interactive mode with a proxy respondent to create-task"
```

---

### Task 7: Epic guard in `/notion-dev:ticket`

Small and independent — refuses to build a worktree against an epic container.

**Files:**
- Modify: `plugins/notion-dev/commands/ticket.md:36-46` (Phase 1.1)

**Interfaces:**
- Consumes: Task 3's `listEpicChildren`; `fetchTicket`'s existing return.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Add the guard**

In `plugins/notion-dev/commands/ticket.md`, in `### 1.1 Fetch the ticket`, immediately after the "Record `TICKET_TYPE`…" paragraph (line 42) and before the "Record `RUN_START`" paragraph, insert:

````markdown
**Epic guard.** The fetched page is an epic container when its `parentTaskProperty` is empty **and** its `epicProperty` is set **and** `listEpicChildren(id)` returns at least one child. In that case abort — an epic is a container, not implementable work:

```
[<KEY>-<n>] <name> is an epic container, not an implementable ticket.
Pick one of its children:
  [<KEY>-67] Fix stale index — Implemented
  [<KEY>-68] Add cache metrics — In Progress
```

Hard abort in both interactive and non-interactive mode. It runs before Phase 2, so no worktree, branch, status change, or ledger line is created.

An **epic-in-waiting** — Epic select set, empty parent, but no children yet — is deliberately **not** guarded: it is indistinguishable from a normal ticket that happens to carry an Epic tag, and blocking it would break the plain Epic-select tagging that works today. Skip the guard entirely when the DB lacks `parentTaskProperty` or `epicProperty`.
````

- [ ] **Step 2: Verify the guard sits before any side effect**

```bash
cd /home/forhas/dev/pure-dev
grep -n 'Epic guard\|updateStatus(id, "inProgress")\|git worktree add' plugins/notion-dev/commands/ticket.md | head -5
```

Expected: the `Epic guard` line number is **smaller** than both the `git worktree add` and `updateStatus(id, "inProgress")` line numbers. If it is not, the guard would fire after the run had already mutated state.

- [ ] **Step 3: Commit**

```bash
git add plugins/notion-dev/commands/ticket.md
git commit -m "feat(notion-dev): refuse to implement an Epic container in ticket"
```

---

### Task 8: Epic update on ticket resolution — shared skill

The §6 procedure lives in **one** new skill that both commands invoke, mirroring how `notion-dev:review-and-merge` is already shared by `ticket.md` Phase 7 and `finalize.md` Phase 2. No duplicated prose, so no drift check is needed.

**Files:**
- Create: `plugins/notion-dev/skills/epic-update/SKILL.md`
- Modify: `plugins/notion-dev/commands/ticket.md:294-301` (Phase 8, between 8.2 and 8.3), `:335` (Phase 10 report)
- Modify: `plugins/notion-dev/commands/finalize.md:83-88` (Phase 3.2), `:121` (Phase 5 report)

**Interfaces:**
- Consumes: Task 3's `listEpicChildren` / `refreshEpicTasks` / `appendToSection` / `updateStatus` and the resolved set; Task 6's non-interactive invocation contract.
- Produces: skill `notion-dev:epic-update`, invoked as
  `Skill(notion-dev:epic-update)` with args `<ticket-id>` plus `--non-interactive` when set, and `REVIEW_REPORT` passed as context. Returns an `EPIC-UPDATE:` output block the callers put in their reports.

- [ ] **Step 1: Create the shared skill**

Create `plugins/notion-dev/skills/epic-update/SKILL.md`. Match the frontmatter style of the sibling skills (see `plugins/notion-dev/skills/review-and-merge/SKILL.md` for the house pattern):

````markdown
---
name: epic-update
description: Use after a ticket reaches Implemented, from /notion-dev:ticket Phase 8 or /notion-dev:finalize Phase 3, to record the resolution on the ticket's Epic container — file deferred follow-ups, refresh the Epic's task list, append a dated log entry, and close the Epic when everything under it is resolved.
---

# epic-update

Records a resolved ticket against its Epic container. Invoked by `/notion-dev:ticket` (Phase 8) and `/notion-dev:finalize` (Phase 3) — the two entry points that take a ticket to `Implemented`.

**Args:** `<ticket-id>` (the numeric or logical key of the just-resolved ticket), plus `--non-interactive` when the caller is in that mode.

**Caller-supplied context:** `REVIEW_REPORT` (the review loop's final report, source of the deferred follow-ups) and `REPO_ROOT` (the primary checkout — the caller recorded it before any `cd` into a worktree).

**Every step here is best-effort**: a failure logs a warning and continues to the next step. This skill never fails its caller's run — the merge has already landed by the time it is invoked, and epic bookkeeping is not worth losing that.

**1. Resolve the epic.** `fetchTicket(<ticket-id>)` and read its `parentTaskProperty`. Empty, or the property absent from the live DB → **skip steps 2-5 entirely** and return `EPIC-UPDATE: none`. Not an error; most tickets have no epic. Otherwise `EPIC_ID` is the referenced page — fetch it for its title and Epic name.

**2. File deferred follow-ups.** Source: `REVIEW_REPORT`'s deferred follow-ups — the same list written to the ticket's `## Merged` section.

- **Interactive**: for each item, `AskUserQuestion` — **File as ticket** / **Skip**. Default File.
- **Non-interactive**: file every item. Nothing is left deferred.

For each item to file, write a context packet to `$REPO_ROOT/.claude/notion-dev/followup-<KEY>-<id>-<n>.md` (`<n>` = 1-based index; the same self-ignored directory the ledger lives in, so it never appears in `git status` or contaminates a branch) containing: the resolved ticket's title, body, and URL; the PR URL and `git show --stat <merge-commit>`; the review finding verbatim; and the rationale recorded when it was deferred. Leave the packet in place after the run as a record of what the ticket was generated from.

Then run:

```
/notion-dev:create-task --non-interactive --context-file=<packet> --epic="<epic name>" --parent=<EPIC_ID> --assignee=<this ticket's assignee> prompt:<finding title>
```

Record `FILED` = `[{ id, title, url }]` for each created ticket, and `UNFILED` = the items the user chose to skip. A create-task failure is **non-fatal**: log it, add the item to `UNFILED`, continue. When `REVIEW_REPORT` has no deferred follow-ups both lists are empty and this step is a no-op.

**3. Refresh the epic's `## Tasks`.** Invoke `notion-dev:ticket-system` operation `refreshEpicTasks(EPIC_ID)`, then `listEpicChildren(EPIC_ID)` to hold the child list for steps 4 and 5. Do **not** render the task list here — `refreshEpicTasks` owns that format, and duplicating it is how this section drifts from the one `/notion-dev:create-task` writes.

The mirror is refreshed only on resolution, so between resolutions it lags reality; the live view is Notion's Parent task relation column, and the section exists so the epic reads as a coherent document.

**4. Append the log entry.** Invoke `appendToSection(EPIC_ID, "Resolution Log", <entry>)`. The entry is a `divider` block followed by:

```
### [<KEY>-<id>] resolved — <YYYY-MM-DD HH:MM UTC>
**Summary** — <2-4 sentences: what was actually done, distilled from the ticket's ## Implementation section and the merge>
**Follow-ups filed** — [<KEY>-69] Backfill historic wallets · <url>    (omit the line when FILED is empty)
**Follow-ups deferred** — <item>                                       (omit the line when UNFILED is empty)
**Epic status** — 2 of 3 tasks resolved
**Next** — <the remaining blocker, or "epic complete">
```

`## Resolution Log` is created on first use by `appendToSection`. Timestamp from `date -u +"%Y-%m-%d %H:%M UTC"`. `Epic status` counts against step 3's child list using the resolved set; when step 5 closes the epic it reads `all N tasks resolved — epic closed`.

**5. Close the epic.** Evaluate against the child list step 3 already fetched — read *after* step 2 filed its follow-ups, so new tickets are in it. Do not re-query.

Close only when **all** of:
1. Every child other than the just-resolved one has a status in the resolved set.
2. `FILED` is empty. Strictly redundant with (1) — a freshly filed follow-up is an unresolved child, so (1) already fails — but stated so the intent survives any future change to when the child list is read.
3. `UNFILED` is empty — a known-but-unfiled follow-up means the work is not finished.

Then `updateStatus(EPIC_ID, "implemented")`, and say so in step 4's `Epic status` and `Next` lines. Otherwise leave the epic's status untouched. The plugin never moves an epic *out* of a resolved status, and never sets an epic to `In Progress`.

Step 2 must run before step 5, or a run that files a follow-up would close the epic that follow-up belongs to.

## Output block

Return exactly one block for the caller's report:

```
EPIC-UPDATE: none | updated | closed | degraded
EPIC: [<KEY>-<n>] <name> · <url>          (omit on `none`)
FILED: <KEY>-69, <KEY>-70                 (or `none`)
DEFERRED: <one-liner>, …                  (or `none`)
CHILDREN: <resolved>/<total> resolved
```

`degraded` means the DB lacks `epicProperty` or `parentTaskProperty`, so epic containers are unavailable — distinct from `none`, which means this ticket simply has no epic.
````

- [ ] **Step 2: Invoke the skill from `ticket.md` Phase 8**

In `plugins/notion-dev/commands/ticket.md`, insert a new section between `### 8.2 Update status` (which ends at line 296) and `### 8.3 Post-merge hooks`:

````markdown
### 8.2a Update the epic

Invoke the `notion-dev:epic-update` skill via the Skill tool with args `<id>`, plus `--non-interactive` when set. Pass `REVIEW_REPORT` (Phase 7) and `$REPO_ROOT` as context.

It owns the whole epic-side record: filing deferred follow-ups as tickets under the epic, refreshing the epic's `## Tasks`, appending the dated `## Resolution Log` entry, and closing the epic when every child is resolved. Record its `EPIC-UPDATE:` output block as `EPIC_REPORT` for Phase 10.

Best-effort by construction — the skill never fails this run. A ticket with no epic is a no-op returning `EPIC-UPDATE: none`.
````

- [ ] **Step 3: Reference it from Phase 10's report**

In `## Phase 10 — Report`, after the `- Ticket end state (`implemented`).` bullet (line 335), add:

```markdown
- Epic outcome, when the ticket had one: the epic's ID and URL, follow-ups filed (with their IDs) versus deferred, and whether the epic closed. Omit the line entirely when the ticket had no epic.
```

- [ ] **Step 4: Invoke the skill from `finalize.md` Phase 3**

In `plugins/notion-dev/commands/finalize.md`, `### 3.2 Update status and post-merge hooks` currently reads:

```markdown
`updateStatus(id, "implemented")` — marks the ticket as merged-and-code-complete. The plugin **never** transitions beyond this; release/deployment status is out of scope.

Then run `git.postMergeHooks` skills in order (empty default — no-op).
```

Replace it with three sections: keep the `updateStatus` sentence under the existing `### 3.2 Update status` heading, add `### 3.3 Update the epic`, then move the `postMergeHooks` sentence under `### 3.4 Post-merge hooks`. The new 3.3 reads:

```markdown
Invoke the `notion-dev:epic-update` skill via the Skill tool with args `<id>`, plus `--non-interactive` when set. Pass `REVIEW_REPORT` (Phase 2) and `$REPO_ROOT` as context.

It owns the whole epic-side record: filing deferred follow-ups as tickets under the epic, refreshing the epic's `## Tasks`, appending the dated `## Resolution Log` entry, and closing the epic when every child is resolved. Record its `EPIC-UPDATE:` output block as `EPIC_REPORT` for Phase 5.

Best-effort by construction — the skill never fails this run. A ticket with no epic is a no-op returning `EPIC-UPDATE: none`.
```

Same invocation as `ticket.md` 8.2a. The only difference is the phase the `REVIEW_REPORT` comes from — finalize's review loop is Phase 2, ticket's is Phase 7.

- [ ] **Step 5: Reference it from finalize's Phase 5 report**

In `## Phase 5 — Report`, after the `- Ticket end state (`implemented`).` bullet (line 121), add:

```markdown
- Epic outcome, when the ticket had one: the epic's ID and URL, follow-ups filed (with their IDs) versus deferred, and whether the epic closed. Omit the line entirely when the ticket had no epic.
```

- [ ] **Step 6: Verify the procedure exists once and both commands invoke it**

```bash
cd /home/forhas/dev/pure-dev
echo "--- procedure defined exactly once ---"
grep -rlc 'Resolution Log' plugins/notion-dev/skills/epic-update/SKILL.md plugins/notion-dev/commands/ticket.md plugins/notion-dev/commands/finalize.md 2>/dev/null
echo "--- both commands invoke the skill ---"
grep -c 'notion-dev:epic-update' plugins/notion-dev/commands/ticket.md plugins/notion-dev/commands/finalize.md
echo "--- frontmatter present ---"
head -4 plugins/notion-dev/skills/epic-update/SKILL.md
```

Expected: the first list names **only** `skills/epic-update/SKILL.md` — if either command file appears, the procedure was duplicated instead of invoked. The second prints `1` for each command. The third shows a `---` / `name: epic-update` / `description:` frontmatter block matching the sibling skills.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/skills/epic-update/SKILL.md plugins/notion-dev/commands/ticket.md plugins/notion-dev/commands/finalize.md
git commit -m "feat(notion-dev): add the epic-update skill and invoke it from ticket and finalize"
```

---

### Task 9: Epic naming guidance, README, and version bump

**Files:**
- Modify: `plugins/notion-dev/skills/task-breakdown/SKILL.md:76` (Epic bullet)
- Modify: `plugins/notion-dev/README.md`
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json:4`

**Interfaces:**
- Consumes: everything above.
- Produces: the shipped `0.8.0` manifest.

- [ ] **Step 1: Tell task-breakdown that epic names title a real page**

In `plugins/notion-dev/skills/task-breakdown/SKILL.md`, replace the `**Epic**` bullet under `### Structural tagging — thresholds within mission` (line 76) with:

```markdown
- **Epic** — always present on a mission result (a mission without a shared initiative wouldn't be a mission). Propose a name derived from the source title or theme. The caller reconciles it against existing DB options **and creates a real container page titled with it**, so the name must read as an initiative or incident a person would recognize months later — `"Large-Wallet Stale-Index Incident"`, not `"Misc fixes"` or `"Work from Tuesday"`. Prefer a noun phrase; avoid dates and ticket numbers, which the ID prefix already supplies.
```

- [ ] **Step 2a: Extend the `ticketSystem` config bullet**

In `plugins/notion-dev/README.md`, append to the end of the `ticketSystem` bullet (line 128, which currently ends "`/notion-dev:init` sets both."):

```markdown
Epic support adds `parentTaskProperty` (the self-referential Relation linking a ticket to its Epic container page, default `"Parent task"`) and `creationDateProperty` (default `"Creation Date"`, tolerating either a `Date` property the plugin writes at creation or a `Created time` property Notion auto-fills). Both are absence-tolerant: when missing from the live database the plugin skips the write with a warning rather than aborting.
```

- [ ] **Step 2b: Document the read-only status entries**

In the same bullet list, immediately after the `reviewer` bullet (line 134), insert:

```markdown
- `ticketSystem.statusMap.{done, cancelled}` — **read-only** entries (defaults `"Done"` / `"Cancelled"`). Together with `implemented` they form the *resolved set*: the statuses that count as finished when deciding whether an Epic's children are all done and the Epic should close. No plugin command ever moves a ticket into these states — they exist purely so the Epic-close check understands your board. `/notion-dev:init` asks which of your live Status options belong in the set.
```

- [ ] **Step 2c: Update the Ticket system property list**

Replace lines 155-157 of `plugins/notion-dev/README.md` with:

```markdown
- Required properties: `Name` (title), `ID` (number or unique-id), `Status` (select/status), `Type` (select), `PR` (URL).
- Optional: `Assignee` (People) — `/notion-dev:create-task` assigns new tickets to a configured default, or prompts you to pick a workspace user when no default is set.
- Optional: `Creation Date` (Date, or a `Created time` property) — set when a ticket is created.
- Optional: `Parent task` (self-referential Relation) — links a ticket to its Epic container. Required for Epics; without it, Epic grouping degrades to the `Epic` select tag alone.
- Status options: `Backlog`, `In Progress`, `Implemented`. (The plugin only ever sets `In Progress` and `Implemented`; add `Delivered` or other shipped states yourself if you run a release flow — the plugin doesn't manage them. It *reads* `Done` and `Cancelled` for the Epic-close check — see `statusMap` above.)
```

- [ ] **Step 2d: Add the Epics section**

Insert a new `## Epics` section between the end of `## Ticket system` (line 158) and `## Input sources` (line 160):

````markdown
## Epics

An **Epic** is a container page in the same ticket database: its `Parent task` is empty, its `Epic` select is set, and its children point back at it via `Parent task` while sharing the same `Epic` value.

- **Missions always get one.** When `/notion-dev:create-task` breaks a request into multiple tickets, it reuses a matching Epic page or creates one, and parents every task to it.
- **Single tickets are offered attachment only when an existing Epic plausibly matches** the work — an incident, feature, or investigation already underway. With no plausible match there is no prompt, so routine single-ticket runs stay quiet.
- **Follow-ups land in the same Epic.** When a review defers an item, `/notion-dev:ticket` and `/notion-dev:finalize` file it as a real ticket under the same Epic (always, in `--non-interactive` mode; on confirmation otherwise).
- **`/notion-dev:ticket` refuses to implement an Epic** and lists its children instead — a container is not implementable work.

An Epic page carries three sections:

| Section | Content |
|---|---|
| `## Overview` | What the initiative or incident is. Written once, at creation. |
| `## Tasks` | Each child with its status: `- [x] [STO-67] Fix stale index — Implemented`. **Refreshed only when a child resolves**, so between resolutions it lags — the live view is Notion's `Parent task` relation column. |
| `## Resolution Log` | Append-only history. Every time a child resolves, a divider and a dated entry are added with what was done, follow-ups filed, how many tasks remain, and what's next. |

When the last unresolved child resolves and no follow-ups are outstanding, the Epic's own status moves to `Implemented`.

**A note on Notion Sub-items.** `/notion-dev:init` can create the `Parent task` relation for you, but the Notion API cannot enable Notion's native *Sub-items* feature — so an API-created relation renders as an ordinary relation column rather than nested sub-rows. Grouping and every plugin behavior work identically either way. For the native nested rendering, enable Sub-items in the Notion UI **before** running `/notion-dev:init`, and init will bind to it instead of creating its own.
````

- [ ] **Step 2e: Note the title prefix and the create-task flags in the Commands table**

Replace the `/notion-dev:create-task` cell (line 117) with:

```markdown
| `/notion-dev:create-task` | Produce a well-formed ticket from a prompt, an existing ticket, or a Notion page. Runs a depth-calibrated interview (`notion-dev:ticket-interviewer`) when requirements need refinement, then decides via `notion-dev:task-breakdown` whether the result is one ticket or a multi-task mission (Epic / Phase / Step / Depends-on). Flags: `--non-interactive` (answers its own interview via a fresh subagent grounded in `--context-file`), `--context-file=<path>`, `--epic=<name>`, `--parent=<id>`, `--assignee=<id>`. |
```

Then add a line immediately after the Commands table (line 120):

```markdown
Ticket titles are prefixed with their ticket ID — `[STO-67] Large-Wallet Stale-Index Incident`. The prefix is applied and stripped automatically; you never type it, and branch names are unaffected.
```

- [ ] **Step 2f: List the new skill in the Layout section**

The `## Layout` section (line 179) enumerates the plugin's directories. Add `skills/epic-update/` to that listing in the same style as its siblings, described as: *records a resolved ticket against its Epic — files deferred follow-ups, refreshes the task list, appends the resolution log entry, closes the Epic when everything under it is done. Shared by `/notion-dev:ticket` and `/notion-dev:finalize`.*

- [ ] **Step 3: Bump the manifest**

In `plugins/notion-dev/.claude-plugin/plugin.json`, change `"version": "0.7.0"` to `"version": "0.8.0"`. Minor: four new user-facing capabilities, no breaking change to any existing config — every new key is optional with a default, and every new Notion property is absence-tolerant.

- [ ] **Step 4: Verify the manifest and run a whole-plan contract sweep**

```bash
cd /home/forhas/dev/pure-dev
python3 -c "import json; print('version:', json.load(open('plugins/notion-dev/.claude-plugin/plugin.json'))['version'])"
python3 -c "import json; json.load(open('plugins/notion-dev/schema/notion-dev.config.schema.json')); print('schema OK')"
echo '--- every adapter operation called by a command must be defined ---'
missing=0
for op in $(grep -ohE '\b(createEpic|findEpics|setParent|listEpicChildren|refreshEpicTasks|appendToSection|upsertSection|createTicket|updateTicket|updateStatus|fetchTicket|setPullRequest|setDependencies|getSelectOptions|addSelectOption|postComment|resolveAssignee)\b' plugins/notion-dev/commands/*.md plugins/notion-dev/skills/epic-update/SKILL.md | sort -u); do
  if [ "$(grep -c "^## $op" plugins/notion-dev/skills/ticket-system/SKILL.md)" -eq 0 ]; then
    echo "UNDEFINED: $op"; missing=1
  fi
done
[ "$missing" -eq 0 ] && echo 'sweep clean — every operation the commands call is defined'
echo '--- quick-dev must be untouched ---'
git diff --name-only main...HEAD -- plugins/quick-dev | wc -l
```

Expected: version `0.8.0`; `schema OK`; `sweep clean — every operation the commands call is defined`; and `0` files changed under `plugins/quick-dev`. Any `UNDEFINED:` line is a command calling an operation the adapter never defines — the single most likely defect in this whole plan. This sweep reports clean on `main` today, so a failure here is always something this work introduced.

- [ ] **Step 5: Commit**

```bash
git add plugins/notion-dev/skills/task-breakdown/SKILL.md plugins/notion-dev/README.md plugins/notion-dev/.claude-plugin/plugin.json
git commit -m "docs(notion-dev): document epics and bump to 0.8.0"
```

---

## Post-implementation

The spec's §11 live smoke run is a **manual** step for the user, not a task — it needs a scratch Notion DB and a real MCP connection:

1. `/notion-dev:init` against a DB missing both new properties → creates `Creation Date` and `Parent task`.
2. `/notion-dev:create-task` with a multi-task source → epic page created, children parented, `## Tasks` populated, every title prefixed.
3. `/notion-dev:ticket <epic-id>` → refused with the child list.
4. `/notion-dev:ticket <child-id>` through to merge → log entry appended, `## Tasks` refreshed.
5. Resolve the last child with no follow-ups → epic closes.
