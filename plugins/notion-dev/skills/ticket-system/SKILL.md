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
| `fetchTicket` | `id` (numeric or prefixed string, or a Notion page id/URL) | `{ title, key, body, status, type, url, metadata }` — `title` has the ID prefix stripped; `key` is the logical ticket key (`"STO-67"`) for display; `metadata` carries `rawTitle` (the literal Notion title), `pageId`, the `idProperty` value, `parentTaskProperty` (the raw related-page id from that Relation, or `""`), `epicProperty` (the raw Select value, or `""`), `epicMarkerProperty` (the raw Checkbox value, or `false`), and `assigneeProperty` (the raw People-column user id, or `""`) — each carries its type's empty default whenever the corresponding configured property is missing from the live DB, unset on the page, or present with a type it cannot be read as — for `assigneeProperty` not a People type, for `epicMarkerProperty` not a Checkbox type, for `parentTaskProperty` not a self-referential Relation; `epicMarkerProperty` is the sole exception to this being silent: it is the sole signal that identifies an epic container, so before collapsing to `false` the adapter distinguishes and records `missing-property:epicMarkerProperty` (absent) or `wrong-type:epicMarkerProperty` (present but not Checkbox) per `notion-dev:issue-log` — the returned value is unchanged and no caller's control flow differs; see step 4a below, which owns this recording for every path that flows through `fetchTicket` (the operations that reach the live schema without it — `findEpics` and `createEpic` — record on their own; `createTicket` records nothing about the marker on any path; see the "Marker usability rule"). `type` is the logical key (`feature`/`bug`/…) when the DB has a mapped type property, else absent |
| `createTicket` | `{ title, body, type?, epic?, parent?, phase?, step?, assignee?, isEpic? }` | `{ id, url }` — `epic`/`parent`/`phase`/`step` are optional mission metadata; `parent` accepts either a logical ticket id or a Notion page id and is resolved to a page id via `fetchTicket`, same as `setParent`; `assignee` is a resolved Notion user id; `isEpic` (bool, default `false`) — when `true` and `epicMarkerProperty` is **usable** on the live DB (present **and** Checkbox-typed — see "Marker usability rule"), sets it to `true` **in this same create call**; a wrong-typed marker is never written to, same as an absent one; used only by `createEpic`. Each is absence-tolerant when the corresponding configured property is missing from the live DB. `parent` is additionally **type**-tolerant on the same terms: an unusable `parentTaskProperty` — absent, or present but not a self-referential Relation — skips the relation write and records `missing-property:parentTaskProperty` or `wrong-type:parentTaskProperty` per `notion-dev:issue-log` (see steps 1a and 2); the ticket is still created, only unparented. `epic`/`phase`/`step` have no wrong-type signature — absence-tolerance is their whole contract |
| `resolveAssignee` | `value` (user id, email, or display name) | `{ id, name }` on a unique person match; `null` on no match or ambiguity. Read-only — never mutates config or the DB |
| `updateTicket` | `id`, `{ title?, body?, type? }` | `{ id, url }` — only the provided fields change |
| `updateStatus` | `id`, `logicalStatus` ∈ `{ inProgress, implemented }` (plugin-invoked set) plus any custom key present in the user's `statusMap` | `void` — the plugin never invokes `delivered` / `done` / shipped-style states; those are reserved for host-project commands |
| `setPullRequest` | `id`, `url` | `void` — persists the PR URL into the configured PR property. No-op when the live DB has no such property. Does not touch body sections. Record `missing-property:prProperty` per `notion-dev:issue-log`. |
| `setDependencies` | `id`, `[titleOrId, …]` | `void` — renders the ticket's `## Blocked by` body section, **the single owner of that section's format**. Resolves entries that look like titles to tickets within the DB. Writes **no** relation property and reads no live schema, so it has no absence path and records no signature — see the operation section for why: keeping the relation out is a design judgment, not an impossibility. **Not** a claim that self-relations are symmetric, **not** a claim that subtype is undetectable, and **not** a claim that no signal predicts write behavior; all three were said here before and all three over-reached. Pass-2 in mission creation. |
| `createEpic` | `{ name, overview, type?, assignee? }` | `{ id, key, url, pageId }` — creates an Epic container page with `epicMarkerProperty` already set to `true` in that same creation call (via `createTicket`'s `isEpic` argument) — the write that actually makes it an epic, with no unmarked intermediate state. No-op returning `null` when either `parentTaskProperty` or `epicMarkerProperty` is **unusable** on the live DB — for the marker that means absent **or present but not a Checkbox**, which degrade identically (see "Marker usability rule"). Record whichever of the four applies — `missing-property:parentTaskProperty`, `wrong-type:parentTaskProperty`, `missing-property:epicMarkerProperty`, `wrong-type:epicMarkerProperty` — per `notion-dev:issue-log`; `createEpic` reads the live schema directly, so it records for its own path. |
| `findEpics` | — | `[{ id, key, pageId, name, title, url, overview }]` — pages where `epicMarkerProperty` is `true` and their own `parentTaskProperty` is empty (the same predicate `getEpicContext` step 2, `epic-update` step 1, and `/notion-dev:ticket`'s epic guard apply), scoped by `staticProperties` when configured (see "Project scoping guardrail"). `null` when **either** `epicMarkerProperty` or `parentTaskProperty` is **unusable** on the live DB — absent, or present with the wrong type; each unusable state degrades identically and none ever reaches the query (see "Marker usability rule"), because a checkbox or relation filter on a wrong-typed column is an MCP error, not an empty result. The two-slot condition is deliberate and matches `createEpic`: a container that cannot be identified, or cannot take children, must not be reported as found (mirrors `getSelectOptions`'s absent-property `null`); `[]` when both are usable but no page has the marker set yet — these are different states, not interchangeable. Record whichever of the four applies — `missing-property:epicMarkerProperty`, `wrong-type:epicMarkerProperty`, `missing-property:parentTaskProperty`, `wrong-type:parentTaskProperty` — per `notion-dev:issue-log`; `findEpics` reads the live schema directly, so it records for its own path. |
| `setParent` | `id`, `epicId` | `void` — writes the `parentTaskProperty` relation. **Currently uncalled** — parenting at creation goes through `createTicket`'s `parent` argument; see this operation's section. No-op when the property is **unusable** — absent, or present but not a self-referential Relation; both degrade identically and neither is ever written to. Record `missing-property:parentTaskProperty` or `wrong-type:parentTaskProperty` per `notion-dev:issue-log`. |
| `listEpicChildren` | `epicId` | `[{ id, key, title, status, url }]` — pages whose `parentTaskProperty` points at `epicId`, ordered by `id`. `[]` when the property is **unusable** — absent, or present but not a self-referential Relation; both degrade identically and neither ever reaches the relation-`contains` query, which against a non-relation column is an MCP error rather than an empty result. Record `missing-property:parentTaskProperty` or `wrong-type:parentTaskProperty` per `notion-dev:issue-log`. |
| `getEpicContext` | `epicId`, `currentTicketId` | bounded markdown context block, or `null` — superseded by `notion-dev:knowledge` `retrieve` for every context read; only `notion-dev:epic-doc`'s Notion-source bootstrap still calls it, when an epic has no brief yet and no seed plan either; `/notion-dev:ticket` no longer calls it directly. Epic identity, verbatim `## Overview`, **live** sibling status (via `listEpicChildren`, never the epic body's stale `## Tasks` snapshot) with the sibling whose `id` equals `currentTicketId` marked, and the most recent 3 `## Resolution Log` entries (with a count of any older entries omitted). `null` (no warning — routine) when `epicId` is empty; `null` when `epicMarkerProperty` is **unusable** on the live DB instead — absent, or present but not a Checkbox, which the "Marker usability rule" requires to behave identically. Distinct causes, not interchangeable with the routine empty-`epicId` case, though this operation records **neither** unusable cause itself: `fetchTicket` step 4a is their recorder for every path through it, this one included (`missing-property:epicMarkerProperty` / `wrong-type:epicMarkerProperty` per `notion-dev:issue-log`), already triggered by the caller's own prior `fetchTicket` call. When `currentTicketId` matches no sibling, mark nothing and continue — never an error. The sole owner of what "epic context" means — callers never assemble it themselves or parse `## Resolution Log`. **Background, not requirements**: callers must never treat its content as spec |
| `refreshEpicTasks` | `epicId` | `void` — re-renders the epic's `## Tasks` section from its live children. The single owner of that section's format. **No-op when the epic has no `## Tasks` section** — a refresh never creates one, for the same reason `refreshAcceptanceCriteria` never creates its own. No-op when `parentTaskProperty` is **unusable** — absent, or present but not a self-referential Relation — since it has no way to enumerate children. Records `missing-property:parentTaskProperty` or `wrong-type:parentTaskProperty` per `notion-dev:issue-log` for its own path — it returns before `listEpicChildren` is called, so it cannot defer the recording to it |
| `refreshAcceptanceCriteria` | `id`, `verdicts` | `void` — re-renders the ticket's `## Acceptance Criteria` to-do blocks with each box ticked or unticked per its verdict. The single owner of the `Acceptance Criteria` section's format after creation, for the same reason `refreshEpicTasks` owns `## Tasks`: two callers write it (`/notion-dev:ticket` Phase 8 and `/notion-dev:finalize` Phase 3) and would otherwise drift apart. Renders criterion text from the caller's criteria file, **never from the verifier's summary**. No-op when the ticket has no `## Acceptance Criteria` section. |
| `appendToSection` | `id`, `sectionName`, `content` | `void` — **appends** to a named body section, creating it if absent. Never replaces, unlike `upsertSection` |
| `getSelectOptions` | `configKey` | `[string]` or `null` — lists option names for a Select / Multi-Select / Status property. Returns a bare `null` if the property is absent from the live DB or present but not a selectable type — callers see the same `null` either way and use it as a control-flow signal, unchanged. `configKey` is the **config key** the caller is asking about (e.g. `phaseProperty`, `epicProperty`) — callers invoke `getSelectOptions(phaseProperty)`, naming the key directly; the adapter resolves that key to its configured live column name itself before reading the schema, so the lookup runs key → live name only, never the reverse. That matters because the config schema puts no uniqueness constraint on these property-name values — two config keys can be configured to the same live column name (e.g. both `epicProperty` and `phaseProperty` set to `"Tags"`) — so recovering a key from a bare live-name value would be ambiguous; naming the key up front removes the guesswork. When recording, the adapter cites the caller-named key directly — annotated inline the same way `createTicket`'s `option-missing:<propertyName>` citation already is (e.g. "here, `epicProperty`") — never the live column name: `missing-property:<configKey>` when absent, `wrong-type:<configKey>` when present but not Select/Multi-Select/Status. When the caller has no owning config key to name (e.g. a name drawn from `staticProperties`), apply the fallback in `issue-log/SKILL.md`'s signature-grammar section instead. Per `notion-dev:issue-log`. Recording is not a warning — still none on `null`. Read-only. |
| `addSelectOption` | `configKey`, `optionName` | `void` — extends a Select's options list on the live DB, identified by the `configKey` the caller names (same rule as `getSelectOptions`). Should only be invoked after explicit user confirmation (adding options mutates shared DB schema). |
| `postComment` | `id`, `text` | `void` |
| `upsertSection` | `id`, `sectionName` (string), `content` (dict of labeled entries OR markdown) | `void` — appends a `## <sectionName>` block to the ticket body, or **overwrites** it if one already exists. Different section names are independent — e.g. `"Implementation"` and `"Merged"` coexist. |

`body` is markdown structured with sections: **Requirements**, **Acceptance Criteria**, **Context**, **Open Questions** (order may vary; missing sections are allowed).

`logicalStatus` is always the logical name. The adapter maps it to the concrete Notion status via `statusMap` in config, falling back to sensible defaults when a key is missing.

## ID normalization

Callers may pass an `id` as a **logical key** — `STO-285`, `STO285`, or `285`. Normalize by stripping the configured `project.key` prefix and any separator, then parsing the remainder as an integer, then resolving it through the `idProperty` lookup. A **Notion page id or page URL** is also accepted, resolving the page directly.

**The value read back off the page needs the same normalization**, and this is not symmetry for
its own sake. A `unique_id` column carries its own prefix, and the two MCP access paths disagree
about whether they apply it: `notion-fetch` returns the property as the *prefixed string*
(`"userDefined:ID": "PDS-1"`), while `notion-query-data-sources` returns the bare integer (`1`) —
verified against a live database. So `fetchTicket` normalizes whatever it read — strip a leading
`<live unique_id prefix>` or `<KEY>` and any separator, then parse the remainder as an integer —
before putting it in `metadata` as the `idProperty` value. Every caller that says "the numeric
`<id>`" (`/notion-dev:ticket` Phase 1.1 derives branch, worktree and file names from it) depends
on that value already being numeric; taken unnormalized it yields `ticket/PDS-PDS-1-<slug>`.

A `number` ID column is unaffected — it has no prefix to strip — and the normalization is a
no-op there.

## Configuration, property types, page headings

Resolution of the configured property names, how each Notion property type is written and read
back, and Notion page heading parsing are in **`references/config.md`**. **Read it before the
first Notion call**; the property-type rules there are load-bearing — a value written in the wrong
shape is accepted by the API and read back wrong.

## Project scoping guardrail

When `staticProperties` is configured, those same properties act as a **fetch-side scope check**: a DB shared across projects will have tickets from other projects, and every per-ID operation starts from `fetchTicket`. After resolving a page, compare each `[name, expected]` in `staticProperties` against the fetched page's value for that property:

- **Match** (or property absent from the live DB) → proceed silently.
- **Mismatch** → abort with: *"`<PREFIX>-<id>` has `<prop>`=`<actual>`; this project is pinned to `<prop>`=`<expected>`. Refusing to operate on a ticket from a different project."* Record `abort:project-scope` per `notion-dev:issue-log`.

This is a hard abort — crossing project boundaries is always a user error in a multi-project DB setup. The guardrail applies to `fetchTicket` (and therefore to every operation that reaches a page through it: `updateTicket`, `updateStatus`, `setPullRequest`, `upsertSection`, `postComment`). `createTicket` is unaffected — it sets the pinned values, it doesn't verify them.

When `staticProperties` is empty or absent, the check is skipped — single-project DBs behave as before.

## Styling conventions

The palette, zone dividers, intro callouts, rich-content rules and heading attribute preservation
are in **`references/styling.md`**. **Read it before any operation that writes page content** —
`createTicket`, `createEpic`, `upsertSection`, `appendToSection`, `refreshEpicTasks`,
`refreshAcceptanceCriteria`. A section written without these conventions renders inconsistently
with every other section of the same ticket.

## Read operations

`fetchTicket`, `findEpics`, `getEpicContext` and `listEpicChildren` are in
**`references/read-ops.md`**. **Read it before the first read.** `fetchTicket`'s id-resolution
rules there are load-bearing: a structured filter can be silently ignored rather than rejected, so
the resolved page's `idProperty` is verified on every path.

## Write operations

`updateTicket`, `updateStatus`, `setPullRequest`, `postComment`, `upsertSection`,
`refreshAcceptanceCriteria` and `appendToSection` are in **`references/write-ops.md`**. **Read it
before the first write.** The `upsertSection` / `appendToSection` distinction there is
load-bearing: a replacing write where an append was meant clobbers a section another phase wrote.

## Creation and epic-container operations

Title prefixing, `resolveAssignee`, `createTicket`, `setDependencies`, `getSelectOptions`,
`addSelectOption`, epic containers, `createEpic`, `setParent` and `refreshEpicTasks` are in
**`references/create-ops.md`**. **Read it before the first create.** The title-prefix escaping
rules there are load-bearing — an unescaped write fails with `No matches found`, and an
unescaped read-back produces a double prefix.

## MCP unavailability

There is no useful CLI fallback for Notion. If the MCP is unreachable, fail with: *"Notion MCP is unavailable. Re-check `.mcp.json`, confirm the `notion` server is listed, and retry."* Record `mcp-unavailable:notion` per `notion-dev:issue-log`.
