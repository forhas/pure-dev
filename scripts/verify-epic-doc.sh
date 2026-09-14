#!/usr/bin/env bash
# Epic docs — the per-epic markdown brief and /notion-dev:next-task.
#
# Spec: docs/superpowers/specs/2026-09-13-epic-doc-design.md
#
# A ticket under an epic used to read the Notion epic page for context. Now it
# reads one markdown brief from origin/<base> (skills/epic-doc, `read`), and every
# resolution rewrites that brief and commits it straight to base (`record`) —
# after the draft report is composed, before the closeout workspace pass, under
# the three assertions the post-merge hooks already use. /notion-dev:next-task
# reads the same brief and delegates the recommended ticket to /notion-dev:ticket.
#
# Every one of those is prose, and prose reverts by accident. Like
# verify-post-merge-ordering.sh this asserts a standing invariant: no baseline,
# no version floor beyond the one release this change shipped in.
#
# Run from anywhere: ./scripts/verify-epic-doc.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
ED=$ND/skills/epic-doc/SKILL.md
NT=$ND/commands/next-task.md
TICKET=$ND/commands/ticket.md
FINALIZE=$ND/commands/finalize.md
TS=$ND/skills/ticket-system/SKILL.md
SIG=$ND/skills/issue-log/references/signatures.md
SCHEMA=$ND/schema/notion-dev.config.schema.json
README=$ND/README.md
MANIFEST=$ND/.claude-plugin/plugin.json

# ---------------------------------------------------------------------------
echo "== epic-doc: format owner =="
# ---------------------------------------------------------------------------
if [ -f "$ED" ]; then
  L=$(total_lines "$ED")
  for h in '## Why' '## Goal' '## Where we stand' '## Open threads' '## Decisions & constraints' '## Next'; do
    assert_present "epic-doc template carries the \`$h\` heading" "$ED" 1 "$L" "^${h}\$"
  done
  assert_has "epic-doc names the soft budget" "$ED" '120 lines'
  assert_has "epic-doc read path resolves the file by key, never slug" "$ED" '<KEY>-<n>-*.md'
  assert_has "epic-doc supports \`--bootstrap\`" "$ED" '--bootstrap'
  assert_has "epic-doc removes the seed with \`git rm\`" "$ED" 'git rm'
  assert_count "epic-doc cites the \`docs(epic):\` prefix four times: three commit kinds and the idempotency lookup" \
    "$ED" 1 "$L" 'docs\(epic\):' 4

  R0=$(find_line "$ED" 1 "$L" '^## `read\(')
  R1=$(find_line "$ED" 1 "$L" '^## `record\(')
  # The record region ends where `note` begins (verify-new-info.sh owns that
  # section); without a note heading it runs to end of file as before.
  R2=$(find_line "$ED" 1 "$L" '^## `note\(')
  [ -n "$R2" ] || R2=$L
  if [ -n "$R0" ] && [ -n "$R1" ]; then
    assert_present "read: reads the brief from \`origin/<epicBranch>\`" \
      "$ED" "$R0" "$R1" 'git show origin/<epicBranch>:'
    assert_present "the brief's branch is defined once as \`<epicBranch>\`" \
      "$ED" 1 "$R0" '^\*\*Branch\.\*\* The brief lives on .* called `<epicBranch>` below'
    assert_absent "epic-doc never reads \`origin/<git.baseBranch>\` directly" \
      "$ED" 1 "$L" 'origin/<git\.baseBranch>'
    assert_absent "read: never commits" "$ED" "$R0" "$R1" 'git commit'
    assert_absent "read: never pushes"  "$ED" "$R0" "$R1" 'git push'
    assert_present "record: asserts the primary is on the base branch" \
      "$ED" "$R1" "$R2" 'rev-parse --abbrev-ref HEAD'
    assert_present "record: asserts the merge commit is an ancestor" \
      "$ED" "$R1" "$R2" 'merge-base --is-ancestor'
    assert_present "record: asserts the primary equals the remote base" \
      "$ED" "$R1" "$R2" 'rev-parse origin/<baseRefName>'
    assert_present "record: output block states its five values" \
      "$ED" "$R1" "$R2" '^EPIC-DOC: created \| updated \| closed \| none \| failed'
    assert_present "record: output block carries \`PATH:\`" \
      "$ED" "$R1" "$R2" '^PATH: '
    assert_present "record: output block carries \`SEED:\`" \
      "$ED" "$R1" "$R2" '^SEED: '
    assert_present "record: output block carries \`THREADS:\`" \
      "$ED" "$R1" "$R2" '^THREADS: '
    assert_present "record: output block carries \`NEXT:\`" \
      "$ED" "$R1" "$R2" '^NEXT: '
    assert_present "record: output block carries \`CAUSE:\`" \
      "$ED" "$R1" "$R2" '^CAUSE: '
    assert_present "record: a rejected push is never forced" \
      "$ED" "$R1" "$R2" 'do not force'
  else
    bad "epic-doc: could not locate the read/record operation headings"
  fi
else
  bad "epic-doc skill missing: $ED"
fi

# ---------------------------------------------------------------------------
echo "== config: epicDocs.dir =="
# ---------------------------------------------------------------------------
assert_has "schema declares \`epicDocs\`" "$SCHEMA" '"epicDocs"'
assert_has "schema defaults the dir to \`docs/epics\`" "$SCHEMA" '"default": "docs/epics"'

# ---------------------------------------------------------------------------
echo "== ticket.md =="
# ---------------------------------------------------------------------------
if [ -f "$TICKET" ]; then
  L=$(total_lines "$TICKET")
  P1=$(find_line "$TICKET" 1 "$L" '^## Phase 1 ')
  P2=$(find_line "$TICKET" 1 "$L" '^## Phase 2 ')
  P10=$(find_line "$TICKET" 1 "$L" '^## Phase 10 ')
  PF=$(find_line "$TICKET" 1 "$L" '^## Failure and stop conditions')

  assert_absent "ticket.md frontmatter no longer disables model invocation" \
    "$TICKET" 1 5 '^disable-model-invocation:'
  assert_present "ticket.md carries the invocation guard" \
    "$TICKET" 1 "$P1" '^\*\*Invocation guard\.\*\*'
  assert_present "ticket.md 1.1 reads the brief via \`epic-doc\` \`read(\`" \
    "$TICKET" "$P1" "$P2" 'notion-dev:epic-doc. skill, operation .read\(metadata\.parentTaskProperty, <id>\)'
  assert_lacks "ticket.md no longer calls getEpicContext" "$TICKET" 'getEpicContext('
  assert_present "ticket.md records after the draft, before the closeout" \
    "$TICKET" "$P10" "$PF" '^\*\*Epic doc — record the resolution\.\*\*'
  assert_order "ticket Phase 10 order: \`record\` before the workspace pass before the summary" \
    "$TICKET" "$P10" "$PF" \
    "record"   'notion-dev:epic-doc. skill, operation .record\(<id>\)' \
    "closeout" 'invoke the \*\*workspace pass\*\* of the .notion-dev:session-closeout' \
    "summary"  '^Print a summary covering:'
  assert_present "ticket.md cites \`partial:epic-doc\`" \
    "$TICKET" "$P10" "$PF" 'record `partial:epic-doc` per `notion-dev:issue-log`'
  assert_present "ticket.md reports the epic doc line" \
    "$TICKET" "$P10" "$PF" '^- \*\*Epic doc\*\*'
  assert_count "ticket.md still invokes epic-update exactly once" \
    "$TICKET" 1 "$L" 'Invoke the `notion-dev:epic-update` skill' 1
else
  bad "missing: $TICKET"
fi

# ---------------------------------------------------------------------------
echo "== finalize.md =="
# ---------------------------------------------------------------------------
if [ -f "$FINALIZE" ]; then
  L=$(total_lines "$FINALIZE")
  P5=$(find_line "$FINALIZE" 1 "$L" '^## Phase 5 ')
  PF=$(find_line "$FINALIZE" 1 "$L" '^## Failure and stop conditions')
  assert_present "finalize.md keeps \`disable-model-invocation: true\`" \
    "$FINALIZE" 1 5 '^disable-model-invocation: true'
  assert_present "finalize.md records after the draft, before the closeout" \
    "$FINALIZE" "$P5" "$PF" '^\*\*Epic doc — record the resolution\.\*\*'
  assert_order "finalize Phase 5 order: \`record\` before the workspace pass before the summary" \
    "$FINALIZE" "$P5" "$PF" \
    "record"   'notion-dev:epic-doc. skill, operation .record\(<id>\)' \
    "closeout" 'invoke the \*\*workspace pass\*\* of the .notion-dev:session-closeout' \
    "summary"  '^Print a summary covering:'
  assert_present "finalize.md cites \`partial:epic-doc\`" \
    "$FINALIZE" "$P5" "$PF" 'record `partial:epic-doc` per `notion-dev:issue-log`'
  assert_present "finalize.md reports the epic doc line" \
    "$FINALIZE" "$P5" "$PF" '^- \*\*Epic doc\*\*'
  assert_count "finalize.md still invokes epic-update exactly once" \
    "$FINALIZE" 1 "$L" 'Invoke the `notion-dev:epic-update` skill' 1
else
  bad "missing: $FINALIZE"
fi

# ---------------------------------------------------------------------------
echo "== ticket-system: getEpicContext kept as the bootstrap source =="
# ---------------------------------------------------------------------------
assert_has "ticket-system still defines \`## getEpicContext(\`" "$TS" '## getEpicContext('
assert_has "ticket-system: getEpicContext is the bootstrap source for \`notion-dev:epic-doc\`" \
  "$TS" 'bootstrap source for `notion-dev:epic-doc`'

# ---------------------------------------------------------------------------
echo "== issue-log: partial:epic-doc =="
# ---------------------------------------------------------------------------
assert_has "signature registry has the \`partial:epic-doc\` row" "$SIG" '| `partial:epic-doc` |'

# ---------------------------------------------------------------------------
echo "== next-task.md =="
# ---------------------------------------------------------------------------
if [ -f "$NT" ]; then
  assert_present "next-task.md is user-invoked only (\`disable-model-invocation: true\`)" \
    "$NT" 1 5 '^disable-model-invocation: true'
  assert_has "next-task: \`--depth\` defaults to 1"           "$NT" '`--depth` absent → 1'
  assert_has "next-task: depth accepts \`all\`"          "$NT" '`all` → unbounded'
  assert_has "next-task: the epic guard is inverted"           "$NT" 'not an epic → abort'
  assert_has "next-task delegates to \`/notion-dev:ticket\`"   "$NT" 'invoke `/notion-dev:ticket <key>'
  assert_has "next-task stops early on a failed run"           "$NT" '**Stop early**'
  assert_has "next-task reads the brief via \`read(<epic-id>)\`"      "$NT" 'operation `read(<epic-id>)`'
  assert_has "next-task bootstraps with \`record --bootstrap\`" "$NT" 'operation `record --bootstrap <epic-id>`'
else
  bad "missing: $NT"
fi

# ---------------------------------------------------------------------------
echo "== README and release =="
# ---------------------------------------------------------------------------
assert_has "README documents \`/notion-dev:next-task\`" "$README" '`/notion-dev:next-task'
assert_has "README has the Epic docs section"            "$README" '### Epic docs'
assert_has "README documents \`epicDocs.dir\`"          "$README" '`epicDocs.dir`'
assert_has "README tree lists epic-doc"                  "$README" 'epic-doc/'
assert_version_above "notion-dev version bumped above the pre-change 0.21.2" "$MANIFEST" 0.21.2

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
  echo
  echo "This harness pins the epic-doc contract (spec: docs/superpowers/specs/2026-09-13-epic-doc-design.md)."
  echo "If a failure above is a deliberate change to that contract, change the"
  echo "assertion with it — in the same commit, with the reasoning."
fi
exit $(( fails > 0 ? 1 : 0 ))
