# Enumerated issue-log signatures

The single definition point for every named signature the notion-dev plugin writes, scoped to **concrete, cited names** — never the `<propertyName>` / `<logicalKey>` / `<tool>` template forms, which stand for a family of names rather than naming one. Call sites cite these names; they never redefine them and never coin variants. See "Consolidations" below for how `/notion-dev:init` reuses this same grammar without adding rows of its own.

Read alongside `../SKILL.md`, which owns the grammar, the entry format, the redaction contract, and the list of conditions that are routine and must not be logged.

`<propertyName>`, `<logicalKey>`, and `<tool>` below are **templates**, not literal signatures — the writer substitutes the real name.

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
| `missing-property:phaseProperty` | degraded | `ticket-system` | absent; Phase select write skipped | once/run |
| `missing-property:stepProperty` | degraded | `ticket-system` | absent; Step number write skipped | once/run |
| `missing-property:epicMarkerProperty` | degraded | `ticket-system` | absent; `findEpics` and `getEpicContext` both return `null`, epic containers unavailable on this DB | once/run |
| `missing-property:dependsOnProperty` | degraded | `ticket-system` | absent; `setDependencies` no-ops | once/run |
| `option-missing:<propertyName>`<br>Kind A: `option-missing:<propertyName>-<logicalKey>` | failed | `ticket-system` | a required Select/Status option is absent; `createTicket` raises. **Kind B** (Epic/Phase — free-form, ticket-derived option values): the bare property-key form on the left, never suffixed with the option value — see note below. **Kind A** (Status/Type — a `statusMap`/`typeMap` logical key): suffix with `-<logicalKey>` so each missing option keeps its own identity; no current call site raises this, documented so the first one that does has a compliant name ready | per occurrence |
| `prefix-mismatch:unique_id` | degraded | `ticket-system` | live `unique_id` column prefix differs from `project.key` | once/run |
| `mcp-unavailable:notion` | failed | `ticket-system` | the Notion MCP is unreachable | per occurrence |
| `mcp-unavailable:notion-get-users` | failed | `ticket-system` | `resolveAssignee` cannot run | per occurrence |
| `mcp-error:<tool>-<error-class>` | unexpected | any — layer-1 vocabulary, no dedicated call site | an MCP call was reached and returned an error; `<error-class>` (see note below) distinguishes different failure modes of the same tool | per occurrence |
| `abort:project-scope` | failed | `ticket-system` | pinned `staticProperties` mismatch; refused to operate across projects | per occurrence |
| `fallback:local-code-review` | degraded | `ticket.md`, `finalize.md` | the configured reviewer was unavailable; the local fallback ran, so no cross-model review validated the PR | once/run |
| `retry-exhausted:plan-review` | degraded | `ticket.md` | `PLAN-REVIEW: degraded` — the reviewer never ran | once/run |
| `retry-exhausted:verify` | failed | `ticket.md` | the verify step never passed after its retries | per occurrence |
| `partial:epic-update` | degraded | `ticket.md`, `finalize.md` | `epic-update` returned a non-empty `SKIPPED` or `FAILED-TO-FILE` bucket | once/run |

**`mcp-error:<tool>-<error-class>`.** `<tool>` is the MCP tool name (e.g. `notion-fetch`); `<error-class>` is the error's class or message *shape*, kebab-cased (`object_not_found` → `object-not-found`). The hyphen joining the two is part of the subject, not the `<class>:<subject>` delimiter — that delimiter stays the single colon immediately after `mcp-error`. **`<error-class>` must be sanitized exactly as `Observed` is** (`../SKILL.md`, "Redaction"): never an id, URL, path, or quoted value, only the class or shape word(s) — this matters more here than in a prose field, because this identity becomes a literal `## mcp-error:<tool>-<error-class>` heading in the log file, where a leaked id would be conspicuous rather than merely present. When the tool's error carries no identifiable class (a bare timeout, a blank message, an opaque failure), use the literal word `unknown` as `<error-class>` rather than omitting it or falling back to a bare `mcp-error:<tool>` — `mcp-error:<tool>-unknown` is a fully compliant, groupable identity, and this is what an agent reaches for instead of being stuck without a compliant name for an error it cannot classify. This is also how a repeat tool failure with a materially different `Observed` (per "Write procedure" in `../SKILL.md`) gets its own compliant signature rather than silently overwriting the first one's recorded fields: two distinct error classes returned by the same tool across different runs produce two distinct headings under this template, never one merged under a bare `mcp-error:<tool>`.

**`option-missing:<propertyName>` vs `option-missing:<propertyName>-<logicalKey>`.** Required Select/Status options split into two kinds, and only one of them may carry the live option name into the subject. **Kind A** — a `statusProperty` or `typeProperty` option selected through `statusMap` / `typeMap` — is keyed by a stable, plugin-defined **logical key** (`implemented`, `cancelled`, `feature`, and their siblings), identical across every client regardless of what the live DB happens to call the option. A missing option here takes the suffixed form `<propertyName>-<logicalKey>`, the hyphen joining the two the same way it joins `<tool>` and `<error-class>` above, so a missing `implemented` and a missing `cancelled` earn separate identities instead of colliding under one bare property name. **Kind B** — `epicProperty` and `phaseProperty` options — are free-form values generated from the ticket or mission being filed (a proposed epic name; a phase label `commands/create-task.md` describes as "generated per-mission structure, not user taxonomy"), never drawn from a fixed vocabulary; for these the subject stays the bare `<propertyName>` with no suffix, and the live option value must never be appended to it. A signature becomes a literal `##` heading — the most exposed spot in this file — and the redaction contract (`../SKILL.md`, "Forbidden, without exception") already forbids any part of a ticket's content from reaching it. Losing per-option dedup on Kind B is an accepted tradeoff, not an oversight: a missing free-form option always has the same diagnosis — the caller skipped the `getSelectOptions` / `addSelectOption` reconcile before `createTicket` — so which option was missing doesn't change what the plugin author needs to know. No enumerated site currently raises `option-missing` for a Kind A property; the suffixed form is registered here so the first one that does has a compliant name ready rather than reaching for the Kind B form by default.

## Consolidations

Deliberate, and not to be undone without re-reading this section.

**`/notion-dev:init` has no signatures of its own.** A property missing at init and the same property missing at ticket time are one condition observed at two moments; both write `missing-property:<propertyName>`. Minting init-specific classes would produce a dozen near-duplicates and destroy the grouping this file exists to provide.

This table's `Kind` and `Condition` columns describe the **ticket-time** manifestation — the value observed when `ticket-system` itself hits the condition mid-run (e.g. "PR property write skipped"). `init`'s schema-drift check (`commands/init.md`) reuses the same signature name for the same underlying condition, but observes it differently: nothing degrades at init, drift is detected and the user is offered Patch/Skip/Update. Because dedup freezes `Kind` and the descriptive fields at first sight (`SKILL.md`, "Write procedure"), `init` writes these entries with `Kind: degraded` — matching the run-continued reality in both cases — paired with a drift-check `Effect` sentence (e.g. "flagged as drift; user offered Patch/Skip/Update") rather than the runtime `Effect` implied by this table's `Condition` column. Whichever site writes first determines which `Effect` text the entry carries; the `Kind` stays consistent either way.

`init`'s drift check also compares config keys this table has no row for at all — `statusProperty`, `typeProperty`, `idProperty`, and type mismatches on `parentTaskProperty` / `epicMarkerProperty` among them — because `ticket-system` has no runtime degrade path for those (a missing `idProperty` or `statusProperty` is a hard failure, not a graceful skip, so it never earns a registry row here). `init` is permitted to mint grammar-conformant `missing-property:<propertyName>` / `wrong-type:<propertyName>` names for these in its own instruction text, in template form, without a corresponding row — see "Adding a signature" below for the closure check this reuse depends on.

**Degraded reviews and partial epic updates are logged by the calling command**, not inside `plan-review/SKILL.md`, `local-code-review/SKILL.md`, `review-and-merge/SKILL.md`, or `epic-update/SKILL.md`. Each degradation is already visible to the caller in the output block those skills return, so no new signal has to be threaded anywhere. `plan-review` Step 1 in particular is a closed enumeration of what reaches the reviewer's prompt: a value threaded in without extending that enumeration is silently never read.

## Adding a signature

1. Add the row here first.
2. If the new signature's subject is a config property name or an external identifier such as a Notion property type name, check the `Context` permitted-keys whitelist in `../SKILL.md` — an entry that can't carry its own property as `Context` is a defect. (`phaseProperty` and `stepProperty` were missed there once; don't repeat it.)
3. Cite the name at the call site, in the form: ``Record `<signature>` per `notion-dev:issue-log`.``
4. Re-run the closure check in the plan's Task 7. The set of **concrete, cited** signature names across `plugins/notion-dev` (excluding this file, and excluding `<...>` template forms) and the set of concrete names in this table must be equal. `/notion-dev:init`'s templated reuse of this grammar (see "Consolidations" above) is out of scope for this check by design — it never appears as a concrete cited string.
