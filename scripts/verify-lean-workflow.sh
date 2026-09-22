#!/usr/bin/env bash
# The current default: executable contracts, not archived prompt wording.
set -uo pipefail
cd "$(dirname "$0")/.."
fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }
. ./scripts/lib/assert.sh
PYBIN=${KNOWLEDGE_PY:-python3}
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_lean_workflow.py'; then
  ok "lean runtime, workflow, recording and routing regressions"
else
  bad "lean runtime, workflow, recording and routing regressions"
fi
assert_has "closeout reuses current evidence" plugins/notion-dev/skills/session-closeout/SKILL.md 'workflow.py verify'
assert_has "new ticket delegates intake" plugins/notion-dev/commands/ticket.md 'references/lean-intake.md'
assert_has "review has code quality and requirements in one seat" plugins/notion-dev/skills/review-and-merge/SKILL.md 'One combined independent internal review'
assert_has "record uses operation planning" plugins/notion-dev/references/record.md 'workflow.py" record-plan'
exit $(( fails > 0 ))
