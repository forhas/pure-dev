# Enumerated issue-log signatures

The single definition point for every named signature the notion-dev plugin writes, scoped to **concrete, cited names** — never the `<propertyName>` / `<tool>` template forms, which stand for a family of names rather than naming one. Call sites cite these names; they never redefine them and never coin variants. See "Consolidations" below for how `/notion-dev:init` reuses this same grammar without adding rows of its own.

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
| `missing-property:phaseProperty` | degraded | `ticket-system` | absent; Phase select write skipped | once/run |
| `missing-property:stepProperty` | degraded | `ticket-system` | absent; Step number write skipped | once/run |
| `missing-property:epicMarkerProperty` | degraded | `ticket-system` | absent; `findEpics` and `getEpicContext` both return `null`, epic containers unavailable on this DB | once/run |
| `missing-property:dependsOnProperty` | degraded | `ticket-system` | absent; `setDependencies` no-ops | once/run |
| `option-missing:<propertyName>` | failed | `ticket-system` | a required Select/Status option is absent; `createTicket` raises | per occurrence |
| `prefix-mismatch:unique_id` | degraded | `ticket-system` | live `unique_id` column prefix differs from `project.key` | once/run |
| `mcp-unavailable:notion` | failed | `ticket-system` | the Notion MCP is unreachable | per occurrence |
| `mcp-unavailable:notion-get-users` | failed | `ticket-system` | `resolveAssignee` cannot run | per occurrence |
| `mcp-error:<tool>` | unexpected | any — layer-1 vocabulary, no dedicated call site | an MCP call was reached and returned an error | per occurrence |
| `abort:project-scope` | failed | `ticket-system` | pinned `staticProperties` mismatch; refused to operate across projects | per occurrence |
| `fallback:local-code-review` | degraded | `ticket.md`, `finalize.md` | the configured reviewer was unavailable; the local fallback ran, so no cross-model review validated the PR | once/run |
| `retry-exhausted:plan-review` | degraded | `ticket.md` | `PLAN-REVIEW: degraded` — the reviewer never ran | once/run |
| `retry-exhausted:verify` | failed | `ticket.md` | the verify step never passed after its retries | per occurrence |
| `partial:epic-update` | degraded | `ticket.md`, `finalize.md` | `epic-update` returned a non-empty `SKIPPED` or `FAILED-TO-FILE` bucket | once/run |

## Consolidations

Deliberate, and not to be undone without re-reading this section.

**`/notion-dev:init` has no signatures of its own.** A property missing at init and the same property missing at ticket time are one condition observed at two moments; both write `missing-property:<propertyName>`. Minting init-specific classes would produce a dozen near-duplicates and destroy the grouping this file exists to provide.

This table's `Kind` and `Condition` columns describe the **ticket-time** manifestation — the value observed when `ticket-system` itself hits the condition mid-run (e.g. "PR property write skipped"). `init`'s schema-drift check (`commands/init.md`) reuses the same signature name for the same underlying condition, but observes it differently: nothing degrades at init, drift is detected and the user is offered Patch/Skip/Update. Because dedup freezes `Kind` and the descriptive fields at first sight (`SKILL.md`, "Write procedure"), `init` writes these entries with `Kind: degraded` — matching the run-continued reality in both cases — paired with a drift-check `Effect` sentence (e.g. "flagged as drift; user offered Patch/Skip/Update") rather than the runtime `Effect` implied by this table's `Condition` column. Whichever site writes first determines which `Effect` text the entry carries; the `Kind` stays consistent either way.

`init`'s drift check also compares config keys this table has no row for at all — `statusProperty`, `typeProperty`, `idProperty`, and type mismatches on `parentTaskProperty` / `epicMarkerProperty` among them — because `ticket-system` has no runtime degrade path for those (a missing `idProperty` or `statusProperty` is a hard failure, not a graceful skip, so it never earns a registry row here). `init` is permitted to mint grammar-conformant `missing-property:<propertyName>` / `wrong-type:<propertyName>` names for these in its own instruction text, in template form, without a corresponding row — see "Adding a signature" below for the closure check this reuse depends on.

**Degraded reviews and partial epic updates are logged by the calling command**, not inside `plan-review/SKILL.md`, `local-code-review/SKILL.md`, `review-and-merge/SKILL.md`, or `epic-update/SKILL.md`. Each degradation is already visible to the caller in the output block those skills return, so no new signal has to be threaded anywhere. `plan-review` Step 1 in particular is a closed enumeration of what reaches the reviewer's prompt: a value threaded in without extending that enumeration is silently never read.

## Adding a signature

1. Add the row here first.
2. If the new signature names a config property, check the `Context` permitted-keys whitelist in `../SKILL.md` — an entry that can't carry its own property as `Context` is a defect. (`phaseProperty` and `stepProperty` were missed there once; don't repeat it.)
3. Cite the name at the call site, in the form: ``Record `<signature>` per `notion-dev:issue-log`.``
4. Re-run the closure check in the plan's Task 7. The set of **concrete, cited** signature names across `plugins/notion-dev` (excluding this file, and excluding `<...>` template forms) and the set of concrete names in this table must be equal. `/notion-dev:init`'s templated reuse of this grammar (see "Consolidations" above) is out of scope for this check by design — it never appears as a concrete cited string.
