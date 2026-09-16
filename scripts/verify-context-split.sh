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

exit $(( fails > 0 ))
