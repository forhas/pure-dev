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

# The query-call contract. 5 of 13 data-source calls in a measured client ticket were the run
# rediscovering this, and the two worst failures do not look like failures: a `?` placeholder
# returns 200 with an empty result set, and a `SELECT *` probe re-reads a schema config already
# holds. Each trap is pinned on its own line — the file is not hard-wrapped here, but a regex
# spanning two of them would go quiet the moment one is reworded.
TSRL=$(total_lines "$TSREAD")
assert_present "read-ops: the call shape passes \`data_source_urls\` as an array of collection URLs" \
  "$TSREAD" 1 "$TSRL" '^ *"data_source_urls": \["collection://<dataSourceId>"\],$'
assert_present "read-ops: the arguments are wrapped in \`data\`, with the quoted collection URL as the table name" \
  "$TSREAD" 1 "$TSRL" 'The arguments are wrapped in `data`, and the table name is the quoted collection URL'
assert_present "read-ops: names the third rejected shape, the \`data_sources\` JSON string, beside the other two" \
  "$TSREAD" 1 "$TSRL" '`data_source_url` \+ `query_type` \+ `sql_query`; a `data_sources` JSON \*string\*'
assert_present "read-ops: the rejected shapes all return one \`Invalid input\` message that names no field" \
  "$TSREAD" 1 "$TSRL" 'Invalid input`, which names no field'
assert_present "read-ops: \`params\` placeholders return an empty result set with no error, so inline the literal" \
  "$TSREAD" 1 "$TSRL" 'Never use `params` with `\?` placeholders. Inline the literal value instead'
assert_present "read-ops: column names come from the config, never from a \`SELECT \*\` probe" \
  "$TSREAD" 1 "$TSRL" 'Column names come from `\.claude/notion-dev\.config\.json`, never from a `SELECT \*` probe'
assert_present "read-ops: there is no bare \`name\` column and guessing one is a hard 400" \
  "$TSREAD" 1 "$TSRL" 'There is no bare `name` column\*\*, and guessing one is a hard `400`'
# Codex round 1, both P-level. The id column is a namespace plus the CONFIGURED name, so a
# hardcoded "userDefined:ID" breaks every database init bound to a different property; and the
# pre-existing ambiguous-lookup recovery still prescribed the `params` form this file now forbids.
assert_present "read-ops: the id column takes a \`userDefined:<idProperty>\` prefix" \
  "$TSREAD" 1 "$TSRL" 'takes a `userDefined:` prefix, `"userDefined:<idProperty>"`'
assert_present "read-ops: the SQL template itself selects and filters on that configured id column" \
  "$TSREAD" 1 "$TSRL" '^ *"query": "SELECT .*userDefined:<idProperty>.*WHERE .*userDefined:<idProperty>'
assert_present "read-ops: hardcoding \`userDefined:ID\` is named as the defect" \
  "$TSREAD" 1 "$TSRL" 'Hardcoding `"userDefined:ID"`$'
assert_present "read-ops: the prefix is a namespace, not a fixed column name" \
  "$TSREAD" 1 "$TSRL" 'That prefix is a namespace, not a fixed column name'
assert_present "read-ops: the ambiguous-lookup recovery inlines the id as a literal, not as a bound parameter" \
  "$TSREAD" 1 "$TSRL" 're-issue the lookup in SQL mode \*\*with the id inlined as a literal\*\*'
assert_present "read-ops: says three-for-three established SQL mode, not the parameter binding" \
  "$TSREAD" 1 "$TSRL" 'established is that \*\*SQL mode\*\* beats'
# Codex round 2: the contract invented a `ticketSystem.titleProperty`. There is none — the title
# is the one column discovered from the live schema, and a guessed name is the same hard 400.
assert_present "read-ops: states there is no \`ticketSystem.titleProperty\` and exactly one title-typed property exists" \
  "$TSREAD" 1 "$TSRL" '`ticketSystem.titleProperty`: every Notion database has exactly one `title`-typed property'
assert_present "read-ops: names the free title column and the three names in use" \
  "$TSREAD" 1 "$TSRL" 'the adapter discovers it by scanning the live schema'
assert_present "read-ops: a lookup that only resolves a page omits the title column rather than guessing" \
  "$TSREAD" 1 "$TSRL" 'select it only in queries that actually need the title'
assert_absent "read-ops: never cites \`ticketSystem.titleProperty\` as a configured name" \
  "$TSREAD" 1 "$TSRL" 'name — `ticketSystem\.titleProperty`'

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
# The move dropped this heading while four cross-references inside the same
# file kept citing "8.2" as a locatable unit.
assert_present "\`references/record.md\` carries the \`### 8.2 Update the epic\` heading its own cross-references locate" \
  "$RECORD" 1 "$(total_lines "$RECORD")" '^### 8\.2 Update the epic$'

assert_present "\`references/record.md\` defines the \`RECORD:\` output block" \
  "$RECORD" 1 "$(total_lines "$RECORD")" '^RECORD:$'
assert_present "\`references/record.md\`'s \`RECORD:\` block carries \`EPIC-DOC-RECORD\`" \
  "$RECORD" 1 "$(total_lines "$RECORD")" '^EPIC-DOC-RECORD: '

# The brief's `PATH:` / outcome / `NEXT:` line — and, on `failed`, the `CAUSE:`
# and the unpushed local commit — are the run's only user-visible epic-doc
# output. `EPIC_DOC_REPORT` itself never crosses the dispatch boundary, so the
# block needs a field to carry them or they are simply lost.
assert_present "\`references/record.md\`'s output block carries \`EPIC-DOC-NEXT\`" \
  "$RECORD" 1 "$(total_lines "$RECORD")" '^EPIC-DOC-NEXT: '

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
echo "== ticket.md: the dispatch prompt supplies everything references/record.md consumes =="

# (D) The gap that let two defects ship: nothing compared the dispatch prompt's
# payload list against what the dispatched unit actually reads. `record.md` was
# given a `DRAFT_REPORT` that could not exist, and never given
# `PLAN_REVIEW_REPORT` — whose absence makes the unit write `null` into four
# ledger metrics that reserve `null` for "no review signal", i.e. a silent
# falsehood rather than a visible failure.
#
# Mechanical and fail-closed: every backticked ALL-CAPS name `record.md` cites
# must appear in the dispatch prompt's list, unless it is declared below as a
# name the unit produces or reads out of another block rather than receiving.
# A new payload name added to `record.md` is caught by default.
DISPATCH_LINE=$(find_line "$TICKET" 1 "$(total_lines "$TICKET")" 'Dispatch one .general-purpose. agent, synchronously')
if [ -z "$DISPATCH_LINE" ]; then
  bad "ticket.md: found the dispatch sentence, to check its payload list against \`references/record.md\`"
else
  # Declared non-payload names. Each is either produced inside the unit or a
  # field name of a block the unit is given, NOT something the caller passes.
  # This is not an allowlist that only grants permission: every entry is
  # re-checked below to still occur in record.md, so a stale one goes red.
  NOT_PAYLOAD="ABSORBED ALREADY_FILED BLOCKED CAVEATS CLAIMS DROPPED EPIC_DOC_REPORT EPIC_REPORT FAILED FILED MERGED NONE PROVENANCE TRIAGE VERDICTS"

  for name in $NOT_PAYLOAD; do
    if ! grep -q "\`\$\?${name}\`" "$RECORD"; then
      bad "the declared non-payload name \`$name\` is still cited in \`references/record.md\` (stale declaration — re-check whether it is now a payload name)"
    fi
  done

  missing=""
  checked=0
  for name in $(grep -o '`\$\?[A-Z][A-Z0-9_]\{3,\}`' "$RECORD" | tr -d '`$' | sort -u); do
    case " $NOT_PAYLOAD " in *" $name "*) continue ;; esac
    checked=$((checked + 1))
    sed -n "${DISPATCH_LINE}p" "$TICKET" | grep -qE "(^|[^A-Z0-9_])${name}([^A-Z0-9_]|\$)" || missing="$missing $name"
  done

  if [ -n "$missing" ]; then
    bad "every name \`references/record.md\` consumes is carried by the dispatch prompt (missing:$missing)"
  else
    ok "all $checked payload names \`references/record.md\` consumes are carried by the dispatch prompt"
  fi

  # Two inputs the sweep above cannot see: `<merge-commit>` is placeholder-shaped,
  # and the ticket body has no name at all. Both are hard requirements of the
  # unit — the merge SHA gates Phase 9's `merge-base --is-ancestor` assertion and
  # fills 8.3's `Merge commit` field; the body is half the post-merge hook contract.
  assert_present "the dispatch prompt carries \`<merge-commit>\`, which the unit hard-gates on" \
    "$TICKET" "$DISPATCH_LINE" "$DISPATCH_LINE" \
    '`<merge-commit>` \(the SHA `notion-dev:review-and-merge` returned\)'

  assert_present "the dispatch prompt carries the ticket body, half the post-merge hook contract" \
    "$TICKET" "$DISPATCH_LINE" "$DISPATCH_LINE" \
    'the ticket id, the ticket body, PR number and URL'

  # The `DRAFT_REPORT` the unit is handed is the caller's *pre-dispatch* draft.
  # A "full draft report" here would be unbuildable: its own lines read the
  # dispatch's return value. This is the sentence that makes it buildable.
  assert_present "Phase 8 composes the pre-dispatch draft as every Phase 10 line that does not read \`RECORD_REPORT\`" \
    "$TICKET" "$PHASE8_START" "$(total_lines "$TICKET")" \
    'Phase 10.s summary list below, minus every line that reads `RECORD_REPORT`'

  assert_present "\`references/record.md\` states that it composes nothing and that \`DRAFT_REPORT\` is the caller's pre-dispatch draft" \
    "$RECORD" 1 "$(total_lines "$RECORD")" \
    '`DRAFT_REPORT` is the \*\*caller.s pre-dispatch draft, not its final report\*\*'
fi

# ---------------------------------------------------------------------------
echo "== ticket.md: every key the RECORD: block defines is consumed by Phase 10 =="

# (E) A key nobody reads is a tail. `TICKET-RECORD` was defined and never
# rendered, so a partial Completeness or `## Merged` write surfaced nowhere at
# all — in the branch that added the zero-tails phase. Pin both consumers.
if [ -n "$PHASE10_START" ]; then
  assert_present "Phase 10 renders \`RECORD_REPORT\`'s \`EPIC-DOC-RECORD\` and then its \`EPIC-DOC-NEXT\` field verbatim, the one place the run says what to do next" \
    "$TICKET" "$PHASE10_START" "$(total_lines "$TICKET")" \
    '`RECORD_REPORT`.s `EPIC-DOC-RECORD` field verbatim.*its `EPIC-DOC-NEXT` field verbatim'

  assert_present "Phase 10 renders \`RECORD_REPORT\`'s \`TICKET-RECORD\` field whenever it is not \`ok\`" \
    "$TICKET" "$PHASE10_START" "$(total_lines "$TICKET")" \
    '`RECORD_REPORT`.s `TICKET-RECORD` field whenever it is not `ok`'
else
  bad "ticket.md: skipped the RECORD: key-consumption checks (Phase 10 heading missing)"
fi

# The producing side: 8.3 must actually set the key from its three separate
# Notion writes, or Phase 10 renders a value nothing ever varies.
assert_present "\`references/record.md\` 8.3 sets \`TICKET-RECORD:\` from what it wrote and records \`partial:ticket-record\`" \
  "$RECORD" 1 "$(total_lines "$RECORD")" \
  'Set `TICKET-RECORD:` from what this subsection actually wrote.*as `partial:ticket-record`'

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
