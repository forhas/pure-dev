---
description: Select the next unblocked ticket from an epic and run the lean ticket workflow.
argument-hint: "<epic-id> [--depth=N|all] [--non-interactive] [--flow=lean|superpowers|feature-dev] [| guidance]"
disable-model-invocation: true
---

# /notion-dev:next-task

Parse depth first: absent means 1; otherwise a positive integer or `all`. Reject invalid
values before writes. Pass non-interactive, explicit flow and user guidance to ticket.
Default flow is lean. Never load the build frameworks merely to choose a ticket.

Use the primary checkout's config and configured `knowledge.python` (`python3` in examples).
Probe GitHub access and required local tools as in `references/lean-intake.md`; cache successful
read-only probes for this invocation, not across plugin reloads. No external build-framework
dependency on the lean path. Confirm the epic via ticket-system: empty parent relation AND
the configured epic-marker checkbox true. A non-epic argument is a stop.

## Select

1. Invoke knowledge `retrieve(<epic-id>)` once. Retain the brief, context and live child list
   as artifact references with source identity and fetch time. The brief supplies scheduling
   guidance, not authoritative ticket requirements or live statuses.
2. If BOOTSTRAP or DRIFT requires a brief write, use epic-doc's bootstrap/refresh operation
   under the primary lock, commit/push through its established write path, and release the lock.
   Reuse the refreshed brief; do not copy the whole bundle through the parent repeatedly.
   A failed provider read is not an empty epic.
3. Resume an unresolved child with an owned resumable worktree before selecting new work.
   Never take over another live run. Otherwise walk NEXT in order: require an exact live-child
   key, unresolved status, no BLOCKED entry, and resolved dependencies from the candidate's
   full `## Blocked by` section. Use configured status mappings.
   An in-progress child without our worktree is held elsewhere, not available.
4. If NEXT has no valid candidate, interactive mode offers the valid children. Non-interactive
   mode selects the first valid child in the established epic order. If none, report complete
   or blocked with evidence; do not invent a ticket or override dependencies.

## Delegate and repeat

Invoke `/notion-dev:ticket <key> [flags] | selected from <brief-path>: <reason>` via Skill.
Pass the saved ticket/context references, not copied histories. Ticket rechecks live ownership
and requirement freshness before writes. Each ticket owns its own runtime invocation; resumes
keep the old invocation and budgets.

Track `DONE` only from `OUTCOME: resolved`; never increment `DONE` for pending workers,
a launch acknowledgement, an unmerged PR, failed recording, or an incomplete closeout.
`claimed-elsewhere` refreshes ownership and selection without counting a resolution.
A stop/failure stops this loop too. Do not pick another ticket over unfinished owned work.

After a resolution retrieve the updated epic once; reuse that retrieval for the next iteration.
No new implementation owner inherits the previous ticket's conversation: supply source/context
references only if delegation is justified. No request to continue between tickets within the
requested depth; a runtime-authorized wait/yield is still unfinished work, not abandonment.

Report resolved ticket/PR pairs, runtime paths, skipped ownership/dependency reasons and why the
loop stopped. Do not reconstruct each ticket's long report.
