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
| `getSelectOptions` returns `null` | `ticket-system/SKILL.md`: "Never logs a warning on `null` — callers use the `null` return as a signal to skip downstream logic." This is the read-only helper itself staying quiet, not an exemption for the underlying absence: when a caller treats that `null` as "property absent" and acts on it (e.g. `/notion-dev:create-task` Pass 0 setting `phase = undefined`), layer 1's standing rule still applies at that point and `missing-property:<propertyName>` gets recorded there. |
| Project-scoping guardrail: pinned `staticProperties` value matches, or the scoped property is absent from the live DB | `ticket-system/SKILL.md`: "Match (or property absent from the live DB) → proceed silently." |
| A configured `done`/`cancelled` status option absent from the live DB (the read-only "resolved set" check) | `ticket-system/SKILL.md`: "it simply never matches ... Wrong in the safe direction." |
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
| `Observed` | The shape of live state — presence, absence, Notion property type, or an MCP error's **class and message shape**, with every id, URL, path, and quoted value stripped out (see below). |
| `Effect` | What the plugin did, skipped, or aborted. |
| `Context` | `key=value` pairs joined by ` · `, drawn only from the closed list below. |

**`Context` permitted keys:** `idProperty`, `epicProperty`, `phaseProperty`, `stepProperty`, `epicMarkerProperty`, `parentTaskProperty`, `assigneeProperty`, `dependsOnProperty`, `prProperty`, `creationDateProperty`, `statusProperty`, `flow`, `reviewer`, `db`.

Values are `present`, `absent`, a Notion type name, a configured property name, or — for `db` only — the last six characters of the database id, written `db=…a41f9c`.

**`Observed` on an `mcp-error`.** An MCP error's raw text routinely embeds a full page or database id, or an API URL — both forbidden below without exception. Every other field in this table stays a closed vocabulary; this is the one field with external input, so it needs its own rule rather than a remembered exception. Reduce the raw error to its class and message *shape*: strip every id, URL, path, and quoted literal, keeping only the error type and the surrounding words.

- **Wanted** — `object_not_found: requested resource not found`
- **Forbidden** — `object_not_found: page <full-page-id> not found at <api-url>` (a live error would spell the id and URL out in full; that is exactly what must never reach this field)

If nothing is left after stripping, fall back to the error's class name alone.

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
