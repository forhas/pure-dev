# notion-dev Runtime Issue Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the notion-dev plugin a durable, redacted, deduplicated runtime issue log at `$REPO_ROOT/.claude/notion-dev/notion-dev-issues.md`, so a client hitting a plugin defect can forward one file to the plugin author.

**Architecture:** A new shared skill `notion-dev:issue-log` owns the file location, entry format, signature vocabulary, redaction contract, dedup algorithm, and the list of conditions that are routine and must not be logged. A companion `references/signatures.md` is the single definition point for every enumerated signature name. Four command files gain a standing-rule preamble, an end-of-run sweep, a conditional report line, and a failure-path sweep. `ticket-system/SKILL.md` gains a signature citation at each of its fifteen existing warning sites. No other skill file is touched.

**Tech Stack:** Markdown instruction text only. No executable code, no hooks, no test framework. This plugin is prompt-and-markdown; every "implementation" file is text an AI agent reads and follows at runtime.

**Spec:** `docs/superpowers/specs/2026-08-02-notion-dev-issue-log-design.md`

## Global Constraints

- **Target version:** `0.8.0` → `0.9.0`. Only `.claude-plugin/plugin.json` and `README.md` state a version. No version literal goes anywhere else.
- **Scope:** `plugins/notion-dev` only. `plugins/quick-dev` is never modified, including its own copies of `flow-triage`, `plan-review`, `local-code-review`, and `review-and-merge`.
- **Untouched skill files:** `plan-review/SKILL.md`, `local-code-review/SKILL.md`, `review-and-merge/SKILL.md`, `epic-update/SKILL.md`. Their degradations are logged by the calling command. `plan-review` Step 1 is a closed enumeration; threading anything into it silently fails.
- **There is no test harness and none is added.** Every task ends in verification commands with stated expected output. Do not propose pytest, jest, bats, or any test framework.
- **Verification of signature closure is directional until the final task.** Tasks 1–6 check only that every signature named in a call site exists in the registry. Full set *equality* — which also catches dead registry entries — runs once, in Task 7, when all call sites exist. An intermediate task that reports "registry has entries no call site names" has not failed.
- **Redaction is structural.** Never write ticket titles, ticket bodies, PR contents, diffs, Notion user ids, email addresses, personal names, full database ids, full page ids, absolute filesystem paths, or URLs into the log or into any example of the log.
- **The two-places rule.** Before finishing any task, check whether each fact you added or changed is stated anywhere else in that same file — a quick-reference table versus its detailed section, a lead-in count versus the length of the list below it, sibling operations that should have received the same change. This single check caught every defect across ten review rounds on the previous branch.

---

## File Structure

| File | Responsibility |
|---|---|
| `plugins/notion-dev/skills/issue-log/SKILL.md` | **New.** The contract: when to log, what is routine and never logged, where the file lives, entry format, dedup procedure, redaction whitelist, best-effort rules. Never lists individual call sites. |
| `plugins/notion-dev/skills/issue-log/references/signatures.md` | **New.** The registry. The only place an enumerated signature name is defined. |
| `plugins/notion-dev/skills/ticket-system/SKILL.md` | **Modify.** Fifteen existing warning sentences each gain a signature citation. No new detection logic. |
| `plugins/notion-dev/commands/ticket.md` | **Modify.** Preamble, Phase 9 sweep, Phase 10 report line, failure-path sweep, four caller-side signatures. |
| `plugins/notion-dev/commands/finalize.md` | **Modify.** Preamble, Phase 4 sweep, Phase 5 report line, failure-path sweep, two caller-side signatures. |
| `plugins/notion-dev/commands/create-task.md` | **Modify.** Preamble, Phase 4 sweep and report line, failure-path sweep. Cites existing signatures only. |
| `plugins/notion-dev/commands/init.md` | **Modify.** Preamble, report-step sweep and report line. Drift items cite existing signatures only. |
| `plugins/notion-dev/.claude-plugin/plugin.json` | **Modify.** Version bump. |
| `plugins/notion-dev/README.md` | **Modify.** New section documenting the log for clients. |

Tasks 3, 4, 5, and 6 touch disjoint files and depend only on Task 1. They may be executed in any order relative to each other.

---

## Shared text used by several tasks

These three blocks appear in more than one task. They are reproduced in full inside each task that needs them — do not cross-reference while implementing, since tasks may be read out of order.

**The standing-rule preamble** (Tasks 3, 4, 5, 6):

```markdown
**Standing rule — runtime issues.** Anything unexpected at runtime — for example an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, or a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens, not batched to the end of the run. That skill is **authoritative** for the full trigger list, the entry format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must **not** be logged; the examples here are illustrative, not exhaustive. The rule applies to conditions nobody enumerated in advance. A failure to write the log never fails the run.
```

**The sweep** (Tasks 3, 4, 5, 6):

```markdown
**Issue-log sweep.** Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`. Best-effort — a failure here never fails the run.
```

**The report line** (Tasks 3, 4, 5, 6) — printed only when this run wrote to the log:

```markdown
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`. Omit the line entirely when the run logged nothing.
```

---

## Task 1: The `issue-log` skill and its signature registry

**Files:**
- Create: `plugins/notion-dev/skills/issue-log/SKILL.md`
- Create: `plugins/notion-dev/skills/issue-log/references/signatures.md`

**Interfaces:**
- Consumes: nothing. This is the first task.
- Produces: the skill name `notion-dev:issue-log`, invoked by every later task. The twenty signature names in the registry, cited verbatim by Tasks 2–6. The entry format and the write procedure, referenced by nothing else — later tasks only cite signature names and invoke the skill.

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p plugins/notion-dev/skills/issue-log/references
```

- [ ] **Step 2: Write `plugins/notion-dev/skills/issue-log/SKILL.md`**

````markdown
---
name: issue-log
description: Use whenever a notion-dev command or skill hits anything unexpected at runtime — an MCP error or outage, a configured property missing or wrongly typed on the live database, a value that had to be guessed at, a retry, a fallback taken, an abort, a failed precondition, or any warning shown to the user. Records a deduplicated, redacted entry in the repo's notion-dev issue log so the plugin author can diagnose it. Also the authority on which conditions are routine and must never be logged.
---

# issue-log — durable record of runtime deviations

The notion-dev plugin has no runtime. There is no `finally`, no exception handler, no process supervising a run. An entry exists in this log because an instruction told an agent to write one and the agent complied.

That shapes what this log is good at. It captures quiet degradations well — they happen mid-flow, while the agent is already following instructions. It captures hard failures unreliably: a killed process, an exhausted context, or a user interrupt leaves nothing running to record its own death. **A short log is not evidence of a healthy run.**

The log is written for the **plugin author**, not the client. It is pure diagnostics. It never advises the client how to fix anything and never classifies whether an entry is the client's setup or the plugin's bug — the author does that.

## When to write an entry

Two layers, both mandatory.

**Layer 1 — the standing rule.** Anything unexpected at runtime, including conditions nobody enumerated in advance: an MCP error, an unexpected schema shape, a value guessed at, a retry, a fallback taken, an abort, a failed precondition, a warning shown to the user. Invent a signature under the grammar below.

**Layer 2 — enumerated sites.** The known degradation points carry explicit signature names, listed in `references/signatures.md`. Cite the registered name so common cases group instead of fragmenting into free-form prose.

Write **at the moment of the deviation**, never batched to the end of a run. A run that dies loses batched entries, and those are the runs whose record matters most.

## What is never logged

This list is as load-bearing as the standing rule. The plugin deliberately treats a number of absences and empty results as routine, and several are annotated in `ticket-system/SKILL.md` as "never a warning — these are routine, not exceptional". Logging them buries the real entries under normal operation.

| Condition | Why it is routine |
|---|---|
| `getEpicContext` returns `null` | Most tickets have no epic. `ticket-system/SKILL.md`: "Not a warning — this is the normal case for most tickets." |
| `findEpics()` returns `[]` | The marker property exists; no page is marked yet. Nothing is wrong. |
| `resolveAssignee` returns `null` (zero or ambiguous matches) | `ticket-system/SKILL.md`: "routine, not exceptional." The caller falls back to a picker. |
| `fetchTicket` returning a type's empty default for an unset or absent property | Absence-tolerant reads are the design. "Never a warning." |
| Zero plausible epic candidates in `/notion-dev:create-task` Phase 2.6 | "The common case, and routine single-ticket runs must stay as quiet as they are today." |
| A user declining a gate, choosing Revise, or aborting at a confirmation prompt | Normal interaction. The ledger already records it as `stopped`. |
| Any failure of this skill itself | See "Best-effort" below. Never recurse. |

**One asymmetry to get right.** `findEpics()` returning **`null`** — `epicMarkerProperty` absent from the live database — **is** logged, as `missing-property:epicMarkerProperty`. Returning **`[]`** is not. The adapter is explicit that callers must never conflate the two states, and neither may this log.

`getEpicContext` never logs, even when it returns `null` because the marker is absent, because that same condition is already recorded at `findEpics` / `createTicket`. One condition, one signature, one entry.

## Where the file lives

`$REPO_ROOT/.claude/notion-dev/notion-dev-issues.md`

In the **primary checkout** of the target repo, never inside a feature worktree — worktrees get deleted. Same directory and same `$REPO_ROOT` resolution as `ledger.jsonl` and `review-report-<KEY>-<id>.md`.

On first write, create the directory with a self-ignoring gitignore:

```bash
mkdir -p .claude/notion-dev
[ -f .claude/notion-dev/.gitignore ] || printf '*\n' > .claude/notion-dev/.gitignore
```

The location is not a preference. A file anywhere visible to git — notably the repo root — trips the clean-tree gates in `commands/ticket.md` Phase 6.6 and `skills/review-and-merge/SKILL.md`, both of which require `git status --porcelain` to be empty, and could sweep the file into a client's PR.

## File header

Written once, when the file is created. Never rewritten, never re-checked on later appends.

```markdown
# notion-dev runtime issues

Written automatically by the notion-dev plugin when a command or skill hits
something unexpected. You do not need to run anything to produce it.

**If you are seeing this, send the whole file to whoever maintains the plugin.**
It contains identifiers only — no ticket titles, bodies, diffs, or user details.

This records what the plugin noticed and had the opportunity to record. It is
not a complete account of everything that went wrong: a run killed mid-flight
leaves nothing behind to record its own death. A short file is not evidence of
a healthy run.
```

## Entry format

Every field is required. `Context` may be the literal `none` when no permitted pair applies.

```markdown
## missing-property:parentTaskProperty
**Kind**: degraded · **Occurrences**: 7
**First seen**: 2026-08-02T14:32Z (notion-dev 0.9.0)
**Last seen**: 2026-08-05T09:11Z (notion-dev 0.9.0)
**Where**: /notion-dev:ticket → epic-update step 1
**Expected**: `parentTaskProperty` "Parent task" present, self-referential relation
**Observed**: property absent from live database
**Effect**: epic linkage skipped; ticket resolved without a Resolution Log entry
**Context**: idProperty=unique_id · db=…a41f9c · epicProperty=present
```

### `Kind`

Exactly one of three values, answering one question only — **did the run continue?**

| Value | Meaning |
|---|---|
| `failed` | The run aborted here. |
| `degraded` | The run continued but did less than it should have. |
| `unexpected` | Catch-all: something was wrong and you cannot confidently say which of the above applies. |

There is deliberately no `drift` value. Drift and degradation are different axes — every `missing-property:*` entry is simultaneously both, so choosing between them is a coin flip and the label comes out inconsistent across runs. Drift is already legible in the signature name.

### Timestamps and version

`First seen` and `Last seen` are ISO 8601 UTC to the minute — `date -u +%FT%RZ` — each followed by the plugin version observed at that moment.

**Read the version from `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` at write time.** Never hardcode it. A literal version string here would be a second copy of a fact that lives in the manifest, and it would go stale at the first release.

An entry whose first-seen and last-seen versions differ is an issue that survived an upgrade.

## Signature grammar

`<class>:<subject>` — both kebab-case, no spaces.

Class is drawn from this closed list:

| Class | Use |
|---|---|
| `missing-property` | A configured property is absent from the live database. |
| `wrong-type` | The property exists but its Notion type is not what the plugin requires. |
| `option-missing` | A Select/Status option the plugin needs is not on the property. |
| `prefix-mismatch` | A live identifier prefix disagrees with config. |
| `mcp-unavailable` | An MCP server or tool could not be reached at all. |
| `mcp-error` | An MCP call was reached and returned an error. |
| `abort` | A guardrail or precondition stopped the run. |
| `retry-exhausted` | An operation was retried per its own contract and still failed. |
| `fallback` | A secondary path ran because the primary was unavailable. |
| `partial` | An operation completed some of its work and not the rest. |
| `unexpected` | Nothing above fits. |

Subject is either a config property name verbatim (`parentTaskProperty`) or a fixed kebab subject (`project-scope`, `notion`, `epic-update`).

Enumerated signatures live in `references/signatures.md`. **Cite a registered name whenever one applies; never coin a variant of one that already exists.** Layer 1 invents new signatures under this same grammar, reusing an existing class wherever one fits and falling back to `unexpected:<subject>`. Constraining the catch-all to the grammar is what keeps it groupable — free-form entries make the log unsearchable, which defeats its purpose.

## Redaction

Redaction is structural: a per-field whitelist, not a cleanup pass. Writing a compliant entry and writing a redacted entry are the same act.

| Field | May contain |
|---|---|
| signature | A class from the list above plus a config property name or fixed subject. |
| `Kind` | One of the three values above. |
| `Occurrences` | An integer. |
| `First seen` / `Last seen` | A UTC timestamp and the plugin version. |
| `Where` | Command name, phase name, skill name, step number. Optionally a ticket key such as `STO-67`. |
| `Expected` | The plugin's expectation, stated in config and schema terms. |
| `Observed` | The shape of live state — presence, absence, Notion property type, error text. |
| `Effect` | What the plugin did, skipped, or aborted. |
| `Context` | `key=value` pairs joined by ` · `, drawn only from the closed list below. |

**`Context` permitted keys:** `idProperty`, `epicProperty`, `epicMarkerProperty`, `parentTaskProperty`, `assigneeProperty`, `dependsOnProperty`, `prProperty`, `creationDateProperty`, `statusProperty`, `flow`, `reviewer`, `db`.

Values are `present`, `absent`, a Notion type name, a configured property name, or — for `db` only — the last six characters of the database id, written `db=…a41f9c`.

### Forbidden, without exception

Ticket titles. Ticket bodies. Any part of a ticket's content. PR titles, descriptions, or contents. Diffs or code. Notion user ids. Email addresses. Personal names. Full database ids. Full page ids. Absolute filesystem paths. URLs of any kind.

`Observed` and `Effect` are the leak risk, because they are prose. **They describe plugin behavior, never ticket content.**

The rationale, so a future editor does not relax this: clients forward this file to the plugin author, possibly without reading it. Plugin bugs live in the plugin's logic, not the client's data, so identifiers are sufficient to diagnose.

## Write procedure

Signature is the identity.

1. Read `$REPO_ROOT/.claude/notion-dev/notion-dev-issues.md` if it exists.
2. Search for a line matching exactly `## <signature>`.
3. **Present** — update that section's `**Last seen**` line to now plus the current version, and increment the integer on its `**Occurrences**` line. Leave every other byte of the section unchanged.
4. **Absent** — append a blank line and the full entry at the end of the file.
5. **File absent** — create the directory and gitignore, write the header, then the entry.

**On a repeat, only `Last seen` and `Occurrences` change.** The five descriptive fields and `Kind` keep their first-seen values. Mutating them would make the entry lie about what was first observed and make the write non-deterministic. If `Observed` would differ materially from what is recorded, that is a different condition and belongs under a different signature.

`Occurrences` counts **write events**, not underlying incidents. Most enumerated sites are specified as "log one warning per run", so for those it counts runs. The registry marks each site's frequency.

Entries are never reordered and never removed. The file has no rotation and no size cap; dedup is what bounds it.

## Best-effort

- A failure to create, read, or write this log **never fails the run**. Mirrors the ledger's "a ledger append failure never fails the run."
- A failure of this log is **never itself logged**. No recursion. This skill never invokes itself.
- A malformed or hand-edited existing file is not repaired. If it cannot be parsed for the dedup search, append the new entry at the end and continue. Never rewrite or discard what is already there.
- Concurrent runs in parallel worktrees can lose an occurrence increment, because dedup is read-modify-write rather than append-only. This is accepted: the log is diagnostics, not accounting, and the entry itself still exists.
````

- [ ] **Step 3: Write `plugins/notion-dev/skills/issue-log/references/signatures.md`**

````markdown
# Enumerated issue-log signatures

The single definition point for every named signature the notion-dev plugin writes. Call sites cite these names; they never redefine them and never coin variants.

Read alongside `../SKILL.md`, which owns the grammar, the entry format, the redaction contract, and the list of conditions that are routine and must not be logged.

`<propertyName>` and `<tool>` below are **templates**, not literal signatures — the writer substitutes the real name.

## Registry

| Signature | Kind | Site | Condition | Frequency |
|---|---|---|---|---|
| `missing-property:prProperty` | degraded | `ticket-system` | `prProperty` absent from live DB; PR property write skipped | once/run |
| `wrong-type:prProperty` | degraded | `ticket-system` | present but not a URL property; PR property write skipped | once/run |
| `missing-property:assigneeProperty` | degraded | `ticket-system` | absent; assignee write skipped | once/run |
| `wrong-type:assigneeProperty` | degraded | `ticket-system` | present but not a People property; assignee write skipped | once/run |
| `missing-property:creationDateProperty` | degraded | `ticket-system` | absent; creation-date write skipped | once/run |
| `wrong-type:creationDateProperty` | degraded | `ticket-system` | present but neither `date` nor `created_time`; write skipped | once/run |
| `missing-property:parentTaskProperty` | degraded | `ticket-system` | absent; guards the parent write, `setParent`, `listEpicChildren`, `refreshEpicTasks` | once/run |
| `missing-property:epicProperty` | degraded | `ticket-system` | absent; Epic select skipped, `createEpic` degrades | once/run |
| `missing-property:epicMarkerProperty` | degraded | `ticket-system` | absent; `findEpics` returns `null`, epic containers unavailable on this DB | once/run |
| `missing-property:dependsOnProperty` | degraded | `ticket-system` | absent; `setDependencies` no-ops | once/run |
| `option-missing:<propertyName>` | failed | `ticket-system` | a required Select/Status option is absent; `createTicket` raises | per occurrence |
| `prefix-mismatch:unique_id` | degraded | `ticket-system` | live `unique_id` column prefix differs from `project.key` | once/run |
| `mcp-unavailable:notion` | failed | `ticket-system` | the Notion MCP is unreachable | per occurrence |
| `mcp-unavailable:notion-get-users` | failed | `ticket-system` | `resolveAssignee` cannot run | per occurrence |
| `mcp-error:<tool>` | unexpected | any | an MCP call was reached and returned an error | per occurrence |
| `abort:project-scope` | failed | `ticket-system` | pinned `staticProperties` mismatch; refused to operate across projects | per occurrence |
| `fallback:local-code-review` | degraded | `ticket.md`, `finalize.md` | the configured reviewer was unavailable; the local fallback ran, so no cross-model review validated the PR | once/run |
| `retry-exhausted:plan-review` | degraded | `ticket.md` | `PLAN-REVIEW: degraded` — the reviewer never ran | once/run |
| `retry-exhausted:verify` | failed | `ticket.md` | the verify step never passed after its retries | per occurrence |
| `partial:epic-update` | degraded | `ticket.md`, `finalize.md` | `epic-update` returned a non-empty `SKIPPED` or `FAILED` bucket | once/run |

## Consolidations

Deliberate, and not to be undone without re-reading this section.

**`/notion-dev:init` has no signatures of its own.** A property missing at init and the same property missing at ticket time are one condition observed at two moments; both write `missing-property:<propertyName>`. Minting init-specific classes would produce a dozen near-duplicates and destroy the grouping this file exists to provide.

**Degraded reviews and partial epic updates are logged by the calling command**, not inside `plan-review/SKILL.md`, `local-code-review/SKILL.md`, `review-and-merge/SKILL.md`, or `epic-update/SKILL.md`. Each degradation is already visible to the caller in the output block those skills return, so no new signal has to be threaded anywhere. `plan-review` Step 1 in particular is a closed enumeration of what reaches the reviewer's prompt: a value threaded in without extending that enumeration is silently never read.

## Adding a signature

1. Add the row here first.
2. Cite the name at the call site, in the form: ``Record `<signature>` per `notion-dev:issue-log`.``
3. Re-run the closure check in the plan's Task 7. The set of signatures named across `plugins/notion-dev` and the set in this table must be equal.
````

- [ ] **Step 4: Verify the two files exist and the skill declares its name**

Run:
```bash
ls plugins/notion-dev/skills/issue-log/SKILL.md plugins/notion-dev/skills/issue-log/references/signatures.md
grep -c '^name: issue-log$' plugins/notion-dev/skills/issue-log/SKILL.md
```
Expected: both paths listed, and `1`.

- [ ] **Step 5: Verify no hardcoded plugin version (spec V4)**

Every version literal must sit on an illustrative `First seen` / `Last seen` line and nowhere else.

Run:
```bash
grep -rnE '0\.[0-9]+\.[0-9]+' plugins/notion-dev/skills/issue-log/ | grep -v 'First seen\|Last seen'
```
Expected: no output.

- [ ] **Step 6: Verify the registry parses to exactly 20 signatures**

Run:
```bash
grep -oE '^\| `[a-z-]+:[A-Za-z_<>-]+`' plugins/notion-dev/skills/issue-log/references/signatures.md | wc -l
```
Expected: `20`.

- [ ] **Step 7: Verify redaction and not-logged sections are present (spec V5, V6)**

Run:
```bash
grep -c 'Forbidden, without exception' plugins/notion-dev/skills/issue-log/SKILL.md
grep -c 'What is never logged' plugins/notion-dev/skills/issue-log/SKILL.md
grep -riE 'https?://|@[a-z0-9.-]+\.(com|org|io)' plugins/notion-dev/skills/issue-log/
```
Expected: `1`, `1`, and no output from the third command.

- [ ] **Step 8: Apply the two-places rule**

Read both new files start to finish. Confirm the class list in `SKILL.md` and every class used in the registry table agree; confirm the not-logged table's `findEpics` row and the asymmetry paragraph below it do not contradict each other; confirm the `Context` permitted-key list covers every key used in the example entry.

- [ ] **Step 9: Commit**

```bash
git add plugins/notion-dev/skills/issue-log/
git commit -m "feat(notion-dev): add issue-log skill and signature registry"
```

---

## Task 2: Cite signatures at the fifteen `ticket-system` sites

**Files:**
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md`

**Interfaces:**
- Consumes: the twenty signature names from Task 1's `references/signatures.md`, and the skill name `notion-dev:issue-log`.
- Produces: nothing later tasks depend on. Commands invoke the adapter; they do not read its citations.

The adapter already detects and warns at every one of these sites. This task gives those warnings a durable destination — **it adds no new detection logic and changes no behavior.** Append the citation to the existing sentence; do not rewrite the surrounding prose.

Standard citation form:

```
Record `<signature>` per `notion-dev:issue-log`.
```

- [ ] **Step 1: Read the whole file first**

Run: `wc -l plugins/notion-dev/skills/ticket-system/SKILL.md` and read it end to end. Line numbers below are anchors from 2026-08-02 and drift; locate each site by its quoted text, not its number.

- [ ] **Step 2: Add citations at the single-location sites**

| Anchor text (locate by this) | Signature to cite |
|---|---|
| "`ID column prefix '<live>' differs from project.key '<KEY>'; titles use '<KEY>'`" (~:65) | `prefix-mismatch:unique_id` |
| "When the configured property is absent from the live DB, skip with a one-time warning" — the **Epic / Phase** Select bullet (~:123) | `missing-property:epicProperty` |
| "raise a clear error telling the caller to add the option first" — same bullet (~:123) | `option-missing:<propertyName>`, substituting the real property name |
| "`parentTaskProperty '<name>' not found on DB; skipping parent write`" (~:130) | `missing-property:parentTaskProperty` |
| "`setDependencies`" / "No-op when the property is absent" (~:24) and "If `dependsOnProperty` is absent from the live DB → warn once and return" (~:329) | `missing-property:dependsOnProperty` — **both** locations |
| "this project is pinned to `<prop>`=`<expected>`. Refusing to operate on a ticket from a different project." (~:136) | `abort:project-scope` |
| "When `mcp__notion__notion-get-users` is unavailable, fail with the standard MCP-unavailability message" (~:260) | `mcp-unavailable:notion-get-users` |
| "If the MCP is unreachable, fail with: *\"Notion MCP is unavailable…\"*" (~:501) | `mcp-unavailable:notion` |
| "When `epicMarkerProperty` is absent from the live DB, epics cannot be identified **at all**" (~:409) | `missing-property:epicMarkerProperty` |

- [ ] **Step 3: Add citations at the four paired sites**

Each of these properties is described in **two** places — a summary bullet under "Property type handling" and a detailed step inside the operation that writes it. **Both copies must cite, and cite identically.** A single-copy edit here is the exact defect class that caused every fix round on the previous branch.

| Property | Location A (summary) | Location B (detail) | Signatures |
|---|---|---|---|
| `prProperty` | "read/write when `prProperty` exists on the live DB. When absent, skip writes and log a single warning per run (no abort)." (~:122) | "If the property is absent or not URL-typed, log one warning (`prProperty '<name>' not found on DB; skipping PR property write`)" (~:323) | `missing-property:prProperty` when absent, `wrong-type:prProperty` when present but not URL-typed |
| `assigneeProperty` | "When the property doesn't exist on the live DB or isn't a People type, skip the write with a warning rather than aborting." (~:76) | "`assigneeProperty '<name>' not found or not a People property on DB; skipping assignee write`" (~:126) | `missing-property:assigneeProperty` when absent, `wrong-type:assigneeProperty` when present but not People-typed |
| `creationDateProperty` | "`creationDateProperty '<name>' not found or not a date/created_time property on DB; skipping creation date write`" (~:127) | "When absent or any other type, skip with the one-time warning from \"Property type handling\"." (~:272) | `missing-property:creationDateProperty` when absent, `wrong-type:creationDateProperty` when present but neither `date` nor `created_time` |
| `prProperty` config bullet | "When the property doesn't exist on the live DB, skip the write with a warning rather than aborting." (~:75) | — covered by the two above | same as `prProperty` row |

Where a site's existing prose already merges the two cases in one sentence ("absent **or** not a People type"), the citation names both signatures with their conditions, in this form:

```
Record `missing-property:assigneeProperty` when the property is absent, or
`wrong-type:assigneeProperty` when it exists but is not a People property, per
`notion-dev:issue-log`.
```

- [ ] **Step 4: Verify every citation names a registered signature**

Run:
```bash
grep -ohE '\b(missing-property|wrong-type|option-missing|prefix-mismatch|mcp-unavailable|mcp-error|abort|retry-exhausted|fallback|partial|unexpected):[A-Za-z_<>-]+' \
  plugins/notion-dev/skills/ticket-system/SKILL.md | grep -v '<' | sort -u > /tmp/cited.txt
grep -oE '`[a-z-]+:[A-Za-z_<>-]+`' plugins/notion-dev/skills/issue-log/references/signatures.md \
  | tr -d '`' | grep -v '<' | sort -u > /tmp/registered.txt
comm -23 /tmp/cited.txt /tmp/registered.txt
```
Expected: no output. Any line printed is a signature cited here but never registered.

- [ ] **Step 5: Verify the citation count**

Run:
```bash
grep -c 'notion-dev:issue-log' plugins/notion-dev/skills/ticket-system/SKILL.md
```
Expected: at least `15`. Paired sites and multi-signature sentences push this higher; a number below 15 means a site was missed.

- [ ] **Step 6: Verify no behavior text was rewritten**

Run: `git diff --stat plugins/notion-dev/skills/ticket-system/SKILL.md`

Expected: insertions substantially exceed deletions. A large deletion count means existing prose was rewritten rather than appended to — revert and redo as appends.

- [ ] **Step 7: Apply the two-places rule**

For each of the four paired properties, confirm both copies now carry the same signatures with the same conditions. Then scan the operations quick-reference table at the top of the file: if any row's prose duplicates a warning you just cited, it needs the same citation.

- [ ] **Step 8: Commit**

```bash
git add plugins/notion-dev/skills/ticket-system/SKILL.md
git commit -m "feat(notion-dev): cite issue-log signatures at ticket-system degradation sites"
```

---

## Task 3: Wire `/notion-dev:ticket`

**Files:**
- Modify: `plugins/notion-dev/commands/ticket.md`

**Interfaces:**
- Consumes: `notion-dev:issue-log`, and these registered signatures — `fallback:local-code-review`, `retry-exhausted:plan-review`, `retry-exhausted:verify`, `partial:epic-update`.
- Produces: nothing later tasks depend on.

This is the most intricate of the four commands. It has ten phases plus a "Failure and stop conditions" section that stops **without** running cleanup — so the Phase 9 sweep never fires on that path, and it needs its own.

- [ ] **Step 1: Add the standing-rule preamble**

Insert after the command's opening description and before its first `## Preconditions` heading:

```markdown
**Standing rule — runtime issues.** Anything unexpected at runtime — for example an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, or a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens, not batched to the end of the run. That skill is **authoritative** for the full trigger list, the entry format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must **not** be logged; the examples here are illustrative, not exhaustive. The rule applies to conditions nobody enumerated in advance. A failure to write the log never fails the run.
```

- [ ] **Step 2: Add the four caller-side signature citations**

Each of these degradations is already visible to this command in a returned output block. Do **not** edit the skills that produce those blocks.

| Where in `ticket.md` | Condition | Citation to add |
|---|---|---|
| Phase 4.2 step (b), where `PLAN_REVIEW_REPORT` is recorded | the block reads `PLAN-REVIEW: degraded` — the reviewer never ran | ``Record `retry-exhausted:plan-review` per `notion-dev:issue-log`.`` |
| `## Phase 7 — Review and merge`, where the reviewer used is determined — the same fact Phase 10's "which loop ran" report line draws from | the local fallback ran because the configured reviewer was unavailable | ``Record `fallback:local-code-review` per `notion-dev:issue-log`.`` |
| The verify step, where retries are exhausted | verify never passed after its retries | ``Record `retry-exhausted:verify` per `notion-dev:issue-log`.`` |
| Phase 8.2a, where `EPIC_REPORT` is received | `epic-update` returned a non-empty `SKIPPED` or `FAILED` bucket | ``Record `partial:epic-update` per `notion-dev:issue-log`.`` |

- [ ] **Step 3: Add the sweep to Phase 9**

In `## Phase 9 — Clean up`, immediately after the ledger outcome append (the paragraph beginning "Append one outcome line to `$REPO_ROOT/.claude/notion-dev/ledger.jsonl`"), add:

```markdown
**Issue-log sweep.** Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`. Best-effort — a failure here never fails the run.
```

- [ ] **Step 4: Add the report line to Phase 10**

In `## Phase 10 — Report`, add to the bullet list:

```markdown
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`. Omit the line entirely when the run logged nothing.
```

- [ ] **Step 5: Add the failure-path sweep**

In `## Failure and stop conditions`, in the bullet beginning "**On any unrecoverable failure**", extend the existing best-effort clause. That bullet currently reads "Best-effort, before stopping: append a ledger outcome line with `result` …". Add, in the same best-effort sentence and mirroring its wording:

```markdown
Also best-effort, before stopping: run the issue-log sweep from Phase 9 — this path skips Phase 9 entirely, and an unrecoverable failure is the single most valuable thing this log can record. A failure to write it never masks the real failure report.
```

- [ ] **Step 6: Verify preamble, sweep, and report line are present**

Run:
```bash
grep -c 'Standing rule — runtime issues' plugins/notion-dev/commands/ticket.md
grep -c 'Issue-log sweep' plugins/notion-dev/commands/ticket.md
grep -c 'issues logged to .claude/notion-dev/notion-dev-issues.md' plugins/notion-dev/commands/ticket.md
```
Expected: `1`, `1`, `1`. The failure-path sweep references Phase 9's sweep rather than restating it, so `Issue-log sweep` appears once.

- [ ] **Step 7: Verify the failure path carries an issue-log instruction**

Run:
```bash
sed -n '/^## Failure and stop conditions/,$p' plugins/notion-dev/commands/ticket.md | grep -c 'issue-log'
```
Expected: `1`.

- [ ] **Step 8: Verify every signature cited here is registered**

Run:
```bash
grep -ohE '\b(missing-property|wrong-type|option-missing|prefix-mismatch|mcp-unavailable|mcp-error|abort|retry-exhausted|fallback|partial|unexpected):[A-Za-z_<>-]+' \
  plugins/notion-dev/commands/ticket.md | grep -v '<' | sort -u > /tmp/cited.txt
grep -oE '`[a-z-]+:[A-Za-z_<>-]+`' plugins/notion-dev/skills/issue-log/references/signatures.md \
  | tr -d '`' | grep -v '<' | sort -u > /tmp/registered.txt
comm -23 /tmp/cited.txt /tmp/registered.txt
```
Expected: no output.

- [ ] **Step 9: Apply the two-places rule**

Check whether Phase 10's report bullet list has a lead-in sentence that counts its items — if so, the count is now wrong. Check whether the command's opening description summarises what it writes to `.claude/notion-dev/`; if it enumerates the ledger and review report, it now needs the issue log too.

- [ ] **Step 10: Commit**

```bash
git add plugins/notion-dev/commands/ticket.md
git commit -m "feat(notion-dev): wire issue-log into /notion-dev:ticket"
```

---

## Task 4: Wire `/notion-dev:finalize`

**Files:**
- Modify: `plugins/notion-dev/commands/finalize.md`

**Interfaces:**
- Consumes: `notion-dev:issue-log`, and these registered signatures — `fallback:local-code-review`, `partial:epic-update`.
- Produces: nothing later tasks depend on.

`finalize.md` has five phases plus a "Failure and stop conditions" section that stops without cleanup. It receives the same reviewer and `epic-update` output blocks `ticket.md` does, but has no plan-review and no verify step of its own — so it cites two signatures, not four.

- [ ] **Step 1: Add the standing-rule preamble**

Insert after the command's opening description and before `## Preconditions`:

```markdown
**Standing rule — runtime issues.** Anything unexpected at runtime — for example an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, or a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens, not batched to the end of the run. That skill is **authoritative** for the full trigger list, the entry format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must **not** be logged; the examples here are illustrative, not exhaustive. The rule applies to conditions nobody enumerated in advance. A failure to write the log never fails the run.
```

- [ ] **Step 2: Add the two caller-side signature citations**

| Where in `finalize.md` | Condition | Citation to add |
|---|---|---|
| Phase 2, where the review loop reports which reviewer ran | the local fallback ran because the configured reviewer was unavailable | ``Record `fallback:local-code-review` per `notion-dev:issue-log`.`` |
| Phase 3.2, where `EPIC_REPORT` is received from `notion-dev:epic-update` | a non-empty `SKIPPED` or `FAILED` bucket | ``Record `partial:epic-update` per `notion-dev:issue-log`.`` |

Phase 3.2 has a post-merge recovery path where `epic-update` returns `EPIC-UPDATE: already-recorded`. That is the idempotency check working correctly — **not** a partial update, and it is never logged.

- [ ] **Step 3: Add the sweep to Phase 4**

In `## Phase 4 — Clean up`, after the ledger outcome append, add:

```markdown
**Issue-log sweep.** Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`. Best-effort — a failure here never fails the run.
```

- [ ] **Step 4: Add the report line to Phase 5**

In `## Phase 5 — Report`, add to the bullet list:

```markdown
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`. Omit the line entirely when the run logged nothing.
```

- [ ] **Step 5: Add the failure-path sweep**

In `## Failure and stop conditions`, in the bullet beginning "**On any unrecoverable failure**", extend the existing best-effort clause:

```markdown
Also best-effort, before stopping: run the issue-log sweep from Phase 4 — this path skips Phase 4 entirely, and an unrecoverable failure is the single most valuable thing this log can record. A failure to write it never masks the real failure report.
```

- [ ] **Step 6: Verify preamble, sweep, report line, and failure path**

Run:
```bash
grep -c 'Standing rule — runtime issues' plugins/notion-dev/commands/finalize.md
grep -c 'Issue-log sweep' plugins/notion-dev/commands/finalize.md
grep -c 'issues logged to .claude/notion-dev/notion-dev-issues.md' plugins/notion-dev/commands/finalize.md
sed -n '/^## Failure and stop conditions/,$p' plugins/notion-dev/commands/finalize.md | grep -c 'issue-log'
```
Expected: `1`, `1`, `1`, `1`.

- [ ] **Step 7: Verify every signature cited here is registered**

Run:
```bash
grep -ohE '\b(missing-property|wrong-type|option-missing|prefix-mismatch|mcp-unavailable|mcp-error|abort|retry-exhausted|fallback|partial|unexpected):[A-Za-z_<>-]+' \
  plugins/notion-dev/commands/finalize.md | grep -v '<' | sort -u > /tmp/cited.txt
grep -oE '`[a-z-]+:[A-Za-z_<>-]+`' plugins/notion-dev/skills/issue-log/references/signatures.md \
  | tr -d '`' | grep -v '<' | sort -u > /tmp/registered.txt
comm -23 /tmp/cited.txt /tmp/registered.txt
```
Expected: no output.

- [ ] **Step 8: Apply the two-places rule**

Confirm the Phase 5 bullet list has no lead-in count that is now wrong. Confirm the `fallback:local-code-review` wording here matches the wording used in `ticket.md` Task 3 — both commands report the same degradation and must describe it identically.

- [ ] **Step 9: Commit**

```bash
git add plugins/notion-dev/commands/finalize.md
git commit -m "feat(notion-dev): wire issue-log into /notion-dev:finalize"
```

---

## Task 5: Wire `/notion-dev:create-task`

**Files:**
- Modify: `plugins/notion-dev/commands/create-task.md`

**Interfaces:**
- Consumes: `notion-dev:issue-log`. Cites **no new signatures** — its epic degradations are already covered by `missing-property:epicMarkerProperty` and `missing-property:epicProperty`, logged inside the adapter in Task 2.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Add the standing-rule preamble**

Insert after the command's opening description and before `## Preconditions`:

```markdown
**Standing rule — runtime issues.** Anything unexpected at runtime — for example an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, or a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens, not batched to the end of the run. That skill is **authoritative** for the full trigger list, the entry format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must **not** be logged; the examples here are illustrative, not exhaustive. The rule applies to conditions nobody enumerated in advance. A failure to write the log never fails the run.
```

- [ ] **Step 2: Add a do-not-log note at the epic degradation sites**

Phase 2.5.2 step 2 and Phase 2.6 step 1 both branch on `findEpics()` returning `null` versus `[]`. The adapter logs the `null` case; this command must not log either case a second time. At both sites, add:

```markdown
Neither branch writes to the issue log here. The `null` case — `epicMarkerProperty` absent — is recorded once by `notion-dev:ticket-system` as `missing-property:epicMarkerProperty`; the `[]` case is routine and is never logged at all. See `notion-dev:issue-log`.
```

Phase 2.6 step 3's "zero plausible candidates → skip silently" is likewise routine and gets no entry.

- [ ] **Step 3: Add the sweep and report line to Phase 4**

`## Phase 4 — Report` is both the final phase and the report. Add the sweep at the **start** of the phase, before the report is composed:

```markdown
**Issue-log sweep.** Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`. Best-effort — a failure here never fails the run.
```

Then add to the report's bullet list:

```markdown
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`. Omit the line entirely when the run logged nothing.
```

- [ ] **Step 4: Add the failure-path sweep**

In `## Failure and stop conditions`, add:

```markdown
Best-effort, before stopping: run the issue-log sweep from Phase 4 — this path skips Phase 4 entirely. A failure to write it never masks the real failure report.
```

- [ ] **Step 5: Verify preamble, sweep, report line, and failure path**

Run:
```bash
grep -c 'Standing rule — runtime issues' plugins/notion-dev/commands/create-task.md
grep -c 'Issue-log sweep' plugins/notion-dev/commands/create-task.md
grep -c 'issues logged to .claude/notion-dev/notion-dev-issues.md' plugins/notion-dev/commands/create-task.md
sed -n '/^## Failure and stop conditions/,$p' plugins/notion-dev/commands/create-task.md | grep -c 'issue-log'
```
Expected: `1`, `1`, `1`, `1`.

- [ ] **Step 6: Verify no unregistered signature was introduced**

Run:
```bash
grep -ohE '\b(missing-property|wrong-type|option-missing|prefix-mismatch|mcp-unavailable|mcp-error|abort|retry-exhausted|fallback|partial|unexpected):[A-Za-z_<>-]+' \
  plugins/notion-dev/commands/create-task.md | grep -v '<' | sort -u > /tmp/cited.txt
grep -oE '`[a-z-]+:[A-Za-z_<>-]+`' plugins/notion-dev/skills/issue-log/references/signatures.md \
  | tr -d '`' | grep -v '<' | sort -u > /tmp/registered.txt
comm -23 /tmp/cited.txt /tmp/registered.txt
```
Expected: no output. The only signature name this file should contain is `missing-property:epicMarkerProperty`, inside the do-not-log note.

- [ ] **Step 7: Apply the two-places rule**

Phase 4's report opens with "one of three lines, chosen by whether `EPIC_ID` is set…". Confirm adding a bullet did not invalidate that count or any other lead-in. Confirm the do-not-log note reads the same at both Phase 2.5.2 and Phase 2.6.

- [ ] **Step 8: Commit**

```bash
git add plugins/notion-dev/commands/create-task.md
git commit -m "feat(notion-dev): wire issue-log into /notion-dev:create-task"
```

---

## Task 6: Wire `/notion-dev:init`

**Files:**
- Modify: `plugins/notion-dev/commands/init.md`

**Interfaces:**
- Consumes: `notion-dev:issue-log`, and the registered property signatures `missing-property:<propertyName>` / `wrong-type:<propertyName>` for whichever properties its drift check reports.
- Produces: nothing later tasks depend on.

`init.md` has no numbered phases — it uses `## Steps` with numbered sub-headings, ending in a report step, followed by `## Re-configuration behavior`. It also has **no hard abort**: its job is to patch config and surface warnings.

- [ ] **Step 1: Add the standing-rule preamble**

Insert after the command's opening description and before `## Steps`:

```markdown
**Standing rule — runtime issues.** Anything unexpected at runtime — for example an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, or a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens, not batched to the end of the run. That skill is **authoritative** for the full trigger list, the entry format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must **not** be logged; the examples here are illustrative, not exhaustive. The rule applies to conditions nobody enumerated in advance. A failure to write the log never fails the run.
```

- [ ] **Step 2: Cite existing signatures in the drift check**

Init's drift check gets **no signatures of its own.** A property missing at init and the same property missing at ticket time are one condition observed at two moments. In the drift-check step, add:

```markdown
Each drift item is also recorded via `notion-dev:issue-log`, using the same signature the adapter uses for that property at runtime — `missing-property:<propertyName>` when the property is absent, `wrong-type:<propertyName>` when it exists with the wrong Notion type. Never coin an init-specific signature: a property missing here and missing at ticket time are one condition observed at two moments, and one entry is what makes the log groupable.
```

- [ ] **Step 3: Add the sweep and report line to the report step**

At the start of init's report step:

```markdown
**Issue-log sweep.** Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`. Best-effort — a failure here never fails the run.
```

And in the report output:

```markdown
- Issues logged, when this run wrote any: `<N> issues logged to .claude/notion-dev/notion-dev-issues.md`. Omit the line entirely when the run logged nothing.
```

Init has no "Failure and stop conditions" section and no hard abort, so it needs no failure-path sweep.

- [ ] **Step 4: Verify preamble, sweep, and report line**

Run:
```bash
grep -c 'Standing rule — runtime issues' plugins/notion-dev/commands/init.md
grep -c 'Issue-log sweep' plugins/notion-dev/commands/init.md
grep -c 'issues logged to .claude/notion-dev/notion-dev-issues.md' plugins/notion-dev/commands/init.md
```
Expected: `1`, `1`, `1`.

- [ ] **Step 5: Verify only template signatures appear**

Run:
```bash
grep -ohE '\b(missing-property|wrong-type):[A-Za-z_<>-]+' plugins/notion-dev/commands/init.md | sort -u
```
Expected: exactly `missing-property:<propertyName>` and `wrong-type:<propertyName>`. Any concrete property name here means an init-specific signature was coined — remove it.

- [ ] **Step 6: Apply the two-places rule**

Init's report step enumerates what it wrote and warned about. Confirm the new bullet does not duplicate an existing "warnings" line, and that any lead-in count is still correct.

- [ ] **Step 7: Commit**

```bash
git add plugins/notion-dev/commands/init.md
git commit -m "feat(notion-dev): wire issue-log into /notion-dev:init"
```

---

## Task 7: Version bump, README, and full closure verification

**Files:**
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json`
- Modify: `plugins/notion-dev/README.md`

**Interfaces:**
- Consumes: every file from Tasks 1–6. This task's closure check is only meaningful once all call sites exist.
- Produces: the shippable branch.

- [ ] **Step 1: Bump the version**

In `plugins/notion-dev/.claude-plugin/plugin.json`, change `"version": "0.8.0"` to `"version": "0.9.0"`.

- [ ] **Step 2: Add the README section**

Add a section documenting the log. Place it near the existing description of what the plugin writes to `.claude/notion-dev/`:

````markdown
## Runtime issue log

When a command or skill hits something unexpected — a configured property missing from your Notion database, an MCP outage, a review that degraded, a step that aborted — the plugin records it in:

```
.claude/notion-dev/notion-dev-issues.md
```

This is automatic. You do not run anything to produce it, and it never interrupts a command: a failure to write the log never fails the run. The file lives in a self-ignored directory, so it never dirties `git status` and never lands in a PR.

**If the plugin misbehaves, send that whole file to whoever maintains the plugin.** It carries identifiers only — property names, command and phase names, error text, config shape, plugin version — and never ticket titles, ticket bodies, diffs, PR contents, user ids, or email addresses.

Repeat problems are deduplicated: the same issue collapses to one entry with an occurrence count and a last-seen timestamp, so the file grows with distinct problems rather than with runs. There is no rotation — nothing is ever discarded.

**One caveat worth understanding.** The plugin has no background process. An entry gets written because a running agent recorded it, so quiet degradations are captured well while abrupt failures — a killed process, an interrupt — may leave nothing behind. A short file is not proof that nothing went wrong.
````

- [ ] **Step 3: Update the README's version mentions — there are two, and they are not the same kind of statement**

The README states a version in two places. A blind find-and-replace across both is wrong, and shipping a README that announces an old version was one of the defects on the previous branch.

| Location | Current text | Action |
|---|---|---|
| `README.md:5` | `**Status**: pre-release (0.8.0). MVP = …` | **Change to `0.9.0`.** This is the plugin's current-version banner. |
| `README.md:170` | `As of \`0.8.0\` (unreleased), no prior version of this plugin has ever created an Epic container…` | **Leave at `0.8.0`.** This is a historical statement about the release in which the Epic marker was introduced, not a current-version claim. Rewriting it to `0.9.0` would assert something false. |

- [ ] **Step 4: Verify the version is consistent (spec V7)**

Run:
```bash
grep '"version"' plugins/notion-dev/.claude-plugin/plugin.json
grep -nE '0\.[0-9]+\.[0-9]+' plugins/notion-dev/README.md
```
Expected: `"version": "0.9.0"`; the README's status line reads `0.9.0`; and the Epic-marker history line still reads `0.8.0`. Exactly two version strings in the README, no more.

- [ ] **Step 5: Run the full signature closure check (spec V1)**

This is the load-bearing verification and it runs only now, with every call site in place. Angle-bracket forms are templates, not signatures, and are filtered from both sides.

**`--exclude=signatures.md` is essential and not optional.** The registry lives inside `plugins/notion-dev`, so a plain recursive grep scans it too — every registered name would appear on the "cited" side, the cited set would always be a superset of the registry, and the dead-entry direction of the check would silently never fire.

Run:
```bash
grep -rhoE '\b(missing-property|wrong-type|option-missing|prefix-mismatch|mcp-unavailable|mcp-error|abort|retry-exhausted|fallback|partial|unexpected):[A-Za-z_<>-]+' \
  plugins/notion-dev --include='*.md' --exclude=signatures.md | grep -v '<' | sort -u > /tmp/all_cited.txt
grep -oE '^\| `[a-z-]+:[A-Za-z_<>-]+`' plugins/notion-dev/skills/issue-log/references/signatures.md \
  | sed 's/^| //; s/`//g' | grep -v '<' | sort -u > /tmp/all_registered.txt
diff /tmp/all_cited.txt /tmp/all_registered.txt
```
Expected: no output — the two sets are equal, at **18** entries each. The registry holds 20 rows; `option-missing:<propertyName>` and `mcp-error:<tool>` are templates and are filtered from both sides.

A line prefixed `<` is a signature cited somewhere but never registered. A line prefixed `>` is a dead registry entry no call site uses. Both are the two-places-disagree defect; fix and re-run.

- [ ] **Step 6: Run the remaining spec checks (V2, V3, V6)**

Run:
```bash
grep -l 'notion-dev:issue-log' plugins/notion-dev/commands/*.md | wc -l
grep -c 'Standing rule — runtime issues' plugins/notion-dev/commands/*.md
grep -c 'Issue-log sweep' plugins/notion-dev/commands/*.md
grep -c 'issues logged to .claude/notion-dev/notion-dev-issues.md' plugins/notion-dev/commands/*.md
```
Expected: `4`; then `1` for each of the four command files in each of the three following commands.

- [ ] **Step 7: Verify quick-dev is untouched**

Run: `git diff --name-only main...HEAD -- plugins/quick-dev/`

Expected: no output.

- [ ] **Step 8: Verify the four protected skill files are untouched**

Run:
```bash
git diff --name-only main...HEAD -- \
  plugins/notion-dev/skills/plan-review/ \
  plugins/notion-dev/skills/local-code-review/ \
  plugins/notion-dev/skills/review-and-merge/ \
  plugins/notion-dev/skills/epic-update/
```
Expected: no output. Any file listed means a degradation was logged inside a shared skill instead of at its caller.

- [ ] **Step 9: Verify no redaction leak in any new or edited text**

Run:
```bash
git diff main...HEAD -- plugins/notion-dev | grep '^+' | grep -iE 'https?://|@[a-z0-9.-]+\.(com|org|io)'
```
Expected: no output, other than any pre-existing URL inside an unchanged line of context.

- [ ] **Step 10: Confirm the whole tree is clean and the branch builds a coherent story**

Run: `git status --porcelain`
Expected: no output.

Then read `git log --oneline main..HEAD` — expect seven commits, one per task, each independently descriptive.

- [ ] **Step 11: Commit**

```bash
git add plugins/notion-dev/.claude-plugin/plugin.json plugins/notion-dev/README.md
git commit -m "feat(notion-dev): document the runtime issue log and bump to 0.9.0"
```

---

## Spec amendments made during planning

Both were discovered while pulling exact anchors, and both are already reflected in the tasks above. Fold them back into the spec if it is revised.

1. **`wrong-type:prProperty` was missing from the registry.** `ticket-system/SKILL.md:323` reads "absent **or not URL-typed**" — the same missing/wrong-type split the spec already gave `assigneeProperty` and `creationDateProperty`. The registry is therefore **20 signatures**, not 19, and `ticket-system` has **15** sites, not the 14 the spec estimated in §7.6.

2. **Four properties are documented in two places each** — `prProperty` (:122 summary, :323 detail), `assigneeProperty` (:76, :126), `creationDateProperty` (:127, :272), `parentTaskProperty` (:86, :130). The spec's §7.4 treated each as a single site. Task 2 Step 3 names the pairs explicitly, because a single-copy edit here is precisely the defect class that produced every fix round on the previous branch.
