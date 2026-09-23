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
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_handoffs.py'; then
  ok "review freshness and efficient handoffs"
else
  bad "review freshness and efficient handoffs"
fi
assert_has "closeout reuses current evidence" plugins/notion-dev/skills/session-closeout/SKILL.md 'workflow.py verify'
assert_has "new ticket delegates intake" plugins/notion-dev/commands/ticket.md 'references/lean-intake.md'
assert_has "review has code quality and requirements in one seat" plugins/notion-dev/skills/review-and-merge/SKILL.md 'One combined independent internal review'
assert_has "record uses operation planning" plugins/notion-dev/references/record.md 'workflow.py" record-plan'
# The frozen ticket and the merge gate agree with each other whatever upstream now says, so
# without this re-fetch a requirement added during review is merged past in silence. The
# legacy flow carried the rule; the lean rewrite dropped it.
assert_has "merge re-fetches the authoritative ticket, not only PR state" \
  plugins/notion-dev/skills/review-and-merge/SKILL.md 'Re-fetch the authoritative ticket and refresh its source file'
# The legacy copies were moved wholesale and kept their internal links, so every one
# loaded the LEAN contract. That is not a broken link: `prepare` omits `result_contract`
# for schema 1/2 (contract_version is None) while the lean
# protocol tells the worker its `result_contract` is authoritative, so a supported
# resumption dispatched workers against a contract their packet does not contain.
for f in plugins/notion-dev/references/legacy/*.md; do
  assert_lacks "$f loads the legacy runtime contract, never the lean one" "$f" '${CLAUDE_PLUGIN_ROOT}/references/runtime.md'
done
assert_has "the lean contract is schema-gated, so legacy packets carry none" \
  plugins/notion-dev/scripts/runtime.py 'contract_version = RESULT_CONTRACT_VERSION if state["schema"] >= 3 else None'
assert_has "review audits have an explicit contract version" plugins/notion-dev/scripts/runtime.py 'RESULT_CONTRACT_VERSION = 3'
assert_has "recording consumes frozen input" plugins/notion-dev/references/record.md 'record-input'
assert_has "child identity is a published contract" plugins/notion-dev/references/record.md ':child:'
exit $(( fails > 0 ))
