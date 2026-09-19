# ticket-system — read operations

Read before the first read. `fetchTicket`, `findEpics`, `getEpicContext`,
`listEpicChildren`. Referenced from `../SKILL.md`.

## Calling `mcp__notion__notion-query-data-sources`

**Every data-source query in this skill uses this one call shape. Use it verbatim.** That is the
operations below *and* the two in `create-ops.md` — `createTicket`'s max-plus-one next-id lookup on
a Number-typed `idProperty`, and `setDependencies` resolving a title reference — neither of which
goes through `fetchTicket`, so neither inherits this contract by being downstream of it. A caller
on the create path reads this section before its first query. Measured on a client
run (BTC-Gateway, notion-dev 0.29.0): 5 of the 13 data-source calls in one ticket were the run
rediscovering this contract, and two of the five failed in ways that do not look like failures.

```
mcp__notion__notion-query-data-sources({
  "data": {
    "data_source_urls": ["collection://<dataSourceId>"],
    "query": "SELECT \"userDefined:<idProperty>\" AS id, \"<live title property>\" AS title, \"<statusProperty>\" AS status FROM \"collection://<dataSourceId>\" WHERE \"userDefined:<idProperty>\" = 142"
  }
})
```

Four things about it, each of which cost that run a round trip:

- **The arguments are wrapped in `data`, and the table name is the quoted collection URL.** Three
  other shapes are rejected with the same unhelpful `Input validation error: Invalid arguments for
  tool notion-query-data-sources: data: Invalid input`, which names no field: a top-level
  `data_source_url` + `query_type` + `sql_query`; a `data_sources` JSON *string*; and a
  `data: { mode, data_source_url, filter }` structured-filter form. None of them is this tool.
- **Never use `params` with `?` placeholders. Inline the literal value instead.** This is the one
  that does not announce itself: `WHERE "ID" = ?` with `params: [142]` returns
  `{"results":[],"has_more":false}` — **HTTP 200, no error, and an empty result set that is
  indistinguishable from a ticket that does not exist.** A run that reads it as "no such ticket"
  goes on to the wrong branch with nothing to say it guessed. Later in the same run the same
  `params` form drew a `400 validation_error` instead, so the failure mode is not even stable.
- **Column names come from `.claude/notion-dev.config.json`, never from a `SELECT *` probe.**
  `/notion-dev:init` records every one this file needs — `idProperty`, `statusProperty`,
  `phaseProperty`, `stepProperty`, `epicProperty`, `parentTaskProperty`, `epicMarkerProperty` —
  so `SELECT * FROM "collection://…" LIMIT 1` to learn them reads a row the caller already has the
  schema for. The client run ran that probe twice, the second time only because a compaction had
  dropped the first one's answer.

  **The title is the one exception, and it is not configured at all.** There is no
  `ticketSystem.titleProperty`: every Notion database has exactly one `title`-typed property and
  the adapter discovers it by scanning the live schema, because its *name* is free — `Name`,
  `Title` and `Task name` are all in use. So resolve it the way `config.md` "Title" says, and
  **select it only in queries that actually need the title**; a lookup that just resolves a page
  omits the column rather than guessing a name, since a wrong guess is the same hard `400` as
  `name`. Discovering one property from the live schema is not the `SELECT *` probe this bullet
  forbids — that probe was re-reading columns the config already names.
- **There is no bare `name` column**, and guessing one is a hard `400`
  (`Failed to execute query: no such column: name`). Every property is queried under its own
  **configured** name — `statusProperty`, `phaseProperty` and the rest — with two exceptions: the
  title, which has no configured key at all (see the bullet above), and **the id column, which
  takes a `userDefined:` prefix, `"userDefined:<idProperty>"`.**
  That prefix is a namespace, not a fixed column name: on a database whose `idProperty` is the
  default `ID` it reads `"userDefined:ID"`, and on one where `/notion-dev:init` bound
  `idProperty` to something else it takes that name instead. **Hardcoding `"userDefined:ID"`
  queries a column that does not exist on such a database**, and the logical-key lookup fails
  before the page is ever fetched. No other property observed on a live database needed the
  prefix; if the prefixed form is rejected, retry once with the bare configured name and record
  the fallback per `notion-dev:issue-log`. See `../SKILL.md` for why the prefix exists and why
  this tool returns the bare integer where `notion-fetch` returns `"userDefined:ID": "PDS-1"`.

`dataSourceId` is `ticketSystem.dataSourceId` when configured, otherwise derive the collection URL
from `ticketSystem.databaseId`. Everything else in this file that says "query the database" means
this call.

## fetchTicket(id)

`id` may arrive as a **Notion page id / URL** (e.g. `383fdf83c4178177beebd41a69bf47bc`, a dashed UUID, or a full `notion.so` / `notion.com` page URL) or as a **logical key** (`STO-285`, `STO285`, `285`). Resolve the page accordingly:

**If no `mcp__notion__*` tool is registered at all, that is a session-level connection failure, not a configuration one — say so, and do not send the user to `/notion-dev:init`.** This operation is the first Notion action of every command, so its absence is where the whole family's unavailability surfaces, and the obvious reading — bad config, bad credentials, wrong database — is the expensive wrong one. **One command discriminates:** run the configured MCP server's own launch command by hand from the repo directory (for the default stdio config, the `mcp-remote` invocation `/notion-dev:init` wrote into `.mcp.json`). If it completes its OAuth discovery and establishes the proxy, then credentials, endpoint and working directory are all sound and the fault is confined to this session's MCP client connect — the remedy is a session-level reconnect of the `notion` server, which the run cannot perform for itself. Report it that way and stop. Measured in a client, where the server was listed as "still connecting" at session start and never produced tools while every sibling server from the same config registered normally; the hand-run proxy succeeded, and the run stopped at this gate having created nothing.

1. **Detect input shape and resolve the page:**
   - If `id` is a Notion page id (32 hex chars with or without dashes), a dashed UUID, or a Notion page URL: **fetch the page directly** with `mcp__notion__notion-fetch` — skip the database query entirely.
   - Otherwise treat `id` as a logical key: normalize it to numeric, then query the database (or data source if configured) for the page where `idProperty` equals the numeric id — use `mcp__notion__notion-query-data-sources` **in the call shape under "Calling `mcp__notion__notion-query-data-sources`" above — inline the numeric id as a literal, never as a `?` placeholder, which returns an empty result set with no error** — with an exact filter on `idProperty` (semantic `notion-search` is not reliable for numeric-ID equality, and `notion-fetch` only fetches by URL/ID; fall back to a DB-scoped `notion-search` only if the query tool is unavailable, verifying the hit's `idProperty` value before trusting it). When `idProperty` is a `unique_id` column, filter by its numeric component — ignore the textual prefix. Load the resolved page content with `mcp__notion__notion-fetch`.

     **Verify the resolved page's `idProperty` equals the id you asked for — on every path, not only the fallback.** The verify-before-trusting clause above reads as if it belonged to the `notion-search` fallback alone; it does not. A structured filter can be **silently ignored** rather than rejected: measured in a client on three separate runs, a `rows`-mode `number_equals` filter on the id column returned the same five unrelated rows of the same database with `has_more: true` and no error, while the same lookup issued in **SQL mode with a bound parameter** returned exactly the one intended row each time. An ignored filter is indistinguishable at the call site from a genuine multi-hit, and the project-scoping guardrail in step 2 does not catch it — those rows carry the same pinned `staticProperties`, because they are the same project's tickets. So: **more than one row, or `has_more: true`, is never resolved by taking the first row** — re-issue the lookup in SQL mode **with the id inlined as a literal**, and confirm the resolved page's `idProperty` before anything downstream uses it. Prefer SQL mode wherever it is available; **this clause said "with a bound parameter" until 0.31.1, and that form is now known to be unsafe** — per the call contract at the top of this file, `?` plus `params` returns an empty result set under HTTP 200, so the documented recovery for an ambiguous lookup could itself report the ticket as missing. What three-for-three actually established is that **SQL mode** beats the structured filter, not that the parameter binding did any of the work; three for three is a reproducible defect, not an incident. Worth knowing when reading a filter that did not bite: a column named `ID` is exposed by the MCP as `userDefined:ID`, a reserved-name remap that the rows-mode filter path may not be applying.
2. **Apply the project scoping guardrail** (see section above) — abort here if any pinned `staticProperties` mismatch the live page. Fail before any further work.

   **A `404 object_not_found` on the configured `databaseId`/`dataSourceId` is ambiguous — report
   its causes, do not pick one.** Three produce the identical response, and nothing available here
   distinguishes them:

   1. the id is **wrong or stale** — mistyped, or pointing at a database since deleted or replaced;
   2. the integration has **not been granted access** to that database, though it exists in the
      workspace the session is bound to;
   3. the database lives in a **different workspace** from the one the session is authenticated to,
      so it is simply not visible.

   The shape that makes the third worth naming is all three symptoms at once — a clean 404 on the
   database id, a 404 on its data-source reference, and `data_source_not_found` on a query — with
   the configured values perfectly correct. That is a *hint*, not a finding.

   **`notion-fetch "self"` names the workspace the session is bound to; it does not prove the
   database is elsewhere.** It cannot see a database it has no access to, so it cannot tell case 3
   from case 2 or case 1. Report the 404 with the bound workspace as context and all three causes
   as the things to check — a run told "wrong workspace" when the real cause was an ungranted
   integration or a stale id is sent to fix the wrong thing. Only another read that actually
   resolves the database elsewhere confirms a workspace mismatch. Stop here either way: the run
   has created nothing yet, and this is the right place for that to stay true.

   **Never widen the lookup to recover from it.** A workspace-scoped search by logical key looks
   like an obvious fallback and is the one thing that must not be done — ticket-key prefixes are
   not globally unique, and an unrelated database in the reachable workspace can carry the same
   `<KEY>-<n>` shape. Measured in a client: the reachable workspace held a different project's
   tickets under the same key prefix, so a relaxed lookup would have resolved to a foreign
   project's ticket and operated on it silently. The DB-scoped fallback in step 1 is bounded for
   this reason, and step 2's guardrail is the backstop; neither is a licence to search wider.
3. Convert blocks to markdown, preserving **Requirements**, **Acceptance Criteria**, **Context**, **Open Questions** sections.
4. Read `typeProperty` (if present): normalize to a logical key via reverse lookup through `typeMap` (defaults above). For `multi_select`, the first option wins.
4a. Read the mission/epic-adjacent raw values, each absence-tolerant (missing or unset → that type's empty default, never a warning — these are routine, not exceptional):
   - `parentTaskProperty` (if **usable** on the live DB — present **and** a self-referential Relation): the related page id from that Relation, or `""` when unset, the property is absent, or it is present but not a self-referential Relation. All three collapse to `""` (see this property under "Property type handling") — `epic-update` step 1 and every containment guard rely on this collapse. `fetchTicket` itself records nothing for this property: the two schema-level signatures are owned by the operations that act on the column — `createTicket`'s parent resolution and write, `createEpic` step 1, `findEpics` step 1, `setParent`, `listEpicChildren`, `refreshEpicTasks`, and `epic-update` step 1 — each for its own path, so a plain ticket read stays silent about it. `epic-update` is on that list precisely because it can conclude "no epic" from this collapsed `""` and return before any of the others runs; without it, a resolved ticket on a DB with a mistyped `Parent task` would lose its epic bookkeeping with nothing recorded anywhere.
   - `epicProperty` (if present): the Select's option value, or `""` when unset or the property is absent.
   - `epicMarkerProperty` (**usable** only when present *and* Checkbox-typed — see the **"Marker usability rule"** under "Epic containers", which this step implements and does not restate): the live boolean, or `false` when unset or the property is unusable. **This one property is a named exception to this step's routine-silence rule** (see `issue-log/SKILL.md`'s "What is never logged"): it is the **sole** signal that identifies a page as an epic container, so silently collapsing *why* it read `false` costs a ticket its epic context — the failure this exception exists to close. Before collapsing, distinguish the cause:
     - property **absent** from the live DB → unusable; record `missing-property:epicMarkerProperty` per `notion-dev:issue-log`.
     - property **present but not a Checkbox** type → unusable, identically; record `wrong-type:epicMarkerProperty` per `notion-dev:issue-log`.
     - property present, Checkbox-typed, simply **unchecked** → usable; routine, record nothing.

     Log at most once per run per cause, same as every other property warning in this file. `metadata.epicMarkerProperty` still returns `false` in all three cases — recording changes nothing about what's returned or any caller's control flow.

     **`fetchTicket` is the sole owner of this recording for every path that flows through it** — and that is every path that reads a ticket: `/notion-dev:ticket`, `/notion-dev:finalize`, `epic-update`, and any future caller. Detecting the cause here, once, covers all of them without any of them changing. In particular `getEpicContext` does **not** record either signature itself; it reaches the marker via this step and relies on it having already run for the current ticket (see its own operation section). The one thing this step does **not** cover is the operations that reach the DB schema **directly, without calling `fetchTicket` at all** — `findEpics` and `createEpic`, both reachable from `/notion-dev:create-task` with no preceding ticket fetch. Those are separate detection paths and record on their own, per the ownership split in the marker usability rule. Same two signatures either way; never two owners for the same read.
   - `assigneeProperty` (if present and People-typed): the first person's user id, or `""` when unset, the property is absent, or it isn't a People type.
   - `phaseProperty` (if present and Select-typed) and `stepProperty` (if present and Number-typed): the raw option name and the raw number, or `""` / `null` respectively when unset, absent, or wrong-typed. Read-only here; `notion-dev:epic-doc` orders an epic's unresolved children by them. Absence-tolerant, never an error, and never recorded here (the two `missing-property:` signatures belong to `createTicket`'s write path).
5. Return `{ title, key, body, status, type, url, metadata: { pageId, idProperty value, rawTitle, parentTaskProperty, epicProperty, epicMarkerProperty, assigneeProperty, phaseProperty, stepProperty } }`. `title` is the page title **with the ID prefix stripped** (see "Title prefix"); `key` is the logical ticket key (`"STO-67"`) for callers that need to *display* the id beside the title; `rawTitle` is the literal Notion title. The `idProperty value` (the numeric key) is read off the **resolved page** regardless of which branch resolved it — callers rely on it for branch/worktree naming. `parentTaskProperty`, `epicProperty`, `epicMarkerProperty`, and `assigneeProperty` are the raw values read in step 4a — callers such as the epic guard in `/notion-dev:ticket`, `getEpicContext`, and `epic-update`'s Step 1 read these directly rather than re-deriving them.

## findEpics()

Read-only.

1. If **either** property epic containers require is **unusable** on the live DB, warn once and return **`null`**, **without proceeding to step 2**:

   - `epicMarkerProperty` unusable — absent, **or present but not a Checkbox**, per the **"Marker usability rule"** above. Record `missing-property:epicMarkerProperty` or `wrong-type:epicMarkerProperty`.
   - `parentTaskProperty` unusable — absent, **or present but not a self-referential Relation**. Record `missing-property:parentTaskProperty` or `wrong-type:parentTaskProperty`. `findEpics` reaches the live schema directly, so it records for its own path, same as it does for the marker.

   **Both slots, not just the marker** — this operation returns `null` under exactly the condition `createEpic` step 1 does, and for the same reason: an epic container needs the marker to be *identifiable* and the relation to be *attachable to*, and a container that cannot take children is not a container. Discovery must therefore not report finding one. Returning marked pages when the relation is unusable is worse than returning nothing: the caller records an `EPIC_ID`, `createTicket` skips every parent write, `refreshEpicTasks` no-ops, and `/notion-dev:create-task` reports "created under Epic" for tickets that only carry the Select tag — a claim that is simply false. `null` here is what makes the caller degrade to Select-tagging *and say so*. This is the same two-slot verdict `/notion-dev:init` reports as Epic-containers availability; `findEpics` checking only one slot was the inconsistency. Mirrors `getSelectOptions`, which returns `null` for the same absent/unsuitable-property case. All four signatures above go through `notion-dev:issue-log` — `findEpics` queries the DB directly, without `fetchTicket`, so per the marker rule's ownership split it records on its own rather than relying on a caller's earlier fetch, and it is likewise a direct recorder for the parent signatures, which `fetchTicket` never writes. `/notion-dev:create-task` invokes this operation directly (Phase 2.5.2 and Phase 2.6) with **no preceding `fetchTicket`**, so `fetchTicket` step 4a's validation does not cover this path — this step is the only thing standing between a retyped `Is Epic` column and step 2's query.

   **Not proceeding is the point.** Step 2 filters on this property with a checkbox `true` predicate; against a text- or select-typed column that is an **MCP query error, not an empty result**, so a presence-only guard here does not degrade — it makes ordinary task creation fail outright. Epics cannot be identified safely at all with an unusable marker: falling back to a structural guess (an Epic-select tag, an empty parent, a child count) is exactly the bug this marker exists to close, so both unusable states degrade to `null` rather than to any such fallback or to any query. Distinct from step 3's `[]`: `null` means epic containers are unavailable on this DB at all; `[]` means the property is usable but no page has it set yet. Callers must not conflate the two.
2. Reached only when step 1 confirmed **both** properties are usable. Query the database (or `dataSourceId` when configured) with `mcp__notion__notion-query-data-sources`, in the call shape this file opens with, for pages where `epicMarkerProperty` is `true` **and** (when `parentTaskProperty` is also usable on the live DB) their own `parentTaskProperty` is empty — the same predicate `getEpicContext` step 2, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply (see "Epic containers" above), so "epic" means the same thing at all four sites. There is no reduced, marker-only form of this query: step 1 returns `null` when `parentTaskProperty` is unusable, so this step only ever runs with **both** properties usable and always filters on both. An earlier version reduced the filter to the marker alone and called the relation's emptiness "vacuously true" — it is not true but *unknowable*, and treating it as satisfied is what let unattachable epics be reported as found. When `staticProperties` is configured, add each `[name, expected]` pair as an additional equality filter on this same query — the same scoping the "Project scoping guardrail" applies per-page, applied here at query time so epic discovery never surfaces a foreign project's epic in a shared DB. When `staticProperties` is empty or absent, the query is unchanged.
3. For each hit return `{ id, key, pageId, name, title, url, overview }` — `key` is the logical ticket key (`"STO-67"`) for display, same meaning and format as in `fetchTicket` and `listEpicChildren`; `name` is the `epicProperty` Select value (display metadata — may be empty on a marker-only epic that was never given one), `title` is the page title with the ID prefix stripped, `overview` is the text of its `## Overview` section (empty string when absent). No hits → `[]`. There is no children-based filtering pass here: a page with zero children is returned exactly like any other epic, since the marker alone decides.

## getEpicContext(epicId, currentTicketId)

Read-only. Assembles the bounded Notion-side context block that `notion-dev:epic-doc` distills into an epic's brief when none exists yet (its bootstrap path) — superseded by `notion-dev:knowledge` `retrieve` for every context read; only `notion-dev:epic-doc`'s Notion-source bootstrap still calls it. `currentTicketId` is the id of the ticket being started — the same `id` `/notion-dev:ticket` Phase 1.1 resolved via its own `fetchTicket(id)` call; passed explicitly so this operation never depends on being invoked in any particular sequence. **The sole owner of what "epic context" means and how much of it is included** — callers must never assemble this themselves or parse `## Resolution Log` directly; that format belongs to `epic-update`, and a second copy of the parser in a command file is how the two drift apart.

1. If `epicId` is empty, return `null`. Not a warning — this is the normal case for most tickets, which have no epic. If instead `epicMarkerProperty` is **unusable** on the live DB — absent, **or present but not a Checkbox** — also return `null`, per the **"Marker usability rule"** under "Epic containers". A wrong-typed marker leaves epic identity just as unverifiable as a missing one; the rule requires the two to be indistinguishable in behavior, and neither may fall through to step 2's fetch to be silently swallowed by that step's `false`-collapsing validation.

   Neither unusable cause is routine, but **neither is recorded here** — this operation is the rule's named non-recorder. `fetchTicket` step 4a owns `missing-property:epicMarkerProperty` and `wrong-type:epicMarkerProperty` for every path that flows through it, and this is one: it already observed and recorded whichever cause applies the moment it read the property for any ticket, including the caller's own `fetchTicket(currentTicketId)` call that resolved `currentTicketId` before this operation was ever invoked. Recording again here would give one condition two owners, exactly the pattern that kept reopening this bug. `/notion-dev:ticket <existing-child-ticket>` can reach this operation directly, without ever calling either direct-schema recorder (`findEpics` or `createEpic`) — but it always does so only after its own `fetchTicket(currentTicketId)` call, which is where these two causes are actually observed and recorded.
2. `fetchTicket(epicId)` → epic identity (`key`, `title`, `url`), `body`, and its own `metadata.parentTaskProperty` / `metadata.epicMarkerProperty`. **Validate before proceeding**: if the fetched page's own `parentTaskProperty` is non-empty, or its `epicMarkerProperty` is not `true` (`false` whether because the box is unchecked, the property is absent from the live DB, or it is present but not a Checkbox — `fetchTicket` collapses all three to the same default; see "Property type handling"), this is not a structurally valid epic — return `null`, the same signal as step 1's "no epic" case, and do nothing further. This is the same predicate `findEpics()`, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply; enforcing it here, inside the adapter, means every caller — present or future — inherits it rather than having to re-check at each call site. Without it, a `parentTaskProperty` value that merely points at an ordinary Notion Sub-items parent (not an epic) would be handed back as if it were one: a nonexistent `## Overview`, the parent's other children mislabeled as "siblings," and none of it flagged as anything other than epic context.
3. **Overview.** Extract the `## Overview` section verbatim from `body`. Omit the heading and body entirely from the output when the section is absent.
4. **Sibling status.** Call `listEpicChildren(epicId)` — a **live** call, never derived from the epic body's `## Tasks` section. That section is documented as "Snapshot as of the last resolution" and is only refreshed when a child resolves, so it is stale by construction; handing a starting ticket stale sibling status would be worse than handing it none. Render one line per child: `[{key}] {title} — {status}`. Mark the entry whose `id` equals `currentTicketId` with a trailing ` (this ticket)` so the reader can locate itself among its siblings. When `currentTicketId` matches no entry — e.g. the parent relation was just set but the epic's child query has not yet picked it up — mark nothing and continue; this is not an error.
5. **Recent resolution history.** Parse `## Resolution Log` from `body` into its `### [<KEY>-<n>] resolved — <datetime>` entries, in document order. **Tolerate the backslash-escaped bracket form** (`### \[<KEY>-<n>\] resolved`) exactly as the title-prefix detection does — see "Title prefix" for the canonical rule and what an unescaped parse costs `epic-update`'s idempotency check. `appendToSection` always appends at the end, so the **last 3** entries in document order are the most recent 3 resolutions — take those. When more than 3 entries exist, prepend a line stating how many older entries were omitted, so the reader knows there is more history and where to find it (the epic `url` from step 2).
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

## listEpicChildren(epicId)

Read-only.

1. If `parentTaskProperty` is **unusable** on the live DB — absent, **or present but not a self-referential Relation** — warn once and return `[]`, **without proceeding to step 3's query**. Both states degrade identically (see this property under "Property type handling"): step 3 filters with a relation-`contains` predicate, and against a non-relation column that is an MCP query error, not an empty result — the same trap the "Marker usability rule" closes for `epicMarkerProperty`. Record `missing-property:parentTaskProperty` when the property is **absent**, or `wrong-type:parentTaskProperty` when it is present but not a self-referential Relation, per `notion-dev:issue-log` — identical behavior, separate conditions, separate signatures.
2. Resolve `epicId` to a page ID via `fetchTicket`.
3. Query the DB for pages whose `parentTaskProperty` contains that page ID.
4. Return `[{ id, key, title, status, url }]` ordered ascending by `id` — `key` the logical ticket key (`"STO-67"`) for display, `title` prefix-stripped, `status` the live option name verbatim (not a logical key; callers compare it against the resolved set).

