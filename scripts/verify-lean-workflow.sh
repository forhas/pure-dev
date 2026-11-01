#!/usr/bin/env bash
# The current default: executable contracts, not archived prompt wording.
set -uo pipefail
cd "$(dirname "$0")/.."
fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }
. ./scripts/lib/assert.sh
PYBIN=${KNOWLEDGE_PY:-python3}
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_execution.py'; then
  ok "portable execution, ready-result consumption and correction preflight"
else
  bad "portable execution, ready-result consumption and correction preflight"
fi
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_lifecycle.py'; then
  ok "scoped lifecycle retrieval, handoffs, typed inputs and approved recording"
else
  bad "scoped lifecycle retrieval, handoffs, typed inputs and approved recording"
fi
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
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_boundaries.py'; then
  ok "host capture, scoped recording and compact deltas"
else
  bad "host capture, scoped recording and compact deltas"
fi
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_review_repair.py'; then
  ok "lossless findings, mandatory/advisory gates and authorized bounded recovery"
else
  bad "lossless findings, mandatory/advisory gates and authorized bounded recovery"
fi
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_scoped_execution.py'; then
  ok "scoped delta inputs, publication and deterministic ticket recording"
else
  bad "scoped delta inputs, publication and deterministic ticket recording"
fi
assert_has "new ticket delegates intake" plugins/notion-dev/commands/ticket.md 'references/lean-intake.md'
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_convergence.py'; then
  ok "immutable verification, landed-effect reconciliation and progressive scheduling"
else
  bad "immutable verification, landed-effect reconciliation and progressive scheduling"
fi
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
  plugins/notion-dev/scripts/runtime.py '(3 if state["schema"] >= 3 else None)'
assert_has "review audits have an explicit contract version" plugins/notion-dev/scripts/runtime.py 'RESULT_CONTRACT_VERSION = 5'
assert_has "recording consumes frozen input" plugins/notion-dev/references/record.md 'record-input'
assert_has "child identity is a published contract" plugins/notion-dev/references/record.md ':child:'

# Session placement (0.51.0): a session enters its worktree after the claim's primary writes
# and leaves it before anything writes the primary again; removal happens only from outside.
LI=plugins/notion-dev/references/lean-intake.md
LIL=$(total_lines "$LI")
SP=$(find_line "$LI" 1 "$LIL" '^## Session placement')
SB=$(find_line "$LI" 1 "$LIL" '^## Boundaries and stop')
assert_order "placement: claim, then the start brief, then EnterWorktree on \`path: \"\$WORKTREE\"\`" "$LI" 1 "$SB" \
  claim 'workflow.py" claim --project' \
  brief 'refresh its start brief under the existing `knowledge.py lock` start section' \
  enter '`EnterWorktree` with `path: "\$WORKTREE"`'
assert_present "placement: fallback when \`EnterWorktree\` is unavailable keeps \`cd \"\$WORKTREE\" &&\`" "$LI" "$SP" "$SB" '^`EnterWorktree` unavailable or refused.*`cd "\$WORKTREE" &&`'
assert_order "placement: leave with \`ExitWorktree\` and \`action: \"keep\"\`, before \`references/record.md\` and a stop" "$LI" "$SP" "$SB" \
  leave 'with `ExitWorktree` and `action: "keep"`:$' \
  record '^before `references/record.md` and before a stop writes the brief'
assert_present "placement: never \`remove\`; cleanup uses \`workflow.py remove-worktree\`" "$LI" "$SP" "$SB" '^Never `remove`: cleanup deletes it with `workflow.py remove-worktree`'
assert_present "placement: a session launched inside runs cleanup from \`\$REPO_ROOT\`" "$LI" "$SP" "$SB" 'cd "\$REPO_ROOT" && python3 \.\.\. remove-worktree'
assert_present "preflight: dirt cleared in the primary runs inside \`knowledge.py lock take --section preflight\`" "$LI" 1 "$SP" '`knowledge.py lock take --section preflight`'
T=plugins/notion-dev/commands/ticket.md
TL=$(total_lines "$T")
assert_order "ticket: \`ExitWorktree\` precedes reading \`references/record.md\`" "$T" 1 "$TL" \
  exit '^After confirmed merge, `ExitWorktree` keep' \
  record 'then read `\$\{CLAUDE_PLUGIN_ROOT\}/references/record.md`'
assert_present "ticket: a failure stop runs \`ExitWorktree\` keep" "$T" 1 "$TL" '^On failure preserve.*; `ExitWorktree` keep\.'
F=plugins/notion-dev/commands/finalize.md
FL=$(total_lines "$F")
assert_order "finalize: enter the PR worktree, then \`ExitWorktree\` before \`references/record.md\`" "$F" 1 "$FL" \
  enter "HEAD; enter it\$" \
  exit '^6\. Either way `ExitWorktree` keep' \
  record 'then read `references/record.md` and run that exact'
R=plugins/notion-dev/references/record.md
assert_present "record cleanup: \`workflow.py remove-worktree --project \"\$REPO_ROOT\" --worktree \"\$WORKTREE\"\`" "$R" 1 "$(total_lines "$R")" '`workflow.py remove-worktree --project "\$REPO_ROOT" --worktree "\$WORKTREE"`'
assert_has "remove-worktree refuses from inside the worktree" plugins/notion-dev/scripts/workflow.py 'this session is inside the worktree it is removing'
assert_has "remove-worktree never forces" plugins/notion-dev/scripts/workflow.py 'git(root, "worktree", "remove", str(target))'
exit $(( fails > 0 ))
