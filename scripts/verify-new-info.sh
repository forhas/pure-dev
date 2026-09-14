#!/usr/bin/env bash
# /notion-dev:new-info — route one fact to every epic brief it affects.
#
# Spec: docs/superpowers/specs/2026-09-14-new-info-design.md
#
# A fact learned between ticket resolutions ("the customer deployed v1.4.2")
# used to reach the epic briefs only by hand. Now one command judges every
# brief against the fact, applies the change through epic-doc's new `note`
# operation (propose, gate, apply), commits it to the epic branch under the
# same preconditions `record --bootstrap` uses, appends a dated entry to the
# Notion epic's `## Notes`, and comments on the tickets a cleared thread freed.
# It never edits a ticket body and never runs the post-merge hooks.
#
# All of that is prose, and prose reverts by accident. Like verify-epic-doc.sh
# this asserts a standing invariant: no baseline, no version floor beyond the
# one release this change shipped in.
#
# Run from anywhere: ./scripts/verify-new-info.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
NI=$ND/commands/new-info.md
ED=$ND/skills/epic-doc/SKILL.md
TS=$ND/skills/ticket-system/SKILL.md
SIG=$ND/skills/issue-log/references/signatures.md
README=$ND/README.md
MANIFEST=$ND/.claude-plugin/plugin.json

# ---------------------------------------------------------------------------
echo "== new-info.md: command contract =="
# ---------------------------------------------------------------------------
if [ -f "$NI" ]; then
  L=$(total_lines "$NI")
  S0=$(find_line "$NI" 1 "$L" '^## Scope$')
  P0=$(find_line "$NI" 1 "$L" '^## Per epic$')
  PR=$(find_line "$NI" 1 "$L" '^## `--pr`$')
  RP=$(find_line "$NI" 1 "$L" '^## Report$')

  assert_present "new-info.md is user-invoked only (\`disable-model-invocation: true\`)" \
    "$NI" 1 5 '^disable-model-invocation: true'
  assert_has "new-info: \`--epic <id>\` restricts the scope"        "$NI" '`--epic <id>` (repeatable'
  assert_has "new-info: \`--non-interactive\` never pauses"         "$NI" '`--non-interactive`: never pause'
  assert_has "new-info: \`--pr\` lands through one pull request"    "$NI" '`--pr`: land through one pull request'
  assert_has "new-info: the fact is truncated to \`<short fact>\`"  "$NI" 'Derive `<short fact>`'

  if [ -n "$S0" ] && [ -n "$P0" ] && [ -n "$PR" ] && [ -n "$RP" ]; then
    # preconditions
    assert_has "new-info does not require \`dependencies.superpowers\`" \
      "$NI" '`dependencies.superpowers` and `dependencies.featureDev` are **not** required'
    assert_present "preconditions: fast-forward the epic branch before anything (\`pull --ff-only\`)" \
      "$NI" 1 "$S0" 'pull --ff-only origin <epicBranch>'
    assert_present "preconditions: a non-epic id stops the run (\`is not an epic container\`)" \
      "$NI" 1 "$S0" 'is not an epic container'
    # scope
    assert_present "scope: briefs are listed from \`origin/<epicBranch>\`" \
      "$NI" "$S0" "$P0" 'ls-tree -r --name-only origin/<epicBranch> -- <epicDocs.dir>/'
    assert_present "scope: brief-less open epics come from \`findEpics()\`" \
      "$NI" "$S0" "$P0" 'findEpics\(\)'
    assert_present "scope: a closed epic is skipped as \`epic closed\`" \
      "$NI" "$P0" "$PR" 'reason `epic closed`'
    # per epic
    assert_present "per epic: reads through \`epic-doc\` \`read(<epic-id>)\`" \
      "$NI" "$P0" "$PR" 'notion-dev:epic-doc. skill, operation .read\(<epic-id>\)'
    assert_present "per epic: proposes through \`note(<fact>, <epic-id>)\`" \
      "$NI" "$P0" "$PR" 'operation `note\(<fact>, <epic-id>\)`, passing'
    assert_present "per epic: applies through \`note --apply <epic-id>\`" \
      "$NI" "$P0" "$PR" 'operation `note --apply <epic-id>`, passing'
    assert_present "per epic: bootstraps an affected brief-less epic with \`record --bootstrap <epic-id>\`" \
      "$NI" "$P0" "$PR" 'operation `record --bootstrap <epic-id>`, passing'
    assert_present "gate: \`Apply\` / \`Skip\` / \`Revise\`" \
      "$NI" "$P0" "$PR" '\*\*Apply\*\* \(default\), \*\*Skip\*\*, \*\*Revise\*\*'
    assert_present "gate: AC impact offers \`Comment\` / \`Nothing\`, never an edit" \
      "$NI" "$P0" "$PR" '\*\*Comment\*\* \(default\) / \*\*Nothing\*\*'
    assert_present "apply: a byte-identical brief skips the Notion note and the comments" \
      "$NI" "$P0" "$PR" 'a re-run must not append a second Notion note'
    assert_present "apply: a rejected push stops the loop (\`earlier push rejected\`)" \
      "$NI" "$P0" "$PR" 'skipped — earlier push rejected'
    assert_present "notion: appends to the epic's \`Notes\` via \`appendToSection\`" \
      "$NI" "$P0" "$PR" 'appendToSection\(EPIC_ID, "Notes", <entry>\)'
    assert_present "notion: the Resolution Log is never written here" \
      "$NI" "$P0" "$PR" '`## Resolution Log` is never written here'
    assert_present "tickets: comments via \`postComment\`" \
      "$NI" "$P0" "$PR" 'postComment\(<id>, <text>\)'
    assert_has   "tickets: the plugin never edits a ticket body" "$NI" 'never edits a ticket body'
    assert_lacks "new-info never calls \`upsertSection\`"        "$NI" 'upsertSection'
    # --pr
    assert_present "pull-request path: cuts \`<noteBranch>\` from \`origin/<epicBranch>\`" \
      "$NI" "$PR" "$RP" 'checkout -b <noteBranch> origin/<epicBranch>'
    assert_present "pull-request path: ancestry replaces remote equality (\`merge-base --is-ancestor\`)" \
      "$NI" "$PR" "$RP" 'merge-base --is-ancestor origin/<epicBranch> HEAD'
    assert_present "pull-request path: pushes the note branch once (\`git push -u origin <noteBranch>\`)" \
      "$NI" "$PR" "$RP" 'git push -u origin <noteBranch>'
    assert_present "pull-request path: opens the pull request with \`--body-file -\`" \
      "$NI" "$PR" "$RP" 'gh pr create --base <epicBranch> --body-file -'
    assert_present "pull-request path: drives the pull request through \`notion-dev:review-and-merge\`" \
      "$NI" "$PR" "$RP" '`notion-dev:review-and-merge <pr>'
    assert_present "pull-request path: returns to the epic branch with \`pull --ff-only\`" \
      "$NI" "$PR" "$RP" 'pull --ff-only origin <epicBranch>'
    # report
    assert_has_n "new-info names \`postMergeHooks\` exactly once — in the report, never as a step" \
      "$NI" 'postMergeHooks' 1
    assert_present "report: knowledge bundles are \`not touched\`" \
      "$NI" "$RP" "$L" 'knowledge bundle: not touched'
    assert_present "report: ends with the closeout workspace pass" \
      "$NI" "$RP" "$L" 'invoke the \*\*workspace pass\*\* of the .notion-dev:session-closeout'
    assert_present "report: the \`CLOSEOUT:\` block closes the report" \
      "$NI" "$RP" "$L" '`CLOSEOUT:` block verbatim'
    assert_has "new-info cites \`partial:new-info\`" \
      "$NI" 'record `partial:new-info` per `notion-dev:issue-log`'
  else
    bad "new-info.md: could not locate the Scope / Per epic / --pr / Report headings"
  fi
else
  bad "missing: $NI"
fi

# ---------------------------------------------------------------------------
echo "== epic-doc: the note operation =="
# ---------------------------------------------------------------------------
if [ -f "$ED" ]; then
  L=$(total_lines "$ED")
  N0=$(find_line "$ED" 1 "$L" '^## `note\(')
  assert_present "epic-doc description names \`/notion-dev:new-info\`" "$ED" 1 4 'notion-dev:new-info'
  assert_present "epic-doc has the \`note(\` operation heading" "$ED" 1 "$L" '^## `note\('
  if [ -n "$N0" ]; then
    assert_present "note: propose \`Writes nothing\`" "$ED" "$N0" "$L" '^\*\*Writes nothing\.\*\*'
    assert_present "note: the four relevance tests start with \`Clears a thread\`" \
      "$ED" "$N0" "$L" '^1\. \*\*Clears a thread\.\*\*'
    assert_present "note: test 4 is \`Changes what is runnable\`" \
      "$ED" "$N0" "$L" '^4\. \*\*Changes what is runnable\.\*\*'
    assert_present "note: proposal block states \`NOTE: affected | unaffected\`" \
      "$ED" "$N0" "$L" '^NOTE: affected \| unaffected'
    assert_present "note: proposal block carries \`REPLACED:\`" "$ED" "$N0" "$L" '^REPLACED: '
    assert_present "note: proposal block carries \`AC-IMPACT:\`" "$ED" "$N0" "$L" '^AC-IMPACT: '
    assert_present "note: proposal block carries \`DIFF:\`"      "$ED" "$N0" "$L" '^DIFF:'
    assert_present "note: apply returns \`UNBLOCKED:\`"          "$ED" "$N0" "$L" '^UNBLOCKED: '
    assert_present "note: preconditions are \`record --bootstrap\`'s, by reference" \
      "$ED" "$N0" "$L" 'exactly `record --bootstrap`.s precondition block'
    assert_absent "note: never restates record's assertion commands (\`rev-parse --abbrev-ref HEAD\`)" \
      "$ED" "$N0" "$L" 'rev-parse --abbrev-ref HEAD'
    assert_present "note: on the note branch, ancestry replaces remote equality (\`merge-base --is-ancestor\`)" \
      "$ED" "$N0" "$L" 'merge-base --is-ancestor origin/<epicBranch> HEAD'
    assert_present "note: a byte-identical brief commits nothing (\`git diff --cached --quiet\`)" \
      "$ED" "$N0" "$L" 'git diff --cached --quiet -- <brief path>'
    assert_present "note: commits \`docs(epic): note\` by pathspec" \
      "$ED" "$N0" "$L" 'git commit --only -m "docs\(epic\): note <KEY>-<n> — <short fact>" -- <brief path>'
    assert_present "note: a rejected push is never forced" "$ED" "$N0" "$L" 'do not force'
  else
    bad "epic-doc: could not locate the note heading"
  fi
else
  bad "epic-doc skill missing: $ED"
fi

# ---------------------------------------------------------------------------
echo "== ticket-system, issue-log =="
# ---------------------------------------------------------------------------
assert_has "ticket-system palette has the \`Notes\` row written by \`/notion-dev:new-info\`" \
  "$TS" '| `Notes` | `/notion-dev:new-info` |'
assert_has "signature registry has the \`partial:new-info\` row" "$SIG" '| `partial:new-info` |'

# ---------------------------------------------------------------------------
echo "== README and release =="
# ---------------------------------------------------------------------------
assert_has "README documents \`/notion-dev:new-info\`"        "$README" '| `/notion-dev:new-info'
assert_has "README Epic docs has the \`New information\` bullet" "$README" '- **New information.**'
assert_version_above "notion-dev version bumped above the pre-change 0.22.0" "$MANIFEST" 0.22.0

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
  echo
  echo "This harness pins the new-info contract (spec: docs/superpowers/specs/2026-09-14-new-info-design.md)."
  echo "If a failure above is a deliberate change to that contract, change the"
  echo "assertion with it — in the same commit, with the reasoning."
fi
exit $(( fails > 0 ? 1 : 0 ))
