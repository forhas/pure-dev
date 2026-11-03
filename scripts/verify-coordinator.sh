#!/usr/bin/env bash
# /notion-dev:run-epic — the coordinator helper's behaviour, and the command contracts that use it.
#
# The helper is tested against a fake `claude` CLI (scripts/tests/fake_claude.py); the
# behaviour the fake emulates was measured live by scripts/analysis/probe-background-sessions.sh,
# which spends tokens and so is not part of this suite. The assertions below pin the mechanisms
# the command relies on — the helper calls and their order, the refusals — not its prose.
set -uo pipefail
cd "$(dirname "$0")/.."
fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }
. ./scripts/lib/assert.sh
PYBIN=${KNOWLEDGE_PY:-python3}
ND=plugins/notion-dev
RE=$ND/commands/run-epic.md
NT=$ND/commands/next-task.md

echo "== coordinator.py =="
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_coordinator.py'; then
  ok "background sessions, state, outcomes, reports and relays"
else
  bad "background sessions, state, outcomes, reports and relays"
fi

echo "== run-epic.md =="
L=$(total_lines "$RE")
assert_present "run-epic is user-invoked only (\`disable-model-invocation: true\`)" "$RE" 1 5 '^disable-model-invocation: true'
assert_present "run-epic argument hint offers \`--serial\` and \`--non-interactive\`" "$RE" 1 5 '^argument-hint: .*--serial.*--non-interactive'
assert_order "one iteration: start, launch next-task, wait, report-view, judge, retire, finish" "$RE" 1 "$L" \
  start 'coordinator.py" start --project' \
  launch 'coordinator.py" launch --state "\$STATE" --kind next-task' \
  wait 'coordinator.py" wait --state' \
  report-view 'coordinator.py" report-view --report' \
  judge 'coordinator.py" judge --state "\$STATE" --session <session> --verdict <verdict>' \
  retire 'coordinator.py" retire --state' \
  finish 'coordinator.py" finish --state'
assert_has "\`--parallel\` is refused in Part A" "$RE" '`--parallel` stops with "`--parallel` is not'
assert_has "each ticket session is a \`/notion-dev:next-task\` launched \`--non-interactive\`" "$RE" '--prompt "/notion-dev:next-task <epic-id> --non-interactive'
assert_has "the wait runs in the foreground at the Bash tool's 600000 ms timeout" "$RE" "Bash tool's timeout at 600000 ms"
assert_has "a remediation resumes the ticket's own session through \`remediate\`" "$RE" 'coordinator.py" remediate --state "$STATE" --session <session>'
assert_has "an approval reaches the ticket only through \`relay\`" "$RE" 'coordinator.py" relay --state "$STATE" --session <session> --phrase'
assert_has "a \`--non-interactive\` coordinator never relays" "$RE" '`--non-interactive` coordinator never relays'
assert_has "the approval is asked in plain text, not AskUserQuestion" "$RE" 'plain text — not AskUserQuestion'
assert_has "a confirmed fact launches in a fresh session through a quoted heredoc" "$RE" "--kind new-info --parent <session> --prompt \"\$(cat <<'RUN'"
assert_has "the confirmed fact's \`run:\` line runs \`--non-interactive\`" "$RE" '<its run: line, verbatim> --non-interactive'
assert_has "a refusal is exit 2 with an \`error\`, never retried blindly" "$RE" 'Exit 2 is a refusal with an `error`'
assert_has "a coordinator that \`no longer owns\` its run stops at once" "$RE" '`no longer owns` means another session adopted'
assert_has "a \`resume forked\` refusal is retried once after 10 seconds" "$RE" '`resume forked` means the session had not'
assert_has "recording outcomes come from \`record-result.json\`, not the report" "$RE" '`record-result.json` beside its runtime'
assert_has "a declined fact is recorded with \`--fact\`" "$RE" '--verdict declined --fact'
assert_has "the run ends with the \`notion-dev:session-closeout\` workspace pass" "$RE" 'workspace pass of `notion-dev:session-closeout`'
assert_present "run-epic forbids launching with \`claude -p\`" "$RE" 1 "$L" '^with `claude -p`, and never pass'
assert_present "run-epic forbids \`--dangerously-skip-permissions\`" "$RE" 1 "$L" 'never pass a permission-bypass flag \(`--dangerously-skip-permissions`,$'
assert_present "run-epic forbids \`--permission-mode bypassPermissions\`" "$RE" 1 "$L" '^`--permission-mode bypassPermissions`\) to any session'
assert_lacks "run-epic never runs \`claude -p\` itself" "$RE" 'claude -p "'
assert_lacks "run-epic never takes the shared lock" "$RE" 'knowledge.py" lock'
assert_lacks "run-epic never uses AskUserQuestion to ask" "$RE" 'use AskUserQuestion'
assert_lacks "coordinator.py never builds a \`--print\` call" "$ND/scripts/coordinator.py" '"--print"'
assert_lacks "coordinator.py never passes \`--dangerously-skip-permissions\`" "$ND/scripts/coordinator.py" 'dangerously-skip-permissions'

echo "== next-task, ticket, finalize =="
assert_lacks "next-task no longer takes \`--depth=N\`" "$NT" '--depth=N'
assert_has "next-task stops a \`--depth\` caller before any write" "$NT" '`--depth` given → stop before any write'
assert_has "next-task names the replacement \`/notion-dev:run-epic\`" "$NT" 'use `/notion-dev:run-epic <epic>`'
assert_has "next-task saves its report with \`save-report\`" "$NT" 'workflow.py save-report --project . --from -'
assert_has "next-task carries the ticket's \`OUTCOME:\` line and \`NEW-INFO:\` and CLOSEOUT blocks, every line" "$NT" '`OUTCOME:` line, `NEW-INFO:` and CLOSEOUT blocks verbatim, every line'
for f in ticket finalize; do
  assert_has "$f saves its report with \`save-report\`" "$ND/commands/$f.md" 'workflow.py save-report --project "$REPO_ROOT" --from -'
done
assert_has "new-info saves its report with \`save-report\`" "$ND/commands/new-info.md" 'save the finished report with `workflow.py save-report --project "$REPO_ROOT" --from -`'
assert_has "new-info under \`--route\` leaves the ticket's report alone" "$ND/commands/new-info.md" 'Under `--route` the calling ticket run saves its own report'
assert_has "new-info states one \`OUTCOME:\` line for the run" "$ND/commands/new-info.md" "- \`OUTCOME: resolved\` when every epic of every fact reads"
assert_has "run-epic judges a new-info session by its own contract, not §5" "$RE" 'It is not a ticket, so §5 does not apply'
assert_has "ticket may run inside a \`run-epic\` run" "$ND/commands/ticket.md" 'authorized next-task or run-epic run'
assert_has "finalize may run inside a \`run-epic\` run" "$ND/commands/finalize.md" 'authorized ticket/next-task/run-epic run'

echo "== policy paths that admit run-epic =="
assert_has "review-accounting admits a \`run-epic\` relay of the typed phrase" "$ND/references/review-accounting.md" 'other sanctioned path is a `run-epic` relay'
assert_has "new-info: a \`run-epic\` launch on the user's explicit yes" "$ND/commands/new-info.md" "or a \`run-epic\` launch on the user's explicit yes"
assert_has "fact-routing: the other path is a \`run-epic\` launch" "$ND/references/fact-routing.md" 'the other is a `run-epic` launch'
assert_has "README documents \`/notion-dev:run-epic\`" "$ND/README.md" '| `/notion-dev:run-epic <epic-id>` |'
assert_lacks "README no longer offers \`--depth\` on next-task" "$ND/README.md" 'next-task <epic> --depth'

echo
if [ "$fails" -eq 0 ]; then echo "verify-coordinator: all checks passed"; else echo "verify-coordinator: $fails check(s) failed"; fi
[ "$fails" -eq 0 ]
