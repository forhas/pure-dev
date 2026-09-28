#!/usr/bin/env bash
# Epic convergence: goal-based closure, filing rules, verified follow-ups, artifact-bound
# PR claims, premise checks and the follow-up circuit breaker. Executable contracts first;
# the assertions below pin that each instruction still routes to its mechanism.
set -uo pipefail
cd "$(dirname "$0")/.."
fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }
. ./scripts/lib/assert.sh
PYBIN=${KNOWLEDGE_PY:-python3}
ND=plugins/notion-dev
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_decomposition.py'; then
  ok "goal closure, filing rules, verified follow-ups, PR artifacts, premises and rate breaker"
else
  bad "goal closure, filing rules, verified follow-ups, PR artifacts, premises and rate breaker"
fi
# Each rule is only as real as the helper call the instruction routes to.
assert_has "epic-update decides closure from the goal helper" \
  $ND/skills/epic-update/SKILL.md 'knowledge.py epic-goal --brief'
assert_has "re-home needs the user's confirmation" \
  $ND/skills/epic-update/SKILL.md 'only after the user confirms'
assert_has "the resolution entry separates non-goal follow-ups" \
  $ND/skills/epic-update/references/with-followups.md '**Follow-ups filed outside the goal** —'
assert_has "approved follow-ups route non-goal work off the epic" \
  $ND/skills/epic-update/references/approved-followup.md 'create the page with NO epic'
assert_has "judgments are validated with the configured threshold" \
  $ND/references/review-accounting.md 'judge-findings --worker <id> --judgments <file> --config <primary-config>'
assert_has "mandatory absorb forbids filing" $ND/references/review-findings.md 'Mandatory absorb — filing is not allowed'
assert_has "the create-task fast path renders through the verified builder" \
  $ND/commands/create-task.md 'followup-body --packet <packet.json> --output <body.json>'
assert_has "intake records premise checks before planning" $ND/references/lean-intake.md 'runtime.py premises'
assert_has "ticket applies the scope rules to its plan" $ND/commands/ticket.md 'references/scope.md'
assert_has "ticket renders the PR body with its config" $ND/commands/ticket.md '--config <config>'
assert_has "next-task is bound by the goal recommendation" $ND/commands/next-task.md 'epic-goal `recommendation`'
assert_has "schedule applies the configured follow-up window" $ND/skills/epic-doc/references/schedule.md '--window <convergence.rateWindow>'
assert_has "schedule passes a met goal into the select plan" $ND/skills/epic-doc/references/schedule.md 'goal_met: true'
assert_has "refresh honours a deferred commit" $ND/skills/epic-doc/references/refresh.md 'COMMIT: deferred'
FMT=$ND/skills/epic-doc/references/format.md
assert_present "the brief template carries a Done when list" "$FMT" 1 "$(total_lines "$FMT")" '^Done when:$'
assert_present "the brief template carries the release ledger" "$FMT" 1 "$(total_lines "$FMT")" '^## Release obligations$'
assert_has "task-breakdown has a re-scope mode" $ND/skills/task-breakdown/SKILL.md '## Re-scope mode'
assert_has "the record stage guide loads the release ledger" \
  $ND/scripts/execution.py '"Release obligations are one ledger"'
assert_has "the reviewer contract charges its own sibling sweep" $ND/scripts/runtime.py 'contract["scope_rules"]'
assert_has "design review reads the project's failure-mode classes" $ND/references/scope.md 'workflow.py failure-modes --config <primary-config>'
assert_has "criterion 3 is measured without generated paths" $ND/references/review-findings.md 'workflow.py changed-lines'
assert_has "intake scans for declared folds" $ND/references/lean-intake.md 'workflow.py fold-scan'
assert_has "approved follow-ups compute their destination from config" \
  $ND/skills/epic-update/references/approved-followup.md '--config <primary-config>`'
assert_has "a spec change writes the re-scope thread" $ND/skills/epic-doc/references/note.md '**Re-scope pending** —'
assert_has "the brief budget follows the retrieve budget" $ND/skills/epic-doc/references/schedule.md '--retrieve-budget <knowledge.retrieveBudget>'
assert_has "the config schema declares the convergence knobs" $ND/schema/notion-dev.config.schema.json '"nonGoalDestination"'
exit $(( fails > 0 ))
