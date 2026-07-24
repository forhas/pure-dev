---
description: Produce a well-formed ticket from a prompt or an existing source. Runs a depth-calibrated interview (via notion-dev:ticket-interviewer) when needed, then writes the result to the configured ticket system.
argument-hint: "[prompt:|existing-ticket:|notion-page:]<text-or-ref>"
---

# /notion-dev:create-task

Create or elaborate a ticket in the configured ticket system.

Args: `[<source>:]<ref>` or free prompt text.
- `prompt:<text>` or just the bare text — treat as a free-form requirement.
- `existing-ticket:<id>` — fetch and elaborate an existing ticket.
- `notion-page:<url-or-id>` — read a Notion page as input.

**Parsing rule.** Only treat a leading `<token>:` as a source selector when `<token>` exactly matches a known source name (`prompt`, `existing-ticket`, `notion-page`). Otherwise — including when the argument merely happens to contain a colon (e.g. `Add rate limiting: 100 req/min`) — default to `prompt` and treat the **entire** argument as raw text. Never infer a source from an arbitrary word before a colon.

## Preconditions

- `.claude/notion-dev.config.json` exists and has `ticketSystem` configured.
- The source named in the arg is listed in `inputSources`; if not, abort and tell the user to add it via `/notion-dev:init`.

---

## Phase 1 — Ingest

Invoke `notion-dev:input-source` with the resolved `(source, ref)`. You get back `{ title, body, sourceRef, confidence }`.

Show a short preview to the user.

---

## Phase 2 — Elaborate

**Invariant:** this phase does not exit until the ticket has a clear goal, well-scoped requirements, explicit acceptance criteria, and no open questions that would change the implementation.

### 2.1 Run the interview

Invoke `notion-dev:ticket-interviewer`, passing `{title, body, sourceRef, confidence}` from Phase 1. The skill:

- Calibrates interview depth to `confidence` (high / medium / low).
- Runs a clarity audit (Goal, Scope, Acceptance Criteria, Edge Cases, Dependencies, Data shape) as its shared safety net across tiers — even on high-confidence input.
- Returns `{ title, body, type? }` where `body` is markdown formatted with `## Requirements`, `## Acceptance Criteria` (checklist), `## Context`, `## Open Questions`, `## Source`.

No `confidence`-branching lives in this command — depth calibration is fully owned by the skill.

### 2.2 Confirm

Show the returned `title` + `body` to the user. Ask `AskUserQuestion`: "Create this ticket? (create / revise / cancel)".
- `revise` — loop back: take user feedback, re-invoke `notion-dev:ticket-interviewer` with the current body + user notes as additional context, re-ask.
- `cancel` — abort.
- `create` — proceed to Phase 2.5.

---

## Phase 2.5 — Breakdown assessment

Decide whether this is one ticket or a multi-task mission. The plugin defaults to single-ticket; splitting requires clear evidence. `existing-ticket` source mode **always skips this phase** — elaborating an existing ticket never splits it.

### 2.5.1 Invoke task-breakdown

Invoke `notion-dev:task-breakdown` passing `{ title, body, sourceRef, type? }` from Phase 2. The skill returns either:

- `{ kind: "single", title, body, type? }` → proceed to Phase 3 with the single-ticket path.
- `{ kind: "mission", epic, tasks: [...] }` → continue with step 2.5.2.

### 2.5.2 Reconcile the proposed Epic

The breakdown skill emits a proposed Epic name. Reconcile it against the configured ticket system before using it — the reconciliation is driven entirely by `getSelectOptions`' return:

1. Invoke `notion-dev:ticket-system` operation `getSelectOptions(<epicProperty>)` (the configured name, default `"Epic"`).
2. If the return is `null` (property absent or not a selectable type) → skip the Epic entirely. Set `epic = undefined` on all tasks; continue to 2.5.3.
3. If the proposed name exists in the returned list (case-insensitive match) → reuse; rebind to the exact live casing; continue to 2.5.3.
4. If no match → ask `AskUserQuestion`:
   - **Create "\<proposed\>"** — invoke `notion-dev:ticket-system` operation `addSelectOption(<epicProperty>, "<proposed>")`; then use it.
   - **Pick existing** — show the live option list as sub-choices; user picks one; rebind.
   - **Collapse to single ticket** — merge the mission's task bodies into one (concatenate `## Requirements`, combine `## Acceptance Criteria` into one checklist, preserve all other sections) and proceed to Phase 3 single-path with no Epic.

### 2.5.3 Confirm the breakdown

Show the user a compact summary:

```
Epic: <resolved name>
Tasks (N):
  1. <phase> · step <n> — <title>          [deps: <titles>]
  2. …
```

Ask `AskUserQuestion`: **Approve / Revise / Collapse to single ticket**.

- **Revise** — capture user feedback and re-invoke `notion-dev:task-breakdown` with the body plus notes.
- **Collapse** — same fallback as 2.5.2 option.
- **Approve** — proceed to Phase 3 mission path.

---

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

---

## Phase 3 — Write

### 3.1 Classify the type

If the interviewer returned a `type`, use it. Otherwise infer from the body content:
- **Feature** — adding new capability.
- **Bug** — fixing broken behavior.
- **Improvement** — refactoring / polish.
- **Research** — investigation without code output.

If still unclear, ask `AskUserQuestion` with the four options.

For `mission` results, `type` is per-task on the breakdown output; apply the same inference per task when a task's `type` is absent.

Before any ticket-system call, normalize `type` to its **logical key** — lowercase the label (`Feature` → `feature`, `Bug` → `bug`, `Improvement` → `improvement`, `Research` → `research`). `notion-dev:ticket-system` translates logical keys through `typeMap`; passing the display label misses the map entry, and `/notion-dev:ticket`'s bug hard-rule depends on the normalized value round-tripping through the DB.

### 3.2 Write to the ticket system

#### Single-ticket path

Invoke `notion-dev:ticket-system`:
- If source was `existing-ticket`, operation is `updateTicket(id, { title, body, type })` — update in place. (Treat this as a `createTicket`-style call with the existing id; the ticket-system skill handles the distinction.)
- Otherwise, operation is `createTicket({ title, body, type, assignee })` — new ticket. Omit `assignee` when Phase 2.75 chose "Leave unassigned". `existing-ticket` `updateTicket` never sets an assignee (assignment is creation-only).

Capture the returned `{ id, url }`.

#### Mission path (two-pass)

**Pass 0 — reconcile Phase options** (mirrors the Epic reconciliation in 2.5.2, but non-interactive — phase labels are generated per-mission structure, not user taxonomy, so missing options are auto-added rather than prompted): invoke `notion-dev:ticket-system` operation `getSelectOptions(<phaseProperty>)` (the configured name, default `"Phase"`). If the return is `null` → set `phase = undefined` on all tasks. Otherwise, rebind case-insensitive matches to the exact live casing, and for each distinct `task.phase` absent from the returned options invoke `addSelectOption(<phaseProperty>, "<phase>")`. `createTicket` requires an exact option match and raises otherwise — reconcile before the first create, or Pass 1 fails partway through.

**Pass 1 — create all tickets** (in declaration order, so each task is visible in the DB before its potential dependents are written):

```
taskMap = []
for task in mission.tasks:
  result = ticket-system.createTicket({
    title:    task.title,
    body:     task.body,
    type:     task.type,
    epic:     mission.epic,     // reconciled name from 2.5.2
    phase:    task.phase,       // omitted fields pass through as absent
    step:     task.step,
    assignee: assignee,         // from Phase 2.75; omit when "unassigned"
  })
  taskMap.push({ id: result.id, url: result.url, title: task.title })
```

**Pass 2 — wire dependencies**:

```
for task in mission.tasks:
  if task.dependsOn is empty: continue
  depIds = []
  for depTitle in task.dependsOn:
    match = taskMap.find(t => t.title === depTitle)
    if not match: warn — "dependency '<depTitle>' not found in this mission; skipping"
    else: depIds.push(match.id)
  if depIds not empty:
    ticket-system.setDependencies(<id-for-this-task>, depIds)
```

If Pass 1 fails partway, report what succeeded (with IDs/URLs) and stop before Pass 2 — leave the partial state for the user to investigate. Do not attempt rollback.

---

## Phase 4 — Report

### Single-ticket result

Print:
- New (or updated) ticket ID and URL.
- A one-line summary of what was captured.
- Next step: "Run `/notion-dev:ticket <ticket-id>` when you're ready to implement (the page id is in the ticket URL above)."

### Mission result

Print a structured summary:

```
Mission created under Epic: <epic name>

<phase 1 name>          (if phases used)
  Step 1 — STO-<id> · <title> · <url>
  Step 2 — STO-<id> · <title> · <url>
<phase 2 name>
  Step 1 — STO-<id> · <title> · <url>
    depends on: STO-<id>, STO-<id>
…

Tickets created: N.
Dependencies wired: M edges across K tasks.

Next step: Run `/notion-dev:ticket <ticket-id>` on any task to implement (the page id is in each task's URL above). The plugin does not auto-sequence — dependency tags are informational.
```

When `phase` isn't used in the mission, flatten to a plain numbered list.

---

## Failure and stop conditions

- Source returns no content (e.g. empty prompt, missing ticket) → ask the user for input or abort.
- Ticket-system MCP unavailable → abort with clear retry guidance.
- User cancels at confirm gate → abort; do not write.
