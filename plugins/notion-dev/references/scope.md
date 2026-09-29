# Scope — keep an epic converging

Load at intake (fold scan), the outcome plan (ticket §2), before PR rendering (ticket §3) and at
selection (next-task). Mechanisms, not advice: each rule below is enforced by a named helper, and
`python3` stands for the configured `knowledge.python`. Settings live under `convergence` in the
primary config (schema defaults in brackets). **Project content lives in the project**: its
failure-mode classes, domain units, generated paths and routing labels are config values or a
project file the config names; the plugin ships only neutral fallbacks.

## Intake: declared fold targets

At intake of X, reuse declared targets in retained follow-up packets, the brief and already
fetched sources. If the actual provider offers body search, search X once and intersect hits
with live open epic children; fetch only those candidates. A title/property search is NOT body
search and an empty result proves nothing about body declarations. Do not invent a search
operation or fetch every sibling to compensate: report discovery coverage as partial when
body search is unavailable. Save candidate bodies as `[{"key": …, "text": …}]` and run
`workflow.py fold-scan --ticket <X> --pages <file>`; its coverage is supplied pages only.

The returned `relation: before` is a prerequisite, not permission to merge. Verify it is
resolved before starting X, or stop on the dependency. `with` (fold/merge/land with X) proposes
a `merge-into`; `conflicting: true` requires checking current intent. A regex hit, unattended
mode or ticket prose does not authorize closing another ticket or ignoring its requirements.
Check live ownership/dependencies, obtain explicit scoped approval (retained approval may
suffice), consolidate ALL requirements/constraints/AC into X, then capture and inventory the
updated authoritative target before implementation. Use task-breakdown's existing re-scope
path; no multi-id runtime is implied. If a declaration is obsolete, record why in context and
the PR; if still required but unauthorized, stop and name the decision, including unattended.
Follow-ups retain `Lands with: [X]` (`lands_with`) as a discovery lead, not automatic authority.

## Outcome plan

- **Sibling sweep.** When the ticket fixes a defect, `context.md`'s outcome plan records the
  search (command or query) that finds other instances of the same defect class, what it found,
  and each instance's disposition. Found siblings are absorbed (review-findings' mandatory-absorb
  case `sibling`); a sibling is never filed. The combined reviewer runs its own sweep
  (the result contract's `scope_rules`), because it never sees this plan.
- **Failure-mode classes.** When the ticket adds or changes a contract surface (anything
  another component, service or person relies on: an API, a message or event, a stored format,
  an on-chain entry point, a CLI), run `workflow.py failure-modes --config <primary-config>
  --project "$REPO_ROOT"`. It returns the project's classes (`failureModeClasses`, else the file
  `failureModeReference` names) or a neutral fallback. The design-review brief enumerates each
  returned class; the plan covers each or defers it explicitly. A deferral is allowed only when
  it does not block the epic goal, and is filed with `blocks_goal: no`. Prefer stacked PRs
  within this ticket over deferring a class to keep each review small.
- **Premises first.** A ticket with `## Premises to verify` is not ready until `runtime.py
  premises` records each one (`lean-intake.md`).

## Filing, dropping and follow-ups

`references/review-findings.md` owns the dispositions. `runtime.py judge-findings --config
<primary-config>` refuses a `file` without `criterion`, `absorb_class: "none"`, `blocks_goal`
and `blocks_goal_reason`, a mandatory-absorb class filed, criterion 3 under
`fileThresholdLines` [800] without a second design question, and a no-consumer drop without
its `reopen_trigger`. Measure criterion 3 with `workflow.py changed-lines --worktree
"$WORKTREE" --base origin/<base> --config <primary-config>`: it excludes `generatedPaths`
(lockfiles, codegen, exported specs), so generated churn never makes work "too large".

A judgment may carry `labels` (for example a severity, `security`, or `meta`). The follow-up's
destination is **computed**, never chosen: `workflow.py followup-body --config <primary-config>`
refuses any other. Routing order: the first `destinations` rule whose `match` fits a label;
then `meta` (case-insensitive: tooling, CI, knowledge-bundle or plugin work found during a product ticket) →
`metaDestination` [backlog], never the product epic; then `blocks_goal: yes` → the epic; else
`nonGoalDestination` [backlog]. A project that must not lose a class of finding (one that gates
its launch or release) maps that label to a gating epic with `destinations`; the plugin never
interprets domain labels. A meta destination must differ from `source_epic`, including when
a label rule chooses it; a conflicting route fails rather than silently falling back.
The builder also refuses a requirement that cites no verified
fact. Packets carry `dependencies` (rendered `## Blocked by`), `surface` (the files or contract
items it touches) and optional `lands_with`, so the next selection can order and bundle them.

## PR body

`workflow.py pr-body --config <primary-config>` refuses a figure (a number with a unit,
percentage or multiplier, plus the project's `figureUnits` such as a currency, `gas` or a
counted noun like `tests`) that cites neither `(artifact: …)` nor, directly after a parameter
the spec defines, `(spec: <section>)` — which never covers a claimed change such as "fell" or
"faster" — and is not a measured fact. It warns
over `prBodyBudget` [3000] characters. Reasoning and rejected alternatives go to the knowledge
capture once, not the PR body. `correction-batch` refuses a third consecutive prose rewrite of
one claim: replace it with an artifact reference or remove it.

## Selection

epic-doc `schedule` runs `knowledge.py epic-goal` and returns its `recommendation`, which binds
next-task before it selects anything (resuming owned unfinished work still comes first):

- `close` — the brief's `Done when:` list holds and no `Re-scope pending` thread exists (a
  pending spec change is re-checked first, since it may change the goal). Select nothing: the select plan returns no
  candidate once `goal_met: true` is passed. Interactive mode offers closing the epic plus the
  one re-home batch (epic-update step 4); non-interactive reports `goal met` with the `rehome`
  list and stops.
- `rescope` — either FOLLOWUP_RATE (goal-blocking follow-ups filed per resolution over the last
  `rateWindow` [3]) is above `rateThreshold` [1.0], or the brief carries a `- **Re-scope
  pending** — <what changed>` thread, written when epic-update or new-info records a change to
  the epic's source spec or a recorded decision. Do not select the next child: recommend a
  re-scope pass (`notion-dev:task-breakdown` re-scope mode over the open children) and stop.
  Every merge, drop and re-home it proposes needs the user's confirmation; the pass removes the
  thread once every open child has been re-checked.
- `repair-goal` — the `Done when:` list does not parse; report it and continue as `undefined`.
- Report every `release.warnings` line (a committed deliverable merged but not yet delivered to
  its consumers while later children add obligations ahead of it) before selecting; interactive
  mode asks whether to deliver it first.
- **Bundle same-surface work.** When the chosen candidate shares a surface (the same files or
  contract item — for example a schema, a message type or a heavily shared module) with other
  open, unblocked children, interactive mode offers to merge them into the candidate — one run,
  one worktree, one PR — through task-breakdown's `merge-into` proposal; the absorbed tickets
  are closed as merged, each with a link, only after the user confirms. Non-interactive mode
  reports the overlap and runs the candidate alone unless a declared dependency or unresolved
  required fold blocks it. The intake scan above preserves approval and inventory boundaries.
  A single run over several ticket ids is not
  supported (#86): merge first, or run them one at a time.

## Bookkeeping

`knowledge.py next` prints `COMMIT: deferred` for a start or drift that only changes in-progress
claim bookkeeping; epic-doc `refresh` then writes nothing. `record` folds every brief change of a
resolution into one commit and prunes over budget, so a normal merged ticket costs at most two
base commits: the brief record and the knowledge capture. The brief is the root of every
`retrieve`, so its budget is both `briefBudget` [150] lines and `briefRetrieveShare` [0.5] of
`knowledge.retrieveBudget`, estimated at 4 bytes per token; `epic-goal --retrieve-budget
<knowledge.retrieveBudget> --retrieve-share <briefRetrieveShare>` reports either overrun as
`brief.over_budget`.
`runtime.py summary` reports `scope` (dispositions, filed by `blocks_goal`, premise verdicts,
start-to-record seconds); `epic-goal --log … --repo …` reports the follow-up rate, maximum
generation, children open after the goal was met and brief commits per resolution.
