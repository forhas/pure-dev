#!/usr/bin/env bash
# Parallel ticket picking — the run marker, ownership check, marker resume
# rules, and `claimed-elsewhere`, plus (Tasks 3-5) next-task validity and the
# `new-info --pr` epic-branch rebase.
#
# Spec: docs/superpowers/specs/2026-09-15-brief-freshness-and-parallel-tickets-design.md §7, §8
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
TICKET=$ND/commands/ticket.md
NT=$ND/commands/next-task.md
SIG=$ND/skills/issue-log/references/signatures.md
L=$(total_lines "$TICKET")
P11=$(find_line "$TICKET" 1 "$L" '^### 1\.1 '); P12=$(find_line "$TICKET" 1 "$L" '^### 1\.2 '); P13=$(find_line "$TICKET" 1 "$L" '^### 1\.3 ')
P21=$(find_line "$TICKET" 1 "$L" '^### 2\.1 '); P3=$(find_line "$TICKET" 1 "$L" '^## Phase 3 ')
P7=$(find_line "$TICKET" 1 "$L" '^## Phase 7 '); P8=$(find_line "$TICKET" 1 "$L" '^## Phase 8 ')
P9=$(find_line "$TICKET" 1 "$L" '^## Phase 9 '); P9H=$(find_line "$TICKET" 1 "$L" '^### Post-merge hooks')
P10=$(find_line "$TICKET" 1 "$L" '^## Phase 10 '); FS=$(find_line "$TICKET" 1 "$L" '^## Failure and stop conditions')
echo "== ticket.md: claim, marker, ownership =="
assert_present "1.1 ownership check: in progress with no worktree of ours aborts \`held elsewhere\`" "$TICKET" "$P11" "$P12" 'is In Progress and has no worktree here — held elsewhere'
assert_present "1.1 ownership check: non-interactive never proceeds" "$TICKET" "$P11" "$P12" 'held elsewhere.*non-interactive mode never proceeds'
assert_present "1.2 resume: a \`running\` marker with a fresh heartbeat aborts \`held by a live session\`" "$TICKET" "$P12" "$P13" '"state": "running".*held by a live session — <phase> since <heartbeat>'
assert_present "1.2 resume: \`stopped\`, a heartbeat older than 2 hours, or no marker resumes" "$TICKET" "$P12" "$P13" '`stopped`.*older than 2 hours.*no marker.*resume'
assert_present "1.2 resume: non-interactive never takes over" "$TICKET" "$P12" "$P13" 'non-interactive never takes over'
assert_present "2.1 claim: the marker path" "$TICKET" "$P21" "$P3" '\$REPO_ROOT/\.claude/notion-dev/runs/<KEY>-<id>\.json'
assert_present "2.1 claim: the marker is written with \`\"state\": \"running\"\`" "$TICKET" "$P21" "$P3" '"state": "running"'
assert_present "2.1 claim: a lost race ends with \`OUTCOME: claimed-elsewhere\` before any status change" "$TICKET" "$P21" "$P3" 'OUTCOME: claimed-elsewhere.*before'
assert_order "2.1: worktree add, then marker, then status, then refresh start" "$TICKET" "$P21" "$P3" \
  worktree 'git worktree add <worktree-path>' marker '"state": "running"' status 'updateStatus\(id, "inProgress"\)' refresh 'operation `refresh\(<epic-id>, start <key>\)`'
assert_present "marker discipline: heartbeat at every phase boundary and every review round" "$TICKET" "$P21" "$P3" 'heartbeat.*every phase boundary and every review round'
assert_present "phase 7: the marker is touched after every reviewer round" "$TICKET" "$P7" "$P8" 'touch the marker.*after every reviewer round'
assert_present "phase 9 step 1: the marker is deleted right after the worktree is removed" "$TICKET" "$P9" "$P9H" 'rm -f "\$REPO_ROOT/\.claude/notion-dev/runs/<KEY>-<id>\.json"'
assert_order "phase 9: worktree removed, then marker deleted" "$TICKET" "$P9" "$P9H" remove 'git worktree remove <worktree-path>' marker 'rm -f "\$REPO_ROOT/\.claude/notion-dev/runs/<KEY>-<id>\.json"'
assert_present "stop path: the marker is set to \`\"state\": \"stopped\"\` with the cause" "$TICKET" "$FS" "$L" '"state": "stopped".*cause'
# The rewrite lives in the unconditional "On any unrecoverable failure" bullet, not the
# epic-only `stop` section below it — no bullet boundary separates the two in the file, so
# a region tightened to "next `^- ` bullet" would still swallow the epic-only text. Proving
# the order instead pins that the unconditional rewrite is not accidentally the epic-only one.
assert_order "stop path: the unconditional \`stopped\` rewrite precedes the epic-only \`refresh\` stop call" "$TICKET" "$FS" "$L" \
  stopped '"state": "stopped".*cause' refresh 'operation `refresh\(<epic-id>, stop <key> <phase> <cause> <worktree-path>\)`'
assert_present "phase 10 report: the marker outcome line" "$TICKET" "$P10" "$FS" '^- \*\*Run marker\*\*'
LS=$(total_lines "$SIG")
assert_absent "signatures: claimed-elsewhere is a run outcome, never a signature row" "$SIG" 1 "$LS" '^\| `claimed-elsewhere` \|'

echo "== next-task.md: lost claims and the marker =="
LN=$(total_lines "$NT"); S2=$(find_line "$NT" 1 "$LN" '^### 2\. Pick'); S3=$(find_line "$NT" 1 "$LN" '^### 3\. Delegate'); S4=$(find_line "$NT" 1 "$LN" '^### 4\. After the run'); SR=$(find_line "$NT" 1 "$LN" '^## Report')
assert_present "step 2: an in-progress child with a \`running\` marker is never a candidate" "$NT" "$S2" "$S3" '`running` marker.*never a'
assert_present "step 2: resume first reads the marker (\`stopped\` or none)" "$NT" "$S2" "$S3" 'Resume first.*marker.*`stopped`'
assert_present "step 4: \`claimed-elsewhere\` is neither a stop nor a resolution" "$NT" "$S4" "$SR" 'claimed-elsewhere.*neither a stop nor a resolution'
assert_present "step 4: on \`claimed-elsewhere\` DONE is not incremented and the next candidate is picked from the same NEXT" "$NT" "$S4" "$SR" 'claimed-elsewhere.*DONE.*same `NEXT`'

echo "== review-and-merge: rebase at the gate (both copies) =="
for f in plugins/quick-dev/skills/review-and-merge/SKILL.md plugins/notion-dev/skills/review-and-merge/SKILL.md; do
  n=$(total_lines "$f"); M5=$(find_line "$f" 1 "$n" '^## 5\. Merge'); SR=$(find_line "$f" "$M5" "$n" '^## Safety rules')
  assert_present "$f: reads \`mergeStateStatus\` at the gate" "$f" "$M5" "$SR" 'gh pr view <pr> --json mergeStateStatus'
  assert_present "$f: \`BEHIND\` or \`DIRTY\` → \`git rebase origin/<base>\` in the worktree" "$f" "$M5" "$SR" '`BEHIND`.*`DIRTY`.*git rebase origin/<base>'
  assert_present "$f: re-run verify, then \`git push --force-with-lease\`" "$f" "$M5" "$SR" 'verify.*git push --force-with-lease'
  assert_present "$f: a clean rebase triggers no new review round" "$f" "$M5" "$SR" 'clean rebase.*no new review round'
  assert_present "$f: \`.claude-plugin/plugin.json\` version conflict: take the base's value and re-apply the bump class" "$f" "$M5" "$SR" '\.claude-plugin/plugin\.json.*take the base.s value.*bump class'
  assert_present "$f: bump class recorded before the rebase (merge-base vs head)" "$f" "$M5" "$SR" 'bump class.*merge-base'
  assert_present "$f: any other conflict → \`git rebase --abort\` and the unmergeable stop" "$f" "$M5" "$SR" 'git rebase --abort.*unmergeable'
  assert_present "$f: rebase once, at the gate, never per round" "$f" "$M5" "$SR" 'once, at the gate, never per'
  assert_present "$f: the bump class is recorded before rebasing" "$f" "$M5" "$SR" 'before rebasing.*record the bump class'
  assert_present "$f: the strictly-greater re-check is unconditional after any rebase" "$f" "$M5" "$SR" 'After any rebase.*unconditionally.*strictly greater'
  assert_present "$f: the bounded re-read distinguishes \`UNKNOWN\` from \`BLOCKED\`" "$f" "$M5" "$SR" '`UNKNOWN`.*wait.*`BLOCKED`.*gate 1'
  assert_present "$f: gate 1 is re-satisfied on the pushed head" "$f" "$M5" "$SR" 're-satisfy gate 1 on the pushed head'
  assert_order "$f: completeness gate, rebase, pre-merge check, merge command" "$f" "$M5" "$SR" \
    completeness '^4\. \*\*Completeness gate\*\*' rebase '^\*\*Rebase at the gate\.\*\*' premerge "Caller's pre-merge check" merge '^gh pr merge <pr> '
  assert_present "$f: the re-bump commit precedes the single push, which precedes gate 1's re-satisfaction" "$f" "$M5" "$SR" 're-bump version after rebase.*git push --force-with-lease.*re-satisfy gate 1 on the pushed head'
done

echo "== review-and-merge: notion-dev-only fork anchors =="
NF=plugins/notion-dev/skills/review-and-merge/SKILL.md
nNF=$(total_lines "$NF"); M5NF=$(find_line "$NF" 1 "$nNF" '^## 5\. Merge'); SRNF=$(find_line "$NF" "$M5NF" "$nNF" '^## Safety rules')
assert_present "notion-dev fork: cites \`/notion-dev:ticket\` Phase 6.1's rule" "$NF" "$M5NF" "$SRNF" '`/notion-dev:ticket`.*Phase 6\.1'
assert_present "notion-dev fork: \`git.mergeStrategy\` is unchanged by the rebase" "$NF" "$M5NF" "$SRNF" '`git\.mergeStrategy` is unchanged by the rebase'

echo "== per-invocation run ids (#44) =="
for f in plugins/notion-dev/commands/new-info.md plugins/notion-dev/commands/knowledge.md plugins/notion-dev/commands/create-task.md; do
  n=$(total_lines "$f")
  assert_present "$f: defines \`<run id>\` once as a per-invocation token with \`date -u +%Y%m%dT%H%M%SZ\`" "$f" 1 "$n" '<run id>.*\$\(date -u \+%Y%m%dT%H%M%SZ\)'
  assert_absent "$f: no bare per-command label remains as the run id" "$f" 1 "$n" '`<run id>` is `(new-info|knowledge|create-task)`'
done
echo "== new-info --pr rebase (#46) =="
NI=plugins/notion-dev/commands/new-info.md; LI=$(total_lines "$NI"); A0=$(find_line "$NI" 1 "$LI" '^### Apply'); A1=$(find_line "$NI" 1 "$LI" '^### Notion epic')
assert_present "apply: on a later epic under --pr, fetch and rebase the note branch when the epic branch moved" "$NI" "$A0" "$A1" 'git -C \$REPO_ROOT rebase origin/<epicBranch>'
assert_present "apply: a conflicting rebase aborts, releases, and stops with the remaining epics skipped" "$NI" "$A0" "$A1" 'git -C \$REPO_ROOT rebase --abort.*release.*skipped'
assert_present "apply: on a later epic under --pr, the note branch is rebased only when \`origin/<epicBranch>\` is no longer an ancestor of HEAD" "$NI" "$A0" "$A1" 'git -C \$REPO_ROOT merge-base --is-ancestor origin/<epicBranch> HEAD'
assert_present "apply: the epic branch is fetched before the ancestry check" "$NI" "$A0" "$A1" 'git -C \$REPO_ROOT fetch origin <epicBranch>'
assert_order "apply: take, re-checkout, fetch, rebase" "$NI" "$A0" "$A1" \
  take 'lock take --run <run id> --section apply' \
  recheckout 'git -C \$REPO_ROOT checkout <noteBranch>` under `--pr`.*`checkout`, never `checkout -b`' \
  fetch 'git -C \$REPO_ROOT fetch origin <epicBranch>' \
  rebase 'git -C \$REPO_ROOT rebase origin/<epicBranch>'

if [ "$fails" -gt 0 ]; then echo "verify-parallel: $fails FAIL"; exit 1; fi
echo "verify-parallel: all PASS"
