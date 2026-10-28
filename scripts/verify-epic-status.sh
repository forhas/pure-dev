#!/usr/bin/env bash
# Epic start status — starting a child ticket moves its Epic container to In Progress
# (ticket-system `startEpic`), a resolution that leaves the epic open repairs a missed start,
# and a resolved epic is never reopened. Reported from a client: a started child left its
# epic in Backlog because the plugin explicitly never set an epic to In Progress.
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
TS=$ND/skills/ticket-system
WO=$TS/references/write-ops.md
OPS=$TS/references/operations.md
INTAKE=$ND/references/lean-intake.md
TICKET=$ND/references/legacy/ticket.md
EU=$ND/skills/epic-update/SKILL.md
WF=$ND/skills/epic-update/references/with-followups.md

echo "== the operation =="
L=$(total_lines "$WO")
S=$(find_line "$WO" 1 "$L" '^## startEpic\(id\)$'); E=$(find_line "$WO" "$S" "$L" '^## setPullRequest')
assert_order "startEpic: no epic, then not an epic, then unchanged, then resolved, then the write" "$WO" "$S" "$E" \
  no-epic 'return `no-epic`' not-an-epic 'return `not-an-epic`' unchanged 'return `unchanged`' \
  resolved 'return `resolved`' write 'updateStatus\(<parent>, "inProgress"\)'
assert_present "startEpic: a resolved epic is never moved out of the resolved set" "$WO" "$S" "$E" \
  'never moves an epic out of a$'
assert_present "startEpic: a failure never stops the run" "$WO" "$S" "$E" 'never stops the ticket run'
assert_present "operations table lists \`startEpic\`" "$OPS" 1 "$(total_lines "$OPS")" '^\| `startEpic` \| `id`'
assert_present "ticket-system routes \`startEpic\` to write-ops" "$TS/SKILL.md" 1 "$(total_lines "$TS/SKILL.md")" \
  '^\|.* / startEpic / .*\| `references/write-ops\.md` \|$'

echo "== call sites =="
L=$(total_lines "$INTAKE")
assert_order "lean intake: ticket \`inProgress\`, then \`startEpic(id)\`" "$INTAKE" 1 "$L" \
  ticket 'Through ticket-system set `inProgress`' epic 'run `startEpic\(id\)`'
L=$(total_lines "$TICKET")
P2=$(find_line "$TICKET" 1 "$L" '^## Phase 2 '); P3=$(find_line "$TICKET" 1 "$L" '^## Phase 3 ')
assert_order "legacy ticket Phase 2: status, then \`startEpic(id)\`, then refresh start" "$TICKET" "$P2" "$P3" \
  status 'updateStatus\(id, "inProgress"\)' epic '^- `startEpic\(id\)`' refresh 'operation `refresh\(<epic-id>, start <key>\)`'
assert_present "epic-update: an open epic is repaired with \`startEpic(<ticket id>)\`" "$EU" 1 "$(total_lines "$EU")" \
  '`startEpic\(<ticket id>\)`'
L=$(total_lines "$WF")
assert_present "with-followups: an open epic is repaired with \`startEpic(<ticket id>)\`" "$WF" 1 "$L" \
  'Otherwise do not close.*`startEpic\(<ticket id>\)`'
assert_absent "with-followups: the old never-set-In-Progress rule is gone" "$WF" 1 "$L" 'never sets an epic to'

if [ "$fails" -gt 0 ]; then echo "verify-epic-status: $fails FAIL"; exit 1; fi
echo "verify-epic-status: all PASS"
