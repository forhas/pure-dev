# Scope — keep an epic converging

Load at the outcome plan (ticket §2), before PR rendering (ticket §3) and at selection
(next-task). Mechanisms, not advice: each rule below is enforced by a named helper, and
`python3` stands for the configured `knowledge.python`. Settings live under `convergence` in
the primary config (schema defaults in brackets).

## Outcome plan

- **Sibling sweep.** When the ticket fixes a defect, `context.md`'s outcome plan records the
  search (command or query) that finds other instances of the same defect class, what it found,
  and each instance's disposition. Found siblings are absorbed (review-findings' mandatory-absorb
  case `sibling`); a sibling is never filed. The combined reviewer runs its own sweep
  (the result contract's `scope_rules`), because it never sees this plan.
- **Failure-mode classes.** When the ticket adds a public endpoint or contract surface, the
  design-review brief enumerates: correctness of each verdict the client acts on; resource
  bounds (time, concurrency, queueing); lifetime and cleanup of borrowed resources; behaviour
  under upstream outage. The plan covers each class or defers it explicitly. A deferral is
  allowed only when it does not block the epic goal, and is filed with `blocks_goal: no`.
  Prefer stacked PRs within this ticket over deferring a class to keep each review small.
- **Premises first.** A ticket with `## Premises to verify` is not ready until `runtime.py
  premises` records each one (`lean-intake.md`).

## Filing, dropping and follow-ups

`references/review-findings.md` owns the dispositions. `runtime.py judge-findings --config
<primary-config>` refuses a `file` without `criterion`, `absorb_class: "none"`, `blocks_goal`
and `blocks_goal_reason`, a mandatory-absorb class filed, criterion 3 under
`fileThresholdLines` [800] without a second design question, and a no-consumer drop without
its `reopen_trigger`. `workflow.py followup-body` refuses a follow-up whose requirement cites
no verified fact, and routes `blocks_goal: no` to `nonGoalDestination` [backlog].

## PR body

`workflow.py pr-body --config <primary-config>` refuses a figure (a unit, percentage or
multiplier) that cites no `(artifact: …)` and is not a measured fact, and warns over
`prBodyBudget` [3000] characters. Reasoning and rejected alternatives go to the knowledge
capture once, not the PR body. `correction-batch` refuses a third consecutive prose rewrite of
one claim: replace it with an artifact reference or remove it.

## Selection

epic-doc `schedule` runs `knowledge.py epic-goal` and returns its `recommendation`, which binds
next-task before it selects anything (resuming owned unfinished work still comes first):

- `close` — the brief's `Done when:` list holds. Select nothing: the select plan returns no
  candidate once `goal_met: true` is passed. Interactive mode offers closing the epic plus the
  one re-home batch (epic-update step 4); non-interactive reports `goal met` with the `rehome`
  list and stops.
- `rescope` — FOLLOWUP_RATE (goal-blocking follow-ups filed per resolution over the last
  `rateWindow` [3]) is above `rateThreshold` [1.0]. Do not select the next child: recommend a
  re-scope pass (`notion-dev:task-breakdown` re-scope mode over the open children) and stop.
  Every merge, drop and re-home it proposes needs the user's confirmation.
- `repair-goal` — the `Done when:` list does not parse; report it and continue as `undefined`.
- Report every `release.warnings` line (a committed deliverable merged but unreleased while
  later children add obligations ahead of it) before selecting; interactive mode asks whether
  to release first.
- **Bundle same-surface work.** When the chosen candidate shares a surface (the same files, DTO,
  error code or contract item) with other open, unblocked children, interactive mode offers to
  merge them into the candidate — one run, one worktree, one PR — through task-breakdown's
  `merge-into` proposal; the absorbed tickets are closed as merged, each with a link, only after
  the user confirms. Non-interactive mode reports the overlap and runs the candidate alone.
  A single run over several ticket ids (runtime, markers and journal per ticket) is not
  supported: merge first, or run them one at a time.

## Bookkeeping

`knowledge.py next` prints `COMMIT: deferred` for a start or drift that only changes in-progress
claim bookkeeping; epic-doc `refresh` then writes nothing. `record` folds every brief change of a
resolution into one commit and prunes over `briefBudget` [150] lines, so a normal merged ticket
costs at most two base commits: the brief record and the knowledge capture.
`runtime.py summary` reports `scope` (dispositions, filed by `blocks_goal`, premise verdicts,
start-to-record seconds); `epic-goal --log … --repo …` reports the follow-up rate, maximum
generation, children open after the goal was met and brief commits per resolution.
