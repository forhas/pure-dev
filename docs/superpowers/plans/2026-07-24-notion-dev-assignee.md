# notion-dev Ticket Assignee Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `/notion-dev:create-task` assign the ticket it creates to a Notion user — silently from config when a default is set, otherwise via an interactive picker of workspace users.

**Architecture:** All Notion lookup/write logic lives in the `ticket-system` skill (new `resolveAssignee` operation + a new optional `assignee` arg on `createTicket`). The `create-task` command adds one phase that decides *who* to assign and threads a resolved user id into every write. `/notion-dev:init` provisions the People column and offers to record a default. Two new optional config keys drive it, both absence-tolerant like the existing `prProperty`/`epicProperty`.

**Tech Stack:** Markdown skill/command files + one JSON-Schema (draft-07) config schema. Notion hosted MCP tools (`mcp__notion__notion-get-users`, `notion-create-pages`, `notion-update-page`, `notion-create-database`, `notion-fetch`).

## Global Constraints

- Config file lives at `.claude/notion-dev.config.json`, validated by `plugins/notion-dev/schema/notion-dev.config.schema.json`. Resolve the path against the **primary checkout**, never `git rev-parse --show-toplevel` (see `ticket-system/SKILL.md`).
- Absence-tolerance is the house style: a configured property missing from the live DB → **one-time warning, never abort** (mirror `prProperty`).
- Assignee writes target a Notion **People**-typed column, written as a **single-item people list**. Single assignee only (no multi-assignee).
- `assigneeProperty` default is `"Assignee"`; it follows the "omit from config when equal to default" convention.
- `defaultAssignee` is the **one exception**: `/notion-dev:init` writes it **explicitly**, including `""` when the user declines a default. Runtime treats `""` and "key absent" **identically** → prompt interactively.
- `defaultAssignee` accepts a user **id, email, or display name**; resolution to a concrete id happens at create time.
- Chosen assignee (interactive) is used **for the current run only** — create-task never writes config.
- These are prose/config files; there is no unit-test harness. "Tests" here = JSON validity for the schema and targeted `grep` consistency checks for the markdown, plus a fresh-eyes read against the spec.

Spec: `docs/superpowers/specs/2026-07-24-notion-dev-assignee-design.md`.

---

## File Structure

- `plugins/notion-dev/schema/notion-dev.config.schema.json` — add `assigneeProperty` + `defaultAssignee` under `ticketSystem.properties`.
- `plugins/notion-dev/skills/ticket-system/SKILL.md` — new `resolveAssignee` op; `assignee` arg on `createTicket`; People property-type handling; two new config bullets.
- `plugins/notion-dev/commands/create-task.md` — new Phase 2.75; thread `assignee` into single + mission write paths.
- `plugins/notion-dev/commands/init.md` — `Assignee` (People) in create-new schema; detect People slot in use-existing; new step 3b; drift-check line.
- `plugins/notion-dev/README.md` — document the two keys + the People property.

Task order follows the dependency chain: schema → skill (defines contracts) → command (consumes them) → init (writes config) → docs.

---

### Task 1: Config schema — `assigneeProperty` + `defaultAssignee`

**Files:**
- Modify: `plugins/notion-dev/schema/notion-dev.config.schema.json` (inside `properties.ticketSystem.properties`, alongside `prProperty`)

**Interfaces:**
- Produces: two config keys consumed by every later task — `ticketSystem.assigneeProperty` (string, default `"Assignee"`) and `ticketSystem.defaultAssignee` (string; id | email | display-name | `""`).

- [ ] **Step 1: Add the two properties**

In `schema/notion-dev.config.schema.json`, inside the `ticketSystem` → `properties` object, add these two entries immediately after the `prProperty` block (before `statusMap`):

```json
        "assigneeProperty": {
          "type": "string",
          "default": "Assignee",
          "description": "People property that create-task assigns new tickets to. Absence-tolerant — when missing or not People-typed on the live DB, the assignment write is skipped with a warning rather than aborting."
        },
        "defaultAssignee": {
          "type": "string",
          "description": "Default assignee for new tickets: a Notion user id, email, or display name, resolved via notion-get-users at create time. Empty string or absent means create-task prompts interactively. Written explicitly by /notion-dev:init (including \"\" when the user declines a default)."
        },
```

`ticketSystem.additionalProperties` is already `false`, so both keys must be declared here to be legal — confirm the block sits inside `properties`, not next to it.

- [ ] **Step 2: Verify the schema is still valid JSON**

Run: `python3 -m json.tool plugins/notion-dev/schema/notion-dev.config.schema.json > /dev/null && echo OK`
Expected: `OK` (non-zero exit / traceback means a comma or brace is off).

- [ ] **Step 3: Verify both keys are present and well-formed**

Run:
```bash
python3 -c "import json; p=json.load(open('plugins/notion-dev/schema/notion-dev.config.schema.json'))['properties']['ticketSystem']['properties']; assert p['assigneeProperty']['default']=='Assignee'; assert 'default' not in p['defaultAssignee']; print('OK')"
```
Expected: `OK` (asserts `assigneeProperty` defaults to `Assignee` and `defaultAssignee` has no default — it is written explicitly, never defaulted).

- [ ] **Step 4: Commit**

```bash
git add plugins/notion-dev/schema/notion-dev.config.schema.json
git commit -m "feat(notion-dev): add assigneeProperty + defaultAssignee to config schema"
```

---

### Task 2: `ticket-system` skill — `resolveAssignee` + `createTicket` assignee arg

**Files:**
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md`

**Interfaces:**
- Consumes: `ticketSystem.assigneeProperty`, `ticketSystem.defaultAssignee` (Task 1).
- Produces (relied on by Task 3 & 4):
  - Operation `resolveAssignee(value)` → `{ id, name }` on a unique person match, else `null` (no match OR ambiguous). Read-only.
  - `createTicket({ title, body, type?, epic?, phase?, step?, assignee? })` where `assignee` is a **resolved Notion user id** (string). Absence-tolerant write to `assigneeProperty`.

- [ ] **Step 1: Add `resolveAssignee` + updated `createTicket` to the operations table**

In the "Logical operations" table, update the `createTicket` row and add a `resolveAssignee` row. Replace the existing `createTicket` row:

```
| `createTicket` | `{ title, body, type?, epic?, phase?, step? }` | `{ id, url }` — `epic`/`phase`/`step` are optional mission metadata; each is absence-tolerant when the corresponding configured property is missing from the live DB |
```

with:

```
| `createTicket` | `{ title, body, type?, epic?, phase?, step?, assignee? }` | `{ id, url }` — `epic`/`phase`/`step` are optional mission metadata; `assignee` is a resolved Notion user id. Each is absence-tolerant when the corresponding configured property is missing from the live DB |
| `resolveAssignee` | `value` (user id, email, or display name) | `{ id, name }` on a unique person match; `null` on no match or ambiguity. Read-only — never mutates config or the DB |
```

- [ ] **Step 2: Add the two config bullets**

In the "## Configuration" section, add these two bullets immediately after the `prProperty` bullet:

```markdown
- `assigneeProperty` — People property that `/notion-dev:create-task` assigns new tickets to (default `"Assignee"`). When the property doesn't exist on the live DB or isn't a People type, skip the write with a warning rather than aborting.
- `defaultAssignee` — default assignee as a Notion user id, email, or display name, resolved via `resolveAssignee` at create time. Empty string or absent → `/notion-dev:create-task` prompts interactively. `/notion-dev:init` writes it explicitly (including `""`).
```

- [ ] **Step 3: Add the People property-handling bullet**

In the "## Property type handling" section, add this bullet after the `Depends on` bullet:

```markdown
- **Assignee** (People) — write as a single-item list of `{ id }` user references to the `assigneeProperty` column. Read is not implemented (the plugin never reads assignee back). When the configured property is absent from the live DB or is not a `people` type, skip the write and log **one** warning per run (`"assigneeProperty '<name>' not found or not a People property on DB; skipping assignee write"`) — never abort. `assignee` is caller-supplied creation state, not a `staticProperty`: `updateTicket` and `upsertSection` never touch it.
```

- [ ] **Step 4: Add the `resolveAssignee` operation section**

Add this new section immediately **before** the `## createTicket(...)` section:

````markdown
## resolveAssignee(value)

Read-only. Turns a human-supplied value into a concrete Notion user id. Used by `/notion-dev:init` (to validate a chosen/typed default) and `/notion-dev:create-task` (to resolve `defaultAssignee` and interactive picks).

1. Fetch workspace users via `mcp__notion__notion-get-users`. Filter to entries whose `type` is `"person"` — skip bots and integrations.
2. Match `value` against the filtered list in this order, stopping at the first rule that yields matches:
   1. exact `id` equality
   2. exact email equality (case-insensitive), where the user exposes an email
   3. exact display-name equality (case-insensitive)
3. Resolve the result:
   - exactly one match → return `{ id, name }` (the canonical id and display name).
   - zero matches, or **more than one** match at the matching rule (ambiguous) → return `null`. Callers decide what to do (create-task falls back to the interactive picker with a warning; init re-prompts).

Never writes config or the database. When `mcp__notion__notion-get-users` is unavailable, fail with the standard MCP-unavailability message (see "MCP unavailability").
````

- [ ] **Step 5: Thread `assignee` into the `createTicket` write steps**

In the `## createTicket({ ... })` section, update its two lines.

First, update the heading and intro line. Replace:

```markdown
## createTicket({ title, body, type?, epic?, phase?, step? })
```

with:

```markdown
## createTicket({ title, body, type?, epic?, phase?, step?, assignee? })
```

Then, inside step 2 (the `notion-create-pages` property list), add this bullet immediately after the `staticProperties` bullet (`- For each [name, value] in staticProperties ...`) and before the `**Mission metadata**` bullet:

```markdown
   - **Assignee** (absence-tolerant): if `assignee` (a resolved user id) is provided AND the live DB has the `assigneeProperty` column AND it is a `people` type, set it to a single-item people list `[{ id: assignee }]`. If the column is absent or not People-typed, skip with the one-time warning from "Property type handling". `assignee` absent → set nothing.
```

- [ ] **Step 6: Verify cross-references are consistent**

Run:
```bash
grep -c "resolveAssignee" plugins/notion-dev/skills/ticket-system/SKILL.md
grep -c "assigneeProperty" plugins/notion-dev/skills/ticket-system/SKILL.md
grep -n "assignee?" plugins/notion-dev/skills/ticket-system/SKILL.md
```
Expected: `resolveAssignee` appears ≥3 times (table row, its own section heading, config bullet); `assigneeProperty` appears ≥4 times (config bullet, property-handling bullet, createTicket step, warning string); the `createTicket` table row and section heading both show `assignee?`.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/skills/ticket-system/SKILL.md
git commit -m "feat(notion-dev): add resolveAssignee op and createTicket assignee arg"
```

---

### Task 3: `create-task` command — resolve-assignee phase + write threading

**Files:**
- Modify: `plugins/notion-dev/commands/create-task.md`

**Interfaces:**
- Consumes: `resolveAssignee(value)` and `createTicket({ ..., assignee? })` from Task 2; `ticketSystem.defaultAssignee` from Task 1.
- Produces: a resolved `assignee` id (or "leave unassigned") threaded into every `createTicket` call in Phase 3.

- [ ] **Step 1: Add Phase 2.75 (Resolve assignee) between Phase 2.5 and Phase 3**

Insert this section immediately before the `## Phase 3 — Write` heading (after Phase 2.5's closing `---`):

```markdown
## Phase 2.75 — Resolve assignee

Decide **who** the new ticket(s) get assigned to. Produces a single `assignee`
value — a resolved Notion user id, or the sentinel "unassigned" — reused for
every `createTicket` in Phase 3. Runs once, even for a mission.

1. Read `ticketSystem.defaultAssignee` from config.
   - **Set and non-empty** → invoke `notion-dev:ticket-system` operation
     `resolveAssignee(defaultAssignee)`.
     - Unique match → `assignee = <id>`; continue to Phase 3 silently.
     - `null` (no match / ambiguous) → warn
       (`"defaultAssignee '<value>' did not resolve to a unique user; pick manually"`)
       and fall through to step 2.
   - **Absent or empty string (`""`)** → go to step 2.
2. **Interactive pick.** Fetch person-users via `notion-dev:ticket-system`
   `resolveAssignee`'s underlying source is not reused here — instead call
   `mcp__notion__notion-get-users`, filter to `type == "person"`, and present
   their display names with `AskUserQuestion`: "Assign this ticket to whom?".
   Include a final **"Leave unassigned"** option.
   - A named pick → resolve to that user's id → `assignee = <id>`.
   - "Leave unassigned" → `assignee = unassigned` (pass no `assignee` in Phase 3).
3. **Missions:** the single `assignee` decided here applies to **every** task —
   pass it into each `createTicket` in Pass 1. "Leave unassigned" applies to all.

This choice is used for the current run only — never written back to config.
```

- [ ] **Step 2: Thread `assignee` into the single-ticket write**

In `### 3.2 Write to the ticket system` → `#### Single-ticket path`, replace:

```markdown
- Otherwise, operation is `createTicket({ title, body, type })` — new ticket.
```

with:

```markdown
- Otherwise, operation is `createTicket({ title, body, type, assignee })` — new ticket. Omit `assignee` when Phase 2.75 chose "Leave unassigned". `existing-ticket` `updateTicket` never sets an assignee (assignment is creation-only).
```

- [ ] **Step 3: Thread `assignee` into the mission write (Pass 1)**

In the `#### Mission path (two-pass)` → **Pass 1** pseudocode block, add `assignee` to the `createTicket` call. Replace:

```
  result = ticket-system.createTicket({
    title: task.title,
    body:  task.body,
    type:  task.type,
    epic:  mission.epic,        // reconciled name from 2.5.2
    phase: task.phase,          // omitted fields pass through as absent
    step:  task.step,
  })
```

with:

```
  result = ticket-system.createTicket({
    title:    task.title,
    body:     task.body,
    type:     task.type,
    epic:     mission.epic,     // reconciled name from 2.5.2
    phase:    task.phase,       // omitted fields pass through as absent
    step:     task.step,
    assignee: assignee,         // from Phase 2.75; omit when "unassigned"
  })
```

- [ ] **Step 4: Verify threading is consistent**

Run:
```bash
grep -n "Phase 2.75" plugins/notion-dev/commands/create-task.md
grep -n "assignee" plugins/notion-dev/commands/create-task.md
```
Expected: `Phase 2.75` referenced in both its own heading and the Pass-1 comment; `assignee` appears in the phase body, the single-ticket path, and the mission Pass-1 block. Confirm no stray `createTicket({ title, body, type })` (the old single-path signature) remains.

- [ ] **Step 5: Commit**

```bash
git add plugins/notion-dev/commands/create-task.md
git commit -m "feat(notion-dev): resolve and assign ticket assignee in create-task"
```

---

### Task 4: `init` command — provision People column + default-assignee prompt

**Files:**
- Modify: `plugins/notion-dev/commands/init.md`

**Interfaces:**
- Consumes: `resolveAssignee` (Task 2, for validating a typed/chosen default); `assigneeProperty` + `defaultAssignee` schema keys (Task 1).
- Produces: config with `defaultAssignee` always written (possibly `""`), and `assigneeProperty` written only when the live People column name differs from `"Assignee"`.

- [ ] **Step 1: Add the `Assignee` People property to the create-new schema (3a-i)**

In `#### 3a-i. Create new`, add a row to the schema table. After the `PR` row:

```
  | `PR` | URL | filled by `/notion-dev:ticket` |
```

insert:

```
  | `Assignee` | People | default assignee target for `/notion-dev:create-task` |
```

- [ ] **Step 2: Detect the People slot in use-existing (3a-ii)**

In `#### 3a-ii. Use existing`, add an assignee-detection bullet immediately after the `PR` matcher bullet (the one starting `- **PR** — prefer "PR" (URL)...`):

```markdown
  - **Assignee** — prefer a `people` property named `"Assignee"` (case-insensitive). If absent, and exactly one `people` property exists, offer it via `AskUserQuestion`: *"Use `<found>` as the assignee property?"* (options: the candidate, or "Add a new `Assignee` People property"). If no `people` property exists at all, ask `AskUserQuestion`: **Add `Assignee` (People)** / **Skip** (assignment writes will warn-and-skip at runtime). Record the chosen name in `assigneeProperty` only when it is not the default `"Assignee"`. Remember whether an assignee slot exists — step 3b keys off it.
```

- [ ] **Step 3: Add step 3b (Default assignee)**

Insert a new step immediately after `#### 3a-iii. Populate config` and before `### 3c. If Cancel`:

```markdown
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
```

- [ ] **Step 4: Add the assignee drift-check line (reconfigure)**

In `#### Notion drift items`, step 2's property list, add this item after the **PR slot** bullet:

```markdown
   - **Assignee slot** (`assigneeProperty`): if config has `assigneeProperty` (or the default `"Assignee"` column is expected), it should exist and be `people`-typed; **informational only**, not a hard drift (mirrors the PR slot).
```

- [ ] **Step 5: Verify init edits are consistent**

Run:
```bash
grep -n "3b. Default assignee" plugins/notion-dev/commands/init.md
grep -n "Assignee" plugins/notion-dev/commands/init.md
grep -n "defaultAssignee" plugins/notion-dev/commands/init.md
```
Expected: step `3b. Default assignee` present; `Assignee` appears in the create-new table row, the use-existing matcher, and step 3b; `defaultAssignee` appears in step 3b (both write branches) and the reconfigure prefill line.

- [ ] **Step 6: Commit**

```bash
git add plugins/notion-dev/commands/init.md
git commit -m "feat(notion-dev): provision assignee column and prompt default in init"
```

---

### Task 5: README — document the assignee config keys and property

**Files:**
- Modify: `plugins/notion-dev/README.md`

**Interfaces:**
- Consumes: the finished behavior from Tasks 1–4. Docs only; no downstream consumer.

- [ ] **Step 1: Mention the keys in the `ticketSystem` config bullet**

In the "## Configuration" → "Key fields" list, replace the `ticketSystem` bullet:

```markdown
- `ticketSystem` — the Notion ticket-database config: `databaseId` (required) plus optional property-name overrides and `statusMap` / `typeMap` / `staticProperties`.
```

with:

```markdown
- `ticketSystem` — the Notion ticket-database config: `databaseId` (required) plus optional property-name overrides and `statusMap` / `typeMap` / `staticProperties`. Assignee support adds `assigneeProperty` (the People column, default `"Assignee"`) and `defaultAssignee` (a user id, email, or display name; `""` means create-task prompts each run). `/notion-dev:init` sets both.
```

- [ ] **Step 2: Add `Assignee` to the ticket-system property list**

In the "## Ticket system" section, replace:

```markdown
- Required properties: `Name` (title), `ID` (number), `Status` (select/status), `Type` (select), `PR` (URL).
```

with:

```markdown
- Required properties: `Name` (title), `ID` (number), `Status` (select/status), `Type` (select), `PR` (URL).
- Optional: `Assignee` (People) — `/notion-dev:create-task` assigns new tickets to a configured default, or prompts you to pick a workspace user when no default is set.
```

- [ ] **Step 3: Verify the README mentions**

Run: `grep -n "assigneeProperty\|defaultAssignee\|Assignee" plugins/notion-dev/README.md`
Expected: matches in both the config bullet and the ticket-system section.

- [ ] **Step 4: Commit**

```bash
git add plugins/notion-dev/README.md
git commit -m "docs(notion-dev): document assignee config keys and People property"
```

---

## Self-Review Notes

- **Spec coverage:** config keys (Task 1); `resolveAssignee` + People handling + `createTicket` arg (Task 2); create-task Phase 2.75 + single/mission threading + leave-unassigned + prompt-once-per-mission (Task 3); init create-new column + use-existing detection + step 3b `""` write + drift (Task 4); README (Task 5). Every spec section maps to a task.
- **Absence-tolerance** is stated once as a Global Constraint and applied identically in Tasks 2 and 4 (warn, never abort).
- **`resolveAssignee` return contract** (`{ id, name }` | `null`) is defined in Task 2 and consumed verbatim in Tasks 3 and 4.
- The interactive picker in create-task (Task 3) calls `notion-get-users` directly rather than through `resolveAssignee`, because it needs the *list* to display, not a single resolution — noted explicitly to avoid a phantom "list mode" of `resolveAssignee`.
