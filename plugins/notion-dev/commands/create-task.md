---
description: Produce a well-formed ticket from a prompt or an existing source. Runs a depth-calibrated interview (via notion-dev:ticket-interviewer) when needed, then writes the result to the configured ticket system.
argument-hint: "[--non-interactive] [--context-file=<path>] [--epic=<name>] [--parent=<id>] [--assignee=<id>] [--title=<text>] [--provenance=<marker>] [prompt:|existing-ticket:|notion-page:]<text-or-ref>"
---

# /notion-dev:create-task

Create or elaborate a ticket in the configured ticket system.

Args: `[<source>:]<ref>` or free prompt text.
- `prompt:<text>` or just the bare text — treat as a free-form requirement.
- `existing-ticket:<id>` — fetch and elaborate an existing ticket.
- `notion-page:<url-or-id>` — read a Notion page as input.

**Parsing rule.** Only treat a leading `<token>:` as a source selector when `<token>` exactly matches a known source name (`prompt`, `existing-ticket`, `notion-page`). Otherwise — including when the argument merely happens to contain a colon (e.g. `Add rate limiting: 100 req/min`) — default to `prompt` and treat the **entire** argument as raw text. Never infer a source from an arbitrary word before a colon.

**Flags.** Six optional flags are parsed off the front of the argument string **before** the source-selector parsing rule runs, so they never interfere with free-prompt text:

| Flag | Effect |
|---|---|
| `--non-interactive` | Never pause for user input; see the phase table below. |
| `--context-file=<path>` | Path to a markdown context packet. Seeds the interviewer, and is the proxy respondent's evidence base. Valid with or without `--non-interactive`. |
| `--epic=<name>` | Skip Phase 2.6's matching; use this Epic select value verbatim. |
| `--parent=<id>` | Epic page ticket id for the `parentTaskProperty` relation. Normally passed with `--epic`. Flows into Phase 3.2's `createTicket({ …, parent })` argument — **not** through `setParent`, which no path in this plugin calls — so the relation is written in the same create call as the page (see `createTicket` steps 1a and 2 in `notion-dev:ticket-system`), never as a follow-up update. **Taken on trust** — unlike `--epic`/`--parent` pairs resolved internally via `findEpics()`, an explicitly supplied `--parent` gets no epic-structure check (there is no way to guard it without also blocking the legitimate case of attaching a brand-new epic's first child); the caller is responsible for passing the id of an actual epic. |
| `--assignee=<id>` | Skip Phase 2.75's resolution; use this Notion user id. |
| `--title=<text>` | Pin the ticket's final title to this exact string (see Phase 2.1). The interviewer still elaborates the body, but does not get to rewrite the title. |
| `--provenance=<marker>` | Pin this exact marker line into the created ticket's `## Context` section (see Phase 2.1). The marker is folded into `body` before Phase 3.2's single write — never appended in a separate call afterward — so the ticket and its provenance marker come into existence in the same atomic operation, or neither does. |

`--epic`, `--parent`, `--assignee`, `--title`, and `--provenance` are what let `/notion-dev:ticket` and `/notion-dev:finalize` file a review follow-up as a sibling under the resolving ticket's epic with no prompting. `--title` and `--provenance` together are what let a caller dedup its own follow-ups reliably: `--title` derives a title, passes it here, and knows that string is exactly what ends up stored; `--provenance` derives a marker and knows it is written into `## Context` as part of ticket creation itself, not as a follow-up step a crash between the two could skip.

**`--non-interactive` phase behavior:**

| Phase | Interactive | Non-interactive |
|---|---|---|
| 2.1 interview | Questions go to the user | Questions go to a **proxy-respondent subagent** (below) |
| 2.1 title | Interviewer's returned `title` is used as-is, unless `--title` is supplied — then that exact string always wins, in either mode | Same rule: `--title`, when supplied, overrides the interviewer's returned `title`; otherwise the interviewer's value is used |
| 2.1 provenance | Interviewer's returned `body`'s `## Context` section is used as-is, unless `--provenance` is supplied — then the marker is force-inserted into `## Context` verbatim before Phase 3.2 writes, in either mode | Same rule: `--provenance`, when supplied, is folded into `## Context` before Phase 3.2's creation call; otherwise the interviewer's `## Context` is used unchanged |
| 2.2 confirm | `create` / `revise` / `cancel` | Auto-`create` |
| 2.5 breakdown | May return a mission | Auto-collapse to `single` |
| 2.6 epic attach | Prompt on candidates | Use `--epic` / `--parent`, or attach to none |
| 2.75 assignee | Prompt when unresolved | Use `--assignee`, else `defaultAssignee`, else leave unassigned |
| 3.1 type | Prompt when unclear | Infer from the body; default `improvement` |

**Proxy-respondent subagent.** The interviewer still runs in full — depth calibration, clarity audit, all of it — but its questions are answered by a **fresh subagent**, not by the main loop.

This is deliberate. When `/notion-dev:ticket` or `/notion-dev:finalize` files a deferred review item, the main loop is the agent that *wrote* that item during review. Having it answer its own interview restates its own assumptions and produces a ticket that looks elaborated but carries no new information. A fresh agent, handed the ticket, the merge diff, and the review thread, has to actually read them.

Dispatch the subagent with the context packet and this instruction: *answer the interviewer's questions as the requester would, grounding every answer in the packet; when the packet does not support an answer, reply "unknown — needs human input" rather than inventing detail.* Answers of that form flow into the ticket's `## Open Questions`, so the gap stays visible instead of becoming a confident-sounding fabrication.

**Standing rule — runtime issues.** Anything unexpected at runtime — for example an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, or a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens, not batched to the end of the run. That skill is **authoritative** for the full trigger list, the entry format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must **not** be logged; the examples here are illustrative, not exhaustive. The rule applies to conditions nobody enumerated in advance. A failure to write the log never fails the run.

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

When `--title` was supplied, it wins: use that exact string as the ticket's title and discard the interviewer's returned `title`. The interviewer still elaborates `body` in full — depth calibration, clarity audit, everything — only the title is pinned. This is what lets a caller (e.g. `epic-update`'s follow-up filing) derive a title once and know it is exactly what gets stored, regardless of what the interviewer would otherwise have produced.

When `--provenance` was supplied, apply the same discipline to `## Context`: after the interviewer returns `body`, ensure its `## Context` section contains the marker as a verbatim line — appended to whatever the interviewer wrote there if not already present, never replacing the section's other content. This happens here, before Phase 3.2's single write — not as a follow-up call after creation. The marker is part of the same `body` that `createTicket`/`updateTicket` writes in one call, so the ticket and its marker are created together, atomically, or neither is. A `revise` loop (Phase 2.2) re-invokes the interviewer with a fresh `body`; re-apply the same insertion on every pass so the marker survives every revision.

No `confidence`-branching lives in this command — depth calibration is fully owned by the skill.

In **non-interactive mode**, the interviewer's questions go to the proxy-respondent subagent described above instead of to the user. Everything else about the interview is unchanged.

### 2.2 Confirm

Show the returned `title` + `body` to the user. Ask `AskUserQuestion`: "Create this ticket? (create / revise / cancel)".
- `revise` — loop back: take user feedback, re-invoke `notion-dev:ticket-interviewer` with the current body + user notes as additional context, re-ask.
- `cancel` — abort.
- `create` — proceed to Phase 2.5.

In **non-interactive mode**, skip this gate: proceed as if the user chose `create`, and log the auto-decision for the Phase 4 report.

---

## Phase 2.5 — Breakdown assessment

Decide whether this is one ticket or a multi-task mission. The plugin defaults to single-ticket; splitting requires clear evidence. `existing-ticket` source mode **always skips this phase** — elaborating an existing ticket never splits it.

In **non-interactive mode**, instruct `notion-dev:task-breakdown` to return `single` and skip 2.5.2 and 2.5.3 entirely. This mode exists to file one deferred review finding, which is one item by construction; running the breakdown and then discarding a mission result would be wasted work.

### 2.5.1 Invoke task-breakdown

Invoke `notion-dev:task-breakdown` passing `{ title, body, sourceRef, type? }` from Phase 2. The skill returns either:

- `{ kind: "single", title, body, type? }` → proceed to Phase 3 with the single-ticket path.
- `{ kind: "mission", epic, tasks: [...] }` → continue with step 2.5.2.

### 2.5.2 Reconcile the proposed Epic

The breakdown skill emits a proposed Epic name. Reconcile it against the configured ticket system before using it — the reconciliation is driven entirely by `getSelectOptions`' return:

1. Invoke `notion-dev:ticket-system` operation `getSelectOptions(epicProperty)` — pass the literal config key `epicProperty` itself, not the live column name it resolves to (`"Epic"` by default).
2. If the return is `null` (property absent or not a selectable type) → skip the Epic entirely. Set `epic = undefined` on all tasks and record `EPIC_PROPERTY_ABSENT = true` — carried through to Phase 4's mission report, where it distinguishes this degradation (no Epic select tag is possible on any task, since `createTicket` only writes the Epic select when `epicProperty` exists) from the narrower case where the select tagging still succeeds and only the container page is missing — because one of the two containment properties (`parentTaskProperty` or `epicMarkerProperty`) was unusable, absent or wrong-typed. Continue to 2.5.3.
3. If the proposed name exists in the returned list (case-insensitive match) → reuse; rebind to the exact live casing; continue to 2.5.3.
4. If no match → ask `AskUserQuestion`:
   - **Create "\<proposed\>"** — invoke `notion-dev:ticket-system` operation `addSelectOption(epicProperty, "<proposed>")` (`epicProperty` is again the literal config key, not its live column name); then use it.
   - **Pick existing** — show the live option list as sub-choices; user picks one; rebind.
   - **Collapse to single ticket** — merge the mission's task bodies into one (concatenate `## Requirements`, combine `## Acceptance Criteria` into one checklist, preserve all other sections) and proceed to Phase 3 single-path with no Epic.

Once the Epic **select value** is reconciled, resolve the Epic **page** — the container the tasks will hang from. This step only decides *which* page: reuse one that already exists, or record that a new one is needed. It does **not** call `createEpic` itself — `createEpic` takes an `assignee`, and Phase 2.75 (which resolves the assignee) runs *after* this phase, so the value doesn't exist yet here. The actual call is deferred to Phase 3.2's mission path, before Pass 0, which is the first point `assignee` is known and also where `EPIC_ID` is first required (by `parent: EPIC_ID` in the create loop).

1. Invoke `notion-dev:ticket-system` operation `findEpics()`.
2. `findEpics()` returned **`null`** (epic containers are unavailable on this DB — **either** `epicMarkerProperty` or `parentTaskProperty` is unusable, absent or wrong-typed; the return does not say which) → `EPIC_ID = undefined`, `EPIC_TO_CREATE` stays unset, and record **`EPIC_UNAVAILABLE_CAUSE = containers-unavailable`** — carried through to Phase 4's mission report. Continue with Epic-select tagging only; do not prompt. (This is the "no epic containers on the DB" degradation path; Phase 3.2's deferred-creation step checks for it via `EPIC_TO_CREATE` being unset, so it never fires here either.) Neither branch writes to the issue log here. The `null` case is recorded once by `notion-dev:ticket-system` — whichever of `missing-property:` / `wrong-type:` applies to whichever containment property was unusable; the `[]` case is routine and is never logged at all. See `notion-dev:issue-log`.
3. Otherwise `findEpics()` returned an array (possibly `[]`, meaning `epicMarkerProperty` is **usable** — present and Checkbox-typed — but no page has it set to `true` yet — a page merely carrying the Epic select tag does not count, see `findEpics()` in `skills/ticket-system/SKILL.md`). A returned epic whose `name` matches the reconciled Epic value (case-insensitive) → reuse it. Record its **`id`** (the logical ticket id, e.g. `67` — *not* `pageId`) as `EPIC_ID`; `EPIC_TO_CREATE` stays unset.
4. No match (including the `[]` case) → do **not** create the epic yet. Record `EPIC_TO_CREATE = { name: <reconciled Epic value>, overview: <2-4 sentence distillation of the mission's goal from the source body>, type: <the dominant task type across the mission> }` — everything `createEpic` will need except `assignee`. `EPIC_ID` stays unresolved until Phase 3.2.

`EPIC_ID` is `undefined` and `EPIC_TO_CREATE` stays unset on the "Collapse to single ticket" branch — a collapsed mission is a single ticket and goes through Phase 2.6 like any other.

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

## Phase 2.6 — Attach to an epic (single-ticket path only)

Runs only when Phase 2.5 returned `kind: "single"`. Skipped entirely for missions (2.5.2 already resolved the epic) and for the `existing-ticket` source mode, which never re-parents a ticket — the same rule that makes it skip Phase 2.5.

1. Invoke `notion-dev:ticket-system` operation `findEpics()`. **`null`** (epic containers are unavailable on this DB — either containment property is unusable, absent or wrong-typed) → skip silently, no prompt: the unavailable-degrade case. **`[]`** (both properties are usable but no page has the marker set to `true` yet) → also skip silently, no prompt, but for a different reason: there is simply nothing to attach to. Both are silent, but they are different states — do not conflate them in any future change here. Neither branch writes to the issue log here. The `null` case is recorded once by `notion-dev:ticket-system` — whichever of `missing-property:` / `wrong-type:` applies to whichever of `epicMarkerProperty` / `parentTaskProperty` was unusable; the `[]` case is routine and is never logged at all. See `notion-dev:issue-log`.

   This command reaches `findEpics()` **directly, with no preceding `fetchTicket`**, so `findEpics` performs the usability check and the recording itself — see the "Marker usability rule" in `notion-dev:ticket-system`. Do not add a caller-side type check here; the adapter owns it.
2. Judge the ticket's title and `## Requirements` against each epic's `name` and `## Overview`. This is a semantic judgment, not string matching: an epic is a plausible candidate when this ticket is work on the same incident, feature, or investigation. A shared word is not a match.
3. **Zero plausible candidates → skip silently.** No prompt. This is the common case, and routine single-ticket runs must stay as quiet as they are today.
4. **One or more plausible candidates** → ask `AskUserQuestion`: *"This looks related to an existing epic. Attach it?"*
   - **Attach to `[<KEY>-<n>] <name>`** — the best candidate first, further candidates as additional options. Record the candidate's **`id`** (the logical ticket id, not `pageId`) as `EPIC_ID`, and the epic name.
   - **Pick another** — show the full `findEpics()` list as sub-choices.
   - **No epic** — proceed unattached; `EPIC_ID = undefined`.

**Non-interactive mode** never prompts here: use `--epic` / `--parent` when supplied, else attach to nothing.

---

## Phase 2.75 — Resolve assignee

Decide **who** the new ticket(s) get assigned to. Produces a single `assignee`
value — a resolved Notion user id, or the sentinel "unassigned" — reused for
every `createTicket` in Phase 3. Runs once, even for a mission.

1. **`--assignee` supplied** → `assignee = <that id>`; skip the rest of this phase. In non-interactive mode without the flag, fall through to `defaultAssignee` resolution below, and if that fails, `assignee = unassigned` — never prompt.
2. Read `ticketSystem.defaultAssignee` from config.
   - **Set and non-empty** → invoke `notion-dev:ticket-system` operation
     `resolveAssignee(defaultAssignee)`.
     - Unique match → `assignee = <id>`; continue to Phase 3 silently.
     - `null` (no match / ambiguous) → warn
       (`"defaultAssignee '<value>' did not resolve to a unique user; pick manually"`)
       and fall through to step 3.
   - **Absent or empty string (`""`)** → go to step 3.
3. **Interactive pick.** This needs the full user *list* to display, so call
   `mcp__notion__notion-get-users` directly (not `resolveAssignee`, which
   resolves a single value). Filter to `type == "person"` and present their
   display names with `AskUserQuestion`: "Assign this ticket to whom?".
   Include a final **"Leave unassigned"** option.
   - A named pick → resolve to that user's id → `assignee = <id>`.
   - "Leave unassigned" → `assignee = unassigned` (pass no `assignee` in Phase 3).
4. **Missions:** the single `assignee` decided here applies to **every** task —
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

In **non-interactive mode**, never ask: infer from the body, and when genuinely unclear default to `improvement` — the least-committal of the four, and the easiest to correct later.

For `mission` results, `type` is per-task on the breakdown output; apply the same inference per task when a task's `type` is absent.

Before any ticket-system call, normalize `type` to its **logical key** — lowercase the label (`Feature` → `feature`, `Bug` → `bug`, `Improvement` → `improvement`, `Research` → `research`). `notion-dev:ticket-system` translates logical keys through `typeMap`; passing the display label misses the map entry, and `/notion-dev:ticket`'s bug hard-rule depends on the normalized value round-tripping through the DB.

### 3.2 Write to the ticket system

#### Single-ticket path

Invoke `notion-dev:ticket-system`:
- If source was `existing-ticket`, operation is `updateTicket(id, { title, body, type })` — update in place. (Treat this as a `createTicket`-style call with the existing id; the ticket-system skill handles the distinction.)
- Otherwise, operation is `createTicket({ title, body, type, assignee, epic, parent })` — new ticket. Omit `assignee` when Phase 2.75 chose "Leave unassigned"; omit `epic` and `parent` when Phase 2.6 attached to no epic (`epic` = the epic name, `parent` = `EPIC_ID`). `existing-ticket` `updateTicket` never sets an assignee or a parent — both are creation-only.

`body` already carries the `--provenance` marker, folded into `## Context` back in Phase 2.1 when the flag was supplied. No separate write follows this call to add it — the marker and the ticket exist from the same operation.

Capture the returned `{ id, url }`.

#### Mission path (two-pass)

**Epic creation** (mission path only; runs before Pass 0 — skip entirely when `EPIC_ID` is already set from 2.5.2's reuse match, or when `EPIC_TO_CREATE` was never set, i.e. the DB lacks epic containers or the mission collapsed): invoke `notion-dev:ticket-system` operation `createEpic({ name: EPIC_TO_CREATE.name, overview: EPIC_TO_CREATE.overview, type: EPIC_TO_CREATE.type, assignee })`. Omit `assignee` when Phase 2.75 chose "Leave unassigned". `assignee` is Phase 2.75's resolved value — this is why the call waits until here instead of running inline in 2.5.2, where `EPIC_TO_CREATE` was recorded but Phase 2.75 hadn't run yet. Record the result's **`id`** (the logical ticket id — the result shape is `{ id, key, url, pageId }`) as `EPIC_ID`, the same field 2.5.2's reuse path records. A `null` return sets **`EPIC_UNAVAILABLE_CAUSE = containers-unavailable`**, the same value 2.5.2 uses — `createEpic` returns a bare `null` when either containment property is unusable and does not say which, so no property may be named here either. Reaching this at all means containers went from usable to unusable **between 2.5.2 and now**: `findEpics()` applies the identical two-slot check, so a run that got past 2.5.2 with containers available has already been told they were. Treat this as the mid-run-change backstop it is, not a routine branch. It then degrades the same way 2.5.2 step 2 does: `EPIC_ID = undefined`, continue with Epic-select tagging only.

**Pass 0 — reconcile Phase options** (mirrors the Epic reconciliation in 2.5.2, but non-interactive — phase labels are generated per-mission structure, not user taxonomy, so missing options are auto-added rather than prompted): invoke `notion-dev:ticket-system` operation `getSelectOptions(phaseProperty)` — pass the literal config key `phaseProperty` itself, not the live column name it resolves to (`"Phase"` by default). If the return is `null` → set `phase = undefined` on all tasks. Otherwise, rebind case-insensitive matches to the exact live casing, and for each distinct `task.phase` absent from the returned options invoke `addSelectOption(phaseProperty, "<phase>")` (same rule: the literal config key, not its live column name). `createTicket` requires an exact option match and raises otherwise — reconcile before the first create, or Pass 1 fails partway through.

**Pass 1 — create all tickets** (in declaration order, so each task is visible in the DB before its potential dependents are written):

```
taskMap = []
for task in mission.tasks:
  result = ticket-system.createTicket({
    title:    task.title,
    body:     task.body,
    type:     task.type,
    epic:     mission.epic,     // reconciled name from 2.5.2
    parent:   EPIC_ID,          // logical ticket id (createTicket resolves it to a page id via fetchTicket, same as setParent); omitted when undefined
    phase:    task.phase,       // omitted fields pass through as absent
    step:     task.step,
    assignee: assignee,         // from Phase 2.75; omit when "unassigned"
  })
  taskMap.push({ id: result.id, url: result.url, title: task.title })
```

**Pass 1.5 — populate the epic's task list** (skip when `EPIC_ID` is undefined):

Invoke `notion-dev:ticket-system` operation `refreshEpicTasks(EPIC_ID)`. That operation owns the `## Tasks` render format entirely — do **not** render the list here, or this command and the epic-update flow will drift apart.

This runs even though nothing has resolved yet, so the epic reads as a real plan the moment it exists. A failure here is non-fatal — warn and continue to Pass 2.

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

**Issue-log sweep.** Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`. Best-effort — a failure here never fails the run.

### Single-ticket result

Print:
- New (or updated) ticket ID and URL.
- The epic it was attached to, when Phase 2.6 attached one: `Epic: [<KEY>-<n>] <name> · <url>`. Omit the line entirely when unattached.
- A one-line summary of what was captured.
- Non-interactive decisions taken during the run, if any (e.g. Phase 2.2's auto-`create`).
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`. Omit the line entirely when the run logged nothing.
- Next step: "Run `/notion-dev:ticket <ticket-id>` when you're ready to implement (the page id is in the ticket URL above)."

### Mission result

Open with one of three lines, chosen by whether `EPIC_ID` is set and, when it is not, by `EPIC_PROPERTY_ABSENT` (recorded in Phase 2.5.2 step 2). The two `EPIC_ID`-undefined cases are **not** interchangeable: `createTicket`'s "Mission metadata" step (`skills/ticket-system/SKILL.md`) writes the Epic select only when `epicProperty` exists on the live DB, independently of whether either containment property (`parentTaskProperty`, `epicMarkerProperty`) is usable — so a missing `epicProperty` degrades further than an unusable containment property alone, and the report must say which happened:

- `EPIC_ID` set → `Mission created under Epic: [<KEY>-<n>] <epic name> · <epic url>`.
- `EPIC_ID` undefined and `EPIC_PROPERTY_ABSENT` is **not** set (`epicProperty` exists, so the Epic select write succeeded; what failed is epic *containment*, because either `parentTaskProperty` or `epicMarkerProperty` was **unusable** — absent, or present but of the wrong type, which degrade identically — per Phase 2.5.2 and Phase 3.2's epic-creation step. Which of the two failed is known only in the `findEpics()` case; see `EPIC_UNAVAILABLE_CAUSE` below, which is the only thing the report may branch on. Never default to naming `Parent task` — that was a real defect here, reporting the wrong missing property in exactly the summary whose job is to say which happened.) → the Epic select write still succeeded on every task; only the container page is missing. Print: `Mission tagged with Epic select "<epic name>" on every task — no container page (<reason>).` Derive `<reason>` from **`EPIC_UNAVAILABLE_CAUSE`**, never from a hardcoded property name:

  - `containers-unavailable` (set by Phase 2.5.2's `findEpics()` returning `null`, or Phase 3.2's `createEpic` returning `null` — both apply the identical two-slot check) → `epic containers are unavailable on this DB`. **Do not name a specific property.** Both operations return a bare `null` when *either* `epicMarkerProperty` or `parentTaskProperty` is unusable, and neither reports which, so any more specific wording would be a guess — the exact defect this rule exists to prevent. An unnamed-but-true reason is correct; the issue log carries the specific property for whoever needs it.
- `EPIC_ID` undefined and `EPIC_PROPERTY_ABSENT` **is** set (`epicProperty` itself is absent from the live DB, so `epic` was already `undefined` on every task from Phase 2.5.2 step 2 onward) → `createTicket` skipped the Epic write entirely: no container page **and** no select tag on any task. Print: `Mission created with no Epic grouping — this DB has no "<epicProperty configured name>" select property to tag tasks with, so there is nothing to group by and no container was attempted.` **Do not name `Parent task` or `Is Epic` here.** On this path `epicProperty` was absent, so Phase 2.5.2 step 2 returned before `findEpics()` ran and Phase 3.2's epic-creation step was skipped for want of `EPIC_TO_CREATE` — meaning neither containment property was ever examined and `EPIC_UNAVAILABLE_CAUSE` is legitimately unset. Claiming the DB "has no Parent task relation" would be a fabrication about a column that may well exist and be correctly typed; this is the one branch where unset is the right answer and the report must say only what it knows. Never silently drop either of the last two lines, and never conflate them — a user who expected grouping metadata needs to know exactly what they didn't get and which property is missing.

Then the structured summary:

```
<phase 1 name>          (if phases used)
  Step 1 — <KEY>-<id> · <title> · <url>
  Step 2 — <KEY>-<id> · <title> · <url>
<phase 2 name>
  Step 1 — <KEY>-<id> · <title> · <url>
    depends on: <KEY>-<id>, <KEY>-<id>
…

Tickets created: N.
Dependencies wired: M edges across K tasks.

Next step: Run `/notion-dev:ticket <ticket-id>` on any task to implement (the page id is in each task's URL above). The plugin does not auto-sequence — dependency tags are informational.
```

Also print any non-interactive decisions taken during the run, if any (e.g. Phase 2.2's auto-`create`), and issues logged, when this run wrote any, same as the single-ticket result above.

When `phase` isn't used in the mission, flatten to a plain numbered list.

---

## Failure and stop conditions

- Source returns no content (e.g. empty prompt, missing ticket) → ask the user for input or abort.
- Ticket-system MCP unavailable → abort with clear retry guidance.
- User cancels at confirm gate → abort; do not write. Best-effort, before stopping: run the issue-log sweep from Phase 4 — this path skips Phase 4 entirely, and an unrecoverable failure is the single most valuable thing this log can record. A failure to write it never masks the real failure report.
