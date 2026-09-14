#!/usr/bin/env bash
# verify-knowledge-py.sh — runs plugins/notion-dev/scripts/knowledge.py against fixture
# bundles and asserts its exit codes and finding lines. A missing iwe or python3 is a FAIL,
# never a skip: CI installs both, and a check that cannot run must say so.
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

PY=plugins/notion-dev/scripts/knowledge.py
ROOT=plugins/notion-dev
FX=scripts/fixtures/knowledge
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

command -v iwe >/dev/null 2>&1 || { echo "FAIL: iwe not on PATH"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 not on PATH"; exit 1; }

run() { # name, expected-exit, args...
  local name=$1 want=$2; shift 2
  python3 "$PY" "$@" > "$OUT/$name.txt" 2>&1; local got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL: $name exited $got, wanted $want"; cat "$OUT/$name.txt"; fails=$((fails+1))
  else echo "ok: $name exit $got"; fi
}

echo "== check: valid bundle =="
run valid 0 check --dir "$FX/valid" --plugin-root "$ROOT" --extra-types commitment
assert_lacks "valid bundle reports no finding" "$OUT/valid.txt" ': schema:'

echo "== check: each broken fixture names its rule =="
for d in "$FX"/broken-*; do
  rule=${d##*/broken-}
  extra=commitment; [ "$rule" = type ] && extra=""
  run "broken-$rule" 1 check --dir "$d" --plugin-root "$ROOT" ${extra:+--extra-types $extra}
done
assert_has "broken-schema names the schema rule"     "$OUT/broken-schema.txt"     'decision/keep-cache.md: schema:'
assert_has "broken-link names the dangling key"       "$OUT/broken-link.txt"       'epic/STO-1-demo-epic.md: link: decision/missing'
assert_has "broken-superseded names the target"       "$OUT/broken-superseded.txt" 'gotcha/old-trap.md: superseded_by: gotcha/nope'
assert_has "broken-superseded-chain: deprecated target" "$OUT/broken-superseded-chain.txt" 'superseded_by: target is deprecated'
assert_has "broken-index names the missing bullet"    "$OUT/broken-index.txt"      'index.md: index: decision/keep-cache'
assert_has "broken-type names the directory"          "$OUT/broken-type.txt"       'type: undeclared directory commitment'
assert_has "broken-iwe names the drifted file"        "$OUT/broken-iwe.txt"        '.iwe/schemas/okf.yaml: iwe: differs from plugin copy'
assert_has "broken-iwe-missing names the absent file" "$OUT/broken-iwe-missing.txt" '.iwe/schemas/okf-index.yaml: iwe: missing'
assert_has "broken-log names the schema rule"         "$OUT/broken-log.txt"        'log.md: schema:'
assert_has "broken-link-outward names the missing outside-bundle target" \
  "$OUT/broken-link-outward.txt" 'epic/STO-1-demo-epic.md: link: ../docs/nope (outside bundle, not on disk)'

echo "== check: warnBytes warns, never fails =="
run warn 0 check --dir "$FX/valid" --plugin-root "$ROOT" --extra-types commitment --warn-bytes 10
assert_has "a tiny warn-bytes produces warn lines" "$OUT/warn.txt" ': warn: '

echo "== check: iwe missing is exit 2 =="
# A bare `PATH=/nonexistent` breaks python3 (and this function's own `cat` fallback) too,
# since the override applies for the whole function call, not just the `iwe` lookup inside
# it — so build a PATH that keeps python3 and coreutils but drops iwe's directory instead.
PYDIR=$(dirname "$(command -v python3)")
PATH="$PYDIR:/usr/bin:/bin" run noiwe 2 check --dir "$FX/valid" --plugin-root "$ROOT"

echo "== check: fail closed — a missing log.md is a finding, not a skipped rule =="
NL=$(mktemp -d); cp -r "$FX/valid/." "$NL/"; rm -f "$NL/log.md"
run nolog 1 check --dir "$NL" --plugin-root "$ROOT" --extra-types commitment
assert_has "check names the missing \`log.md\`" "$OUT/nolog.txt" 'log.md: missing:'
rm -rf "$NL"

echo "== check: fail closed — a --plugin-root with no shipped iwe copy is exit 2 =="
BOGUS=$(mktemp -d)
run badroot 2 check --dir "$FX/valid" --plugin-root "$BOGUS" --extra-types commitment
assert_has "the drift rule refuses to run rather than skipping" "$OUT/badroot.txt" 'drift rule cannot run'
rm -rf "$BOGUS"

echo "== check: --config supplies dir, extraTypes and warnBytes when the flags are absent =="
CFGD=$(mktemp -d); mkdir -p "$CFGD/.claude"; cp -r "$FX/valid" "$CFGD/bundle"
cat > "$CFGD/.claude/notion-dev.config.json" <<JSON
{ "knowledge": { "dir": "bundle", "extraTypes": ["commitment"], "warnBytes": 10 } }
JSON
run cfg 0 check --config "$CFGD/.claude/notion-dev.config.json" --plugin-root "$ROOT"
assert_lacks "the configured \`extraTypes\` silences the type rule with no --extra-types flag" \
  "$OUT/cfg.txt" ': type: undeclared directory'
assert_has "the configured \`warnBytes\` is what the size rule warns against" \
  "$OUT/cfg.txt" 'exceeds warnBytes 10'
rm -rf "$CFGD"

echo "== touched: fixture repo =="
REPO=$(mktemp -d); cp -r "$FX/valid" "$REPO/knowledge"; mkdir -p "$REPO/src/cache" "$REPO/src/other"
( cd "$REPO" && git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm base \
  && echo x > src/cache/a.rs && echo y > src/other/b.rs && git add -A \
  && git -c user.name=t -c user.email=t@t commit -qm touch )
SHA=$(git -C "$REPO" rev-parse HEAD)
( cd "$REPO" && python3 "$OLDPWD/$PY" touched "$SHA" --dir knowledge > "$OUT/touched.txt" 2>&1 )
tex=$?
if [ "$tex" -ne 0 ]; then
  echo "FAIL: touched exited $tex, wanted 0"; cat "$OUT/touched.txt"; fails=$((fails+1))
else echo "ok: touched exit 0"; fi
assert_has   "touched lists the concept whose applies_to matched" "$OUT/touched.txt" 'decision/keep-cache.md'
assert_lacks "touched omits concepts without applies_to"          "$OUT/touched.txt" 'gotcha/new-trap.md'
rm -rf "$REPO"

echo "== migrate: dry run writes nothing, apply matches expected =="
# git-inited (and committed) because migrate step 5b enumerates `git ls-files '*.md'` to find
# and repoint external links to the moved brief; mirrors the touched-block setup above. `.git`
# itself is excluded from every byte-exact diff below, since the static fixtures on disk are
# plain directories, not repos.
M=$(mktemp -d); cp -r "$FX/migrate-input/." "$M/"
( cd "$M" && git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm base )
run migrate-dry 0 migrate --dir "$M/knowledge" --config "$M/.claude/notion-dev.config.json" --plugin-root "$ROOT"
diff -r -x .git "$FX/migrate-input" "$M" >/dev/null && echo "ok: dry run left the tree byte-identical" \
  || { echo "FAIL: dry run modified the tree"; fails=$((fails+1)); }
assert_has "dry run prints a unified diff" "$OUT/migrate-dry.txt" '+++ '
run migrate-apply 0 migrate --apply --dir "$M/knowledge" --config "$M/.claude/notion-dev.config.json" --plugin-root "$ROOT"
diff -r -x .git "$FX/migrate-expected" "$M" && echo "ok: apply produced the expected tree" \
  || { echo "FAIL: apply differs from expected"; fails=$((fails+1)); }
run migrate-check 0 check --dir "$M/knowledge" --plugin-root "$ROOT"
rm -rf "$M"

echo "== migrate: wrapped frontmatter, a wrapped log and a bulletless index section =="
# The three transforms that destroyed both real client bundles, each with its own input:
# a frontmatter key whose flow mapping wraps over two lines, a log whose bullets wrap and
# whose sub-sections the log schema forbids, and an index section carrying prose and no
# bullet at all. None of them was exercised by any fixture before.
MW=$(mktemp -d); cp -r "$FX/migrate-wrapped/." "$MW/"
( cd "$MW" && git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm base )
run migrate-wrapped-dry 0 migrate --dir "$MW/knowledge" --config "$MW/.claude/notion-dev.config.json" --plugin-root "$ROOT"
assert_has "migrate says step 4 moved no brief when \`docs/epics\` is absent" \
  "$OUT/migrate-wrapped-dry.txt" 'migrate step 4 moved no brief — docs/epics/ does not exist'
run migrate-wrapped 0 migrate --apply --dir "$MW/knowledge" --config "$MW/.claude/notion-dev.config.json" --plugin-root "$ROOT"
diff -r -x .git "$FX/migrate-wrapped-expected" "$MW" && echo "ok: wrapped apply produced the expected tree" \
  || { echo "FAIL: wrapped apply differs from expected"; fails=$((fails+1)); }
assert_lacks "the dropped \`reconciled\` key takes its wrapped continuation line with it" \
  "$MW/knowledge/decision/flow-mapping.md" 'against: [pr-82'
assert_lacks "the dropped \`verified\` key takes its nested block lines with it" \
  "$MW/knowledge/decision/flow-mapping.md" 'by: human:yogev'
MWL=$(total_lines "$MW/knowledge/log.md")
MWI=$(total_lines "$MW/knowledge/index.md")
assert_present "the wrapped log bullet keeps its continuation line, indented under its bullet" \
  "$MW/knowledge/log.md" 1 "$MWL" '^  the first line break the way the flat entry matcher did\.$'
assert_present "a \`###\` sub-section the log schema forbids becomes a bullet, never a deletion" \
  "$MW/knowledge/log.md" 1 "$MWL" '^- \*\*A sub-section the log schema'
assert_absent "the bulletless \`# The bundle\` index section is dropped, not emitted" \
  "$MW/knowledge/index.md" 1 "$MWI" '^# The bundle$'
assert_present "every stable concept gets its index bullet, including \`gotcha/uncatalogued.md\`, which the client never catalogued" \
  "$MW/knowledge/index.md" 1 "$MWI" '^- \[.*\]\(gotcha/uncatalogued\.md\)'
assert_has "the client's own \`warnBytes\` survives the config rewrite" \
  "$MW/.claude/notion-dev.config.json" '"warnBytes": 65536'
run migrate-wrapped-check 0 check --dir "$MW/knowledge" --plugin-root "$ROOT"
rm -rf "$MW"

echo "== migrate: a failed post-apply check reverts every file AND every directory it created =="
MF=$(mktemp -d); cp -r "$FX/migrate-fail/." "$MF/"
( cd "$MF" && git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm base )
run migrate-fail 1 migrate --apply --dir "$MF/knowledge" --config "$MF/.claude/notion-dev.config.json" --plugin-root "$ROOT"
assert_has "the reverted apply's own output names the surviving finding" \
  "$OUT/migrate-fail.txt" 'ticket/STO-9.md: link: decision/missing'
diff -r -x .git "$FX/migrate-fail" "$MF" && echo "ok: reverted apply left no byte or directory changed" \
  || { echo "FAIL: reverted apply left stray files or directories behind"; fails=$((fails+1)); }
rm -rf "$MF"

echo
if [ "$fails" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "$fails CHECK(S) FAILED"; fi
exit $(( fails > 0 ? 1 : 0 ))
