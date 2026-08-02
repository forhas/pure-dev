# notion-dev: runtime issue log

**Date:** 2026-08-02
**Plugin:** `plugins/notion-dev` (quick-dev is not affected)
**Target version:** `0.8.0` → `0.9.0` (minor — new capability, nothing breaking)

## Goal

When the plugin misbehaves in a client's repo, leave a durable, shareable record the plugin author can act on. The client forwards one file; the author reads it and fixes the plugin.

Coverage is **total by intent**, in two layers:

1. **A standing rule** — any command or skill that encounters anything unexpected at runtime records it, including situations nobody enumerated in advance.
2. **Enumerated known sites** — the already-known degradation points carry explicit named signatures, so common cases produce consistent, groupable entries instead of free-form prose.

Layer 1 without layer 2 is unsearchable. Layer 2 without layer 1 only ever captures what was foreseen. Both ship together.

## Non-goals

- **quick-dev.** Its copies of the four shared skills (`flow-triage`, `plan-review`, `local-code-review`, `review-and-merge`) are separate files and are not touched.
- **Remediation advice.** The log is author-facing diagnostics. It never tells the client how to fix anything, and never classifies whether a given entry is the client's setup or the plugin's bug.
- **Rotation, truncation, or archival.** The file grows with distinct problems, not with runs. Signature dedup is the bounding mechanism.
- **A `/notion-dev:report-issues` command.** `cat` works. Rejected as YAGNI.
- **Executable code of any kind.** No hooks, no scripts. The plugin stays prompt-and-markdown.
- **Ticket content.** See §5.

---

## 1. Components

```
plugins/notion-dev/skills/issue-log/
  SKILL.md                    ← the contract: when to log, how to write, redaction, dedup, best-effort
  references/signatures.md    ← the layer-2 signature registry
```

Two files, mirroring the existing `flow-triage` / `references/ledger.md` split.

`SKILL.md` is the **how**. It never lists individual call sites. `signatures.md` is the **what** — the only place a layer-2 signature name is defined. Call sites cite names; they never redefine them.

This split is the primary defence against the repo's dominant defect class (a fact stated in two places, one copy updated). A signature name exists once in the registry and is referenced everywhere else.

---

## 2. The file

### 2.1 Location

`$REPO_ROOT/.claude/notion-dev/notion-dev-issues.md`

In the **primary checkout** of the target repo, never inside a feature worktree — worktrees get deleted. Same rule, and the same `$REPO_ROOT`, as `ledger.jsonl` and `review-report-<KEY>-<id>.md`, which already live in this directory.

On first write, create the directory with a self-ignoring gitignore, verbatim from `skills/flow-triage/references/ledger.md`:

```bash
mkdir -p .claude/notion-dev
[ -f .claude/notion-dev/.gitignore ] || printf '*\n' > .claude/notion-dev/.gitignore
```

The location is not a preference. A file anywhere visible to git — notably the repo root — trips the clean-tree gates in `commands/ticket.md` Phase 6.6 and `skills/review-and-merge/SKILL.md`, both of which require `git status --porcelain` to be empty, and could sweep the file into a client's PR. A root-level file is a functional bug.

### 2.2 Header

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

### 2.3 Ordering

Entries append in first-seen order. A new signature becomes a new section at the end of the file. A repeat signature updates its existing section in place. Nothing is ever reordered or removed.

---

## 3. Entry format

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

Every field is required. `Context` may be the literal `none` when no permitted pair applies.

### 3.1 `Kind`

Exactly one of three values, answering one question only — **did the run continue?**

| Value | Meaning |
|---|---|
| `failed` | The run aborted here. |
| `degraded` | The run continued but did less than it should have. |
| `unexpected` | Layer 1 catch-all: something was wrong and the writer cannot confidently say which of the above applies. |

The handoff proposed a fourth value, `drift` (live state disagrees with config). It is **deliberately excluded**. Drift and degradation are different axes: every `missing-property:*` entry is simultaneously drift *and* a degradation, so a writer choosing between them is making a coin flip, and the label comes out inconsistent across runs. Drift is already legible in the signature name. Kind stays one axis.

### 3.2 Timestamps and version

`First seen` and `Last seen` are ISO 8601 UTC to the minute (`date -u +%FT%RZ`), each followed by the plugin version observed at that moment.

**The version is read from `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` at write time.** It is never hardcoded in `SKILL.md` — a literal version string in the skill is a second copy of a fact that lives in the manifest, and it would go stale at the first release. §9 verifies this.

Because both timestamps carry a version, an entry whose first-seen and last-seen versions differ is an issue that survived an upgrade. That is the version-mismatch signal, obtained for free.

### 3.3 Dedup

Signature is the identity. On every write:

1. Read the file if it exists.
2. Search for a line exactly matching `## <signature>`.
3. **Present** — update that section's `**Last seen**` line to now plus the current version, and increment the integer on its `**Occurrences**` line. Leave every other byte of the section unchanged.
4. **Absent** — append a blank line and the full entry at the end of the file.
5. **File absent** — create the directory and gitignore per §2.1, write the §2.2 header, then the entry.

**On a repeat, only `Last seen` and `Occurrences` change.** The five descriptive fields and `Kind` keep their first-seen values. This is deliberate on two grounds: mutating them makes the entry lie about what was first observed, and it makes the write non-deterministic. If `Observed` would differ materially from the recorded value, that is a different condition and belongs under a different signature.

`Occurrences` counts **write events**, not underlying incidents. Most layer-2 sites are specified as "log one warning per run", so for those it counts runs. The registry marks the frequency of each.

---

## 4. Signature grammar

`<class>:<subject>` — both kebab-case, no spaces.

**Class** is drawn from a closed list:

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

**Subject** is either a config property name verbatim (`parentTaskProperty`) or a fixed kebab subject (`project-scope`, `notion`, `epic-update`).

Layer 1 invents signatures at write time under this same grammar, reusing an existing class wherever one fits and falling back to `unexpected:<subject>`. Constraining the catch-all to the grammar is what keeps it groupable — free-form prose entries would make the log unsearchable, which §3.1 of the handoff identifies as the failure mode that kills the feature.

---

## 5. Redaction

> **Amended during execution (2026-08-02):** final review found `Observed`'s original "error text" allowance let raw MCP error strings carry a full id or URL — both forbidden under §5.1. `Observed` was constrained to an error's class-and-message *shape* with ids, URLs, paths, and quoted values stripped; see `SKILL.md` for the current wording and worked examples. The `Context` permitted-keys list below also gained `phaseProperty` and `stepProperty` — two config properties whose registry signatures (§7.4) had no key to carry `Context: <property>=absent`. A second review round found the same list still missing `typeProperty`, needed because `/notion-dev:init`'s drift check can emit `missing-property:typeProperty` / `wrong-type:typeProperty`; the list gained that key too. That same round found §4's "both kebab-case" sentence contradicted §4's own "subject ... verbatim" sentence a few lines below it — a subject naming a config property is reproduced verbatim in its original camelCase and is never kebab-ized; only `<class>` and a *fixed* subject are kebab-case. The tables below reflect the original design; `SKILL.md` is current for both points.
>
> **Amended during execution, round 3 (2026-08-02):** a Codex review found that `mcp-error:<tool>` alone cannot express two different failures of the same tool — `object_not_found` on one run and `rate_limited` on another would collapse into one section, frozen at whichever `Observed` was first recorded, with the second failure mode permanently invisible behind a bumped `Occurrences` counter. The template grew a second component: `mcp-error:<tool>-<error-class>`, with `<error-class>` kebab-cased and, because this identity lands in a literal `## …` heading rather than a prose field, sanitized under the **same** rule §5.1 already applies to `Observed` — never an id, URL, path, or quoted value. A tool error with no identifiable class uses the literal fallback `unknown` rather than leaving the writer stuck without a compliant name. `references/signatures.md` carries the full contract and is current; the row below is the original, single-component form.
>
> **Amended during execution, round 4 (2026-08-02):** a further Codex review found that `getSelectOptions`/`addSelectOption`'s `<propertyName>` templates (§7.4) are populated from the caller's **live column name** argument, not from a config key — citing it literally would splice the class prefix directly onto the live column value (e.g. whatever the client happens to call that column) instead of onto the registered config key (`phaseProperty`, `epicProperty`, …), breaking dedup, evading the closure check (which excludes anything containing `<`), and risking the client's own column label — which can contain a space, forbidden by §4's grammar — landing in the log. `SKILL.md`'s signature-grammar section now states the rule generally: a property subject is always the config key that owns the property, never the live column value some operations receive as an argument; such an operation maps the argument back to its owning config key before recording, the same way `createTicket`'s `option-missing:<propertyName>` citation already annotates the concrete key inline. When no config key owns the argument (e.g. one drawn from `staticProperties`, which the plugin never binds to a dedicated key), the operation falls back to the standing Layer-1 rule rather than ever citing the raw column name. `SKILL.md` is current; the tables above reflect the original design.
>
> **Amended during execution, round 5 (2026-08-02):** a further Codex review found that §4's two-form subject grammar (config property, verbatim camelCase; or fixed subject, kebab-case) does not cover `prefix-mismatch:unique_id` (§7.4) — `unique_id` is neither a config property nor an invented fixed subject, it is a Notion property type name, borrowed in snake_case. The reviewer proposed re-casing the registered signature to a kebab form instead; that remedy was rejected, because it repeats the exact mistake round 1's fix to §4 (above) already corrected once for config properties — re-casing a borrowed identifier splits its dedup bucket, and `unique_id` is Notion's own API type name, spelled that way eight times over in `ticket-system/SKILL.md`. `SKILL.md`'s signature-grammar section instead grew a third subject form: an external identifier borrowed from Notion's own vocabulary — a property type name — is reproduced verbatim in its native form, never re-cased, on the same footing as a borrowed config property name. The unifying rule is now stated as one question, not three separate cases: kebab-case for a subject the plugin invents, verbatim for a subject it borrows, whether from its own config or from Notion. `references/signatures.md`'s "Adding a signature" step 2 was generalized to match. `prefix-mismatch:unique_id` itself, and its citation in `ticket-system/SKILL.md`, are unchanged — they were already the conforming form; only the grammar describing them was incomplete. `SKILL.md` is current; §4 and §7.4 above reflect the original, now-incomplete design.
>
> **Amended during execution, round 6 (2026-08-02):** a further Codex review found `option-missing:<propertyName>` has the same collapsing defect round 3's `mcp-error` fix addressed above: it is per-property, so two different missing options — on the same property, or across runs — freeze at whichever `Expected`/`Observed` was recorded first, with the second permanently invisible behind a bumped `Occurrences`. Unlike `mcp-error`, the fix could not simply append the live option name to the subject: `epicProperty` and `phaseProperty` options are free-form values generated from the ticket or mission itself (a proposed epic name; a per-mission phase label), and the redaction contract already forbids any part of a ticket's content from reaching a signature, which is written into a literal `##` heading — the most exposed spot in the file. `statusProperty` and `typeProperty` options, by contrast, are selected through `statusMap`/`typeMap`, whose keys (`implemented`, `cancelled`, `feature`, and their siblings) are stable, plugin-defined vocabulary identical across every client — safe to fold into the subject. The template split in two: `option-missing:<propertyName>` stays the bare, unsuffixed form for the free-form (Epic/Phase) case; `option-missing:<propertyName>-<logicalKey>` is the new suffixed form for the `statusMap`/`typeMap` case, the same hyphen-compound convention round 3 established for `mcp-error:<tool>-<error-class>`. No current call site raises the suffixed form — it is registered so the first one that does has a compliant name ready rather than reaching for the unsuffixed form by default. The Redaction whitelist's `signature` row (below) gained a `statusMap`/`typeMap` logical key as a permitted component, alongside a new paragraph in `SKILL.md`'s "Forbidden, without exception" stating explicitly that a free-form Select option value counts as ticket content. `SKILL.md` and `references/signatures.md` are current; §5 and §7.4 below reflect the pre-round-6 design.

Redaction is **structural** — a per-field whitelist, not a cleanup pass someone remembers to run. Writing a compliant entry and writing a redacted entry are the same act.

| Field | May contain |
|---|---|
| signature | A class from §4 plus a config property name or fixed subject. |
| `Kind` | One of the three §3.1 values. |
| `Occurrences` | An integer. |
| `First seen` / `Last seen` | A UTC timestamp and the plugin version. |
| `Where` | Command name, phase name, skill name, step number. Optionally a ticket key (`STO-67`). |
| `Expected` | The plugin's expectation, stated in config and schema terms. |
| `Observed` | The shape of live state — presence, absence, Notion property type, error text. |
| `Effect` | What the plugin did, skipped, or aborted. |
| `Context` | `key=value` pairs joined by ` · `, drawn only from the closed list below. |

**`Context` permitted keys:** `idProperty`, `epicProperty`, `epicMarkerProperty`, `parentTaskProperty`, `assigneeProperty`, `dependsOnProperty`, `prProperty`, `creationDateProperty`, `statusProperty`, `flow`, `reviewer`, `db`.

Values are `present`, `absent`, a Notion type name, a configured property name, or — for `db` only — the last six characters of the database id, written `db=…a41f9c`.

### 5.1 Forbidden, without exception

Ticket titles. Ticket bodies. Any part of a ticket's content. PR titles, descriptions, or contents. Diffs or code. Notion user ids. Email addresses. Personal names. Full database ids. Full page ids. Absolute filesystem paths. URLs of any kind.

`Observed` and `Effect` are the leak risk, because they are prose. Their contract states it directly: **these describe plugin behavior, never ticket content.** `SKILL.md` carries this forbidden list verbatim adjacent to the field table.

The rationale, which `SKILL.md` states so a future editor does not relax it: clients forward this file to the plugin author, possibly without reading it. Plugin bugs live in the plugin's logic, not the client's data, so identifiers are sufficient to diagnose.

---

## 6. What is *not* logged

Necessary counterweight to layer 1. The plugin already declares a set of absences and empty results **routine**, annotating several of them "never a warning — these are routine, not exceptional". Logging them would bury the real entries under normal operation.

Never logged:

| Condition | Where declared |
|---|---|
| `getEpicContext` returns `null` (ticket has no epic, or `epicMarkerProperty` absent) | `ticket-system/SKILL.md` — "Not a warning — this is the normal case for most tickets" |
| `findEpics()` returns `[]` (property exists, no page marked yet) | `ticket-system/SKILL.md`, `create-task.md` Phase 2.6 |
| `resolveAssignee` returns `null` (zero or ambiguous matches) | `ticket-system/SKILL.md` — "routine, not exceptional" |
| `fetchTicket` returning a type's empty default for an unset or absent property | `ticket-system/SKILL.md` — "never a warning" |
| Zero plausible epic candidates in `create-task.md` Phase 2.6 | "the common case, and routine single-ticket runs must stay as quiet as they are today" |
| A user declining a gate, choosing Revise, or aborting at a confirmation prompt | Normal interaction; the ledger already records it as `stopped` |
| Anything the issue log itself fails at | §8 |

Note the asymmetry that makes this list non-obvious: `findEpics()` returning **`null`** — `epicMarkerProperty` absent from the database — **is** logged, as `missing-property:epicMarkerProperty`. Returning **`[]`** is not. The adapter is explicit that callers must not conflate the two, and neither may the issue log.

`getEpicContext` never logs even when it returns `null` because the marker is absent, because that same condition is already recorded at `findEpics`/`createTicket`. One condition, one signature, one entry.

---

## 7. Wiring

### 7.1 Layer 1 — the standing rule

Each of the four commands gains one short preamble block, near the top, before its first phase:

> **Standing rule — runtime issues.** Anything unexpected at runtime — an MCP error, an unexpected schema shape, a value you had to guess at, a retry, a fallback taken, an abort, a failed precondition, a warning shown to the user — is recorded via `notion-dev:issue-log`, at the moment it happens. That skill owns the format, the signature vocabulary, the redaction contract, and the list of conditions that are routine and must *not* be logged. This applies to conditions nobody enumerated in advance, not only to the named ones below.

The full rule, the vocabulary, and the not-logged list live in `SKILL.md` and are **not** duplicated into the commands. A slash command file *is* the prompt, so this block is guaranteed-read for the whole run, including skills invoked mid-flow.

**Timing: write at the moment of the deviation, never batched to end of run.** A run that dies loses batched entries, and those are precisely the runs whose record matters most.

### 7.2 Layer 1 — the end-of-run sweep

A second net, for conditions the agent noticed but did not stop to record. Placed in each command's final phase:

| Command | Sweep location | Report-line location |
|---|---|---|
| `ticket.md` | Phase 9 (Clean up), alongside the ledger outcome append | Phase 10 (Report) |
| `finalize.md` | Phase 4 (Clean up) | Phase 5 (Report) |
| `create-task.md` | Phase 4 (Report), before the report is composed | Phase 4 (Report) |
| `init.md` | Its report step | Its report step |

Text: *"Review this run for unexpected conditions not already recorded, and record them now via `notion-dev:issue-log`."*

**The sweep must also run on the unrecoverable-failure path.** `ticket.md`'s "Failure and stop conditions" section stops without running cleanup, so Phase 9's sweep never fires there — and that path is where the interesting failures are. It gets its own best-effort sweep, placed and worded to mirror exactly how the ledger outcome append is already handled there. Same for `finalize.md` and `create-task.md`.

### 7.3 Layer 1 — the report line

Each command prints one line in its final report, **only when that run wrote to the log**:

```
2 issues logged to .claude/notion-dev/notion-dev-issues.md
```

Without this the feature depends on a client stumbling across a dotfile inside a self-ignored directory. An author-facing diagnostic nobody mentions never gets sent.

### 7.4 Layer 2 — the registry

> **Amended during execution (2026-08-02):** final review found this table missing `missing-property:stepProperty` — governed identically to the `phaseProperty` row below (same absence-tolerant Number property, same umbrella warning), just never given its own row because Step had no dedicated prose paragraph for the sweep to find. The live registry now holds 22 rows, not the 19 below. Treat this table as a historical snapshot of design intent; `references/signatures.md` is current.
>
> **Amended during execution, round 3 (2026-08-02):** two further Codex findings landed without changing the row count (still 22). First, `getSelectOptions`'s row-less `null` contract (§7.4 has no row for it — it returns `null`, it doesn't log) was tightened: the adapter, not the caller, now distinguishes *why* the `null` happened, citing the same `missing-property:<propertyName>` / `wrong-type:<propertyName>` templates the `assigneeProperty` and `creationDateProperty` rows below already use — no new row needed, since both templates already existed. Second, the `mcp-error:<tool>` row (below) gained an `<error-class>` component so two different failure modes of the same tool no longer collapse into one section; see the amended note on §5 above for the sanitization rule this added. `references/signatures.md` holds the current row for both; this table stays a historical snapshot.
>
> **Amended during execution, round 4 (2026-08-02):** the round-3 fix above assumed `getSelectOptions`/`addSelectOption`'s `<propertyName>` templates were already config-key names; a further review found the argument passed into both operations is actually the caller's **live column name** (callers invoke, e.g., `getSelectOptions(<phaseProperty>)`, passing the resolved value, not the key). Both operations' prose in `ticket-system/SKILL.md`, and the corresponding `getSelectOptions`-returns-`null` row in `issue-log/SKILL.md` §6, now instruct mapping that argument back to its owning config key before citing `missing-property:<key>` / `wrong-type:<key>` — still no new row, since the config keys these resolve to (`phaseProperty`, `epicProperty`, …) already have rows or fit the same `<propertyName>` template. The registry stays at 22 rows. See the round-4 note on §5 above for the full rule.
>
> **Amended during execution, round 6 (2026-08-02):** the `option-missing:<propertyName>` row below split in two without changing the row count (still 22) — see the round-6 note on §5 above for the full Kind A / Kind B rationale. The row now documents both the unsuffixed form (`epicProperty`/`phaseProperty` — free-form, ticket-derived option values, never suffixed) and the new suffixed form `option-missing:<propertyName>-<logicalKey>` (`statusProperty`/`typeProperty` options selected through `statusMap`/`typeMap`, whose logical keys are stable plugin vocabulary). `references/signatures.md` holds the current row; this table stays a historical snapshot.

`references/signatures.md` holds one table. Seeded from the sites verified present in the current tree:

| Signature | Kind | Site | Condition | Frequency |
|---|---|---|---|---|
| `missing-property:prProperty` | degraded | `ticket-system` | `prProperty` absent; PR write skipped | once/run |
| `missing-property:assigneeProperty` | degraded | `ticket-system` | `assigneeProperty` absent; assignee write skipped | once/run |
| `wrong-type:assigneeProperty` | degraded | `ticket-system` | present but not a People property | once/run |
| `missing-property:creationDateProperty` | degraded | `ticket-system` | absent; creation-date write skipped | once/run |
| `wrong-type:creationDateProperty` | degraded | `ticket-system` | present but neither `date` nor `created_time` | once/run |
| `missing-property:parentTaskProperty` | degraded | `ticket-system` | absent; guards parent write, `setParent`, `listEpicChildren`, `refreshEpicTasks` | once/run |
| `missing-property:epicProperty` | degraded | `ticket-system` | absent; Epic select skipped, `createEpic` degrades | once/run |
| `missing-property:epicMarkerProperty` | degraded | `ticket-system` | absent; `findEpics` returns `null`, epic containers unavailable | once/run |
| `missing-property:dependsOnProperty` | degraded | `ticket-system` | absent; `setDependencies` no-ops | once/run |
| `option-missing:<propertyName>` | failed | `ticket-system` | required Select/Status option absent; `createTicket` raises | per occurrence |
| `prefix-mismatch:unique_id` | degraded | `ticket-system` | live `unique_id` prefix differs from `project.key` | once/run |
| `mcp-unavailable:notion` | failed | `ticket-system` | Notion MCP unreachable | per occurrence |
| `mcp-unavailable:notion-get-users` | failed | `ticket-system` | `resolveAssignee` cannot run | per occurrence |
| `mcp-error:<tool>` | unexpected | any | an MCP call returned an error | per occurrence |
| `abort:project-scope` | failed | `ticket-system` | pinned `staticProperties` mismatch; refused to cross projects | per occurrence |
| `fallback:local-code-review` | degraded | `ticket.md`, `finalize.md` | configured reviewer unavailable; local fallback ran, no cross-model validation | once/run |
| `retry-exhausted:plan-review` | degraded | `ticket.md` | `PLAN-REVIEW: degraded` — reviewer never ran | once/run |
| `retry-exhausted:verify` | failed | `ticket.md` | verify step never passed after its retries | per occurrence |
| `partial:epic-update` | degraded | `ticket.md`, `finalize.md` | `epic-update` returned a non-empty `SKIPPED` or `FAILED` bucket | once/run |

Each existing warning sentence at these sites gains a signature citation. The prose already exists — `ticket-system/SKILL.md` alone already says "log **one** warning per run" repeatedly. This work gives those warnings a durable destination; it does not invent new detection logic.

Where a condition splits `missing-property` from `wrong-type` (assignee, creation date), the call site says which to use: absent → `missing-property`, present-but-wrong-type → `wrong-type`. Existing prose already distinguishes the two cases in the same sentence.

### 7.5 Layer 2 — log at the caller

`init.md`'s schema-drift items get **no signatures of their own.** A `parentTaskProperty` missing at init and the same property missing at ticket time are one condition observed at two moments; both write `missing-property:parentTaskProperty`. Minting init-specific classes would produce a dozen near-duplicates and destroy the grouping the file exists to provide.

Degraded plan review, degraded code review, and partial `epic-update` are logged **by the calling command**, not inside `plan-review/SKILL.md`, `local-code-review/SKILL.md`, `review-and-merge/SKILL.md`, or `epic-update/SKILL.md`. Two reasons:

1. Each degradation is already visible to the caller in the output block those skills return — `PLAN-REVIEW: degraded`, the reviewer-used line, `epic-update`'s `SKIPPED`/`FAILED` buckets. No new signal has to be threaded anywhere.
2. `plan-review/SKILL.md` Step 1 is a **closed enumeration** of what reaches the reviewer's prompt. Threading a value into it without extending that enumeration produces a silently ignored instruction — the exact defect §7a of the handoff records. Logging at the caller means those four skill files are not touched at all.

### 7.6 Files changed

> **Amended during execution (2026-08-02):** final review found `createTicket`'s Epic/Phase option-match raises, its per-property missing-configured-property warning, and `addSelectOption`'s schema-mismatch raise all uncited at design time, pushing `ticket-system/SKILL.md`'s citation count well past 14. The row below is the original estimate; count the live citations with `grep -c 'notion-dev:issue-log' plugins/notion-dev/skills/ticket-system/SKILL.md` rather than trusting this number.

| File | Change |
|---|---|
| `skills/issue-log/SKILL.md` | new |
| `skills/issue-log/references/signatures.md` | new |
| `skills/ticket-system/SKILL.md` | signature citations at 14 sites |
| `commands/ticket.md` | preamble, Phase 9 sweep, Phase 10 report line, failure-path sweep, 4 caller-side signatures |
| `commands/finalize.md` | preamble, Phase 4 sweep, Phase 5 report line, failure-path sweep, 2 caller-side signatures |
| `commands/create-task.md` | preamble, Phase 4 sweep + report line, failure-path sweep |
| `commands/init.md` | preamble, report-step sweep + report line, drift items cite existing signatures |
| `.claude-plugin/plugin.json` | `0.8.0` → `0.9.0` |
| `README.md` | new section documenting the log |

---

## 8. Best-effort contract

Stated in `SKILL.md` and echoed at every sweep site:

- A failure to create, read, or write the issue log **never fails the run**. Copied in spirit from the ledger's "a ledger append failure never fails the run."
- A failure of the issue log is **never itself logged**. No recursion. The issue-log skill never invokes itself.
- The log is written to `$REPO_ROOT`, resolved the same way the ledger resolves it — the primary checkout, never a worktree.
- A malformed or hand-edited existing file is not repaired. If the file cannot be parsed for the dedup search, append the new entry at the end and continue. Never rewrite or discard what is already there.

---

## 9. Verification

No test harness exists in this repo and none is added. Verification is cross-file consistency, run as commands with stated expected output.

**V1 — signature closure (the load-bearing check).**

```bash
grep -rhoE '\b(missing-property|wrong-type|option-missing|prefix-mismatch|mcp-unavailable|mcp-error|abort|retry-exhausted|fallback|partial|unexpected):[A-Za-z_<>-]+' \
  plugins/notion-dev --include='*.md' | sort -u
```

Two details this check gets wrong if implemented naively, both verified against a draft of this spec:

- The character class must include `_`, or `prefix-mismatch:unique_id` is truncated and reported as a spurious mismatch.
- Angle-bracket forms are **templates, not signatures** — `option-missing:<propertyName>` and `mcp-error:<tool>` in the registry, `unexpected:<subject>` in the §4 grammar. Filter `| grep -v '<'` from both sides before comparing, or the grammar's illustrative form is reported as an unregistered signature on every run.

Compared against the signature column of `references/signatures.md`, the two sets must be **equal**. A signature present only in the first set is a call site naming something nobody defined. A signature present only in the second is a dead registry entry. Both are the two-places-disagree defect, caught mechanically.

**V2 — every command carries the standing rule.** `grep -l 'notion-dev:issue-log' plugins/notion-dev/commands/*.md | wc -l` returns `4`.

**V3 — every command has a sweep and a report line.** Grep each of the four command files for the sweep sentence and the report-line format; expect one of each per file, plus a failure-path sweep in `ticket.md`, `finalize.md`, and `create-task.md`.

**V4 — no hardcoded version.** Every version literal in the new skill must sit on an illustrative `First seen` / `Last seen` example line and nowhere else:

```bash
grep -rnE '0\.[0-9]+\.[0-9]+' plugins/notion-dev/skills/issue-log/ | grep -v 'First seen\|Last seen'
```

Expect no output. The skill reads the version from the manifest at write time (§3.2).

**V5 — redaction contract present.** `SKILL.md` contains the §5 field table and the §5.1 forbidden list, and no example entry in either new file contains a URL, an email, a full id, or prose that reads as ticket content.

**V6 — not-logged list is reachable.** `SKILL.md` contains the §6 table, and the standing-rule preamble in all four commands points at it.

**V7 — version consistency.** `.claude-plugin/plugin.json` reads `0.9.0` and `README.md` states the same version.

**V8 — the two-places sweep.** For every file edited, check whether each fact added is stated anywhere else in that same file — quick-reference table versus detailed section, lead-in count versus list length, sibling operations that should have received the same change. This single check caught every defect across ten review rounds on the epics branch; it goes verbatim into every reviewer prompt.

---

## 10. Known limitations

Stated here and, where client-visible, in the file header and README.

**An entry is written only if the agent follows the instruction to write it.** The plugin has no runtime — no `finally`, no exception handler, no process. In practice this captures quiet degradations well, because they happen mid-flow while the agent is already following instructions, and captures hard failures unreliably, because a killed process, an exhausted context, or a user interrupt leaves nothing running to record its own death. This is the inverse of a conventional log's strengths. A short file is not evidence of a healthy run.

Writing is nonetheless **automatic** during ordinary command runs. The client types nothing.

**Concurrent runs can lose an occurrence increment.** Dedup is read-modify-write, unlike the ledger's append-only JSONL. Two agents in parallel worktrees writing the same signature at the same moment will have one overwrite the other's increment. Acceptable: this is diagnostics, not accounting, and the entry itself still exists.

**The file grows without bound in principle.** In practice it grows with *distinct* problems rather than with runs, since dedup collapses repeats. No rotation, by decision.

---

## 11. Rejected alternatives

**Repeating the standing rule in full in each command** instead of referencing the skill. More likely to be obeyed, since the agent never has to load the skill to know the rule. It also creates four copies of one fact, which is the failure mode behind every fix round on the epics branch. Rejected.

**A `Stop` hook that sweeps the run.** Technically available — `plugin.json` can declare hooks, and a run-marker file would keep it silent in sessions that never ran a notion-dev command. But it does not fire on an Esc interrupt or an exhausted context either, which are exactly the cases §10 loses, so its gain over the in-band sweep is close to zero. Its cost is real: the first executable file in a plugin whose no-code property is load-bearing for how everything else is verified. Rejected.

**Repo root plus auto-editing the client's `.gitignore`.** More discoverable. Edits a file the plugin does not own, and fails open if the ignore line is ever removed. Rejected — see §2.1.

**A `drift` value in the `Kind` taxonomy.** See §3.1.

**A `/notion-dev:report-issues` command.** See Non-goals.

**Splitting the file into "your setup" and "plugin issues" sections.** Sharper signal, but requires the plugin to classify blame at write time, and it would sometimes be wrong. The log is author-facing; the author can classify. Rejected.
