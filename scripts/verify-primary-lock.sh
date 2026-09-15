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

# section <label> <file> <start-ere> <end-ere> <section-word> <wait>
section() {
  local label=$1 f=$2 s_re=$3 e_re=$4 word=$5 wait=$6
  local L; L=$(total_lines "$f")
  local s; s=$(find_line "$f" 1 "$L" "$s_re")
  [ -n "$s" ] || { bad "$label: start anchor not found ($s_re)"; return; }
  local e; e=$(find_line "$f" "$((s + 1))" "$L" "$e_re"); [ -n "$e" ] || e=$L
  assert_present "$label: takes the lock with \`--section $word\` and \`--wait $wait\`" "$f" "$s" "$e" "${TAKE}${word} --wait ${wait}"
  assert_present "$label: releases the lock (\`lock release\`)" "$f" "$s" "$e" "$REL"
  assert_order "$label: take before release" "$f" "$s" "$e" take "${TAKE}${word}" release "$REL"
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

echo "== epic-doc read takes nothing =="
LE=$(total_lines "$ED"); R0=$(find_line "$ED" 1 "$LE" '^## `read\('); RB=$(find_line "$ED" 1 "$LE" '^## Bootstrap')
assert_absent "epic-doc read never takes the lock" "$ED" "$R0" "$RB" 'lock take'

if [ "$fails" -gt 0 ]; then echo "verify-primary-lock: $fails FAIL"; exit 1; fi
echo "verify-primary-lock: all PASS"
