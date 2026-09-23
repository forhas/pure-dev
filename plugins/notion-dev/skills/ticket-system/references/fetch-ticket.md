Use the shared guards in `../SKILL.md` and `config.md`. Before any data-source query read `query.md`; before resolving a page read `fetch-ticket.md`.

## fetchTicket(id)

**Runtime capture (schema 4).** Preserve the complete original notion-fetch JSON/envelope in
a new UTF-8 file and retain the actual host tool-call ID. Pass that raw capture to runtime
ticket-source / refresh-ticket; do not reconstruct it from this operation's normalized return.
Before a merge-boundary read, begin refresh-ticket, then fetch the exact bound page. Capture
only after the call returns. A query selecting status, a cache hit on an old local artifact,
an incomplete response or a failed read cannot serve as the full-source refresh receipt.

`id` may arrive as a **Notion page id / URL** (e.g. `383fdf83c4178177beebd41a69bf47bc`, a dashed UUID, or a full `notion.so` / `notion.com` page URL) or as a **logical key** (`STO-285`, `STO285`, `285`). Resolve the page accordingly:

**If no `mcp__notion__*` tool is registered at all, that is a session-level connection failure, not a configuration one — say so, and do not send the user to `/notion-dev:init`.** This operation is the first Notion action of every command, so its absence is where the whole family's unavailability surfaces, and the obvious reading — bad config, bad credentials, wrong database — is the expensive wrong one. **One command discriminates:** run the configured MCP server's own launch command by hand from the repo directory (for the default stdio config, the `mcp-remote` invocation `/notion-dev:init` wrote into `.mcp.json`). If it completes its OAuth discovery and establishes the proxy, then credentials, endpoint and working directory are all sound and the fault is confined to this session's MCP client connect — the remedy is a session-level reconnect of the `notion` server, which the run cannot perform for itself. Report it that way and stop. Measured in a client, where the server was listed as "still connecting" at session start and never produced tools while every sibling server from the same config registered normally; the hand-run proxy succeeded, and the run stopped at this gate having created nothing.

1. **Detect input shape and resolve the page:**
   - If `id` is a Notion page id (32 hex chars with or without dashes), a dashed UUID, or a Notion page URL: **fetch the page directly** with `mcp__notion__notion-fetch` — skip the database query entirely.
   - Otherwise treat `id` as a logical key: normalize it to numeric, then query the database (or data source if configured) for the page where `idProperty` equals the numeric id — use `mcp__notion__notion-query-data-sources` **in the call shape under "Calling `mcp__notion__notion-query-data-sources`" in `query.md` — inline the numeric id as a literal, never as a `?` placeholder, which returns an empty result set with no error** — with an exact filter on `idProperty` (semantic `notion-search` is not reliable for numeric-ID equality, and `notion-fetch` only fetches by URL/ID; fall back to a DB-scoped `notion-search` only if the query tool is unavailable, verifying the hit's `idProperty` value before trusting it). When `idProperty` is a `unique_id` column, filter by its numeric component — ignore the textual prefix. Load the resolved page content with `mcp__notion__notion-fetch`.

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
