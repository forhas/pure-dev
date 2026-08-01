---
description: Initialize the notion-dev plugin in this project. Configures ticket system, patches .mcp.json, writes .claude/notion-dev.config.json. Idempotent.
---

# /notion-dev:init

Interactive, idempotent setup. Produces `.claude/notion-dev.config.json` and a merged `.mcp.json` so that `/notion-dev:create-task`, `/notion-dev:ticket`, and `/notion-dev:finalize` work in this project.

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
  | `Depends on` | Relation (self-referential) | blocking dependencies between mission tasks |
  | `Creation Date` | Date | set by `createTicket` at ticket creation |
  | `Parent task` | Relation (self-referential) | links a ticket to its Epic container page; distinct from `Depends on` |

  Database title: `Tasks - <project.name>`.

  `Epic`, `Phase`, `Step`, and `Depends on` are the structural-mission properties (`/notion-dev:create-task` mission path); without them a fresh install silently loses mission grouping, order, and dependency edges — the same properties 3a-ii actively detects on existing DBs. If the create API cannot declare the self-referential `Depends on` relation at creation time (the DB's own ID is only known afterwards), add it immediately after via a schema update (`mcp__notion__notion-update-data-source`) pointing the relation at the new database. `Parent task` carries the same creation caveat as `Depends on`: if the create API cannot declare a self-referential relation before the database's own ID exists, add it immediately afterward via `mcp__notion__notion-update-data-source` pointing at the new database. `Creation Date` is a plain Date property — the plugin writes the timestamp itself rather than using a `Created time` property, so the value stays editable and backfillable.

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
- **Resolved statuses** — first exclude the live option already bound to `statusMap.implemented` (default `"Implemented"`) from the choices entirely: it is a **write key** the plugin sets itself (`/notion-dev:ticket` Phase 8, `/notion-dev:finalize` Phase 3.2) and this question must never reassign it. Then ask `AskUserQuestion` (multi-select) over the remaining live Status options: *"Besides Implemented, which of these also mean a ticket is resolved?"*

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
  - `parentTaskProperty` (default `"Parent task"`) — **resolved before `dependsOnProperty` below**, so containment claims the correct relation first. **In reconfigure mode, apply the general reconfigure rule ("Re-configuration behavior" below) before any name-based scan**: take the existing config's effective `parentTaskProperty` (the written override if present, else the default `"Parent task"`) and check whether it still resolves live to a self-referential `relation` property of that exact name. If it does, bind it and skip the name-based scan below entirely — this is what stops a reconfigure from silently repointing an already-bound custom relation (e.g. `Epic parent`) onto a same-DB, default-named `Parent task` column that exists for an unrelated reason (such as Notion's native Sub-items). Only fall back to the scan below when the previously configured property no longer resolves live (renamed or deleted), or on a fresh run with no existing config to prefer. Scan self-referential `relation` properties for a parent-like name: `"Parent task"` (case-insensitive), then `"Parent item"`, then `"Parent"`, then the name Notion's native Sub-items feature uses for its relation half of the sub-item pair (when Notion Sub-items has been enabled on this DB — see the README's guidance to enable it before running init — its relation property reads as a self-referential relation under one of these names). Bind the first match found. If none is found, ask `AskUserQuestion`: **Create `Parent task` (Relation)** / **Bind to `<found>`** (only when a candidate self-referential relation exists) / **Skip**. The Create option's prompt must state the limitation plainly: *"The API creates a plain self-referential relation, not Notion's native Sub-items feature — grouping and every plugin feature work identically, but rows render as a normal relation column rather than nested sub-rows. To get the native rendering, enable Sub-items in the Notion UI first and re-run init to bind to it."* On **Skip**, epic containers are unavailable and Epic grouping degrades to Select-tagging only.
  - `dependsOnProperty` (default `"Depends on"`) — self-referential `relation` property, chosen only from candidates **not already claimed** by `parentTaskProperty` above. Accept any such remaining relation (self-referential is the distinguishing trait; name match is secondary) — **except** a parent-like name (`"Parent task"`, `"Parent item"`, `"Parent"`, or the Sub-items relation name) is never eligible here, even when it is the only self-referential relation left unclaimed: binding a relation named `Parent task` as `Depends on` is always wrong — containment and blocking-order are different relationships and must never share a column — and leaving `dependsOnProperty` unresolved is safer than binding the wrong one. When no eligible candidate remains, omit `dependsOnProperty` (absence-tolerant; a later init run can bind it once the user adds a real `Depends on` relation).
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
- **Omit** `idProperty` / `statusProperty` / `typeProperty` / `prProperty` / `epicProperty` / `phaseProperty` / `stepProperty` / `dependsOnProperty` / `parentTaskProperty` / `creationDateProperty` from the written config when they equal their default. Only write them when the resolved live name differs.
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

Print a short summary:
- Ticket system configured
- Input sources enabled
- Verify steps
- Code reviewer: <codex|copilot>.
- Optional slots resolved: `Creation Date`, `Parent task` — and whether **Epic containers are available** (both the Epic property and the Parent task property present **on the live Notion database**, regardless of whether `epicProperty` / `parentTaskProperty` were written to config — omit-when-default means they're commonly absent from config even when present live). When either is missing live, say so plainly: "Epic containers unavailable — Epic grouping will use the Select tag only."
- Build-flow plugins verified: superpowers + feature-dev (required dependencies)
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
   - **Parent task slot** (`parentTaskProperty`): if config has the key, it should exist and be a self-referential `relation`; **informational only**. Skip the check when the key is absent from config.
   - **Status options**: expected always includes `statusMap.inProgress`, `statusMap.implemented`, and `"Backlog"` — the options the plugin actively writes or creates. `statusMap.done` and `statusMap.cancelled` are **read-only** (see "Resolved set" in `skills/ticket-system/SKILL.md`) — the plugin never writes them, so include each in the expected set only when it was **explicitly configured** (present as a written key in `.claude/notion-dev.config.json` — under the omit-when-default convention, presence means the user bound a non-default option name) or its resolved option name already exists live. Otherwise omit it from the expected set entirely: a create-new DB that legitimately has only `Backlog`/`In Progress`/`Implemented` must not be reported as missing `Done`/`Cancelled` on every later `init` run — their absence there is not drift. Report any expected option (under this narrowed set) that's missing; extras are informational.
   - **Type options**: expected = `typeMap` values (defaults `Feature`/`Bug`/`Improvement`/`Research` when the key is absent). Report any expected option missing; extras are informational.
3. For each drift item, ask `AskUserQuestion`:
   - **Patch** — add the missing property / option via Notion MCP.
   - **Skip** — leave as-is; commands relying on it may fail.
   - **Update config to match live** — rebind the local config (e.g. change `statusMap.inProgress` or `typeMap.feature` to the live option name; change `typeProperty` to point at a different live property). **Prefer this over Patch when the live label differs only cosmetically** (e.g. `"In progress"` vs `"In Progress"`, `"Feature request"` vs `"Feature"`) — it preserves existing ticket data.

### Report

Print a drift summary with three columns: `item`, `expected`, `live`, and the action taken. No surprises: if nothing changed, say "no drift detected".
