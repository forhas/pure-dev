# ticket-system — creation and epic-container operations

Read before the first create. Title prefixing, `resolveAssignee`, `createTicket`,
`setDependencies`, `getSelectOptions`, `addSelectOption`, epic containers, `createEpic`,
`setParent`, `refreshEpicTasks`. Referenced from `../SKILL.md`.

`/notion-dev:ticket` never reaches this file — it creates no ticket and no epic.
`/notion-dev:create-task` is its principal consumer.

## Title prefix

Every ticket title carries its ticket ID as a leading tag: `[STO-67] Large-Wallet Stale-Index Incident`. The adapter owns this entirely — **callers pass and receive bare titles and never construct, parse, or strip the prefix themselves**. Applies to epics identically.

Format: `[<KEY>-<n>] ` — literal `[`, `project.key`, `-`, the numeric ID, `]`, one space.

Detection (case-insensitive on the key, tolerant of stray inner whitespace, **and of the
backslash-escaped bracket form**):

```
^\\?\[\s*<KEY>-(\d+)\s*\\?\]\s*
```

**The optional backslashes are not defensive padding.** Notion-flavored markdown escapes `[` and
`]`, so the title-typed property of a page read back through `notion-fetch` arrives as
`\[PDS-1\] Add a farewell helper` — verified against a live database. Against the unescaped
regex the strip silently fails, and every consequence this rule exists to prevent follows: the
branch slug carries the id twice (`ticket/PDS-1-pds-1-add-a-farewell-…`, the exact shape the
Reading paragraph below promises not to produce), and `updateTicket`'s "never double-prefixes"
idempotence breaks, accumulating `[PDS-1] [PDS-1] …` one prefix per touch.

Strip the escapes from the captured title as well, not only from the prefix: a title whose body
contains brackets arrives escaped throughout.

**The escaping is a property of Notion's markdown, not of the title property — so it binds every
read-back of a `[<KEY>-<n>]` bracket form this plugin writes, not just the title.** This is the
canonical statement; the other two sites cite it. Any parse or targeted search-and-replace
written against the *unescaped* form fails silently on a page that demonstrably contains the
text, and the two failures look nothing alike:

- **A parse finds zero entries** on a populated section. `getEpicContext` step 5's
  `### [<KEY>-<n>] resolved` parse of `## Resolution Log` is the consequential one, because
  `epic-update` step 1a's idempotency check reads it: against the unescaped form `already-recorded`
  can never fire, so a recovery invocation re-runs the filing pass and appends a **duplicate log
  entry**. Per-follow-up `PROVENANCE` dedup still prevents duplicate *tickets*, so the damage is a
  duplicated entry rather than lost work — but the check is defeated, not degraded.
- **A write fails outright.** An `update_content` whose `old_str` uses the unescaped form returns
  `validation_error: No matches found` — which at least fails loudly, unlike the parse above.

Measured in a client under a live database: a `## Tasks` line read back as
`- [ ] \[<KEY>-<n>\] <title> — Backlog` and a log heading as `### \[<KEY>-<n>\] resolved — …`, both
escaped, and an unescaped `### \[<KEY>-\d+\] resolved` regex matched **zero** entries on a page
holding several. Tolerate an optional `\` before `[` and
before `]` at every such site, and strip it from whatever is captured.

Only a prefix matching **this project's** `project.key` counts. On a DB shared between projects, a leading `[FOO-12] ` is part of the title, not a prefix — leave it alone.

**Writing.** `createTicket` and `updateTicket` write `[<KEY>-<n>] <bare title>`, stripping any already-matching prefix from the incoming value first. Idempotent: never double-prefixes, and a prefix carrying the wrong number is corrected to the page's real ID.

**Reading.** `fetchTicket` returns `title` with the prefix stripped, and `metadata.rawTitle` with the literal Notion title. This is what keeps callers correct without changes — `/notion-dev:ticket` kebab-cases the title into a branch slug, and a stripped title keeps branches as `ticket/STO-67-large-wallet-stale-index` rather than `ticket/STO-67-sto-67-large-wallet-stale-i`.

Callers that need to *show* the id alongside the title use the `key` field (`"STO-67"`) and render `[{key}] {title}` themselves. That is display formatting, not prefix construction — what the adapter owns is the title stored in Notion.

**`unique_id` prefix mismatch.** A Notion `unique_id` column carries its own prefix. When it differs from `project.key`, titles still use `project.key` — config is the source of truth for the plugin's naming, and branch names already depend on it. Log **one** warning per run: `"ID column prefix '<live>' differs from project.key '<KEY>'; titles use '<KEY>'"`. Record `prefix-mismatch:unique_id` per `notion-dev:issue-log`.

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
1a. If `parent` is provided AND `parentTaskProperty` is **usable** on the live DB — present **and** a self-referential Relation, per that property's entry under "Property type handling", which states the check once for every site that applies it — **resolve it to a page id now, before the create call** — it may arrive as a logical ticket id or already a Notion page id; resolve it via `fetchTicket` (`setParent` step 2 does the same, from its own entry point). This is the only piece of mission metadata that needs work before creation; `epic`/`phase`/`step` are written as-is in step 2.
2. Create the page via `mcp__notion__notion-create-pages`:
   - Parent = configured database / data source.
   - Properties: `idProperty` = new id (omit when `unique_id`), the **title-typed property** (discovered from the live schema — see Property type handling above), `statusProperty` = `"Backlog"` (or the first option if Backlog not present). The title value depends on the ID column type — see the retitle rule in step 3.
   - If the live DB has `typeProperty` AND `type` was provided, set it: translate the logical key through `typeMap` to the Notion option label, then write it as a scalar (Select) or single-item list (Multi-Select) depending on the live property type.
   - For each `[name, value]` in `staticProperties` (if configured), set that property on the page. Property type is inferred from the live database schema (Select/Status → option name match; Multi-Select → single-item list unless the value is already a list; text → verbatim). Skip silently with a warning if the property doesn't exist on the DB.
   - **Assignee** (absence-tolerant): if `assignee` (a resolved user id) is provided AND the live DB has the `assigneeProperty` column AND it is a `people` type, set it to a single-item people list `[{ id: assignee }]`. If the column is absent or not People-typed, skip with the one-time warning from "Property type handling". `assignee` absent → set nothing.
   - **Creation Date** (absence-tolerant): if the live DB has the `creationDateProperty` column AND it is a `date` type, set it to the current UTC timestamp in ISO 8601 with time (e.g. `2026-08-01T14:32:00Z`). When it is a `created_time` type, set nothing — Notion fills it. When absent or any other type, skip with the one-time warning from "Property type handling". Record `missing-property:creationDateProperty` when the property is absent, or `wrong-type:creationDateProperty` when it exists but is neither `date` nor `created_time`, per `notion-dev:issue-log`.
   - **Mission metadata** (absence-tolerant, independent of each other):
     - If `epic` is provided AND `epicProperty` exists on the live DB, set that Select to `epic` (exact option-name match required; if the option doesn't exist, raise an error — the caller should have resolved it via `getSelectOptions` / `addSelectOption` first). Record `option-missing:<propertyName>` (here, `epicProperty`) per `notion-dev:issue-log` — Kind B: `epic` is a proposed name generated for this mission, not a fixed vocabulary, so the subject stays `epicProperty` alone; the proposed name is never appended to it.
     - If `parent` was provided AND `parentTaskProperty` is **usable** on the live DB (per step 1a), set that Relation **in this same create call** to a single-element list containing the page id resolved in step 1a. An **unusable** `parentTaskProperty` — absent, or present but not a self-referential Relation — skips this write with the one-time warning and the recording its "Property type handling" entry specifies, exactly as `setParent` does; the ticket is still created, only unparented. This is the plugin's primary parent-writing path, so the check cannot be weaker here than in `setParent`: writing a relation payload to a non-relation column is an MCP error, not a silent no-op. `epic` and `parent` are independent: the Epic select makes the grouping visible in DB views and filters, the Parent task relation makes it a container. Callers normally set both.
     - If `phase` is provided AND `phaseProperty` exists, set that Select to `phase` (same option-match rule). Record `option-missing:<propertyName>` (here, `phaseProperty`) per `notion-dev:issue-log` — Kind B, same reasoning: `phase` is generated per-mission structure, not a fixed vocabulary, so the subject stays `phaseProperty` alone.
     - If `step` is provided AND `stepProperty` exists, set that Number to `step`.
     - If `isEpic` is `true` AND `epicMarkerProperty` is **usable** on the live DB — present **and** Checkbox-typed, per the "Marker usability rule" under "Epic containers" below — set that Checkbox to `true` **in this same create call**; this is the write that actually makes the page an epic. A wrong-typed marker is **never written to**, exactly as an absent one is not: the write side obeys the same usability check as the read side, because sending a boolean to a select- or text-typed column is the write-side twin of the MCP error the rule exists to prevent. `isEpic` defaults to `false`; only `createEpic` ever passes `true`, and it has already returned `null` on an unusable marker in its own step 1 — so this check is **defence in depth and unreachable by construction**, not a second detection site. Accordingly `createTicket` **records nothing** about `epicMarkerProperty` on either path: nothing here, because the branch cannot execute; and nothing when `isEpic` is unset, because the marker is not read at all then and logging would fire on every ordinary task creation against a marker-less DB. Skipping the write does not stop the create — the page is still created and `{ id, url }` still returned; it is the marker write alone that degrades.
     - Any **missing** configured property emits a one-time warning (`"<name>Property '<n>' not found on DB; skipping"`) and continues. Record `missing-property:epicProperty`, `missing-property:phaseProperty`, `missing-property:stepProperty`, or `missing-property:parentTaskProperty` (whichever property was missing) per `notion-dev:issue-log`. **`epicMarkerProperty` is deliberately not in that list** — `createTicket` records nothing about the marker on any path (see the previous bullet and the "Marker usability rule"); adding it here would restore the recorder that rule removes. This bullet is about **absence only** — do not widen it to cover wrong types. Each property that also tolerates a wrong live type states that case in its own "Property type handling" entry, and they do not agree with each other: `parentTaskProperty` records a distinct `wrong-type` signature, `epicMarkerProperty`'s wrong-typed case is recorded by other operations and never by `createTicket` (see the "Marker usability rule"), and `epicProperty` / `phaseProperty` / `stepProperty` have **no** `wrong-type` signature at all — so a single widened sentence here would mint names that do not exist and contradict three separate contracts.
   - Children blocks: render `body` markdown, **applying the Styling conventions above**. Each canonical heading (`Requirements`, `Acceptance Criteria`, `Context`, `Open Questions`, `Source`, `Overview`, `Tasks`) gets its palette color; intro callouts prepend sections that define one; `Acceptance Criteria` renders as to-do blocks. No divider appears yet at creation — only zone transitions add dividers. `Overview` and `Tasks` only appear when `createEpic` is the caller (see "Epic containers" below); this is the code path that colors them gray and blue respectively at creation time.

   **Setting `parent` here, rather than as a follow-up update, is deliberate and load-bearing.** The page, its body (including any caller-supplied provenance marker in `## Context`), and its parent relation are all written in this single `mcp__notion__notion-create-pages` call — there is no intermediate state where the page exists but is not yet a child of its epic, and therefore no window in which an interrupted run leaves an orphaned follow-up that `listEpicChildren(EPIC_ID)`-based dedup cannot see. Do not split `parent` back out into a separate write after creation: unlike the `unique_id` retitle in step 3 below, it does not need the new page's id — the relation points *from* the new page *to* the epic, and the epic's page id is already known (resolved in step 1a) before the create call is issued. Only the retitle genuinely has to wait, because that id does not exist until the page does.
3. Apply the title prefix (see "Title prefix"):
   - **`number` ID column** — the id was computed in step 1, so the create in step 2 already wrote `[<KEY>-<n>] <title>`. Nothing further.
   - **`unique_id` ID column** — the id does not exist until the page does. Step 2 created the page with the **bare** title; now read the assigned id off the created page and call `mcp__notion__notion-update-page` to set the title-typed property to `[<KEY>-<n>] <title>`. Two calls; unavoidable.

   If this retitle call fails, **do not roll back** — the page exists and is usable. Return normally and report that the prefix is missing. `updateTicket`'s backfill (below) repairs it on the next touch, and `fetchTicket`'s strip tolerates its absence.
4. Return `{ id: newId, url: pageUrl }`.

**`dependsOn` is never set here.** Mission callers run a second pass with `setDependencies` once all pages exist and their IDs are known — it renders a `## Blocked by` body section rather than writing any relation property.

`staticProperties` are **creation-only**. `updateTicket` and `upsertSection` must not touch them — they're user-owned after the ticket exists.

## setDependencies(id, references)

Renders the ticket's `## Blocked by` body section. **The single owner of that section's format** — callers never render it themselves, so `/notion-dev:create-task` cannot drift from it. `references` is a list whose entries are either numeric/prefixed IDs (e.g. `285`, `"STO-285"`) or ticket titles (any string that isn't a numeric or `<PREFIX>-N` form).

**This operation writes no relation property, and there is no `dependsOnProperty` config key.** The reason is **not** that Notion self-relations are symmetric — they are not, and an earlier version of this file wrongly said so. Both forms preserve direction: a `single_property` self-relation writes one edge and creates no reverse edge at all, and a `dual_property` one splits the two directions across two separate columns. This is the **canonical statement** of why the relation is nevertheless unused; every other site cites it rather than restating it.

A subtype indicator exists: **`propertyUrl`**, which the MCP surface carries on every `dual_property` half and on no `single_property` relation (verified across nine relations, plus six non-relation controls that never carry it). An earlier version of this file said subtype was not exposed at all. That was wrong.

The signal is **asymmetric**, and stating that precisely matters:

- **`propertyUrl` absent → `single_property` → writes are safe.** On the evidence, this branch is conclusive: a one-way relation writes one edge and produces no reverse edge anywhere. A conservative guard binding *only* such columns would be sound.
- **`propertyUrl` present → ambiguous.** Deleting a two-way relation's companion leaves the surviving half still carrying its `propertyUrl` while it behaves exactly one-way. Verified directly, and not a curiosity — it is the state the reporting client's own database was left in. A live dual half and an orphaned one are **identical on this surface and opposite in behavior**, so nothing here distinguishes a column that will produce a companion edge from one that will not.

So the honest claim is not "no signal predicts write behavior" — an earlier wording said that and it over-reached. It is that the signal **proves safety on one branch and says nothing on the other**.

**The relation nonetheless stays unused, and that is now a design judgment rather than an impossibility.** Three reasons, in order of weight:

1. **It would make the plugin's dependency representation conditional on a schema accident.** Some databases would carry relation edges, others only the body section, with nothing on the page telling a reader which. `## Blocked by` covers every database unconditionally; a partial second mechanism buys redundancy on a subset and ambiguity everywhere.
2. **The gate would rest on an undocumented field.** `propertyUrl` is not a documented Notion API contract — it is a proxy inferred from nine columns. This investigation has already had three structural inferences falsified in sequence, and the specific failure each time was trusting a pattern that looked airtight. Gating *writes* on the next one is a poor bet, and Notion can change it silently.
3. **It restores real config surface** — the `dependsOnProperty` key, init's resolution block, a signature row, a whitelist entry — for a feature that works on a subset of databases.

None of that is a claim it *cannot* be done. If the partial-support tradeoff is judged worth taking, the safe branch is well-defined and this paragraph is the place to revisit it. What must **not** happen is reopening it on subtype detection alone for the `propertyUrl`-present branch: that branch is still genuinely ambiguous, and the public REST API remains untested (the only available credential is an `mcp.notion.com` OAuth token, which `api.notion.com` rejects) — and even an explicit discriminator there would answer subtype, not companion state.

1. Resolve each entry to a ticket:
   - Numeric / prefixed → normalize via `ID normalization` above, then run a DB-scoped `fetchTicket`. Skips the project-scoping guardrail for this lookup (we're within the same DB by construction).
   - Otherwise (title) → titles are stored as `[<KEY>-<n>] <bare title>` (see "Title prefix"), but a caller passing a title reference is expected to pass the bare form, same as every other caller in this file. First strip any leading `[<KEY>-<n>] ` from the caller's string too, so an already-prefixed string still matches — the adapter owns the prefix on both sides of the comparison, never the caller. Query the DB with a filter on the title-typed property **containing** the stripped string (a stored, prefixed title can never satisfy an equality filter against a bare candidate), then, in memory, strip the prefix from each returned page's live title — the same normalisation `fetchTicket` applies on read — and keep only the pages whose stripped title equals the caller's stripped string exactly. On zero matches raise: *"`setDependencies`: no ticket with title '<x>' in this DB"*. On multiple matches raise: *"`setDependencies`: title '<x>' is ambiguous (N matches); use a numeric ID instead"*.

   Each resolved entry yields the `key`, `title` (prefix-stripped), and `url` the render needs. Resolution order is the caller's order; do not sort.
2. Render one bullet per resolved blocker, in that order:

```
- [STO-67] Add Litecoin config schema · https://notion.so/…
- [STO-68] Implement LtcConnector · https://notion.so/…
```

   Each line is `[{key}] {title} · {url}`.

   **Plain bullets, not to-do blocks, and no status** — a deliberate divergence from `## Tasks`, which renders both. `refreshEpicTasks` can afford live statuses because it is re-run on every resolution (`/notion-dev:ticket` Phase 8, `/notion-dev:finalize` Phase 3) and points readers at a live column for truth. This section is written **once**, at Pass-2 of mission creation, and nothing ever refreshes it: a checkbox left unticked after its blocker ships asserts something false, where no checkbox asserts nothing. The `url` carries the navigability the relation column used to provide, so a reader can still click through for live status.
3. `upsertSection(id, "Blocked by", <rendered bullets>)` — replacement semantics, so re-running a mission re-renders the section instead of stacking a duplicate.

Safe to call repeatedly. Never raises over the live schema — the only raise paths are the two title-resolution failures in step 1.

## getSelectOptions(configKey)

Read-only. Used by callers (e.g. `/notion-dev:create-task`) to decide whether a proposed option name is new.

1. `configKey` is the config key the caller is asking about (`phaseProperty`, `epicProperty`, or a sibling) — the caller names it directly (e.g. invoking `getSelectOptions(phaseProperty)`); resolve it against `.claude/notion-dev.config.json` to get its configured live column name (e.g. `"Phase"`). This lookup runs key → live name only — the adapter never needs to go the other direction.
2. Fetch the data source schema via `mcp__notion__notion-fetch` on the configured `databaseId` (or `dataSourceId` if set).
3. Locate the property named by the live column name resolved in step 1.
4. If it's `select`, `multi_select`, or `status`, return the list of option names (`[string]`).
5. If that live column name is missing from the live schema entirely, return `null`. Record `missing-property:<configKey>` per `notion-dev:issue-log`, citing the exact key the caller named in step 1 — annotated inline the same way `createTicket`'s `option-missing:<propertyName>` citation already is (e.g. "here, `epicProperty`") — never the live column name itself, and never re-derived from it. When the caller has no owning config key to name (e.g. a name drawn from `staticProperties`), apply the fallback in `issue-log/SKILL.md`'s signature-grammar section instead.
6. If the property exists but is some other type, return `null`. Record `wrong-type:<configKey>` per `notion-dev:issue-log`, same rule, with the same `staticProperties` fallback when the caller has no key to name.

Never logs a **warning** on `null` — callers use the `null` return as a signal to skip downstream logic, unchanged by the above. Recording an issue-log entry (steps 5–6) is not a warning: it is the adapter citing the exact config key the caller named for this call, while every caller keeps receiving the same bare `null` and the same control flow either way.

## addSelectOption(configKey, optionName)

Mutates the live DB schema by appending an option to a Select property. **Only invoke after explicit user confirmation** — adding options alters shared state visible to everyone using the DB.

1. `configKey` is the config key the caller names directly, same rule as `getSelectOptions`; resolve it against config to get its live column name. Fetch the data source schema; confirm the resolved live column name exists and is `select` or `multi_select`. Raise if not — record `missing-property:<configKey>` when absent, or `wrong-type:<configKey>` when it exists but isn't Select/Multi-Select, per `notion-dev:issue-log`, citing the exact key the caller named, annotated inline the same way `createTicket`'s `option-missing:<propertyName>` citation already is (e.g. "here, `epicProperty`"). When the caller has no owning config key to name (e.g. a name drawn from `staticProperties`), apply the fallback in `issue-log/SKILL.md`'s signature-grammar section instead.
2. If the option already exists (case-insensitive match), no-op and return.
3. Call `mcp__notion__notion-update-data-source` with a property update that extends the option list by one entry. Pick a default color deterministically (e.g. round-robin from the standard Notion palette) — don't leave it unset.
4. Return after the MCP confirms the update.

Never adds options to `status` properties — those are workflow-scoped and should be managed by an admin in Notion directly.

## Epic containers

An **epic** is a page in this same database where `epicMarkerProperty` (a Checkbox) is `true`, and its own `parentTaskProperty` is empty — the empty-parent check is a sanity check only (an epic has no parent of its own), not part of what makes it an epic. Children still typically carry the same `epicProperty` (Select) value as the epic page, for visual grouping in DB views, but that Select value is display metadata, not identity: a ticket carrying an `epicProperty` value, with no children or even with an ordinary Sub-items child, is **not** a container unless `epicMarkerProperty` is `true`. Epics are identified by this explicit marker, not by shape — shape alone is ambiguous: a legacy Epic-tagged *ticket* on a database upgraded to Notion's native Sub-items relation can pick up an ordinary sub-item and satisfy every structural signal an epic does (empty parent, Epic tag, a child); only the marker tells them apart, and there is no requirement on child count left to lean on instead — a freshly created epic with **zero** children is a perfectly valid epic.

### Marker usability rule

**This is the single statement of what it means to read `epicMarkerProperty`. Every operation that reads it cites this rule rather than restating a partial guard.**

Usability is a property of the **live database schema**, not of any one page. The marker is **usable** only when it both **exists on the live DB** and **is a `checkbox` type**. Exactly two schema states make it unusable, and they degrade **identically** — an operation may not distinguish them in its *behavior*. It must still distinguish them to pick the right **signature**, which is a reporting concern, not a control-flow one: same branch taken, different name recorded.

| Live **schema** state | Usable? | Behavior |
|---|---|---|
| Absent from the DB | no | degrade (below) |
| Present but **not** a Checkbox | no | degrade (below) — *identical to absent* |
| Present **and** Checkbox-typed | **yes** | proceed; the per-page value now decides (next table) |

Only once the schema is usable does the **per-page** value mean anything. That is a separate, routine question:

| Per-page value (marker usable) | This page is… | Logged? |
|---|---|---|
| `true` — checked | **an epic** (subject to the empty-parent sanity check above) | no |
| `false` — unchecked | not an epic | no — the overwhelmingly common case |

Keep the two levels distinct. "Unusable" never means "unchecked", and a page reading `false` on a perfectly good Checkbox is not a degradation of anything.

**To degrade** is to do all of: **never query or write the property**; warn once; return `null` — or, for a per-page guard, treat the page as **not an epic**; and never fall back to a structural guess. Validation happens **before** the property is used, not after a failure. Every operation that *detects* an unusable marker returns `null` (or treats the page as not-an-epic). `createTicket`'s `isEpic: true` write path is the one site that would instead skip just the marker write and still return `{ id, url }` — and it is precisely because that outcome would leave an unmarked page masquerading as an epic that `createEpic` performs the returning-`null` check itself, before `createTicket` is ever called. So that path is unreachable in practice; its check remains only as defence in depth, and it is not an exception to this definition so much as the reason the definition can stay simple.

**"Never query it" is load-bearing, not merely defensive.** A checkbox `true` filter applied to a text- or select-typed column is an **MCP query error, not an empty result** — so an operation that checks only presence and falls through to its query *fails outright* instead of degrading. That single clause is the whole difference between this rule and a presence-only guard, and it is why the type check cannot be treated as an optional refinement of the presence check.

**Recording, and who owns it.** `missing-property:epicMarkerProperty` when absent, `wrong-type:epicMarkerProperty` when present but not a Checkbox, per `notion-dev:issue-log`. Once per run per cause. Ownership follows *how the operation reaches the property*, so that one condition never gets two owners:

- **`fetchTicket` (step 4a)** reads the marker's live schema state on **every** ticket fetch and records for every path that flows through it. It is the one operation every ticket read goes through, so detecting the cause there once covers every caller without any of them changing.
- **`findEpics` and `createEpic`** reach the live schema **directly, without `fetchTicket`** — they are genuinely separate detection paths, reachable (via `/notion-dev:create-task`) with no preceding `fetchTicket` at all, and so they record on their own.
- **`getEpicContext` reaches the marker *via* `fetchTicket`** and therefore **does not record**. It still degrades exactly as above; the recording was already done by the caller's own preceding `fetchTicket`. Recording there too would give one condition two owners.
- **`createTicket` records nothing about the marker, ever.** It still applies the usability check on its `isEpic: true` write path — a wrong-typed marker is never written to — but that check is **defence in depth, unreachable by construction**: the only caller that passes `isEpic: true` is `createEpic`, which has already returned `null` on an unusable marker before calling. Do not add recording here on the theory that it is a direct-schema path: the branch cannot execute, so it would be a signature that never fires, and on the `isEpic`-unset path (every ordinary task creation) the marker is not read at all and logging would fire on every run against a marker-less DB.

Both marker signatures are already in the registry — no operation needs a new one.

### How the two required properties fail differently

`parentTaskProperty` and `epicMarkerProperty` are both required for epic containers to function, but they fail differently. When `epicMarkerProperty` is **unusable** (per the rule above — absent *or* wrong-typed), epics cannot be identified **at all**: every operation below degrades to a no-op with one warning, and the guard/validation sites (`findEpics`, `getEpicContext`, `epic-update`, `/notion-dev:ticket`'s epic guard) treat every page as **not an epic** rather than fall back to any structural guess — guessing from shape is exactly the bug this marker exists to close. When `parentTaskProperty` alone is unusable (absent, or present but not a self-referential Relation — see "Property type handling"), a marked epic can still be identified but can never gain children, and the plugin falls back to plain Epic-select tagging for containment purposes.

## createEpic({ name, overview, type?, assignee? })

1. If either `parentTaskProperty` or `epicMarkerProperty` is **unusable** on the live DB, warn once and return `null` — the caller degrades to Epic-select tagging. For `epicMarkerProperty`, "unusable" is defined by the **"Marker usability rule"** above: absent, **or present but not a Checkbox** — both degrade identically here, and this check runs *before* step 3 writes the marker, so a wrong-typed marker never reaches a write. Record `missing-property:epicMarkerProperty` (absent) or `wrong-type:epicMarkerProperty` (present but not a Checkbox) per `notion-dev:issue-log` — `createEpic` queries the DB schema directly, without `fetchTicket`, so per that rule's ownership split it records on its own. For `parentTaskProperty`, "unusable" means absent or not a self-referential Relation (see "Property type handling"); record `missing-property:parentTaskProperty` when it is absent, or `wrong-type:parentTaskProperty` when it is present but not a self-referential Relation, per `notion-dev:issue-log`. `createEpic` must record this itself: it reads the live schema directly, reachable from `/notion-dev:create-task` with no `fetchTicket` in front of it, and `fetchTicket` records nothing for this property — so leaving it out would make a wrong-typed `Parent task` observed here a condition nobody records.
2. Compose the body as two sections:
   - `## Overview` — the `overview` argument: a short statement of the initiative or incident.
   - `## Tasks` — empty at creation; the epic-refresh step populates it later.
3. Call `createTicket({ title: name, body, type, assignee, epic: name, isEpic: true })`. Reusing the normal creation path means the epic gets an ID, the title prefix, `Creation Date`, `staticProperties`, the assignee, and now `epicMarkerProperty` itself, all for free. Status is `"Backlog"` like any new ticket. `createTicket` returns only `{ id, url }` — it does not expose `pageId`. This also sets `epicProperty` to `name` when that property exists on the live DB, via `createTicket`'s own absence-tolerant Mission-metadata write — the Select tag stays useful for grouping in DB views, but per "Epic containers" above it is display metadata, not what makes this page an epic. **The page and `epicMarkerProperty` are written in this single `createTicket` call** — there is no intermediate state where the page exists but is not yet marked as an epic, so a create that fails partway, or a fetch/update failure afterward, can never leave an unmarked, complete-looking epic page for `findEpics()` to miss and a retry to duplicate. This is the same atomicity guarantee `createTicket`'s follow-up-creation path (see its `PROVENANCE` note, and its `parent`-relation note above) already documents for a page-identifying property — write it with the page, not after.
3a. Resolve `pageId`: call `fetchTicket(id)` on the id just created and read `metadata.pageId` off the result. This is the only source `createEpic` has for the Notion page id — one extra read, but unavoidable given `createTicket`'s return shape. This read is not load-bearing for the marker: `epicMarkerProperty` is already set by the time this runs, so a failure here only costs `createEpic` its `pageId` return value, never the page's epic status.
4. `parentTaskProperty` is left empty — an epic has no parent. `phase`, `step`, and `dependsOn` are never set on an epic.
5. `type` defaults to the dominant child type when the caller knows the children, else `feature`.
6. Return `{ id, key, url, pageId }` — `pageId` from step 3a; `key` is the logical ticket key (`"STO-67"`) derived the same way `fetchTicket` derives it (`project.key` + the numeric `id` from step 3), so callers can display `[{key}] {name}` without constructing the prefix themselves.

## setParent(id, epicId)

**No caller in this plugin currently invokes this operation.** Every parenting path writes the relation through `createTicket`'s `parent` argument instead (steps 1a and 2), which is deliberate: writing it with the page is atomic, whereas a create-then-`setParent` sequence has a window where the child exists unparented. `/notion-dev:create-task`'s `--parent` flag flows to that argument, not here. This operation stays specified because re-parenting an *existing* ticket has no other path and is the obvious next caller — but do not describe any current flow as going through it, and do not treat it as the reference implementation for the parenting **write**: `createTicket` step 1a is, and its atomicity is the reason. The shared usability check both apply is stated once under "Property type handling", so neither operation is the other's source for it. Its guard and recording below are part of the contract and must stay consistent with the other `parentTaskProperty` sites regardless of being uncalled.

1. If `parentTaskProperty` is **unusable** on the live DB — absent, **or present but not a self-referential Relation** — warn once and return, **without writing to or filtering on the property**. Both states degrade identically (see this property under "Property type handling"), and for the same reason the marker rule gives: a relation write or a relation-`contains` filter against a non-relation column is an MCP error, not a silent no-op. Record `missing-property:parentTaskProperty` when the property is **absent**, or `wrong-type:parentTaskProperty` when it is present but not a self-referential Relation, per `notion-dev:issue-log` — identical behavior, separate conditions, separate signatures.
2. Resolve `id` and `epicId` to page IDs via `fetchTicket`.
3. If they are the same page, raise: *"`setParent`: a ticket cannot be its own parent"*.
4. Call `mcp__notion__notion-update-page` setting `parentTaskProperty` to a single-element Relation list containing the epic's page id. Replacement semantics are correct here — a ticket has exactly one parent.

## refreshEpicTasks(epicId)

Re-renders an epic's `## Tasks` section from its live children. **The single owner of that section's format** — callers never render it themselves, so `/notion-dev:create-task` and the epic-update flow cannot drift apart.

1. **If the epic page has no `## Tasks` section, warn once and return without writing one.** Step 6 renders through `upsertSection`, which *creates* a section that is absent — correct for an epic this plugin created, wrong for one it was merely pointed at. Measured in a client: an epic organised its children under a hand-authored, curated heading, and creating `## Tasks` beside it would have appended a second ~50-item list that disagrees with the curated one from the first subsequent status change, with nothing on the page saying which governs — the precise opposite of the coherent-document purpose this section exists for. `refreshAcceptanceCriteria` already declines for the same reason (its step 1: *"inventing the section here would fabricate a definition of done"*), so the asymmetry between the two was the defect, not the rule. Creating the section belongs to `/notion-dev:create-task`, which is authoring the epic; never to a refresh.
2. If `parentTaskProperty` is **unusable** on the live DB — absent, **or present but not a self-referential Relation** — warn once and return without re-rendering. Both states degrade identically (see this property under "Property type handling"): with no usable containment relation there is no way to enumerate the epic's children, so any `## Tasks` section this rendered would be empty-by-accident rather than empty-in-fact — worse than leaving the existing one untouched. Record `missing-property:parentTaskProperty` when the property is **absent**, or `wrong-type:parentTaskProperty` when it is present but not a self-referential Relation, per `notion-dev:issue-log`. **Record here, do not defer to `listEpicChildren`**: this step returns before step 3 runs, so `listEpicChildren` never observes the condition on this path and could not record it. (The two are not a double-log risk in any case — both signatures are capped once/run.) This step exists only to return early, before step 4 renders an accidentally-empty section over a good one.
3. `listEpicChildren(epicId)` — applies the same usability check for callers that reach it directly; unreachable-as-unusable from here, since step 2 has already returned in that case.
4. Render one Notion to-do block per child, ordered by id:

```
- [x] [STO-67] Fix stale index — Implemented
- [ ] [STO-68] Add cache metrics — In Progress
- [ ] [STO-69] Backfill historic wallets — Backlog
```

   The box is ticked when the child's `status` is in the **resolved set**. Each line is `[{key}] {title} — {status}` from the `listEpicChildren` entry. **When updating an existing line rather than re-rendering the section, match the backslash-escaped bracket form too** — a read-back line arrives as `- [ ] \[<KEY>-<n>\] <title> — <status>`, and an `old_str` written against the unescaped form fails with `validation_error: No matches found`. See "Title prefix" for the canonical rule.
5. Prepend this note as the section's first paragraph: *"Snapshot as of the last resolution — see the Parent task column for live status."*
6. `upsertSection(epicId, "Tasks", <rendered blocks>)`.

Safe to call repeatedly. `upsertSection` replaces only up to the next top-level heading, so a `## Resolution Log` below it is never touched.

