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
  R0=$(find_line "$ED" 1 "$L" '^## `read\(')
  R1=$(find_line "$ED" 1 "$L" '^## `record\(')
  # `read`'s own body ends where `## Bootstrap` begins; Bootstrap legitimately
  # runs `git ls-tree`/`git show` for the seed search, so the "read never
  # touches git directly" checks below must not spill into it.
  RB=$(find_line "$ED" 1 "$L" '^## Bootstrap')
  [ -n "$RB" ] || RB=$R1
  # `refresh` and `## The write path` now sit between `## Bootstrap` and
  # `## \`record(` — the write path legitimately runs `git commit`/`git push`,
  # so the "read never commits/pushes" checks below must end at RF, not R1,
  # or they'd spill into the write path's own commands.
  RF=$(find_line "$ED" 1 "$L" '^## `refresh\(<epic-id>, <reason>\)` — the derived writer$')
  [ -n "$RF" ] || RF=$R1
  # The record region ends where `note` begins (verify-new-info.sh owns that
  # section); without a note heading it runs to end of file as before.
  R2=$(find_line "$ED" 1 "$L" '^## `note\(')
  [ -n "$R2" ] || R2=$L
  if [ -n "$R0" ] && [ -n "$R1" ]; then
    assert_present "read: delegates the fetch to the \`notion-dev:knowledge\` skill, operation \`retrieve(<epic-id>, <ticket-title>?, <current-ticket-id>)\` — the id in the THIRD argument, where the signature puts it" \
      "$ED" "$R0" "$RB" 'notion-dev:knowledge. skill, operation .retrieve\(<epic-id>, <ticket-title>\?, <current-ticket-id>\)'
    assert_present "read: skips the fetch entirely — no fetch of any kind — when the caller supplies \`KNOWLEDGE_CONTEXT\`" \
      "$ED" "$R0" "$RB" 'KNOWLEDGE_CONTEXT. supplied by the caller.*no fetch of any kind'
    assert_absent "read: never runs \`git ls-tree\` itself — that fetch moved to \`retrieve\`" \
      "$ED" "$R0" "$RB" 'git ls-tree'
    assert_absent "read: never runs \`git show\` itself — that fetch moved to \`retrieve\`" \
      "$ED" "$R0" "$RB" 'git show'
    assert_present "the brief's branch is defined once as \`<epicBranch>\`" \
      "$ED" 1 "$R0" '^\*\*Branch\.\*\* The brief lives on .* called `<epicBranch>` below'
    assert_absent "epic-doc never reads \`origin/<git.baseBranch>\` directly" \
      "$ED" 1 "$L" 'origin/<git\.baseBranch>'
    assert_absent "read: never commits" "$ED" "$R0" "$RF" 'git commit'
    assert_absent "read: never pushes"  "$ED" "$R0" "$RF" 'git push'
    assert_present "record: asserts the primary is on the base branch" \
      "$ED" "$R1" "$R2" 'rev-parse --abbrev-ref HEAD'
    assert_present "record: asserts the merge commit is an ancestor" \
      "$ED" "$R1" "$R2" 'merge-base --is-ancestor'
    assert_present "record: asserts the primary equals the remote base" \
      "$ED" "$R1" "$R2" 'rev-parse origin/<baseRefName>'
    assert_present "record: output block states its seven values" \
      "$ED" "$R1" "$R2" '^EPIC-DOC: created \| updated \| closed \| refreshed \| unchanged \| none \| failed'
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
echo "== epic-doc: refresh and the write path (spec 2026-09-15 §2–§3) =="
# ---------------------------------------------------------------------------
if [ -f "$ED" ]; then
  L=$(total_lines "$ED")
  R0=$(find_line "$ED" 1 "$L" '^## `read\(')
  R1=$(find_line "$ED" 1 "$L" '^## `record\(')
  RB=$(find_line "$ED" 1 "$L" '^## Bootstrap')
  [ -n "$RB" ] || RB=$R1
  R2=$(find_line "$ED" 1 "$L" '^## `note\(')
  [ -n "$R2" ] || R2=$L
  # RF (the `refresh` heading) is computed once, above, in the "format owner"
  # block, and reused here — same variable, same meaning.
  RF=$(find_line "$ED" 1 "$L" '^## `refresh\(<epic-id>, <reason>\)` — the derived writer$')
  WP=$(find_line "$ED" 1 "$L" '^## The write path — every commit from the primary checkout$')
  OB=$(find_line "$ED" 1 "$L" '^## Output block$')
  [ -n "$RF" ] && ok "epic-doc defines \`refresh(<epic-id>, <reason>)\`" || bad "epic-doc lacks the refresh heading (L1)"
  [ -n "$WP" ] && ok "epic-doc defines \`## The write path\`" || bad "epic-doc lacks the write path heading (L2)"
  if [ -n "$RF" ] && [ -n "$WP" ] && [ -n "$R0" ] && [ -n "$R1" ]; then
    assert_present "template carries the \`In progress:\` line" "$ED" 1 "$R0" '^In progress: \[STO-72\] Backfill v2 — since 2026-09-15$'
    assert_present "refresh: the four reasons are \`start\`, \`stop\`, \`create\`, \`drift\`" "$ED" "$RF" "$WP" '`start <KEY>-<n>`.*`stop <KEY>-<n> <phase> <cause> <worktree-path>`.*`create <KEY>-<n>`.*`drift`'
    assert_present "refresh: derivation is \`knowledge.py\` \`next\` with \`--brief\`, \`--state\`, \`--today\`" "$ED" "$RF" "$WP" 'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/knowledge.py" next --brief <tmp brief> --state <tmp state.json> --today <YYYY-MM-DD>'
    assert_present "refresh: \`stop\` adds the bullet, \`start\` removes it" "$ED" "$RF" "$WP" '`stop` adds .* `start` removes'
    assert_present "refresh: byte-identical → \`unchanged\`, no commit" "$ED" "$RF" "$WP" 'Byte-identical .* `unchanged`, no commit'
    assert_present "refresh: the state JSON shape names \`status_class\`, \`blocked_by\`, \`thread_blocked\`" "$ED" "$RF" "$WP" '`status_class`.*`blocked_by`.*`thread_blocked`'
    assert_present "refresh: exit-code contract (0 unchanged, 1 differs, 2 malformed)" "$ED" "$RF" "$WP" 'exit 0 = .*exit 1 = .*exit 2 = '
    assert_present "write path step 1: \`lock take\` unless \`LOCK_HELD\`" "$ED" "$WP" "$R1" 'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/knowledge.py" lock take --run <run id> --section <name> --wait <seconds>.*LOCK_HELD'
    assert_present "write path step 2: \`git -C \$REPO_ROOT pull --ff-only origin <epicBranch>\`" "$ED" "$WP" "$R1" 'git -C \$REPO_ROOT pull --ff-only origin <epicBranch>'
    assert_present "write path step 4: \`git push origin <epicBranch>\`" "$ED" "$WP" "$R1" 'git push origin <epicBranch>'
    assert_present "write path step 4: \`git rev-list origin/<epicBranch>..HEAD\` names **exactly one** commit" "$ED" "$WP" "$R1" 'git rev-list origin/<epicBranch>\.\.HEAD. names \*\*exactly one\*\* commit'
    assert_present "write path step 4: \`git -C \$REPO_ROOT reset --hard origin/<epicBranch>\` only after the rev-list proof" "$ED" "$WP" "$R1" 'git -C \$REPO_ROOT reset --hard origin/<epicBranch>'
    # Both halves of the converge reset. Hard, so every path outside the pathspec becomes the
    # fetched tree rather than a staged reversion of it; across a stash, so the exempt setup
    # files the preconditions permit to be dirty are not discarded with this attempt's commit.
    assert_present "write path step 4: the exempt setup files are stashed across the reset" "$ED" "$WP" "$R1" 'git -C \$REPO_ROOT stash push --quiet --'
    assert_present "write path step 4: the stash is popped after the reset" "$ED" "$WP" "$R1" '`git -C \$REPO_ROOT stash pop'
    assert_present "write path step 4: \`Three attempts.\`" "$ED" "$WP" "$R1" 'Three attempts\.'
    assert_present "write path step 5: \`lock release\` unless \`LOCK_HELD\`" "$ED" "$WP" "$R1" 'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/knowledge.py" lock release --run <run id>.*LOCK_HELD'
    assert_order "write path: lock, ff-pull, commit, push, converge, unlock in that order" "$ED" "$WP" "$R1" \
      take 'lock take --run' pull 'git -C \$REPO_ROOT pull --ff-only origin <epicBranch>' commit 'git commit --only' push 'git push origin <epicBranch>' revlist 'git rev-list origin/<epicBranch>\.\.HEAD' stash 'stash push --quiet --' reset 'reset --hard origin/<epicBranch>' release 'lock release --run'
    if [ -n "$OB" ]; then
      assert_present "output block lists \`refreshed\` and \`unchanged\`" "$ED" "$OB" "$L" '^EPIC-DOC: created \| updated \| closed \| refreshed \| unchanged \| none \| failed$'
      assert_present "output block carries \`IN-PROGRESS:\`" "$ED" "$OB" "$L" '^IN-PROGRESS: '
      assert_present "output block carries \`DRIFT:\`" "$ED" "$OB" "$L" '^DRIFT: '
      assert_present "output block carries \`ATTEMPTS:\`" "$ED" "$OB" "$L" '^ATTEMPTS: '
    else
      bad "epic-doc lacks the ## Output block heading"
    fi
    assert_present "read reports \`DRIFT: true\` and writes nothing" "$ED" "$R0" "$RB" 'DRIFT: true.*writes nothing'
    assert_present "read assembles \`thread_blocked\` from \`## Open threads\`" "$ED" "$R0" "$RB" 'thread_blocked.*## Open threads'
    assert_absent "read never takes the lock" "$ED" "$R0" "$RB" 'lock take'
    assert_present "record step 2 recomputes \`## Next\` through \`refresh\`'s derivation" "$ED" "$R1" "$R2" '`## Next` — recompute through `refresh`'
    assert_count "record commits through the write path (cited twice on purpose: the resolution path's step 4, and the bootstrap path's)" \
      "$ED" "$R1" "$R2" 'through `## The write path`' 2
    assert_count "commit subjects: after, bootstrap, note, start, stop, create, refresh (lines citing \`docs(epic):\`)" \
      "$ED" 1 "$L" 'docs\(epic\):' 8
  else
    bad "epic-doc: could not locate the refresh/write-path/read/record operation headings"
  fi
else
  bad "epic-doc skill missing: $ED"
fi

# ---------------------------------------------------------------------------
echo "== config: knowledge.dir =="
# ---------------------------------------------------------------------------
assert_lacks "schema no longer declares \`epicDocs\`" "$SCHEMA" '"epicDocs"'
assert_has "config schema: \`knowledge\` block's dir key defaults to \`knowledge\`" "$SCHEMA" '"default": "knowledge"'

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
  assert_present "ticket.md 1.1 reads the brief via \`notion-dev:knowledge\` \`retrieve(\`" \
    "$TICKET" "$P1" "$P2" 'notion-dev:knowledge. skill, operation .retrieve\(metadata\.parentTaskProperty, <title>, <id>\)'
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
assert_has "ticket-system: getEpicContext superseded by \`notion-dev:knowledge\` \`retrieve\`; only \`notion-dev:epic-doc\`'\''s Notion-source bootstrap still calls it" \
  "$TS" 'superseded by `notion-dev:knowledge` `retrieve` for every context read; only `notion-dev:epic-doc`'\''s Notion-source bootstrap still calls it.'

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
  assert_has "next-task reads the brief via \`retrieve(<epic-id>)\`"      "$NT" 'operation `retrieve(<epic-id>)`'
  assert_has "next-task bootstraps with \`record --bootstrap\`" "$NT" 'operation `record --bootstrap <epic-id>`'
else
  bad "missing: $NT"
fi

# ---------------------------------------------------------------------------
echo "== README and release =="
# ---------------------------------------------------------------------------
assert_has "README documents \`/notion-dev:next-task\`" "$README" '`/notion-dev:next-task'
assert_has "README has the Knowledge bundle section"      "$README" '### Knowledge bundle'
assert_has "README documents \`knowledge.dir\`"           "$README" '`knowledge.dir`'
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
