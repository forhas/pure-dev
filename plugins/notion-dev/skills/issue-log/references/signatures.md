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
