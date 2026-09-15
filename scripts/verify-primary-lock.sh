#!/usr/bin/env bash
# The primary-checkout lock — every section that commits from the primary checkout or rewrites
# the Notion epic page takes `knowledge.py lock take` and releases it, with the wait spec §4
# assigns; `read` never takes it.
#
# Spec: docs/superpowers/specs/2026-09-15-brief-freshness-and-parallel-tickets-design.md §4, §6
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
TICKET=$ND/commands/ticket.md
FINALIZE=$ND/commands/finalize.md
NT=$ND/commands/next-task.md
NI=$ND/commands/new-info.md
KC=$ND/commands/knowledge.md
CT=$ND/commands/create-task.md
ED=$ND/skills/epic-doc/SKILL.md
KS=$ND/skills/knowledge/SKILL.md

TAKE='knowledge\.py" lock take --run <run id> --section '
REL='knowledge\.py" lock release --run <run id>'

# section <label> <file> <start-ere> <end-ere> <section-word> <wait> [ffpull]
# The optional seventh argument, when non-empty, adds the take-then-checkout-and-pull
# order check (F5): the region must also show the lock taken before the ff-only pull
# that establishes the base, exactly once each.
section() {
  local label=$1 f=$2 s_re=$3 e_re=$4 word=$5 wait=$6 ffpull=${7:-}
  local L; L=$(total_lines "$f")
  local s; s=$(find_line "$f" 1 "$L" "$s_re")
  [ -n "$s" ] || { bad "$label: start anchor not found ($s_re)"; return; }
  local e; e=$(find_line "$f" "$((s + 1))" "$L" "$e_re"); [ -n "$e" ] || e=$L
  assert_present "$label: takes the lock with \`--section $word\` and \`--wait $wait\`" "$f" "$s" "$e" "${TAKE}${word} --wait ${wait}"
  assert_present "$label: releases the lock (\`lock release\`)" "$f" "$s" "$e" "$REL"
  assert_order "$label: take before release" "$f" "$s" "$e" take "${TAKE}${word}" release "$REL"
  if [ -n "$ffpull" ]; then
    assert_order "$label: take, then checkout and \`pull --ff-only\`" "$f" "$s" "$e" \
      take "${TAKE}${word}" pull 'pull --ff-only origin <epicBranch>'
  fi
}

echo "== ticket.md =="
section "ticket Phase 2 start"   "$TICKET" '^## Phase 2 '  '^## Phase 3 '            start  600
section "ticket record section"  "$TICKET" '^### 8\.2 '    '^\*\*Closeout — zero tails' record 3600
section "ticket stop path"       "$TICKET" '^## Failure and stop conditions' '^## [^F]' stop 600
echo "== finalize.md =="
section "finalize record section" "$FINALIZE" '^## Phase 3 ' '^\*\*Closeout — zero tails' record 3600

L=$(total_lines "$TICKET")
P2=$(find_line "$TICKET" 1 "$L" '^## Phase 2 '); P3=$(find_line "$TICKET" 1 "$L" '^## Phase 3 ')
assert_present "ticket Phase 2: \`refresh(<epic-id>, start <key>)\` is invoked" "$TICKET" "$P2" "$P3" 'operation `refresh\(<epic-id>, start <key>\)`'
assert_order "ticket Phase 2: worktree, then status, then refresh start" "$TICKET" "$P2" "$P3" \
  worktree 'git worktree add <worktree-path>' status 'updateStatus\(id, "inProgress"\)' refresh 'operation `refresh\(<epic-id>, start <key>\)`'
FS=$(find_line "$TICKET" 1 "$L" '^## Failure and stop conditions')
assert_present "ticket stop path: \`refresh(<epic-id>, stop <key> <phase> <cause> <worktree-path>)\`" "$TICKET" "$FS" "$L" 'operation `refresh\(<epic-id>, stop <key> <phase> <cause> <worktree-path>\)`'
P82=$(find_line "$TICKET" 1 "$L" '^### 8\.2 '); P10=$(find_line "$TICKET" 1 "$L" '^## Phase 10 ')
assert_present "ticket 8.2: \`epic-update\` runs with \`LOCK_HELD\`" "$TICKET" "$P82" "$P10" 'epic-update.*LOCK_HELD'
assert_present "ticket phase 10: \`record\` runs with \`LOCK_HELD\`" "$TICKET" "$P10" "$L" 'operation `record\(<id>\)`.*LOCK_HELD'
assert_present "ticket phase 9 hooks: hook receives \`LOCK_HELD\`" "$TICKET" "$P82" "$P10" 'hook receives .*LOCK_HELD'
assert_present "ticket report names lock waits" "$TICKET" "$P10" "$L" '^- \*\*Lock waits\*\*'

LF=$(total_lines "$FINALIZE")
F32=$(find_line "$FINALIZE" 1 "$LF" '^### 3\.2 '); F5=$(find_line "$FINALIZE" 1 "$LF" '^## Phase 5 ')
assert_present "finalize 3.2: \`epic-update\` runs with \`LOCK_HELD\`" "$FINALIZE" "$F32" "$F5" 'epic-update.*LOCK_HELD'
assert_present "finalize phase 4 hooks: hook receives \`LOCK_HELD\`" "$FINALIZE" "$F32" "$F5" 'hook receives .*LOCK_HELD'
assert_present "finalize phase 5: \`record\` runs with \`LOCK_HELD\`" "$FINALIZE" "$F5" "$LF" 'operation `record\(<id>\)`.*LOCK_HELD'

echo "== epic-doc read takes nothing =="
LE=$(total_lines "$ED"); R0=$(find_line "$ED" 1 "$LE" '^## `read\('); RB=$(find_line "$ED" 1 "$LE" '^## Bootstrap')
assert_absent "epic-doc read never takes the lock" "$ED" "$R0" "$RB" 'lock take'

echo "== next-task.md =="
section "next-task bootstrap" "$NT" '^\*\*`BOOTSTRAP: true`' '^\*\*`DRIFT: true`' bootstrap 600
section "next-task drift"     "$NT" '^\*\*`DRIFT: true`'     '^### 2\. Pick' drift 600
LN=$(total_lines "$NT"); S1=$(find_line "$NT" 1 "$LN" '^### 1\. Read the brief'); S2=$(find_line "$NT" 1 "$LN" '^### 2\. Pick')
assert_present "next-task step 1: \`refresh(<epic-id>, drift)\` on \`DRIFT: true\`" "$NT" "$S1" "$S2" '`DRIFT: true`.*operation `refresh\(<epic-id>, drift\)`'
assert_present "next-task step 1: splices the refreshed brief into \`KNOWLEDGE_CONTEXT\` — no second retrieve" "$NT" "$S1" "$S2" 'replace the root document of .*KNOWLEDGE_CONTEXT.*no second `retrieve`'
assert_present "next-task step 1: a failed drift refresh stops the loop" "$NT" "$S1" "$S2" 'drift refresh .*`EPIC-DOC: failed` → stop'
echo "== new-info.md =="
section "new-info apply" "$NI" '^### Apply' '^### Notion epic' apply 600 ffpull
LI=$(total_lines "$NI"); A0=$(find_line "$NI" 1 "$LI" '^### Apply'); A1=$(find_line "$NI" 1 "$LI" '^### Notion epic')
assert_present "new-info apply: \`note --apply\` receives \`LOCK_HELD\`" "$NI" "$A0" "$A1" 'operation `note --apply <epic-id>`.*LOCK_HELD'
assert_present "new-info apply: \`capture --fact\` receives \`LOCK_HELD\`" "$NI" "$A0" "$A1" 'operation `capture --fact <fact> <epic-id>`.*LOCK_HELD'
assert_present "new-info apply: \`record --bootstrap\` receives \`LOCK_HELD\`" "$NI" "$A0" "$A1" 'operation `record --bootstrap <epic-id>`.*LOCK_HELD'
echo "== knowledge.md =="
section "knowledge capture" "$KC" '^## `capture <ticket-id> <merge-sha>`$' '^## `migrate`$' capture 600 ffpull
section "knowledge migrate" "$KC" '^## `migrate`$' '^## `curate`$'  migrate 600 ffpull
section "knowledge curate"  "$KC" '^## `curate`$'  '^## Report$'   curate 600 ffpull
echo "== create-task.md =="
section "create-task create" "$CT" '^### 3\.2 ' '^## Phase 4' create 600
LC=$(total_lines "$CT"); C0=$(find_line "$CT" 1 "$LC" '^### 3\.2 '); C1=$(find_line "$CT" 1 "$LC" '^## Phase 4')
assert_present "create-task 3.2: \`refresh(<epic-id>, create <key>)\` after the page has a parent" "$CT" "$C0" "$C1" 'operation `refresh\(<epic-id>, create <key>\)`'
assert_present "create-task 3.2: skipped under \`LOCK_HELD\` (epic-update filing)" "$CT" "$C0" "$C1" 'skip.*invoked with `LOCK_HELD`'
echo "== knowledge skill: capture commits through the write path =="
LK=$(total_lines "$KS")
assert_present "knowledge capture: commits and pushes through \`## The write path\`" "$KS" 1 "$LK" 'through `## The write path`'
assert_absent "knowledge capture: no longer states its own push (\`Then push as\`)" "$KS" 1 "$LK" 'Then push as `epic-doc record` pushes'
echo "== signatures =="
SIG=$ND/skills/issue-log/references/signatures.md; LS=$(total_lines "$SIG")
assert_present "signature \`lock-stale:primary\`"   "$SIG" 1 "$LS" '^\| `lock-stale:primary` \| unexpected \|'
assert_present "signature \`lock-timeout:primary\`" "$SIG" 1 "$LS" '^\| `lock-timeout:primary` \| degraded \|'
assert_present "signature \`partial:epic-doc\` now covers \`refresh\` in \`next-task.md\` and \`create-task.md\`" "$SIG" 1 "$LS" '^\| `partial:epic-doc` \| degraded \| `ticket.md`, `finalize.md`, `next-task.md`, `create-task.md` \|.*refresh'

if [ "$fails" -gt 0 ]; then echo "verify-primary-lock: $fails FAIL"; exit 1; fi
echo "verify-primary-lock: all PASS"
