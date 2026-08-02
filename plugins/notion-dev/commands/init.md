---
description: Initialize the notion-dev plugin in this project. Configures ticket system, patches .mcp.json, writes .claude/notion-dev.config.json. Idempotent.
---

# /notion-dev:init

Interactive, idempotent setup. Produces `.claude/notion-dev.config.json` and a merged `.mcp.json` so that `/notion-dev:create-task`, `/notion-dev:ticket`, and `/notion-dev:finalize` work in this project.

**Standing rule — runtime issues.** Anything unexpected at runtime — for example an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, or a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens, not batched to the end of the run. That skill is **authoritative** for the full trigger list, the entry format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must **not** be logged; the examples here are illustrative, not exhaustive. The rule applies to conditions nobody enumerated in advance. A failure to write the log never fails the run.

## Steps

### 1. Preflight

Read project state:
- `git rev-parse --is-inside-work-tree` — fail with a clear error if not in a git repo.
- Detect the default branch: `git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'`; fall back to `master` then `main`.
- Detect tech stack by probing: `foundry.toml`, `Makefile`, `package.json`, `pyproject.toml`.
- Probe `gh` CLI: `command -v gh` and `gh auth status 2>&1`. Record whether `gh` is available and authenticated — used later in step 4.
- **Build-flow plugins (hard requirement).** `/notion-dev:ticket` needs both flows
  available regardless of which one triage picks. Check the available-skills list for:
  - superpowers: `superpowers:writing-plans`, `superpowers:subagent-driven-development`,
    `superpowers:receiving-code-review`
  - feature-dev: `feature-dev:feature-dev`

  For each plugin whose skills are missing, install at project scope:
  `claude plugin install superpowers@claude-plugins-official --scope project` and/or
  `claude plugin install feature-dev@claude-plugins-official --scope project`. The
  installs write enablement to `.claude/settings.json` — commit that change once with
  `git add .claude/settings.json && git commit --only .claude/settings.json -m "chore: enable build-flow plugins"`
  (the `git add` is required: `--only` alone errors on an untracked file, and
  `.claude/settings.json` is newly created when this is the first project-scoped plugin).
  Exception: if the repo gitignores the path (`git check-ignore -q .claude/settings.json`
  succeeds), skip the add/commit entirely — an ignored file never shows in `git status`,
  so it cannot trip the dirty-tree gate the commit exists to protect; do not force-add
  over the project's ignore rules. Then
  STOP with **one** combined message naming everything installed: "<plugin(s)> installed
  at project scope (settings change committed). Run `/reload-plugins`, then re-run
  `/notion-dev:init`." Newly installed plugins only load after a reload — do not continue
  without them, and never stop twice when both were missing. If an install command
  fails, abort with the manual instruction ("/plugin marketplace → <plugin>") and write
  no config (no-partial-config rule).
- Check if `.claude/notion-dev.config.json` already exists. If yes, read it; this becomes a **re-configuration run** — every subsequent `AskUserQuestion` should prefill with the existing value.

### 2. Project identifiers

- Propose `project.name` from the repo directory basename.
- Ask `AskUserQuestion`: "What's the ticket ID prefix for this project?" (e.g. `STO`, `LAST`, `BTC`). Pre-fill with an uppercase slug of `project.name`.

### 3. Ticket system (Notion)

Notion is the plugin's ticket backend — no selection to make.

### 3a. Notion setup

- Ask `AskUserQuestion`: "Notion database setup?"
  - **Create new** — the plugin creates a fresh database with the required schema.
  - **Use existing** — paste the ID of an existing database.
  - **Cancel** — abort init; do **not** write any config (see 3c). The plugin cannot function without its ticket database, so there is no "partial config" path.
- On **Create new** or **Use existing**, merge this block into `.mcp.json` at the repo root (preserve existing `mcpServers` entries; do not clobber):
  ```json
  {
    "mcpServers": {
      "notion": {
        "command": "npx",
        "args": ["-y", "mcp-remote", "https://mcp.notion.com/mcp"]
      }
    }
  }
  ```
  This is Notion's **hosted** MCP server (OAuth on first connect). Its tool vocabulary — `notion-fetch`, `notion-search`, `notion-query-data-sources`, `notion-create-pages`, `notion-update-page`, `notion-create-database`, `notion-create-comment`, `notion-update-data-source` — is what `skills/ticket-system/SKILL.md` calls. Do not swap in the self-hosted `@notionhq/notion-mcp-server`: it exposes different tool names and the adapter's calls would fail.
- **Reload gate**: everything from 3a-i onward calls `mcp__notion__*` tools, but a freshly added project-scope MCP server only starts (and gets approved/OAuth'd) after Claude Code reloads — the same constraint the GitHub-MCP section notes below. If the Notion tools are not present in the current session (no `mcp__notion__*` in the available tools — always the case when this step just created the entry), stop here with: "Notion MCP added to `.mcp.json`. Run `/reload-plugins` (approve the server and complete the Notion OAuth if prompted), then re-run `/notion-dev:init`." Init is idempotent — the rerun detects the existing entry, skips this patch, and continues into 3a-i/3a-ii. When the tools are already available (entry pre-existed the session), continue directly.

#### 3a-i. Create new

- Ask for a **parent page**: user provides a Notion page URL or ID where the database will be created.
- Validate: fetch the page via `mcp__notion__notion-fetch` to confirm access.
- Create the database via `mcp__notion__notion-create-database` with this schema:

  | Property | Type | Options |
  |---|---|---|
  | `Name` | Title | — |
  | `ID` | Unique ID (`unique_id`) | auto-assigned ticket id; prefix = `project.key`. Atomic — two concurrent `createTicket` calls can never collide, unlike the adapter's max+1 fallback for Number columns. If the create API cannot declare a `unique_id` property, fall back to Number and warn that concurrent create-task runs may race on IDs. |
  | `Status` | Status (or Select) | `Backlog`, `In Progress`, `Implemented` (add `Delivered` / other shipped states yourself if you have a release flow — the plugin doesn't manage them) |
  | `Type` | Select | `Feature`, `Bug`, `Improvement`, `Research` |
  | `PR` | URL | filled by `/notion-dev:ticket` |
  | `Assignee` | People | default assignee target for `/notion-dev:create-task` |
  | `Epic` | Select | no preset options — mission creation adds them |
  | `Phase` | Select | no preset options — mission creation adds them |
  | `Step` | Number | position within a Phase |
  | `Creation Date` | Date | set by `createTicket` at ticket creation |
  | `Parent task` | Relation (self-referential) | links a ticket to its Epic container page — the only relation this plugin uses |
  | `Is Epic` | Checkbox | set to `true` by `createEpic` on the container page it creates; the **sole** signal that identifies a page as an Epic — never set by hand and never on an ordinary ticket |

  Database title: `Tasks - <project.name>`.

  `Epic`, `Phase`, and `Step` are the structural-mission properties (`/notion-dev:create-task` mission path); without them a fresh install silently loses mission grouping and order — the same properties 3a-ii actively detects on existing DBs. **Do not add a `Depends on` relation here.** Blocking order is not stored in a relation — `setDependencies` renders it into the ticket body as a `## Blocked by` section — as a design judgment rather than an impossibility (canonical statement in `skills/ticket-system/SKILL.md` → `setDependencies`; self-relations are **not** symmetric, subtype **is** detectable, and a `propertyUrl`-absent column is provably safe). A `Depends on` column created here would never be read or written by anything. `Parent task` carries a creation-order caveat: if the create API cannot declare a self-referential relation before the database's own ID exists, add it immediately afterward via `mcp__notion__notion-update-data-source` pointing at the new database. `Creation Date` is a plain Date property — the plugin writes the timestamp itself rather than using a `Created time` property, so the value stays editable and backfillable. `Is Epic` is a plain Checkbox — unlike the self-referential relation above, it carries no creation-order caveat and can be declared directly in the initial `mcp__notion__notion-create-database` call.

- Capture the returned `databaseId` and `dataSourceId`.

#### 3a-ii. Use existing

- Ask user for the **Notion database ID** via `AskUserQuestion` (paste).
- Ask for the optional **data source ID**. If the user does not supply one, **omit the key entirely** from the config (do not write `null` — the schema does not allow it).
- **Validate the schema**: fetch the database and resolve each canonical property. For the ID, Status, Type, and PR slots the matcher is **name-first, fall back to type-shape**:
  - **ID** — look for a property named `"ID"`. If missing, scan for any `number` or `unique_id` property and offer via `AskUserQuestion`: *"Use `<found>` as the ID property?"* (options: the candidate names, or "create a new `ID` number property"). Record the chosen name in `idProperty` when it is not the default. `unique_id` is fully supported — the adapter reads the numeric component and ignores the prefix.
  - **Status** — same pattern: prefer `"Status"`, otherwise offer any `status` or `select` property that looks like a status column.
  - **Type** — prefer `"Type"`, otherwise offer any `select` or **`multi_select`** property. Record the chosen name in `typeProperty`. When the resolved property is `multi_select`, announce: *"Type is multi-select on this DB — the plugin will read the first value and write a single-item list."*
  - **PR** — prefer `"PR"` (URL). If missing, ask `AskUserQuestion`: *"Add a `PR` (URL) property so `/notion-dev:ticket` can write the PR link as a first-class Notion field?"* (options: **Add `PR` (URL)** / **Use existing URL property `<name>`** if one exists / **Skip** — plugin will only record the PR URL in the body's `## Implementation` section). Record the chosen name in `prProperty` when it is not the default, or omit `prProperty` and skip writes when the user picks Skip.
  - **Assignee** — prefer a `people` property named `"Assignee"` (case-insensitive). If absent, and exactly one `people` property exists, offer it via `AskUserQuestion`: *"Use `<found>` as the assignee property?"* (options: the candidate, or "Add a new `Assignee` People property"). If no `people` property exists at all, ask `AskUserQuestion`: **Add `Assignee` (People)** / **Skip** (assignment writes will warn-and-skip at runtime). Record the chosen name in `assigneeProperty` only when it is not the default `"Assignee"`. Remember whether an assignee slot exists — step 3b keys off it.
  - For any still-missing required slot (ID/Status/Type), offer via `AskUserQuestion` to auto-create it as an addition to the existing database. If the user declines, warn that some operations may fail; continue.
- **Type options**: after Type is resolved, compare its option list against `typeMap` values (default: `Feature`/`Bug`/`Improvement`/`Research`). For each mismatch, ask `AskUserQuestion`: **Patch** (add the missing option) / **Update config to match live** (rebind `typeMap[<key>]` to an existing option) / **Skip**. *Prefer rebinding over renaming when the live label differs only cosmetically — e.g. `"Feature request"` vs `"Feature"` — to preserve existing ticket data.*
- **Resolved statuses** — first exclude the live option already bound to `statusMap.implemented` (default `"Implemented"`) from the choices entirely: it is a **write key** the plugin sets itself (`/notion-dev:ticket` Phase 8, `/notion-dev:finalize` Phase 3.1) and this question must never reassign it. Then ask `AskUserQuestion` (multi-select) over the remaining live Status options: *"Besides Implemented, which of these also mean a ticket is resolved?"*

  Pre-check by the general reconfigure-prefill rule (see "Re-configuration behavior" below: every `AskUserQuestion` prefills with the current value) — applied here explicitly so this question does not drift from that rule again. **In reconfigure mode**: pre-check the live options currently bound to the existing config's effective `statusMap.done` / `statusMap.cancelled` — the written config value when the key is present, else its default (`"Done"` / `"Cancelled"`) under the omit-when-default convention. This matters most when the existing config maps them to custom labels (e.g. `statusMap.done = "Closed"`, `statusMap.cancelled = "Abandoned"`): pre-check `"Closed"` / `"Abandoned"`, not whatever option happens to literally read "Done" / "Cancelled". **On a fresh run with no existing config** (first-time use-existing): fall back to pre-checking any option matching `Done` / `Cancelled` case-insensitively, same as before — there is no existing mapping to prefill from.

  The picks map deterministically to the two read-only keys `statusMap.done` and `statusMap.cancelled` — never to `statusMap.implemented`:
  - **0 picks** → both keys stay at their defaults; write nothing.
  - **1 pick** → `statusMap.done` = that option; `statusMap.cancelled` stays at its default.
  - **2 picks** → whichever matches `Cancelled` case-insensitively → `statusMap.cancelled`; the other → `statusMap.done`. If neither matches by name, ask one follow-up `AskUserQuestion`: *"Which of these two means cancelled/abandoned?"* — that one → `statusMap.cancelled`, the other → `statusMap.done`.
  - **3+ picks** — `statusMap` has room for exactly one `done` option and one `cancelled` option, not N. Ask one follow-up `AskUserQuestion`: *"Pick the one that means cancelled/abandoned"* over the picks → `statusMap.cancelled`. Of the remaining picks, the first in live option-list order → `statusMap.done`; report the rest to the user as *not captured by `statusMap`* — they will not count toward the epic-close check or auto-tick a `## Tasks` checkbox unless they also happen to equal the `done` or `cancelled` option chosen above.

  Write the resulting `statusMap.done` / `statusMap.cancelled`, following the omit-when-default convention — when both resolve to exactly the defaults, write nothing. This set is read-only to the plugin: it decides when an Epic auto-closes, and no command ever transitions a ticket into `done` or `cancelled` (nor, via this question, into `implemented`). Skip this question on the **create-new** path (3a-i), where the Status options are the plugin's own three and the defaults already apply.
- **Detect structural-mission properties** — probe the live schema for the five optional properties used by multi-task missions. Detection is silent when a property resolves unambiguously; it prompts via `AskUserQuestion` only when it can't (an ambiguous candidate, or none found). For each, record an override in config only when the resolved live name differs from the default:
  - `epicProperty` (default `"Epic"`) — look for any `select` property named `Epic` (case-insensitive). If missing under that name, scan for a `select` property whose name contains "epic" / "initiative" / "theme" and offer it as the binding via `AskUserQuestion` only if exactly one candidate exists. Otherwise omit (feature degrades gracefully).
  - `phaseProperty` (default `"Phase"`) — same pattern, scanning for "phase" / "stage".
  - `stepProperty` (default `"Step"`) — `number` property named `Step`.
  - `parentTaskProperty` (default `"Parent task"`) — **the only relation slot init resolves.** **In reconfigure mode, apply the general reconfigure rule ("Re-configuration behavior" below) before any name-based scan**: take the existing config's effective `parentTaskProperty` (the written override if present, else the default `"Parent task"`) and check whether it still resolves live to a self-referential `relation` property of that exact name. If it does, bind it and skip the name-based scan below entirely — this is what stops a reconfigure from silently repointing an already-bound custom relation (e.g. `Epic parent`) onto a same-DB, default-named `Parent task` column that exists for an unrelated reason (such as Notion's native Sub-items). Only fall back to the scan below when the previously configured property no longer resolves live (renamed or deleted), or on a fresh run with no existing config to prefer.

    **The short-circuit has exactly one exception: never honour a configured name that is a sub-item half** (per (a)'s parent-half rule). Reject it, do **not** bind, and fall through to the scan below — which will exclude it too, leaving the slot to (a) or (c) to resolve correctly. Report the rejection in the availability summary rather than repairing it silently, since it changes a value the user's config explicitly names.

    This exception exists because the exclusion cannot live only in (a). Earlier versions of step (c) offered *any* unmatched self-referential relation, so a `Sub-tasks` binding could already have been written into a config and committed. Preferring the existing config would then re-bind the inverted column on every subsequent run and the scan's exclusion would never once execute — the misconfiguration would be permanent, and worse than a fresh one, because containment inversion is silent: `listEpicChildren` queries the downward half as though it pointed upward, and parent writes land in it. A configured value earns preference for being *deliberate*, not for being *correct*, and this is the one value that cannot be both.

    Otherwise resolve it in these steps:

    **(a) Bind.** Scan self-referential `relation` properties for a parent-like name: `"Parent task"`, then `"Parent item"`, then `"Parent"`, then the name Notion's native Sub-items feature uses for its relation half of the sub-item pair (when Notion Sub-items has been enabled on this DB — see the README's guidance to enable it before running init — its relation property reads as a self-referential relation under one of these names). **Work the candidates in that order and bind from the first candidate that matches anything** — resolving *within* that candidate by the precedence rule below, never by schema enumeration order.

    **Match these names loosely**, not by literal equality. Compare case-insensitively **and** treat `-`, `_`, and whitespace as equivalent, collapsing runs of them — so `Parent-task`, `parent_task`, and `Parent  Task` all match the candidate `"Parent task"`. This is not hypothetical tidiness: Notion names its native Sub-items halves differently across workspaces, and a live database whose pair is `Parent-task` + `Sub-tasks` failed the old exact-match scan on every candidate. The consequence is quiet and expensive. A failed match binds **nothing** — it never mis-binds — so the parent slot stays unbound and epic containment is unavailable, with no wrong value anywhere to notice. Step (c) does still ask, but it asks the user to *create or bind* a relation that already exists under a name the scan just failed to recognise, which reads as a confusing non-sequitur and invites **Skip**. One database ran unbound for eleven days that way. A failed match must never be mistaken for "this DB has no parent relation."

    **Literal beats loose, within each candidate.** Loose matching widens what can match, which means a single candidate can now match several live columns at once — a DB holding both `Parent task` and `Parent-task` matches the first candidate twice. Resolve that deterministically, never by whichever the schema happens to enumerate first:

    1. An **exact** (case-insensitive, no separator folding) match on the candidate wins outright. The precisely-named column is what the user meant; a variant must never displace it.
    2. Otherwise, exactly **one** loose match binds. This is the case the eleven-day database was in.
    3. Otherwise — two or more loose matches and no exact one — the candidate is **ambiguous**. Bind nothing for it and move to the next candidate; if no candidate resolves, leave the slot unbound and let (c) list the loose matches individually so the user picks. Guessing between same-rank variants is how a parent write lands in an unrelated column, and leaving it unresolved is the safer failure — the same reasoning this file applies wherever a wrong binding is worse than no binding.

    Order-dependent binding is not a theoretical concern here: Notion does not guarantee property enumeration order, so the same database could resolve differently between two runs of init.

    **Match only the parent half.** The sub-item half of the native pair (`Sub-tasks`, `Sub-item`, `Sub tasks`, and loose-match variants) is **never** eligible for this slot. Binding it inverts containment: `listEpicChildren` would query the downward column as though it pointed upward, and an epic's children would resolve to its own children's children. If the only self-referential relation found is a sub-item half, treat the slot as unbound and fall through to (c).

    **(b) Diagnose the default name — always, whatever (a) did.** This step produces **two distinct signals**, and conflating them is itself a bug:

    - **`PARENT_NAME_TAKEN = <actual type>`** — set when a property matching `"Parent task"` by **literal** name (case-insensitive, but **no** separator folding) exists and is not a self-referential `relation`. Its only job is the creation-collision gate in (c). Notion rejects a duplicate property only under the *exact* same name, so loose matching must never feed this signal: a live `Parent-task` leaves the name `Parent task` free, and suppressing `Create` over it would strand the slot for no reason.
    - **`PARENT_MISTYPED = <live name>:<actual type>`** — set when a **loosely** matching name (per (a)'s rule) is held by a non-relation type. This is the diagnostic signal: it names the column the user can actually fix, drives the `Retype` option and the availability summary, and feeds (d). A literal match sets both signals; a `Parent-task` sets only this one.

    Run this on **every** path: when (a) bound a later candidate such as `Parent item`, and on reconfigure runs that short-circuited to a custom name — the short-circuit above skips only the *binding* scan, never this check. Gating it on (a) having failed would make one database report a stale column and an otherwise identical one stay silent, on nothing more than what the healthy relation happens to be named.

    **(c) Ask, only when the parent slot is still unbound** — neither the reconfigure short-circuit nor (a) bound anything. `AskUserQuestion` with: **Create `Parent task` (Relation)** — offered **only when `PARENT_NAME_TAKEN` is unset**. That gate is about a **literal** name collision and nothing else: Notion rejects a second property only under the exact same name, so a loosely-matching `Parent-task` must **not** suppress this option — the name `Parent task` is still free and creating it still succeeds. Gate on `PARENT_NAME_TAKEN`, never on `PARENT_MISTYPED`. / **Bind to `<found>`** — where `<found>` is any live **self-referential `relation`** that neither matched the parent-like list in (a) **nor is a sub-item half** under (a)'s parent-half rule; offered only when at least one exists, listed individually when there are several. Excluding sub-item halves here is **not** redundant with (a): (a) declares them ineligible and then routes to this step, so without the same exclusion this option would hand the user the exact column (a) just refused, and binding it inverts containment. (Nothing else competes for a relation — this is the only relation slot.) / **Retype `<the live name in PARENT_MISTYPED>` to a self-referential Relation in Notion, then re-run init** — offered only when `PARENT_MISTYPED` **is** set, naming the actual live column and its actual type; that name may be `Parent-task` rather than the default spelling, and naming the real column is the whole point of the option / **Skip**. The Create option's prompt must state the limitation plainly: *"The API creates a plain self-referential relation, not Notion's native Sub-items feature — grouping and every plugin feature work identically, but rows render as a normal relation column rather than nested sub-rows. To get the native rendering, enable Sub-items in the Notion UI first and re-run init to bind to it."* **Retype behaves exactly like Skip for this run**: the slot stays unbound, the key is omitted from config, and the availability summary reports it unavailable-because-mistyped. Init does not abort over an optional slot. On **Skip**, the parent slot is unbound, so epic containers are unavailable and Epic grouping degrades to Select-tagging only.

    **(d) Whether to record a mistyped parent column depends on what got bound** — the same three-way split the marker slot below states in full, for the same reason (the signature's subject is the config key). Key this on **`PARENT_NAME_TAKEN`**, the *literal* signal — **not** `PARENT_MISTYPED`, even though the loose signal is the one that drives the prompt and the summary.

    The reason is that an unbound slot omits the key, so the effective property name is the exact default `"Parent task"`, and the runtime resolves that name **exactly**. If the only parent-like column is `Parent-task`, the runtime looks up `"Parent task"`, finds nothing, and records `missing-property:parentTaskProperty` — which is **true**. An init-time `wrong-type` entry for that same database would be a false diagnosis and would contradict what every runtime site observes. Only a literal-name collision makes the runtime see a property that is present-but-wrong-typed, and that is exactly what `PARENT_NAME_TAKEN` detects.

    Nothing is lost by this: the loose-only case is still recorded, under the signature that is actually accurate for it.

    - **(a) or (c) bound a relation** → write nothing; `parentTaskProperty` resolves to a healthy column, so an entry would name it broken. Report the stale column in the availability summary.
    - **Nothing bound and `PARENT_NAME_TAKEN` set** → **record `wrong-type:parentTaskProperty`** here, at detection. The key is omitted when unbound, so the effective property is the mistyped, literally-named `Parent task`.
    - **Nothing bound and `PARENT_NAME_TAKEN` unset** → write nothing here, even when `PARENT_MISTYPED` is set. A declined gate on a DB with no such column is routine, and a loose-only mistype is an *absence* at the configured name — the runtime records `missing-property:parentTaskProperty` for it on its own.

    **Recording here matters more than it does for the marker.** `fetchTicket` does **not** record for this property (see its step 4a), so at runtime the entry can only come from an operation that acts on the column — `createTicket`'s parent write, `createEpic`, `findEpics`, `setParent`, `listEpicChildren`, `refreshEpicTasks`, or `epic-update` step 1. A database with a wrong-typed `Parent task`, a usable marker, and no epic activity yet goes unrecorded until one of those runs. There is no first-ticket-read backstop to fall back on the way the marker has.

    Neither signal is a verdict on the slot: binding a differently-named self-referential relation resolves **the parent slot** normally, and whether *Epic containers* are available remains the separate two-slot question. The two have strictly separate jobs, and merging them back into one is a mistake this file has already made once — **`PARENT_NAME_TAKEN`** answers only "is the literal name `Parent task` already occupied?", gating creation in (c) and the recording in (d); **`PARENT_MISTYPED`** answers only "is there a parent-like column the user could repair?", naming it in the `Retype` prompt and the availability summary. The literal one never reaches the user; the loose one never reaches the issue log.
  - `epicMarkerProperty` (default `"Is Epic"`) — **in reconfigure mode, apply the general reconfigure rule ("Re-configuration behavior" below) before any name-based scan**: take the existing config's effective `epicMarkerProperty` (the written override if present, else the default `"Is Epic"`) and check whether it still resolves live to a `checkbox` property of that exact name. If it does, bind it and skip the name-based scan below entirely — the same fix applied to `parentTaskProperty` and `creationDateProperty` above, for the same reason: a reconfigure must not silently rebind an already-bound custom checkbox onto a same-named default column that exists for an unrelated reason. Only fall back to the scan when the previously configured property no longer resolves live, or on a fresh run with no existing config to prefer. Otherwise, look for a `checkbox` property named `"Is Epic"` (case-insensitive). Bind it if found.

    **Diagnose the default name — always, whatever the step above did.** Set `MARKER_NAME_TAKEN = <actual type>` when a live property named `"Is Epic"` (case-insensitive) exists but is **not** a `checkbox`, else leave it unset. Run this on **every** path, including reconfigure runs that short-circuited to a custom name: the short-circuit skips only the binding scan, never this check. This mirrors step (b) of `parentTaskProperty` above, so an identical stale column is reported identically regardless of what the healthy property happens to be called.

    **When the marker slot is still unbound** — meaning *neither* the reconfigure short-circuit *nor* the `"Is Epic"` scan above bound anything — **`MARKER_NAME_TAKEN` decides which remedies are offerable**, which is what makes them correct rather than merely plausible. The gate is "the slot is unbound", **not** "nothing was bound under the name `Is Epic`": a reconfigure run that short-circuited to a healthy custom checkbox (say `Epic flag`) while a stale `Is Epic` select still sits on the DB has a perfectly good marker, and must never reach these remedies — offering them there would unbind a working slot and drop its override from the rewritten config, contradicting both the note below and the availability summary in step 11. The remedies are for a slot with nothing in it; `MARKER_NAME_TAKEN` only shapes *which* of them can work:

    - Scan for other `checkbox` properties. **One** candidate → offer it via `AskUserQuestion`: *"Use `<found>` as the Is Epic marker?"* **Two or more** → list them all as separate options in one `AskUserQuestion`: *"Which checkbox marks a page as an Epic container?"* Never auto-bind when there is more than one candidate — unlike the parent slot's name-ranked scan, checkbox names carry no ordering that would make a first-match rule safe (`Blocked?` and `Needs QA` are equally plausible shapes and neither is a marker). Alongside the candidate(s), offer: **Create a new `Is Epic` checkbox property** — **only when `MARKER_NAME_TAKEN` is unset** — and **Skip**.
    - If no other `checkbox` exists at all, ask `AskUserQuestion`: **Add `Is Epic` (Checkbox)** — again **only when `MARKER_NAME_TAKEN` is unset** — / **Skip**. Without a bound marker, epics cannot be identified at all: `findEpics` returns `null` and every epic-aware operation degrades to "not an epic".
    - **When `MARKER_NAME_TAKEN` is set, every create/add option is suppressed** and replaced by **Retype `Is Epic` to Checkbox in Notion, then re-run init**. Notion will not accept a second property under a name already in use, so an add under that name cannot succeed — offering it would hand the user a remedy that fails. Always name the actual type found in the prompt. **Choosing Retype does not abort init**: this is an optional slot, so continue the run with the marker slot **unbound** — exactly as **Skip** does — omit `epicMarkerProperty` from the written config, and report the slot unavailable-because-mistyped in the availability summary. The difference between Retype and Skip is only what the user intends to do next, not what this run writes; a later `/notion-dev:init` re-run binds it once the column is fixed.

    **Whether to write an issue-log entry for `MARKER_NAME_TAKEN` depends on what got bound — and only on that.** The signature's subject is the **config key**, per the grammar rule in `notion-dev:issue-log`, so the entry is true only when the *configured* marker is the mistyped column:

    - **A checkbox was bound** (under `Is Epic` or any other name) → **write nothing.** `epicMarkerProperty` now resolves to a perfectly good column, so `wrong-type:epicMarkerProperty` would name a healthy property as broken and assert unavailability in the same run this command reports the slot resolved. Report the stale column in the availability summary instead — that is the right channel for a configuration observation, and the mislabeling here would be of a kind the log itself cannot detect.
    - **Nothing was bound** (**Skip** or **Retype**) **and `MARKER_NAME_TAKEN` is set** → **record `wrong-type:epicMarkerProperty`** per `notion-dev:issue-log`, at this detection point. The key is omitted from config when unbound, so the effective marker is the default `"Is Epic"` — which *is* the mistyped column. The claim is true as written, and this is the moment it is known. Do not defer it to `fetchTicket` step 4a on the theory that the first ticket read will catch it: a ticket read is **not guaranteed to happen**, least of all when init is being run precisely to diagnose a broken configuration, and deferring can lose the only record of why epic containers are unavailable.
    - **Nothing was bound and `MARKER_NAME_TAKEN` is unset** → **write nothing.** There is no such column at all; the user declined a gate on a database that simply has no marker, which `notion-dev:issue-log` lists as routine ("a user declining a gate … normal interaction"). The runtime records `missing-property:epicMarkerProperty` if and when it matters. The distinction from the case above is deliberate: nobody types `Is Epic` as a select *intending* a marker, so a mistyped column is an accident worth recording, while no column at all is a clean opt-out.

    The same three-way split applies to `PARENT_NAME_TAKEN` in the `parentTaskProperty` bullet above — and matters *more* there, because that property has no `fetchTicket` fallback at all.

    `MARKER_NAME_TAKEN` is a **diagnostic about the default name, not a verdict on the slot**: binding a differently-named checkbox resolves **the marker slot** normally, even though `"Is Epic"` is still held by the wrong type. Whether *Epic containers* are available is a separate, two-slot question — the parent slot must also have bound — so never report the feature available off this slot alone. Report the mistyped column in the availability summary either way — as the *reason* when nothing was bound, and as a note when something was. Record the chosen name in `epicMarkerProperty` only when it is not the default.
  - **No dependency relation is resolved.** `parentTaskProperty` is the only relation slot init binds. Blocking order between tickets is not stored in a relation at all — `setDependencies` renders it into the ticket body as a `## Blocked by` section — for the reason stated once in `skills/ticket-system/SKILL.md` → `setDependencies`: binding a relation column is a design judgment this plugin declines, for the three reasons the canonical statement gives. **This is not a property of Notion relations** — self-referential relations *are* directional, and an earlier version of this file wrongly claimed otherwise.

    Two corrected facts here have each already tempted a premature restoration, so state both plainly. Relations are directional. Subtype *is* detectable — `propertyUrl` marks two-way halves. **Neither is sufficient**, because a two-way relation whose companion has been deleted keeps its `propertyUrl` and yet behaves one-way, so the detectable signal over-reports and a guard built on it would refuse safe columns. What would justify restoring the slot is a signal that predicts **write behavior** — subtype *plus* live companion state — which nothing available provides today. Until then, leave any live `Depends on` column alone — do not bind it, warn about it, or offer to delete it; its contents may predate the plugin.
- **Detect the Creation Date property** — **in reconfigure mode, apply the general reconfigure rule ("Re-configuration behavior" below) before any name-based detection**: take the existing config's effective `creationDateProperty` (the written override if present, else the default `"Creation Date"`) and check whether it still resolves live to a property of type `date` or `created_time`. If it does, bind it and skip name-based detection below — the same fix applied to `parentTaskProperty` above, for the same reason: a reconfigure must not silently rebind a bound custom property onto a same-named default column that happens to also exist live. Only fall back to detection when the previously configured property no longer resolves live, or on a fresh run with no existing config. Otherwise, prefer a property named `"Creation Date"` (case-insensitive) of type `date` or `created_time`. If missing under that name, scan for a single `created_time` property and offer it. If still unresolved, ask `AskUserQuestion`: **Add `Creation Date` (Date)** / **Bind to `<found>`** (only when a candidate exists) / **Skip** (creation-date writes are skipped at runtime with a warning). Record `creationDateProperty` only when the resolved live name differs from the default.
- **Detect extra Select/Status/Multi-Select properties** (for `staticProperties`) — anything other than the resolved `idProperty` / `statusProperty` / `typeProperty` / `epicProperty` / `phaseProperty`. For each such property, ask `AskUserQuestion`: *"Set a fixed value on `<prop>` for every new ticket?"* Options = the property's live option list, plus "Leave unset". When the user picks a concrete option, record it in `ticketSystem.staticProperties` as `<prop>: <option>`. Skip this whole step silently if no extra properties exist. Example use case: a `Project` property distinguishing multiple apps that share one DB.

#### 3a-iii. Populate config

Populate `ticketSystem` with the collected IDs:

```json
{
  "databaseId": "<captured>",
  "idProperty": "ID",
  "statusProperty": "Status",
  "typeProperty": "Type",
  "prProperty": "PR",
  "statusMap": {
    "inProgress": "In Progress",
    "implemented": "Implemented"
  },
  "typeMap": {
    "feature": "Feature",
    "bug": "Bug",
    "improvement": "Improvement",
    "research": "Research"
  }
}
```

- Include `"dataSourceId": "<captured>"` only when a value was provided. Never serialize it as `null`.
- **Omit** `idProperty` / `statusProperty` / `typeProperty` / `prProperty` / `epicProperty` / `phaseProperty` / `stepProperty` / `parentTaskProperty` / `creationDateProperty` / `epicMarkerProperty` from the written config when they equal their default. Only write them when the resolved live name differs.
- Similarly, only write `typeMap` / `statusMap` when one or more entries differ from the defaults (see `skills/ticket-system/SKILL.md`).
- When the user chose **Skip** for the PR property, write the config without `prProperty` — the adapter's absence-tolerant path kicks in.

If the user bound any `staticProperties` in step 3a-ii, include them:

```json
"staticProperties": {
  "Project": "BTC-Gateway"
}
```

Omit the key entirely when empty.

### 3b. Default assignee

Applies to both create-new and use-existing. **Skip this step entirely** (write
neither `assigneeProperty` nor `defaultAssignee`) only when the assignee slot was
skipped in 3a-ii — i.e. the DB has no People column and the user declined to add
one. Otherwise:

Ask `AskUserQuestion`: "Set a default assignee for new tickets?"
- **Pick a user** — call `mcp__notion__notion-get-users`, filter to
  `type == "person"`, present display names as sub-choices. Write the chosen
  user's **id** to `ticketSystem.defaultAssignee`.
- **No default** — write `ticketSystem.defaultAssignee: ""`. `/notion-dev:create-task`
  will prompt each run.

In **reconfigure mode**, prefill this question with the current `defaultAssignee`
(show "No default" when it is `""` or absent).

`defaultAssignee` is written **explicitly** in both cases — a deliberate exception
to the "omit when equal to default" rule in 3a-iii, so the knob is discoverable in
the config file. `assigneeProperty` still follows the omit-when-default convention
(written only when the resolved People column name differs from `"Assignee"`).

### 3c. If Cancel

Exit `/notion-dev:init` without writing `.claude/notion-dev.config.json` or touching `.mcp.json`. Tell the user: "Init cancelled. Re-run `/notion-dev:init` when you're ready."

### 4. GitHub integration

`/notion-dev:ticket` (PR creation) and `/notion-dev:finalize` (reviews + merge) both need GitHub write access. Their review loop (`notion-dev:review-and-merge`) **requires the authenticated `gh` CLI** — paginated comment reads and GraphQL review-thread resolution have no GitHub MCP equivalent. The MCP is optional; when present, commands prefer it for the operations it supports.

**GitHub MCP entry**. Key by server name `github`:

- If `.mcp.json` **already contains** `mcpServers.github`, leave it untouched and record that the existing entry will be used. Do not overwrite, do not duplicate.
- If `.mcp.json` does **not** contain `mcpServers.github`, merge this entry in (preserving every other existing `mcpServers` key):
  ```json
  {
    "mcpServers": {
      "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
          "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
        }
      }
    }
  }
  ```

Users who run a GitHub MCP under a non-standard server name (e.g. `github-enterprise`) are out of scope for auto-detection — they should reconcile naming manually; the plugin assumes the entry is `github`.

**`gh` CLI check**. Using the probe result from step 1:

- `gh` installed and authenticated → report: "GitHub access: `gh` CLI (required — working) + GitHub MCP (optional, preferred where supported) — all good."
- `gh` missing or unauthenticated → warn: "`gh` is **required** by the review loop in `/notion-dev:ticket` and `/notion-dev:finalize`. Install it and run `gh auth login` before running either command."

**No hard abort in init.** Init cannot actually verify the GitHub MCP works at setup time (the MCP server only starts when Claude Code reloads), and a missing `gh` can be installed after init without re-running it — so a fail-fast abort would be premature here. The real gate is at the top of `/notion-dev:ticket` and `/notion-dev:finalize`, which probe `gh auth status` at command entry and abort if it is unavailable. Init's job is to patch the config and surface warnings.

No config field is written — this dependency is behavioral, not configurable.

### 5. Input sources

Default enabled list: `["prompt", "existing-ticket", "notion-page"]`.

Ask `AskUserQuestion` (multi-select) if the user wants to adjust this list.

### 6. Git flow defaults

- `baseBranch`: prefill with detected default branch. Ask `AskUserQuestion` to confirm or override.
- `prTargetBranch`: default to `baseBranch` (omit from config if same).
- `mergeStrategy`: default `"squash"`. Don't prompt unless the user asks to customize.
- `preMergeChecks: []`, `postMergeHooks: []`. Do not prompt — these are phase-2 seams and empty is correct for the simple flow.

### 6a. Code reviewer

Ask `AskUserQuestion`: "Which code reviewer should the review loop use?"
- **Codex** — triggers via an `@codex review` comment (`chatgpt-codex-connector[bot]`).
- **Copilot** — requests the `copilot-pull-request-reviewer[bot]` reviewer via the REST API
  (the repo/org must have Copilot code review enabled).

Default/prefill **Codex**. In reconfigure mode, prefill with the existing `reviewer` value.
Record the answer as `reviewer` (`"codex"` or `"copilot"`).

### 7. Worktree prefix

Default to `"{name}-{key}-{id}"`. Do not prompt unless the user explicitly asks to customize.

### 8. Verify suite (auto-detect)

Select a template based on Step 1 detection; show the proposed list to the user and ask `AskUserQuestion` to accept or edit.

- **Foundry + Makefile**:
  ```json
  [
    { "name": "fmt",   "cmd": "forge fmt",  "retries": 1 },
    { "name": "build", "cmd": "make build", "retries": 3 },
    { "name": "test",  "cmd": "make test",  "retries": 3 }
  ]
  ```
- **Node/TypeScript** (`package.json` present):
  ```json
  [
    { "name": "build", "cmd": "npm run build",     "retries": 3 },
    { "name": "tsc",   "cmd": "npx tsc --noEmit",  "retries": 3 },
    { "name": "lint",  "cmd": "npx eslint .",      "retries": 2 },
    { "name": "test",  "cmd": "npm run test",      "retries": 3 }
  ]
  ```
- **Python** (`pyproject.toml`):
  ```json
  [
    { "name": "test", "cmd": "pytest", "retries": 3 }
  ]
  ```
- **Fallback**: empty list. Warn: "No tech stack detected — add verify steps to `.claude/notion-dev.config.json` manually before running `/notion-dev:ticket`."

### 9. Write files

Create directory `.claude/` if missing. Write `.claude/notion-dev.config.json` with the collected values, this first key, and the recorded build-flow dependencies (verified in step 1):

```json
{
  "$schema": "https://raw.githubusercontent.com/forhas/pure-dev/main/plugins/notion-dev/schema/notion-dev.config.schema.json",
  "reviewer": "codex",
  ...
  "dependencies": { "superpowers": true, "featureDev": true }
}
```

Always write `reviewer` explicitly (unlike the omit-when-default properties above) — it is exempt from the "omit when equal to default" convention, so it appears in the config even when the answer was the default `codex`.

**Preserve `reviewsCap` on reconfigure.** `reviewsCap` (the review-loop round cap; see the schema and README) is a hand-edited knob that init never prompts for. When reconfiguring an existing config, carry any `reviewsCap` it already contained through to the rewritten file verbatim — this rewrite is from collected values, so a value init never collects would otherwise be silently dropped, and the next review loop would fall back to 15 despite the user's documented setting. A fresh init omits the key (the review loop defaults to 15).

Write/update `.mcp.json` at the repo root with merged `mcpServers`.

### 10. Commit (optional)

Ask `AskUserQuestion`: "Commit the new config files?" If yes:

```
git add .claude/notion-dev.config.json .mcp.json
git commit -m "chore: initialize notion-dev plugin"
```

### 11. Report

**Issue-log sweep.** Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`. Best-effort — a failure here never fails the run.

Print a short summary:
- Ticket system configured
- Input sources enabled
- Verify steps
- Code reviewer: <codex|copilot>.
- Optional slots resolved: `Creation Date`, `Parent task`, `Is Epic` — and whether **Epic containers are available**. Availability is decided on the **property each slot actually resolved to**, whatever its name, not on the default name: the marker slot must have bound a live `checkbox`, and the parent slot a live self-referential `relation`. A slot that bound a differently-named property (`Epic parent`, a Sub-items relation, any other checkbox) is **available**; a slot that bound nothing is **unavailable**. This holds regardless of whether `epicMarkerProperty` / `parentTaskProperty` were written to config — omit-when-default means they are commonly absent from config even when resolved live. **Presence of the default name is not availability, and neither is its absence a bar**: what matters is whether a correctly-typed property was bound, because that is exactly what `notion-dev:ticket-system` checks at runtime (see its "Marker usability rule"). The `Epic` select tag is unrelated to availability — it's display metadata, never what identifies a container.

  When a slot bound nothing, say so plainly and give the reason, distinguishing missing from mistyped: "Epic containers unavailable — no Checkbox property to use as the Is Epic marker, and `Is Epic` itself is a `select`. Epic grouping will use the Select tag only." versus "…no Checkbox property named `Is Epic` or otherwise available…". When a slot bound a correctly-typed property but the default name is still held by a wrong-typed column (`MARKER_NAME_TAKEN` / `PARENT_MISTYPED` from the resolution steps above — the parent one is the loose diagnostic, which is what names the column the user would clean up), report **available** and add the mistyped column as a note, not as a failure — it is a stale column the user may want to clean up, not something blocking the plugin.
- Build-flow plugins verified: superpowers + feature-dev (required dependencies)
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`. Omit the line entirely when the run logged nothing.
- Next actions: "Run `/notion-dev:create-task` to create your first ticket, or `/notion-dev:ticket <ticket-id>` to work on an existing one."

## Re-configuration behavior

If `.claude/notion-dev.config.json` existed on entry, `/notion-dev:init` runs in **reconfigure mode**:
- Prefill every `AskUserQuestion` with the current value — including the code reviewer question (step 6a), which prefills with the existing `reviewer` value instead of the `codex` default.
- Never silently overwrite existing config — every change goes through explicit confirmation.
- After collecting any updates, run the **schema-drift check** below before writing.

### Schema-drift check

Compare the configured ticket system against its live backend state. This runs automatically at the end of a reconfigure, and can also be invoked on its own by re-running `/notion-dev:init` and choosing "Review & update" with no field changes.

#### Notion drift items

1. Fetch the database via `mcp__notion__notion-fetch` using `ticketSystem.databaseId`.
2. Compare against the configured schema, resolving each canonical slot by the override if set, else by default name:
   - **ID slot** (`idProperty`): must exist and be `number` or `unique_id`. Report missing; report type mismatches informationally.
   - **Status slot** (`statusProperty`): must exist and be `status` or `select`. Report missing.
   - **Type slot** (`typeProperty`): must exist and be `select` or `multi_select`. Report missing.
   - **PR slot** (`prProperty`): if config has `prProperty`, must exist and be `url`; informational only, not a hard drift.
   - **Assignee slot** (`assigneeProperty`): if config has `assigneeProperty`, it should exist and be `people`-typed; **informational only**, not a hard drift (mirrors the PR slot). Skip the check when `assigneeProperty` is absent from config.
   - **Creation Date slot** (`creationDateProperty`): if config has the key, it should exist and be `date` or `created_time`; **informational only**, not a hard drift (mirrors the PR and Assignee slots). Skip the check when the key is absent from config.
   - **Parent task slot** (`parentTaskProperty`): if config has the key, it should exist and be a self-referential `relation`; **informational only**. Skip the check when the key is absent from config — which under omit-when-default is the common case, so this item is **not** the plugin's primary defence against a retyped column. The resolution step above is: it re-derives the live type on every run regardless of config, and the Epic-containers availability summary reports the outcome. This item only adds a check for the *non-default* configured name, and stays informational because the runtime already degrades safely and records `wrong-type:parentTaskProperty`.
   - **Is Epic slot** (`epicMarkerProperty`): if config has the key, it should exist and be `checkbox`-typed; **informational only**, not a hard drift (mirrors the Parent task slot, and stays informational for the same reason: the runtime degrades safely and records `wrong-type:epicMarkerProperty`). Skip the check when the key is absent from config — and as with the Parent task slot, that is the common case under omit-when-default, so the resolution step and the availability summary, not this item, are what actually catch a retyped marker.
   - **Status options**: expected always includes `statusMap.inProgress`, `statusMap.implemented`, and `"Backlog"` — the options the plugin actively writes or creates. `statusMap.done` and `statusMap.cancelled` are **read-only** (see "Resolved set" in `skills/ticket-system/SKILL.md`) — the plugin never writes them, so include each in the expected set only when it was **explicitly configured** (present as a written key in `.claude/notion-dev.config.json` — under the omit-when-default convention, presence means the user bound a non-default option name) or its resolved option name already exists live. Otherwise omit it from the expected set entirely: a create-new DB that legitimately has only `Backlog`/`In Progress`/`Implemented` must not be reported as missing `Done`/`Cancelled` on every later `init` run — their absence there is not drift. Report any expected option (under this narrowed set) that's missing; extras are informational.
   - **Type options**: expected = `typeMap` values (defaults `Feature`/`Bug`/`Improvement`/`Research` when the key is absent). Report any expected option missing; extras are informational.
3. For each drift item, ask `AskUserQuestion`:
   - **Patch** — add the missing property / option via Notion MCP.
   - **Skip** — leave as-is; commands relying on it may fail.
   - **Update config to match live** — rebind the local config (e.g. change `statusMap.inProgress` or `typeMap.feature` to the live option name; change `typeProperty` to point at a different live property). **Prefer this over Patch when the live label differs only cosmetically** (e.g. `"In progress"` vs `"In Progress"`, `"Feature request"` vs `"Feature"`) — it preserves existing ticket data.

Each drift item is also recorded via `notion-dev:issue-log`, using the same signature the adapter uses for that property at runtime — `missing-property:<propertyName>` when the property is absent, `wrong-type:<propertyName>` when it exists with the wrong Notion type. Never coin an init-specific signature: a property missing here and missing at ticket time are one condition observed at two moments, and one entry is what makes the log groupable.

### Report

Print a drift summary with three columns: `item`, `expected`, `live`, and the action taken. No surprises: if nothing changed, say "no drift detected".
