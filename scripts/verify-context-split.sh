#!/usr/bin/env bash
# Context split — progressive disclosure and the delegated record unit.
#
# Spec: docs/superpowers/specs/2026-09-16-notion-dev-context-reduction-design.md
#
# Three changes share this harness: issue-log reads its signature catalogue only
# when it is about to write an entry; ticket-system's operation index resolves to
# the reference file that owns each operation; and /notion-dev:ticket's record
# phase is dispatched with a bounded wait and an inline fallback.
#
# Standing invariants — no baseline, no version floor. Each goes red the moment
# the mechanism it names stops being in the document.
#
# Run from anywhere: ./scripts/verify-context-split.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
IL=$ND/skills/issue-log/SKILL.md
TS=$ND/skills/ticket-system/SKILL.md
TICKET=$ND/commands/ticket.md
RECORD=$ND/references/record.md

# ---------------------------------------------------------------------------
echo "== issue-log: the signature catalogue is read on first record =="

assert_present "issue-log defers reading \`references/signatures.md\` to the first entry of the run" \
  "$IL" 1 60 'Read .references/signatures\.md. before writing the first entry'

# ---------------------------------------------------------------------------
echo "== ticket-system: the configuration reference is present and pinned =="

TSCFG=$ND/skills/ticket-system/references/config.md

assert_present "\`references/config.md\` pins \`databaseId\` as the Notion database config key" \
  "$TSCFG" 1 "$(total_lines "$TSCFG")" '`databaseId` — the Notion database'

# ---------------------------------------------------------------------------
echo "== ticket-system: the styling reference is present and pinned =="

TSSTY=$ND/skills/ticket-system/references/styling.md

assert_present "\`references/styling.md\` pins the zone-divider rule inserting a \`divider\` block" \
  "$TSSTY" 1 "$(total_lines "$TSSTY")" 'insert a `divider` block'

# ---------------------------------------------------------------------------
echo "== ticket-system: the read-operations reference is present and pinned =="

TSREAD=$ND/skills/ticket-system/references/read-ops.md

assert_present "\`references/read-ops.md\` pins fetchTicket's rule that more than one row or \`has_more: true\` is never resolved by taking the first row" \
  "$TSREAD" 1 "$(total_lines "$TSREAD")" 'more than one row, or `has_more: true`, is never resolved by taking the first row'

# ---------------------------------------------------------------------------
echo "== ticket-system: the write-operations reference is present and pinned =="

TSWRITE=$ND/skills/ticket-system/references/write-ops.md

assert_present "\`references/write-ops.md\` pins the append-only counterpart to \`upsertSection\`, so an append never clobbers a section another phase wrote" \
  "$TSWRITE" 1 "$(total_lines "$TSWRITE")" '\*\*append-only\*\* counterpart to `upsertSection`'

# ---------------------------------------------------------------------------
echo "== ticket-system: the creation-operations reference is present and pinned =="

TSCREATE=$ND/skills/ticket-system/references/create-ops.md

assert_present "\`references/create-ops.md\` pins the title-prefix detection regex's optional escape before the bracket" \
  "$TSCREATE" 1 "$(total_lines "$TSCREATE")" '\*\*The optional backslashes are not defensive padding\.\*\*'

# ---------------------------------------------------------------------------
echo "== ticket-system: every \`Logical operations\` row resolves to the Reference file that defines it, not the dispatcher =="

# Region-delimit the table without a magic line number: anchor on the header
# line, stop at the first blank line after it.
TABLE_START=$(find_line "$TS" 1 "$(total_lines "$TS")" '^\| Operation \|')
TABLE_END=$(awk -v s="$TABLE_START" 'NR > s && /^$/ { print NR; exit }' "$TS")

# An independent count of the table's data rows, by a rule that does NOT
# depend on the operation name being backticked: any `| `-prefixed line in
# the region except the header and the `|---|` separator. If a row's
# operation name loses its backticks, this count still sees it — the loop
# below, keyed on the first backticked literal, would not — so the two are
# compared below to catch exactly that drop.
ROW_COUNT=$(awk -v s="$TABLE_START" -v e="$TABLE_END" \
  'NR > s && NR < e && /^\| / && !/^\|---/ { c++ } END { print c + 0 }' "$TS")

n=0
seen=""
while IFS= read -r row; do
  op=$(grep -o '`[A-Za-z]*`' <<<"$row" | head -1 | tr -d '`')
  ref=$(grep -o 'references/[a-z-]*\.md' <<<"$row" | head -1)
  [ -n "$op" ] || continue
  n=$((n + 1))
  seen="$seen $op"

  if [ -z "$ref" ] || [ ! -f "$ND/skills/ticket-system/$ref" ]; then
    bad "\`$op\`'s \`Reference\` cell names a file that exists (got: '${ref:-<none>}')"
    continue
  fi
  reffile="$ND/skills/ticket-system/$ref"

  if ! grep -q "^## ${op}(" "$reffile"; then
    bad "\`$op\`'s \`Reference\` file (\`$ref\`) actually defines \`$op\`"
    continue
  fi

  if grep -q "^## ${op}(" "$TS"; then
    bad "\`$op\`'s body is no longer in the dispatcher (found \`## ${op}(\` in SKILL.md)"
    continue
  fi

  ok "\`$op\` -> \`$ref\`: defined there, not duplicated in SKILL.md"
done < <(sed -n "${TABLE_START},${TABLE_END}p" "$TS" | grep '^| `')

echo "  (checked $n table rows)"

if [ "$n" -eq "$ROW_COUNT" ]; then
  ok "the backtick-keyed parse saw all $ROW_COUNT data rows in the \`Logical operations\` table"
else
  bad "the backtick-keyed parse saw $n of $ROW_COUNT data rows in the \`Logical operations\` table — a row lost its backticked operation name and dropped out unguarded (parsed:$seen)"
fi

# ---------------------------------------------------------------------------
echo "== ticket-system: the read-before-use gate on the Reference column is stated =="

assert_present "SKILL.md gates every operation behind reading its \`Reference\` file first" \
  "$TS" 1 "$(total_lines "$TS")" 'may not perform an operation whose `Reference` file you have not read in this run'

# ---------------------------------------------------------------------------
echo "== ticket.md: the record unit (Phases 8-10) is present and pinned in references/record.md =="

assert_present "\`references/record.md\` opens by stating the caller already took the lock and resolved the filing gate" \
  "$RECORD" 1 "$(total_lines "$RECORD")" 'already resolved the interactive filing gate'
assert_present "\`references/record.md\` tells the reader not to take the lock, ask the user, or release the lock" \
  "$RECORD" 1 "$(total_lines "$RECORD")" 'Do not take the lock again, do not ask the user anything, and do not release the'
assert_present "\`references/record.md\` defines the \`RECORD:\` output block" \
  "$RECORD" 1 "$(total_lines "$RECORD")" '^RECORD:$'
assert_present "\`references/record.md\`'s \`RECORD:\` block carries \`EPIC-DOC-RECORD\`" \
  "$RECORD" 1 "$(total_lines "$RECORD")" '^EPIC-DOC-RECORD: '

# ---------------------------------------------------------------------------
echo "== ticket: the record unit is dispatched, and recoverable when it is not =="

assert_order "Phase 8 asks, locks, leaves the worktree, then dispatches" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  "filing gate"  'Resolve the interactive filing gate before the lock is taken' \
  "lock take"    'knowledge\.py. lock take .*--section record' \
  "cd REPO_ROOT" 'Leave the worktree: .cd \$REPO_ROOT' \
  "dispatch"     'Dispatch one .general-purpose. agent, synchronously'

assert_present "the dispatch names \`\${CLAUDE_PLUGIN_ROOT}/references/record.md\` as the agent's instructions" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  'instruction to read .\${CLAUDE_PLUGIN_ROOT}/references/record\.md. and follow it exactly'

assert_present "the wait is bounded at ~15 minutes" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  'Bound the wait at ~15 minutes'

assert_present "a lost dispatch records \`unexpected:record-unit-not-dispatched\` and runs inline" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  'Record .unexpected:record-unit-not-dispatched. per .notion-dev:issue-log.'

assert_present "the fallback runs \`\${CLAUDE_PLUGIN_ROOT}/references/record.md\` inline rather than stopping" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  '\*\*read .\${CLAUDE_PLUGIN_ROOT}/references/record\.md. and run it inline yourself\*\*'

assert_present "\`references/record.md\` returns a \`RECORD:\` block" \
  "$RECORD" 1 "$(total_lines "$RECORD")" '^RECORD:$'

assert_present "\`references/record.md\` is told the lock is already held" \
  "$RECORD" 1 "$(total_lines "$RECORD")" 'taken the primary lock.*LOCK_HELD: true'

# Region bounds for the checks below that must be anchored on Phase 8/10 —
# computed once into variables rather than inlined as $(find_line ...) in an
# argument list: if the heading is ever renamed, find_line returns empty, an
# inlined empty string silently collapses the argument list, and the
# assertion misbehaves instead of failing. Computed once, checked, and
# reported loudly with `bad` if either anchor is gone.
PHASE8_START=$(find_line "$TICKET" 1 "$(total_lines "$TICKET")" '^## Phase 8')
PHASE10_START=$(find_line "$TICKET" 1 "$(total_lines "$TICKET")" '^## Phase 10')
if [ -z "$PHASE8_START" ]; then
  bad "ticket.md: found the \`## Phase 8\` heading, to bound the record-section checks"
fi
if [ -z "$PHASE10_START" ]; then
  bad "ticket.md: found the \`## Phase 10\` heading, to bound the record-section checks"
fi

# The saving is the point: the orchestrator's own record phase must not name the
# skills the unit was created to carry. This is what goes red if the delegation
# is quietly unwound by a later edit.
if [ -n "$PHASE8_START" ]; then
  assert_absent "the orchestrator's record phase no longer invokes \`notion-dev:epic-update\`" \
    "$TICKET" "$PHASE8_START" "$(total_lines "$TICKET")" 'notion-dev:epic-update'
fi

# ---------------------------------------------------------------------------
echo "== ticket.md: the dispatch's return value is what Phase 10 actually consumes =="

# (A) "wait for it" wording alone is satisfiable by accident; a demonstrated
# data dependency on the dispatch's return value is the strongest proxy prose
# can express for "the call already returned". assert_order proves the
# dispatch instruction (asserted `synchronously` above) precedes the line
# that reads a named field out of the `RECORD:` block the dispatch returns.
assert_order "ticket.md: the synchronous dispatch precedes the epic-doc line's read of RECORD_REPORT's \`EPIC-DOC-RECORD\` field" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  "dispatch"           'Dispatch one .general-purpose. agent, synchronously' \
  "epic-doc field read" 'RECORD_REPORT.*EPIC-DOC-RECORD.*field verbatim'

# ---------------------------------------------------------------------------
echo "== ticket.md: the record-section lock's failure semantics =="

# (B) Never guarded before this plan: the Exit-1 stop path, the stale-lock
# recording, and the sentence bounding what runs under the lock. All three
# were silently dropped once by this plan's own draft prose and recovered
# only by a line-by-line accounting.
if [ -n "$PHASE8_START" ] && [ -n "$PHASE10_START" ]; then
  PHASE8_END=$((PHASE10_START - 1))

  assert_present "the record-section lock's Exit-1 path stops naming \`CAUSE: primary lock held by\`" \
    "$TICKET" "$PHASE8_START" "$PHASE8_END" \
    'Exit 1.*stop per "Failure and stop conditions" with `CAUSE: primary lock held by'

  assert_present "a \`stale:\` line on the record-section lock records \`lock-stale:primary\` and names the old owner" \
    "$TICKET" "$PHASE8_START" "$PHASE8_END" \
    'A `stale:` line.*record `lock-stale:primary` and name the old owner in the report'

  assert_present "the record section states what runs under the lock, ending at Phase 10's epic-doc step" \
    "$TICKET" "$PHASE8_START" "$PHASE8_END" \
    'Everything from here to the end of Phase 10.s epic-doc step.*runs with the lock held'
else
  bad "ticket.md: skipped the record-section lock checks (Phase 8/10 heading missing)"
fi

# ---------------------------------------------------------------------------
echo "== ticket.md: an explicit subagent prohibition is not a dispatch failure =="

# (C) The prohibition path takes the same inline route as a failed dispatch,
# but is not a degradation and must not be logged as one. An assertion that
# only proves the signature appears somewhere would still pass if a later
# edit wired it to fire on the prohibition path too — the actual error worth
# catching — so this pins the "do not record" sentence itself.
assert_present "an explicit user prohibition on the dispatch takes the same inline path as a failed one" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  'An explicit user prohibition on this dispatch takes the same inline path as a failed one'

assert_present "the prohibition path states it does not record \`unexpected:record-unit-not-dispatched\`, unlike the failure path" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  'do \*\*not\*\* record `unexpected:record-unit-not-dispatched`'

exit $(( fails > 0 ))
