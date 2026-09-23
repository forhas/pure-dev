#!/usr/bin/env bash
# Historical contracts below cover opt-in legacy flows; verify-lean-workflow.sh covers the new default.
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
. ./scripts/lib/instruction-view.sh

ND=plugins/notion-dev
TICKET=$ND/references/legacy/ticket.md
RECORD=$ND/references/legacy/record.md
FINALIZE=$ND/references/legacy/finalize.md
NT=$ND/references/legacy/next-task.md
NI=$ND/commands/new-info.md
KC=$ND/commands/knowledge.md
CT=$ND/commands/create-task.md
ED=$(instruction_view epic-doc)
KS=$(instruction_view knowledge)

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
# Task 9 folded the `### 8.2` heading into flowing Phase 8 dispatch prose (nothing
# under it literally "updates the epic" any more — that now happens inside the
# dispatched unit), so this section starts at the phase heading instead.
section "ticket record section"  "$TICKET" '^## Phase 8 '  '^\*\*Closeout — zero tails' record 3600
section "ticket stop path"       "$TICKET" '^## Failure and stop conditions' '^## [^F]' stop 600
echo "== finalize.md =="
section "finalize record section" "$FINALIZE" '^## Phase 3 ' '^\*\*Closeout — zero tails' record 3600

L=$(total_lines "$TICKET")
P2=$(find_line "$TICKET" 1 "$L" '^## Phase 2 '); P3=$(find_line "$TICKET" 1 "$L" '^## Phase 3 ')
assert_present "ticket Phase 2: \`refresh(<epic-id>, start <key>)\` is invoked" "$TICKET" "$P2" "$P3" 'operation `refresh\(<epic-id>, start <key>\)`'
# refresh has no missing-brief path, so the start section must not run when Phase 1.1 said
# the brief does not exist yet — Phase 10's record is what creates it.
assert_present "ticket Phase 2: the start section is skipped on BOOTSTRAP: true" "$TICKET" "$P2" "$P3" \
  'start` section.*and Phase 1\.1.*did not report.*`BOOTSTRAP: true`'
assert_order "ticket Phase 2: worktree, then status, then refresh start" "$TICKET" "$P2" "$P3" \
  worktree 'git worktree add <worktree-path>' status 'updateStatus\(id, "inProgress"\)' refresh 'operation `refresh\(<epic-id>, start <key>\)`'
FS=$(find_line "$TICKET" 1 "$L" '^## Failure and stop conditions')
assert_present "ticket stop path: \`refresh(<epic-id>, stop <key> <phase> <cause> <worktree-path>)\`" "$TICKET" "$FS" "$L" 'operation `refresh\(<epic-id>, stop <key> <phase> <cause> <worktree-path>\)`'
P10=$(find_line "$TICKET" 1 "$L" '^## Phase 10 ')
LR=$(total_lines "$RECORD")
# The epic-update invocation, the epic-doc `record` invocation and the post-merge hook
# paragraph all moved into references/record.md with the rest of Phase 8-10's record unit
# (Task 8); `ticket.md` itself no longer carries any of the three LOCK_HELD grants.
assert_present "record.md: \`epic-update\` runs with \`LOCK_HELD\`" "$RECORD" 1 "$LR" 'epic-update.*LOCK_HELD'
assert_present "record.md: \`record\` runs with \`LOCK_HELD\`" "$RECORD" 1 "$LR" 'operation `record\(<id>\)`.*LOCK_HELD'
assert_present "record.md: hook receives \`LOCK_HELD\`" "$RECORD" 1 "$LR" 'hook receives .*LOCK_HELD'
assert_present "ticket report names lock waits" "$TICKET" "$P10" "$L" '^- \*\*Lock waits\*\*'

# The record sections span epic-update, whose interactive filing gate asks File/Drop. The lock
# goes stale in 60 minutes, so those answers are taken before the take, never under it.
#
# Task 9: `epic-update` is no longer invoked directly from ticket.md (it moved into the
# dispatched references/record.md, per Task 8), so the filing gate here only carries its
# answers forward as `FILING_DECISIONS` for that later dispatch — it no longer "passes
# into the invocation below", since there is no invocation below any more.
TR0=$(find_line "$TICKET" 1 "$L" '^## Phase 8 ')
TR1=$(find_line "$TICKET" "$((TR0 + 1))" "$L" '^\*\*Closeout — zero tails'); [ -n "$TR1" ] || TR1=$L
assert_order "ticket record section: the filing gate is resolved before the lock take" "$TICKET" "$TR0" "$TR1" \
  AskUserQuestion 'filing gate before the lock is taken.*`AskUserQuestion`' take "${TAKE}record"
assert_present "ticket record section: the answers carry forward as FILING_DECISIONS" "$TICKET" "$TR0" "$TR1" \
  'carry the answers forward as .FILING_DECISIONS.'

LF=$(total_lines "$FINALIZE")
F32=$(find_line "$FINALIZE" 1 "$LF" '^### 3\.2 '); F5=$(find_line "$FINALIZE" 1 "$LF" '^## Phase 5 ')
assert_present "finalize 3.2: \`epic-update\` runs with \`LOCK_HELD\`" "$FINALIZE" "$F32" "$F5" 'epic-update.*LOCK_HELD'
assert_present "finalize phase 4 hooks: hook receives \`LOCK_HELD\`" "$FINALIZE" "$F32" "$F5" 'hook receives .*LOCK_HELD'
assert_present "finalize phase 5: \`record\` runs with \`LOCK_HELD\`" "$FINALIZE" "$F5" "$LF" 'operation `record\(<id>\)`.*LOCK_HELD'
FR0=$(find_line "$FINALIZE" 1 "$LF" '^## Phase 3 ')
FR1=$(find_line "$FINALIZE" "$((FR0 + 1))" "$LF" '^\*\*Closeout — zero tails'); [ -n "$FR1" ] || FR1=$LF
assert_order "finalize record section: the filing gate is resolved before the lock take" "$FINALIZE" "$FR0" "$FR1" \
  AskUserQuestion 'filing gate before the lock is taken.*`AskUserQuestion`' take "${TAKE}record"
assert_present "finalize record section: the answers reach epic-update as FILING_DECISIONS" "$FINALIZE" "$FR0" "$FR1" \
  'pass the result into the invocation below as.*FILING_DECISIONS'
echo "== epic-update: the gate is silent under the lock =="
EU=$ND/skills/epic-update/references/with-followups.md; LEU=$(total_lines "$EU")
assert_present "epic-update: FILING_DECISIONS in context means the gate asks nothing" "$EU" 1 "$LEU" \
  'With `FILING_DECISIONS` in context this gate asks nothing'

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
# The drift path must stop on a timed-out take, as the bootstrap path does: without it the
# run hands LOCK_HELD to a write path that holds nothing and races the real holder.
assert_present "next-task drift: a timed-out lock take stops with the CAUSE line" "$NT" "$S1" "$S2" \
  'lock take --run <run id> --section drift --wait 600. \(exit 1 → stop with .CAUSE: primary lock held by'
echo "== new-info.md =="
section "new-info apply" "$NI" '^### Apply' '^### Notion epic' apply 600 ffpull
LI=$(total_lines "$NI"); A0=$(find_line "$NI" 1 "$LI" '^### Apply'); A1=$(find_line "$NI" 1 "$LI" '^### Notion epic')
# The lock is released between epics, so a later Apply must not assume the primary is still
# on the branch the previous epic left it on — an intervening locked writer may check out
# <epicBranch>, and note --apply then fails its HEAD-branch assertion.
assert_present "new-info apply: a later epic checks the branch out again after its take" "$NI" "$A0" "$A1" \
  'On a later epic, check the branch out again rather than assuming it survived'
assert_present "new-info apply: the later-epic checkout is \`checkout <noteBranch>\`, never \`checkout -b\`" "$NI" "$A0" "$A1" \
  'git -C \$REPO_ROOT checkout <noteBranch>` under `--pr`.*`checkout`, never `checkout -b`'
assert_present "new-info apply: \`note --apply\` receives \`LOCK_HELD\`" "$NI" "$A0" "$A1" 'operation `note --apply <epic-id>`.*LOCK_HELD'
assert_present "new-info apply: \`capture --fact\` receives \`LOCK_HELD\`" "$NI" "$A0" "$A1" 'operation `capture --fact <fact> <epic-id>`.*LOCK_HELD'
assert_present "new-info apply: \`record --bootstrap\` receives \`LOCK_HELD\`" "$NI" "$A0" "$A1" 'operation `record --bootstrap <epic-id>`.*LOCK_HELD'
echo "== knowledge.md =="
section "knowledge capture" "$KC" '^## `capture <ticket-id> <merge-sha>`$' '^## `migrate`$' capture 600 ffpull
section "knowledge migrate" "$KC" '^## `migrate`$' '^## `curate`$'  migrate 600 ffpull
section "knowledge curate"  "$KC" '^## `curate`$'  '^## Report$'   curate 600 ffpull
# No interactive gate is ever held under the primary lock: the lock goes stale in 60 minutes,
# so questions answered under it are a live lock another run breaks while this one still writes.
LKC=$(total_lines "$KC"); CU0=$(find_line "$KC" 1 "$LKC" '^## `curate`$')
CU1=$(find_line "$KC" "$((CU0 + 1))" "$LKC" '^## Report$'); [ -n "$CU1" ] || CU1=$LKC
assert_order "knowledge curate: \`AskUserQuestion\` comes before the lock take" "$KC" "$CU0" "$CU1" \
  AskUserQuestion 'put it to the user with `AskUserQuestion`' take "${TAKE}curate"
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
