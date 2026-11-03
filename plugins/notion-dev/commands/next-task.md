---
description: Select the next unblocked ticket from an epic and run the lean ticket workflow.
argument-hint: "<epic-id> [--non-interactive] [--flow=lean|superpowers|feature-dev] [| guidance]"
disable-model-invocation: true
---

# /notion-dev:next-task

Resolves exactly one ticket. `--depth` given → stop before any write: "`--depth` was removed
in 1.0.0; use `/notion-dev:run-epic <epic>`".
Pass non-interactive, explicit flow and user guidance to ticket.
Default flow is lean. Never load the build frameworks merely to choose a ticket.

Use the primary checkout's config and configured `knowledge.python` (`python3` in examples).
Probe GitHub access and required local tools as in `references/lean-intake.md`; cache successful
read-only probes for this invocation, not across plugin reloads. No external build-framework
dependency on the lean path. Confirm the epic via ticket-system: empty parent relation AND
the configured epic-marker checkbox true. A non-epic argument is a stop.

## Select

1. Invoke epic-doc `schedule(<epic-id>)` once. Retain the brief and live child list
   as artifact references with source identity and fetch time. The brief supplies scheduling
   guidance, not authoritative ticket requirements or live statuses.
2. If BOOTSTRAP or DRIFT requires a brief write, use epic-doc's bootstrap/refresh operation
   under the primary lock, commit/push through its established write path, and release the lock.
   Reuse the refreshed brief. A failed provider read is not an empty epic. Schedule's
   epic-goal `recommendation` binds selection per `references/scope.md` §Selection.
3. Resume an unresolved child with an owned resumable worktree before selecting new work.
   Use schedule's `knowledge.py retrieval-plan` loop; do not start a sibling-body gatherer.
   Never take over another live run. Otherwise walk NEXT in order: require an exact live-child
   key, unresolved status, no BLOCKED entry, and resolved dependencies from the candidate's
   full `## Blocked by` section. Use configured status mappings.
   An in-progress child without our worktree is held elsewhere, not available.
4. If NEXT has no valid candidate, interactive mode offers the valid children. Non-interactive
   mode selects the first valid child in the established epic order. If none, report complete
   or blocked with evidence; do not invent a ticket or override dependencies.

## Delegate

For the chosen ticket invoke knowledge `retrieve(<epic-id>, <ticket-title>, <ticket-key>)` once.
Pass schedule's same-boundary metadata/root revision for reuse; do not repeat its epic fetch.
Invoke `/notion-dev:ticket <key> [flags] | selected from <brief-path>: <reason>` via Skill.
Pass the saved ticket/context references, not copied histories. Ticket rechecks live ownership
and requirement freshness before writes.

Report `OUTCOME: resolved` only from the ticket's own `OUTCOME: resolved`; never for pending workers,
a launch acknowledgement, an unmerged PR, failed recording, or an incomplete closeout.
`claimed-elsewhere` refreshes ownership and selection once, then delegates the next valid child.
A stop/failure ends this run; never pick another ticket over unfinished owned work. A
runtime-authorized wait/yield is unfinished work, not an end.

Report ticket/PR, runtime path, skipped ownership/dependency reasons, and the ticket's
`OUTCOME:` line, `NEW-INFO:` and CLOSEOUT blocks verbatim, every line, not its long report. Last step of
every outcome (resolved, stopped, none selected, epic complete): save it with
`workflow.py save-report --project . --from -` (report on stdin).
