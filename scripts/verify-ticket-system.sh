#!/usr/bin/env bash
# Standing-invariant checks for notion-dev's Notion adapter and the worktree
# layout its commands depend on.
#
# Everything here was found by RUNNING the flows against a live Notion database
# and a scratch GitHub repository (issue #31), not by reading them. Each is a
# fact about how the MCP surface or git actually behaves, which the instructions
# had wrong — the class of defect no amount of structural checking of the *other*
# harnesses would ever have reached, because the documents were internally
# consistent and simply did not match reality.
#
# Standing invariants, in the verify-mirror.sh model: no version floors, nothing
# to go stale.
#
# Run from anywhere: ./scripts/verify-ticket-system.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# (cd to the repo root already happened above, so this path is stable.)
. ./scripts/lib/assert.sh

TS=plugins/notion-dev/skills/ticket-system/SKILL.md
TICKET=plugins/notion-dev/commands/ticket.md
FINALIZE=plugins/notion-dev/commands/finalize.md

echo "== the ID read back off the page is normalized =="

if [ ! -f "$TS" ]; then
  bad "$TS is missing"
else
  n=$(total_lines "$TS")
  # The two MCP access paths disagree — notion-fetch returns "PDS-1", the SQL
  # query returns 1 — and every caller that says "the numeric <id>" depends on
  # the normalization. Anchor on the rule, then on each half of the evidence.
  assert_present "$TS: fetchTicket normalizes the value it read, not only caller input" \
    "$TS" 1 "$n" '^[*][*]The value read back off the page needs the same normalization'
  assert_present "$TS: names notion-fetch as the path that returns the prefixed form" \
    "$TS" 1 "$n" 'notion-fetch. returns the property as the .prefixed string'
  assert_present "$TS: names notion-query-data-sources as the path that returns the bare integer" \
    "$TS" 1 "$n" 'notion-query-data-sources. returns the bare integer'
  assert_present "$TS: states the consequence an unnormalized value produces" \
    "$TS" 1 "$n" 'ticket/PDS-PDS-1-<slug>'
  assert_present "$TS: a number ID column is a no-op for this rule" \
    "$TS" 1 "$n" 'A .number. ID column is unaffected'
fi

echo
echo "== the title-prefix regex tolerates Notion's escaped brackets =="

if [ -f "$TS" ]; then
  n=$(total_lines "$TS")
  # Notion-flavored markdown escapes [ and ], so the live title is `\[PDS-1\] …`.
  # The detection regex must carry the optional backslashes; without them the
  # strip silently fails and the id lands in the branch slug twice.
  assert_present "$TS: the detection regex carries the optional escape before the bracket" \
    "$TS" 1 "$n" '^\^\\\\[?]\\\[\\s[*]<KEY>-'
  assert_present "$TS: says why the optional backslashes are there" \
    "$TS" 1 "$n" '^[*][*]The optional backslashes are not defensive padding[.][*][*]'
  assert_present "$TS: cites the live escaped form" \
    "$TS" 1 "$n" 'arrives as$'
  assert_present "$TS: names the double-prefix consequence" \
    "$TS" 1 "$n" 'accumulating .[[]PDS-1[]] [[]PDS-1[]]'
  assert_present "$TS: the escapes are stripped from the title body too" \
    "$TS" 1 "$n" '^Strip the escapes from the captured title as well'
fi

echo
echo "== worktrees live in a <repo>-worktrees container =="

# Without the container, `rmdir "$(dirname <worktree-path>)"` in each flow's
# cleanup names the directory holding the primary checkout — a step that can
# never succeed and that points at a directory the flow does not own. quick-dev's
# develop has always had the container; these two had not.
for f in "$TICKET" "$FINALIZE"; do
  if [ ! -f "$f" ]; then bad "$f is missing"; continue; fi
  n=$(total_lines "$f")
  assert_present "$f: resolves the worktree under a <repo-name>-worktrees container" \
    "$f" 1 "$n" '[$][(]dirname "[$]REPO_ROOT"[)]/<repo-name>-worktrees/<prefix>'
done

assert_present "$TICKET: says why the container is load-bearing for the rmdir step" \
  "$TICKET" 1 "$(total_lines "$TICKET")" \
  '^[*][*]The .<repo-name>-worktrees. container is load-bearing'

# quick-dev is the layout the two above were aligned to; if it ever moves, they
# have to move with it, so assert the pair rather than each alone.
assert_present "develop creates the same <repo>-worktrees container" \
  plugins/quick-dev/skills/develop/SKILL.md 1 \
  "$(total_lines plugins/quick-dev/skills/develop/SKILL.md)" \
  'git worktree add "[$][(]dirname "[$]REPO_ROOT"[)]/[$][{]REPO_NAME[}]-worktrees/[$]SLUG"'

echo
echo "== a Codex summary comment is not a response until it reads Completed =="

# Codex posts its summary comment within seconds of the trigger, from the same bot
# login as the review itself, with the status cell reading `Running`. A loop that
# watches only for a new comment from that author fires on the placeholder and
# merges before the review exists. Observed live on two scratch pull requests.
RAM_DOCS="plugins/quick-dev/skills/review-and-merge/SKILL.md
plugins/notion-dev/skills/review-and-merge/SKILL.md
.claude/skills/review-and-merge/SKILL.md"
for f in $RAM_DOCS; do
  if [ ! -f "$f" ]; then bad "$f is missing"; continue; fi
  n=$(total_lines "$f")
  assert_present "$f: the reviewer profile has a row for the not-yet-a-response comment" \
    "$f" 1 "$n" '^[|] [*][*]a comment that is not yet the response[*][*] [|]'
  assert_present "$f: it names the summary marker Codex posts within seconds" \
    "$f" 1 "$n" 'Codex posts a .<!-- codex-pull-request-review-summary -->. comment'
  assert_present "$f: a summary comment counts only once its status reads Completed" \
    "$f" 1 "$n" 'is a response only once its Status cell reads .*Completed'
  assert_present "$f: the placeholder is running, not silent — do not re-trigger" \
    "$f" 1 "$n" 'it is running, not silent, so do not re-trigger'
done

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
