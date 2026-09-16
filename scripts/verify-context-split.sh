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
RECORD=$ND/commands/references/record.md

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

exit $(( fails > 0 ))
