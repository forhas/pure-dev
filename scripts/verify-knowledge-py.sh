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

echo "== touched: fixture repo =="
REPO=$(mktemp -d); cp -r "$FX/valid" "$REPO/knowledge"; mkdir -p "$REPO/src/cache" "$REPO/src/other"
( cd "$REPO" && git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm base \
  && echo x > src/cache/a.rs && echo y > src/other/b.rs && git add -A \
  && git -c user.name=t -c user.email=t@t commit -qm touch )
SHA=$(git -C "$REPO" rev-parse HEAD)
( cd "$REPO" && python3 "$OLDPWD/$PY" touched "$SHA" --dir knowledge > "$OUT/touched.txt" 2>&1 ); echo "exit $? (touched)"
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
