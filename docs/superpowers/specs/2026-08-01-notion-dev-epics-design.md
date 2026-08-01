# notion-dev: Creation Date, ID-prefixed titles, Epic containers, and epic resolution logs

**Date:** 2026-08-01
**Plugin:** `plugins/notion-dev` (quick-dev is not affected)
**Target version:** `0.7.0` → `0.8.0` (minor — new capability)

## Goal

Four related changes to the notion-dev plugin:

1. Support a `Creation Date` property — detected or created by `/notion-dev:init`, populated at ticket creation.
2. Prefix every ticket title with its ticket ID: `[STO-67] Large-Wallet Stale-Index Incident`. Applies to epics too.
3. Introduce **Epic containers** — a real page in the ticket DB that groups related tickets, so an incident and everything that follows from it live under one parent.
4. When a ticket resolves, append an update entry to its epic so the epic accumulates the history and current state of the issue.

## Non-goals

- Backend-agnostic ticket abstractions. Every change here is Notion-specific and lives in `notion-dev`.
- Changes to `quick-dev`.
- Release/deployment status transitions. The plugin still stops at `Implemented`.
- Retroactive migration of existing tickets. Title prefixes are backfilled opportunistically (§3), never in a batch pass.

---

## 1. Config and schema additions

Three additions to `ticketSystem` in `schema/notion-dev.config.schema.json`, all absence-tolerant.

| Key | Type | Default | Behavior |
|---|---|---|---|
| `creationDateProperty` | string | `"Creation Date"` | Property holding the ticket's creation timestamp. |
| `parentTaskProperty` | string | `"Parent task"` | Self-referential Relation linking a ticket to its epic container. Distinct from `dependsOnProperty`. |
| `statusMap.done`, `statusMap.cancelled` | string | `"Done"`, `"Cancelled"` | **Read-only** logical statuses. |

### 1.1 `creationDateProperty` type tolerance

The adapter reads the live property type and branches:

- **`date`** — `createTicket` writes the current timestamp (`date.start` = ISO 8601 UTC, with time).
- **`created_time`** — the plugin never writes it; Notion auto-populates. Reads work identically.
- **Absent from the live DB, or any other type** — skip the write, log **one** warning per run: `"creationDateProperty '<name>' not found or not a date/created_time property on DB; skipping creation date write"`. Never abort.

`/notion-dev:init` creates a `date` property when the slot is missing (§8).

### 1.2 `statusMap` gains read-only entries

Today `statusMap` documents logical statuses the plugin **writes** (`inProgress`, `implemented`). `done` and `cancelled` are added as entries the plugin **only reads**. The skill and schema must say this explicitly, because the distinction is otherwise invisible and a future reader will assume the plugin transitions tickets into them.

The **resolved set** is the set of live Notion option names produced by `statusMap.implemented`, `statusMap.done`, and `statusMap.cancelled`. A child ticket counts as resolved when its status matches any member, case-insensitively. This set is used by exactly one thing: the epic-close check (§6.5).

A missing `done` or `cancelled` key falls back to its default option name. If that option does not exist on the live DB, it simply never matches — a status the plugin has not been told about is not resolved, so the epic does not auto-close. Wrong in the safe direction.

---

## 2. Terminology

- **Epic** — a page in the ticket database where `parentTaskProperty` is empty, `epicProperty` (Select) is set, and one or more other pages point at it via `parentTaskProperty`.
- **Epic name** — the `epicProperty` Select option value. Shared by the epic page and every child.
- **Child** — a page whose `parentTaskProperty` points at an epic page. Carries the same `epicProperty` value.
- **Resolved set** — see §1.2.
- **Title prefix** — the `[<KEY>-<n>] ` string at the head of a ticket title, where `<KEY>` is `project.key`.

An epic is identified structurally (empty parent + Epic select + ≥1 child), not by a dedicated property. A page with an Epic select and an empty parent but **no** children is not yet an epic — it is an epic-in-waiting, and `findEpics` still returns it so a first child can attach.

---

## 3. Ticket ID in the title

The prefix is owned entirely by the `ticket-system` skill. **No caller ever sees or constructs it.** Callers pass and receive bare titles; the adapter adds the prefix on write and strips it on read.

### 3.1 Prefix format and detection

Format: `[<KEY>-<n>] ` — literal bracket, `project.key`, hyphen, the numeric ID, closing bracket, one space.

Detection regex (case-insensitive on the key, tolerant of stray inner whitespace):

```
^\[\s*<KEY>-(\d+)\s*\]\s*
```

Only a prefix matching **this project's** `project.key` is recognized. A leading `[FOO-12] ` on a DB shared with another project is *not* a prefix — it is part of the title — and is left alone.

### 3.2 `createTicket`

- **`unique_id` ID column (the canonical schema).** The ID does not exist until the page does. So: create the page with the bare title → read the assigned ID off the created page → call `mcp__notion__notion-update-page` to set the title to `[<KEY>-<n>] <title>`. Two calls; unavoidable.
- **`number` ID column (the max+1 fallback).** The ID is computed before creation, so the prefixed title is set in the single create call.

If the retitle call fails, the page exists with a bare title. Do **not** roll back — report the created ID and URL, and note the missing prefix. §3.4's backfill repairs it on the next `updateTicket`, and §3.3's strip tolerates its absence, so nothing downstream breaks.

### 3.3 `fetchTicket`

Returns `title` with the prefix **stripped**. Adds `metadata.rawTitle` carrying the literal Notion title for anything that needs it.

This is what keeps existing consumers correct without edits: `commands/ticket.md` 2.1 computes the branch slug by kebab-casing the ticket title, so stripping at the adapter keeps branches as `ticket/STO-67-large-wallet-stale-index` instead of `ticket/STO-67-sto-67-large-wallet-stale-i`.

### 3.4 `updateTicket` — write and backfill

- When `patch.title` is provided: strip any prefix matching §3.1 from the incoming value, then write `[<KEY>-<n>] <stripped>`. Idempotent; corrects a prefix carrying the wrong number; never double-prefixes.
- When `patch.title` is **absent**: still inspect the live title. If it has no prefix, or a prefix whose number does not match this page's ID, rewrite it. This is the backfill path that makes `/notion-dev:create-task existing-ticket:<id>` repair legacy titles without any change to that command.

### 3.5 `unique_id` prefix mismatch

A Notion `unique_id` column carries its own prefix, configured on the property. When it differs from `project.key`, the title prefix still uses `project.key` (config is the source of truth for the plugin's naming, and branch names already depend on it). Log **one** warning per run: `"ID column prefix '<live>' differs from project.key '<KEY>'; titles use '<KEY>'"`.

---

## 4. Epic operations in `ticket-system`

### 4.1 New operations

| Operation | Arguments | Returns |
|---|---|---|
| `createEpic` | `{ name, overview, type?, assignee? }` | `{ id, url, pageId }` |
| `findEpics` | — | `[{ id, pageId, name, title, url, overview }]` |
| `setParent` | `id`, `epicId` | `void` |
| `listEpicChildren` | `epicId` | `[{ id, title, status, url }]` |
| `appendToSection` | `id`, `sectionName`, `content` | `void` |

`createTicket`'s argument object gains `parent?` (an epic's ticket ID or page ID) alongside the existing `epic?`.

### 4.2 `createEpic({ name, overview, type?, assignee? })`

1. Compose `body` as two sections:
   - `## Overview` — the `overview` argument (a short statement of the initiative or incident).
   - `## Tasks` — empty at creation; §6.3 populates it.
2. Call `createTicket({ title: name, body, type, assignee, epic: name })` — reusing the normal creation path, so the epic gets an ID, the title prefix (§3.2), `Creation Date`, `staticProperties`, and the assignee for free.
3. `parentTaskProperty` is left empty (an epic has no parent). `phase`, `step`, and `dependsOn` are never set on an epic.
4. `type` defaults to the dominant child type when the caller knows the children, else `feature`.
5. Status is `Backlog`, like any new ticket.

Returns the created ticket's `{ id, url }` plus the resolved `pageId`.

### 4.3 `findEpics()`

Query the database (or data source) for pages where `epicProperty` is not empty **and** `parentTaskProperty` is empty. Return one entry per page with its ID, page ID, Epic select value (`name`), stripped title, URL, and the text of its `## Overview` section when present.

- `epicProperty` absent from the live DB → return `[]` with one warning. Epic features degrade off entirely.
- `parentTaskProperty` absent → return `[]` with one warning. Without the relation there is no container to point at; Epic-select tagging still works (today's behavior) but no epic pages are created or matched.

### 4.4 `setParent(id, epicId)`

1. Absent `parentTaskProperty` → warn once, return. (Mirrors `prProperty` tolerance.)
2. Resolve both `id` and `epicId` to page IDs via `fetchTicket`.
3. Reject a self-reference (`id == epicId`) with a clear error.
4. Relation writes in Notion are replacement, not append — `setParent` writes a **single-element** list. A ticket has exactly one parent.

### 4.5 `listEpicChildren(epicId)`

Query the DB for pages whose `parentTaskProperty` contains the epic's page ID. Return `{ id, title (stripped), status (the live option name), url }` for each, ordered ascending by `id`. Absent `parentTaskProperty` → `[]` plus one warning.

### 4.6 `appendToSection(id, sectionName, content)`

The append-only counterpart to `upsertSection`. Where `upsertSection` **replaces** a section's children, `appendToSection` **adds to the end** of them.

1. `fetchTicket(id)` → `pageId`.
2. Locate `## <sectionName>` (base-text match, ignoring trailing Notion attributes such as `{color="..."}`).
3. **Absent** → create it at the end of the page, applying the palette color from §7, then write `content` beneath it.
4. **Present** → append `content`'s blocks immediately before the next top-level (`##`) heading, or at end of page when it is the last section. Existing children are never read back, rewritten, or reordered.

`content` is markdown, rendered with the same block conventions as `upsertSection`.

### 4.7 `createTicket` gains `parent?`

After the page is created (and retitled, per §3.2), if `parent` is provided and `parentTaskProperty` exists on the live DB, call `setParent(newId, parent)`. Absence-tolerant, same as `epic` / `phase` / `step`.

`epic` and `parent` are independent arguments and both should normally be set together — the Epic select is what makes the grouping visible in DB views and filters; the Parent task relation is what makes it a container. A caller that sets only one gets a valid but partially-grouped ticket; the commands in §5 and §6 always set both.

---

## 5. `/notion-dev:create-task` — attaching to an epic

### 5.1 Mission path (Phase 2.5.2, extended)

After the Epic **select** value is reconciled against the live options (existing behavior, unchanged), resolve the Epic **page**:

1. Call `findEpics()`.
2. A returned epic whose `name` matches the reconciled Epic value (case-insensitive) → reuse it. Record its ID as `EPIC_ID`.
3. No match → `createEpic({ name: <reconciled Epic value>, overview: <2-4 sentence distillation of the mission's goal from the source body>, type: <dominant task type>, assignee: <from Phase 2.75> })`. Record `EPIC_ID`.
4. `findEpics()` returned `[]` because the DB lacks `epicProperty` or `parentTaskProperty` → `EPIC_ID = undefined`; continue with today's degraded behavior.

Phase 3.2 Pass 1 passes `epic: <name>` **and** `parent: EPIC_ID` on every `createTicket`.

**New Pass 1.5** (between Pass 1 and the dependency wiring in Pass 2): refresh the epic's `## Tasks` section per §6.3. This runs even though no ticket has resolved yet, so the epic reads as a real plan the moment it exists.

Phase 4's mission report gains a first line naming the epic: `Epic: [STO-66] <name> · <url>`.

### 5.2 Single-ticket path (new Phase 2.6)

Runs after Phase 2.5 returns `kind: "single"`, and before Phase 2.75 (assignee). The two are independent — the position is fixed only so the phase numbering stays stable across runs.

1. Call `findEpics()`. Empty (no epics exist, or the DB lacks the properties) → skip silently. **No prompt.**
2. Match the ticket's title and `## Requirements` against each epic's `name` and `## Overview`. This is a semantic judgment, not string matching: an epic is a plausible candidate when the new ticket is work on the same incident, feature, or investigation.
3. **Zero plausible candidates → skip silently.** No prompt. This is the common case and routine single-ticket runs must stay as quiet as they are today.
4. **≥1 plausible candidate** → `AskUserQuestion`: "This looks related to an existing epic. Attach it?"
   - **Attach to `[STO-66] <name>`** (best candidate first; further candidates as additional options) — record `EPIC_ID` and the epic name.
   - **Pick another** — show the full `findEpics()` list.
   - **No epic** — proceed unattached.
5. When an epic is chosen, Phase 3.2's single-ticket `createTicket` passes `epic: <epic name>` and `parent: EPIC_ID`, and Phase 4's report names the epic.

`existing-ticket` source mode skips Phase 2.6 entirely, matching how it skips Phase 2.5 — elaborating an existing ticket never re-parents it.

**Non-interactive mode** (§5.3) never prompts here: the epic is either supplied by the caller or omitted.

### 5.3 Non-interactive mode

`/notion-dev:create-task` gains five flags. All are optional and parsed off the front of the argument string before the source-selector parsing rule runs, so they never interfere with free-prompt text:

| Flag | Effect |
|---|---|
| `--non-interactive` | Never pause for input; see the phase table below. |
| `--context-file=<path>` | Path to a markdown context packet. Seeds the interviewer, and is the proxy respondent's evidence base (below). Valid with or without `--non-interactive`. |
| `--epic=<name>` | Skip Phase 2.6's matching; use this Epic select value verbatim. |
| `--parent=<id>` | Epic page ticket ID for the `parentTaskProperty` relation. Normally passed together with `--epic`. |
| `--assignee=<id>` | Skip Phase 2.75's resolution; use this Notion user id. |

`--epic`, `--parent`, and `--assignee` are what let §6.2 file a follow-up as a sibling under the resolving ticket's epic without any prompting.

`--non-interactive` changes these phases:

| Phase | Interactive | Non-interactive |
|---|---|---|
| 2.1 interview | Questions go to the user | Questions go to a **proxy-respondent subagent** (below) |
| 2.2 confirm | `create` / `revise` / `cancel` | Auto-`create` |
| 2.5 breakdown | May return a mission | Auto-collapse to `single` |
| 2.5.2 epic reconcile | Prompt on a new Epic name | N/A — collapsed to single |
| 2.6 epic attach | Prompt on candidates | Use `--epic` / `--parent`, or attach to none |
| 2.75 assignee | Prompt when unresolved | Use `--assignee`, else `defaultAssignee`, else leave unassigned |
| 3.1 type | Prompt when unclear | Infer; default `improvement` |

**Proxy-respondent subagent.** The interviewer runs in full — depth calibration, clarity audit, all of it — but its questions are answered by a **fresh subagent**, not by the main loop.

This is deliberate. In the follow-up-filing flow (§6.2) the main loop is the agent that *wrote* the deferred item during review. Having it answer its own interview restates its own assumptions and produces a ticket that looks elaborated but contains no new information. A fresh agent, given the ticket, the merge diff, and the review thread, has to actually read them.

The subagent receives a context packet and a single instruction: answer the interviewer's questions as the requester would, grounding every answer in the packet, and say "unknown — needs human input" rather than inventing detail. Answers of that form flow into the ticket's `## Open Questions`.

The context packet is a markdown file assembled by the caller. For a follow-up (§6.2) it contains:

- The resolved parent ticket's title, body, and URL.
- The PR URL and `git show --stat <merge-commit>`.
- The review finding verbatim.
- The rationale recorded when the finding was deferred.

§6.2 writes it to `$REPO_ROOT/.claude/notion-dev/followup-<KEY>-<id>-<n>.md` — the same self-ignored directory the ledger lives in, so it never appears in `git status` or contaminates a branch. It is left in place after the run as a record of what the ticket was generated from.

`--context-file` without `--non-interactive` is accepted and simply seeds the interviewer with extra context.

**Auto-collapse to `single`.** A deferred review finding is one item by construction. Running the breakdown skill and then ignoring a mission result would be wasted work, so non-interactive mode instructs `task-breakdown` to return `single` and skips 2.5.2/2.5.3 entirely.

---

## 6. Epic update on ticket resolution

A single shared procedure, invoked from **both** `commands/ticket.md` Phase 8 and `commands/finalize.md` Phase 3, immediately after `updateStatus(id, "implemented")` and before the post-merge hooks.

The two commands must not diverge. The procedure is specified once here and both command files reference it by the same step numbers.

### 6.1 Resolve the epic

`fetchTicket(id)` already ran. Read the page's `parentTaskProperty`.

- Empty, or the property is absent from the live DB → **skip §6.2 through §6.5 entirely.** Not an error; most tickets have no epic.
- Set → `EPIC_ID` is the referenced page. Fetch it for its title and Epic name.

### 6.2 File deferred follow-ups

Source: `REVIEW_REPORT`'s deferred follow-ups (the same list already written to the ticket's `## Merged` section).

- **Interactive**: for each item, `AskUserQuestion` — **File as ticket** / **Skip**. Default File.
- **`--non-interactive`**: file every item. Nothing is left deferred.

Each filed item runs `/notion-dev:create-task` per §5.3 with:

```
--non-interactive --context-file=<packet> --epic="<epic name>" --parent=<EPIC_ID> --assignee=<resolving ticket's assignee> prompt:<finding title>
```

so the new ticket lands as a sibling under the same epic. `/notion-dev:create-task` has no `disable-model-invocation` flag (unlike `ticket` and `finalize`), so this is a normal command invocation.

Record for §6.4 and §6.5:
- `FILED` — `[{ id, title, url }]` for each created ticket.
- `UNFILED` — items the user chose to skip.

A create-task failure here is **non-fatal**: log it, add the item to `UNFILED`, and continue. Ticket bookkeeping must never fail a run whose merge already landed.

When `REVIEW_REPORT` has no deferred follow-ups, both lists are empty and this step is a no-op.

### 6.3 Refresh the epic's `## Tasks`

`listEpicChildren(EPIC_ID)`, then `upsertSection(EPIC_ID, "Tasks", <rendered list>)`.

Rendering, one line per child, ordered by ID:

```
- [x] [STO-67] Fix stale index — Implemented
- [ ] [STO-68] Add cache metrics — In Progress
- [ ] [STO-69] Backfill historic wallets — Backlog
```

The checkbox is ticked when the child's status is in the resolved set (§1.2). Rendered as Notion to-do blocks, matching the `Acceptance Criteria` convention.

This mirror is refreshed **only here** — on each resolution log entry. Between resolutions it lags reality. That is an accepted tradeoff: the live view is the Parent-task relation column in Notion's UI, and the mirror exists so the epic reads as a coherent document. The `## Tasks` heading must state this: *"Snapshot as of the last resolution — see the Parent task column for live status."*

`upsertSection` is safe here precisely because §4.6 puts the log in its own `## Resolution Log` section: replacing `## Tasks` stops at the next top-level heading, so history is never clobbered.

### 6.4 Append the log entry

`appendToSection(EPIC_ID, "Resolution Log", <entry>)`.

Entry structure — a `divider` block, then:

```
### [STO-67] resolved — 2026-08-01 14:32 UTC
**Summary** — <2-4 sentences: what was actually done, distilled from the ticket's
`## Implementation` section and the merge>
**Follow-ups filed** — [STO-69] Backfill historic wallets · <url>   (omit when FILED is empty)
**Follow-ups deferred** — <item>                                     (omit when UNFILED is empty)
**Epic status** — 2 of 3 tasks resolved
**Next** — <what should happen next: the remaining blocker, or "epic complete">
```

The `###` heading and the divider are what §4.6 appends; `## Resolution Log` itself is created on first use.

`Epic status` counts against `listEpicChildren`, using the resolved set. When §6.5 closes the epic, this line reads `all N tasks resolved — epic closed`.

Timestamp is `date -u +"%Y-%m-%d %H:%M UTC"`.

### 6.5 Close the epic

Evaluate against the child list §6.3 already fetched — which was read *after* §6.2 filed its follow-ups, so newly filed tickets are in it. Do not re-query.

Close **only** when all of:

1. Every child other than the just-resolved one has a status in the resolved set (§1.2).
2. `FILED` is empty. Strictly redundant with (1) — a freshly filed follow-up is an unresolved child, so (1) already fails — but stated explicitly so the intent survives any future change to when the child list is read.
3. `UNFILED` is empty — a known-but-unfiled follow-up means the work is not finished.

Then `updateStatus(EPIC_ID, "implemented")`, and say so in the §6.4 entry's `Epic status` and `Next` lines.

Otherwise leave the epic's status untouched. The plugin never moves an epic *out* of a resolved status, and never sets an epic to `In Progress`.

Step ordering matters: §6.2 must run before §6.5, or a run that files a follow-up would close the epic the follow-up belongs to.

### 6.6 Failure tolerance

Every step in §6 is best-effort. A failure logs a warning and continues to the next step; the run's overall result is unaffected. The merge has already landed by this point, and epic bookkeeping is never worth failing a successful run over.

---

## 7. Epic guard in `/notion-dev:ticket`

New check in Phase 1.1, immediately after `fetchTicket(id)` and before the worktree resolution in 1.2.

The fetched page is an epic container when: `parentTaskProperty` is empty **and** `epicProperty` is set **and** `listEpicChildren(id)` returns ≥1 child.

Abort with:

```
[STO-66] <name> is an epic container, not an implementable ticket.
Pick one of its children:
  [STO-67] Fix stale index — Implemented
  [STO-68] Add cache metrics — In Progress
```

Hard abort in both interactive and non-interactive mode. This runs before Phase 2, so no worktree, branch, or status change happens.

An epic-in-waiting (no children yet) is **not** guarded — it is indistinguishable from a normal ticket that happens to carry an Epic tag, and blocking it would break the plain Epic-select tagging that works today.

---

## 8. `/notion-dev:init` changes

### 8.1 Create-new schema (3a-i)

The property table gains two rows:

| Property | Type | Options |
|---|---|---|
| `Creation Date` | Date | set by `createTicket` at creation |
| `Parent task` | Relation (self-referential) | links a ticket to its epic container; distinct from `Depends on` |

`Parent task` has the same creation caveat already documented for `Depends on`: if the create API cannot declare a self-referential relation before the DB's own ID exists, add it immediately afterward via `mcp__notion__notion-update-data-source`.

### 8.2 Use-existing detection (3a-ii)

Two additions to the detection pass:

- **`Creation Date`** — prefer a property named `"Creation Date"` (case-insensitive) of type `date` or `created_time`. If missing, scan for a single `created_time` property and offer it. If still unresolved, `AskUserQuestion`: **Add `Creation Date` (Date)** / **Bind to `<found>`** / **Skip** (writes are skipped at runtime with a warning). Record `creationDateProperty` only when the resolved name differs from the default.
- **`Parent task`** — scan for a self-referential relation **other than** the one bound to `dependsOnProperty`. Prefer the name `"Parent task"` (case-insensitive), then `"Parent item"` / `"Parent"`. If missing, `AskUserQuestion`: **Create `Parent task` (Relation)** / **Bind to `<found>`** / **Skip**. Record `parentTaskProperty` only when the resolved name differs from the default.

The **Create** option's prompt text must state the limitation plainly: *"The API creates a plain self-referential relation, not Notion's native Sub-items feature — grouping works identically, but rows render as a normal relation column rather than nested sub-rows. To get native rendering, enable Sub-items in the Notion UI first and re-run init to bind to it."*

### 8.3 Resolved-status prompt (new, in 3a-ii after the Status slot resolves)

`AskUserQuestion` (multi-select) over the Status property's live options: *"Which of these mean a ticket is resolved?"* Pre-check any option matching `Implemented` / `Done` / `Cancelled` case-insensitively.

Write `statusMap.done` and `statusMap.cancelled` from the picks. When the picks are exactly the defaults, follow the existing omit-when-default convention and write nothing.

On the **create-new** path (3a-i) the Status options are the plugin's own (`Backlog`, `In Progress`, `Implemented`), so this prompt is skipped and no keys are written.

### 8.4 Drift check

Two informational-only items (matching the `PR` and `Assignee` precedent — reported, never a hard drift):

- **Creation Date slot** — when `creationDateProperty` is in config, it should exist and be `date` or `created_time`.
- **Parent task slot** — when `parentTaskProperty` is in config, it should exist and be a self-referential relation.

### 8.5 Report

Step 11's summary gains one line naming which optional slots resolved: `Creation Date`, `Parent task`, and whether epic containers are available (both `epicProperty` and `parentTaskProperty` present).

---

## 9. Styling

The `ticket-system` palette table gains three entries, all written to **epic pages only**:

| Heading | Written by | Heading color | Intro callout | Icon |
|---|---|---|---|---|
| `Overview` | `createEpic` | `gray` | — | — |
| `Tasks` | §6.3 refresh | `blue` | — | — |
| `Resolution Log` | §6.4 append | `purple` | — | — |

No intro callouts — these sections are self-explanatory and a callout on every one would be noise. `Tasks` renders as to-do blocks (§6.3).

Zone dividers (the `Implementation` / `Merged` rule) do not apply to epic pages; §6.4's per-entry divider is its own convention.

---

## 10. Files changed

| File | Change |
|---|---|
| `schema/notion-dev.config.schema.json` | `creationDateProperty`, `parentTaskProperty`; `statusMap` description notes read-only entries |
| `skills/ticket-system/SKILL.md` | Largest change: 5 new operations, `parent?` on `createTicket`, title-prefix ownership, `Creation Date` handling, palette entries |
| `commands/init.md` | §8 in full |
| `commands/create-task.md` | Phase 2.5.2 epic-page resolution, Pass 1.5, new Phase 2.6, `--non-interactive` / `--context-file` (§5.3) |
| `commands/ticket.md` | Epic guard in 1.1 (§7); §6 procedure in Phase 8 |
| `commands/finalize.md` | §6 procedure in Phase 3 |
| `skills/task-breakdown/SKILL.md` | Minor: epic-name guidance — names should read as initiatives/incidents, since they now title a real page |
| `README.md` | Document the new properties, epic containers, and the resolution log |
| `.claude-plugin/plugin.json` | `0.7.0` → `0.8.0` |

`quick-dev` is untouched.

---

## 11. Testing

There is no test harness in this repo — the plugin is prompt-and-markdown. Verification is by inspection plus a live run:

1. **Schema validity** — the config schema is valid JSON Schema draft-07 and a config using every new key validates.
2. **Cross-file contract check** — every operation named in a command file exists in `ticket-system/SKILL.md` with matching arguments; every config key referenced by a skill exists in the schema; the §6 procedure reads identically in `ticket.md` and `finalize.md`.
3. **Live smoke run** on a scratch Notion DB: `/notion-dev:init` on a DB missing both new properties → creates them; `/notion-dev:create-task` with a multi-task source → epic page created, children parented, `## Tasks` populated, all titles prefixed; `/notion-dev:ticket` on the epic → refused with the child list; `/notion-dev:ticket` on a child through to merge → log entry appended, `## Tasks` refreshed; resolving the last child with no follow-ups → epic closes.

---

## 12. Known limitations

1. **Native Sub-items cannot be enabled via the Notion API.** Init creates a plain self-referential relation. Grouping and every plugin feature work identically; only the nested-row rendering differs. Enabling Sub-items in the Notion UI before running init gives the native look, and init binds to it.
2. **The `## Tasks` mirror lags.** Refreshed only on resolution (§6.3), by explicit choice. The heading says so.
3. **Two-call ticket creation has a failure window.** A failed retitle leaves a bare-titled page; §3.4's backfill is self-healing and §3.3 tolerates it.
4. **Epic auto-close is silent when unsure.** A child in a status not covered by the resolved set never counts as resolved, so the epic simply does not close.
5. **No batch migration.** Existing tickets get their title prefix only when something calls `updateTicket` on them.
