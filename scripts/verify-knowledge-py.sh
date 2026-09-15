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

# `valid/` carries BOTH superseded_by spellings spec §3 resolves: `gotcha/old-trap.md` writes
# the bundle-root-relative form both clients store, `decision/legacy-cache.md` the
# concept-relative one. Resolving against either base alone makes `valid` exit 1.
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

echo "== check: an outward link to an EXTENSIONLESS file resolves to the exact path first =="
# iwe leaves `../LICENSE` as is (it only strips `.md`), so appending `.md` unconditionally
# would report a valid link as missing and block captures; the exact path must be tried first.
XL=$(mktemp -d); cp -r "$FX/valid" "$XL/knowledge"; printf 'MIT\n' > "$XL/LICENSE"
printf '\nSee [the licence](../../LICENSE).\n' >> "$XL/knowledge/epic/STO-1-demo-epic.md"
run ext-present 0 check --dir "$XL/knowledge" --plugin-root "$ROOT" --extra-types commitment
rm -f "$XL/LICENSE"
run ext-missing 1 check --dir "$XL/knowledge" --plugin-root "$ROOT" --extra-types commitment
assert_has "a missing extensionless target is still a finding" "$OUT/ext-missing.txt" 'link: ../LICENSE (outside bundle, not on disk)'
rm -rf "$XL"

echo "== check: warnBytes warns, never fails =="
run warn 0 check --dir "$FX/valid" --plugin-root "$ROOT" --extra-types commitment --warn-bytes 10
assert_has "a tiny warn-bytes produces warn lines" "$OUT/warn.txt" ': warn: '

echo "== check: iwe missing is exit 2 =="
# A bare `PATH=/nonexistent` breaks python3 (and this function's own `cat` fallback) too,
# since the override applies for the whole function call, not just the `iwe` lookup inside
# it — so build a PATH that keeps python3 and coreutils but drops iwe's directory instead.
PYDIR=$(dirname "$(command -v python3)")
PATH="$PYDIR:/usr/bin:/bin" run noiwe 2 check --dir "$FX/valid" --plugin-root "$ROOT"

echo "== check: fail closed — an iwe call that cannot run is exit 2, never an empty bundle =="
# `iwe find` exits non-zero on an unparseable .iwe/config.toml. Reading that as `"" or "[]"`
# reported a clean bundle — the "checks that pass when they cannot run" failure mode, inside
# the tool meant to replace it.
run unrunnable 2 check --dir "$FX/unrunnable-iwe-config" --plugin-root "$ROOT" --extra-types commitment
assert_has "the failed \`iwe find\` names its exit code rather than returning an empty result" \
  "$OUT/unrunnable.txt" 'iwe find --filter  -f json failed (exit 1)'

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
# A two-parent MERGE commit: `git show` lists nothing for it, so touched must diff against the
# first parent or every applies_to concept is skipped on a `mergeStrategy: merge` client.
( cd "$REPO" && git checkout -q -b topic && echo z > src/cache/c.rs && git add -A \
  && git -c user.name=t -c user.email=t@t commit -qm topic && git checkout -q - \
  && git -c user.name=t -c user.email=t@t merge -q --no-ff -m merge topic )
MSHA=$(git -C "$REPO" rev-parse HEAD)
[ "$(git -C "$REPO" rev-list --parents -n1 "$MSHA" | wc -w)" -eq 3 ] || { echo "FAIL: fixture merge commit is not two-parent"; fails=$((fails+1)); }
( cd "$REPO" && python3 "$OLDPWD/$PY" touched "$MSHA" --dir knowledge > "$OUT/touched-merge.txt" 2>&1 ); echo "exit $? (touched, merge commit)"
assert_has "touched lists the applies_to concept for a two-parent merge commit" "$OUT/touched-merge.txt" 'decision/keep-cache.md'
# A RENAME away from a matched path: `--name-only` reports only the destination, so the
# concept whose subject moved would never be re-read; both sides of an R record must count.
( cd "$REPO" && git mv src/cache/a.rs src/other/moved.rs && git -c user.name=t -c user.email=t@t commit -qm rename )
RSHA=$(git -C "$REPO" rev-parse HEAD)
( cd "$REPO" && python3 "$OLDPWD/$PY" touched "$RSHA" --dir knowledge > "$OUT/touched-rename.txt" 2>&1 ); echo "exit $? (touched, rename)"
assert_has "touched lists the concept whose applies_to path was renamed away" "$OUT/touched-rename.txt" 'decision/keep-cache.md'
rm -rf "$REPO"

echo "== migrate: dry run writes nothing, apply matches expected =="
# git-inited (and committed) because migrate step 5b enumerates `git ls-files '*.md'` to find
# and repoint external links to the moved brief; mirrors the touched-block setup above. `.git`
# itself is excluded from every byte-exact diff below, since the static fixtures on disk are
# plain directories, not repos.
M=$(mktemp -d); cp -r "$FX/migrate-input/." "$M/"
# CRLF is manufactured here, not stored: core.autocrlf=input would normalise a committed CRLF
# fixture to LF on the way in, so the on-disk fixture is LF and the temp copy gets its CRs
# back before migrate runs. The expected tree is LF, so the byte-exact diff below is what
# proves the migrated file was written with \n endings whatever it was read with.
sed -i 's/$/\r/' "$M/knowledge/ticket/STO-10.md"
( cd "$M" && git init -q && git -c core.autocrlf=false add -A && git -c user.name=t -c user.email=t@t commit -qm base )
run migrate-dry 0 migrate --dir "$M/knowledge" --config "$M/.claude/notion-dev.config.json" --plugin-root "$ROOT"
diff -r -x .git -x STO-10.md "$FX/migrate-input" "$M" >/dev/null && echo "ok: dry run left the tree byte-identical" \
  || { echo "FAIL: dry run modified the tree"; fails=$((fails+1)); }
CRS=$(tr -cd '\r' < "$M/knowledge/ticket/STO-10.md" | wc -c)
[ "$CRS" -gt 0 ] && echo "ok: dry run left the CRLF concept's $CRS CRs in place" \
  || { echo "FAIL: dry run rewrote the CRLF concept"; fails=$((fails+1)); }
assert_has "dry run prints a unified diff" "$OUT/migrate-dry.txt" '+++ '
run migrate-apply 0 migrate --apply --dir "$M/knowledge" --config "$M/.claude/notion-dev.config.json" --plugin-root "$ROOT"
diff -r -x .git "$FX/migrate-expected" "$M" && echo "ok: apply produced the expected tree" \
  || { echo "FAIL: apply differs from expected"; fails=$((fails+1)); }
CRS=$(tr -cd '\r' < "$M/knowledge/ticket/STO-10.md" | wc -c)
[ "$CRS" -eq 0 ] && echo "ok: apply wrote the CRLF concept back with LF endings" \
  || { echo "FAIL: apply left $CRS CRs in the migrated concept"; fails=$((fails+1)); }
run migrate-check 0 check --dir "$M/knowledge" --plugin-root "$ROOT"
# A bundle with no log.md is SEEDED, not left without one: the shipped log schema requires a
# dated group holding a bullet, so an unseeded bundle fails the check migrate has to pass.
ML=$(total_lines "$M/knowledge/log.md")
assert_present "migrate seeds a dated group into a bundle whose update log did not exist" \
  "$M/knowledge/log.md" 1 "$ML" '^## [0-9]{4}-[0-9]{2}-[0-9]{2}$'
assert_present "that seeded log carries the \`- bundle created\` bullet the shipped schema needs" \
  "$M/knowledge/log.md" 1 "$ML" '^- bundle created$'
rm -rf "$M"

echo "== migrate: a post-apply check that cannot run still restores the tree =="
# `check` dying (exit 2: iwe missing) after the apply wrote files must leave the tree as it was.
MX=$(mktemp -d); cp -r "$FX/migrate-input/." "$MX/"
( cd "$MX" && git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm base )
FAKE=$(mktemp -d); printf '#!/bin/sh\ncase "$*" in *"schema validate"*|*find*) exit 2;; esac\nexec %s "$@"\n' "$(command -v iwe)" > "$FAKE/iwe"; chmod +x "$FAKE/iwe"
PATH="$FAKE:$PATH" run migrate-check-dies 2 migrate --apply --dir "$MX/knowledge" --config "$MX/.claude/notion-dev.config.json" --plugin-root "$ROOT"
diff -r -x .git "$FX/migrate-input" "$MX" >/dev/null && echo "ok: a dying post-apply check restored the tree byte-identically" \
  || { echo "FAIL: a dying post-apply check left the migration in place"; fails=$((fails+1)); }
rm -rf "$MX" "$FAKE"

echo "== migrate: a brief whose epic concept already exists is a collision, not an overwrite =="
MC=$(mktemp -d); cp -r "$FX/migrate-collide/." "$MC/"
( cd "$MC" && git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm base )
run migrate-collide-dry 1 migrate --dir "$MC/knowledge" --config "$MC/.claude/notion-dev.config.json" --plugin-root "$ROOT"
assert_has "collision names the destination, the source, and the rule" "$OUT/migrate-collide-dry.txt" 'knowledge/epic/STO-9-demo.md: migrate: collides with docs/epics/STO-9-demo.md'
run migrate-collide-apply 1 migrate --apply --dir "$MC/knowledge" --config "$MC/.claude/notion-dev.config.json" --plugin-root "$ROOT"
diff -r -x .git "$FX/migrate-collide" "$MC" >/dev/null && echo "ok: a colliding apply wrote nothing" \
  || { echo "FAIL: a colliding apply modified the tree"; fails=$((fails+1)); }
rm -rf "$MC"

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
  "$MW/.claude/notion-dev.config.json" '"warnBytes": 200'
assert_has "migrate's post-apply check honours the configured \`warnBytes\`, not a hardcoded 8192" \
  "$OUT/migrate-wrapped.txt" 'exceeds warnBytes 200'
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

echo "== next: renders ## Next, the header and the stop bullet deterministically =="
NX=$FX/next
TODAY=2026-09-15
nx() { # name, expected-exit, brief, state, [reason args...]
  local name=$1 want=$2 brief=$3 state=$4; shift 4
  python3 "$PY" next --brief "$brief" --state "$state" --today "$TODAY" "$@" \
    > "$OUT/next-$name.md" 2> "$OUT/next-$name.err"; local got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL: next-$name exited $got, wanted $want"; cat "$OUT/next-$name.err"; fails=$((fails+1))
  else echo "ok: next-$name exit $got"; fi
}
nx basic    0 "$NX/brief.md"          "$NX/state-basic.json"
assert_identical "next: a true brief re-renders byte-identical" "$OUT/next-basic.md" "$NX/brief.md"
assert_has "next: a true brief reports DRIFT: 0" "$OUT/next-basic.err" 'DRIFT: 0'
nx start    1 "$NX/brief.md"          "$NX/state-start.json"    --reason start STO-71
assert_identical "next: start moves the key to In progress with today's since and keeps the other since" \
  "$OUT/next-start.md" "$NX/expected-start.md"
nx stop     1 "$NX/brief.md"          "$NX/state-stop.json"     --reason stop STO-72
assert_identical "next: stop adds the thread bullet and moves the key to Blocked" \
  "$OUT/next-stop.md" "$NX/expected-stop.md"
nx restart  1 "$NX/expected-stop.md"  "$NX/state-basic.json"    --reason start STO-72
assert_identical "next: start removes the stop bullet and restores In progress" \
  "$OUT/next-restart.md" "$NX/expected-restart.md"
nx create   1 "$NX/brief.md"          "$NX/state-create.json"   --reason create STO-74
assert_identical "next: create appends the new child as ready" "$OUT/next-create.md" "$NX/expected-create.md"
assert_has "next: create reports the missing key as drift" "$OUT/next-create.err" 'drift: STO-74 missing from ## Next'
nx drift    1 "$NX/brief-drift.md"    "$NX/state-basic.json"
assert_identical "next: drift repairs a resolved item, a missing child and the In progress line" \
  "$OUT/next-drift.md" "$NX/expected-drift.md"
assert_has "next: drift names the resolved item"   "$OUT/next-drift.err" 'drift: STO-70 listed, live status resolved'
assert_has "next: drift names the missing child"   "$OUT/next-drift.err" 'drift: STO-73 missing from ## Next'
assert_has "next: drift names the missing In progress line" "$OUT/next-drift.err" 'drift: In progress line missing'
assert_has "next: drift counts four findings"      "$OUT/next-drift.err" 'DRIFT: 4'
nx complete 1 "$NX/brief.md"          "$NX/state-complete.json"
assert_identical "next: a resolved epic renders epic complete and Status: closed" \
  "$OUT/next-complete.md" "$NX/expected-complete.md"
nx rerender 0 "$OUT/next-start.md"    "$NX/state-start.json"
assert_identical "next: re-rendering its own output is byte-identical" "$OUT/next-rerender.md" "$OUT/next-start.md"
nx client   1 "$NX/brief.md"          "$NX/state-client-shaped.json"
# partition invariant: every unresolved key appears in exactly one of the three lists
if python3 - "$NX/state-client-shaped.json" "$OUT/next-client.md" <<'PYEOF'
import json, re, sys
state = json.load(open(sys.argv[1])); text = open(sys.argv[2], encoding="utf-8").read()
region = text.split("\n## Next\n", 1)[1].split("\n## ", 1)[0].splitlines()
num = [m.group(1) for ln in region for m in [re.match(r"^\d+\. (?:\*\*)?\[([A-Z0-9-]+)\]", ln)] if m]
ip = re.findall(r"\[([A-Z0-9-]+)\] [^,]*? — since \d{4}-\d{2}-\d{2}", next((l for l in region if l.startswith("In progress: ")), ""))
bl = re.findall(r"[A-Z][A-Z0-9]+-\d+", next((l for l in region if l.startswith("Blocked: ")), ""))
want = sorted(c["key"] for c in state["children"] if c["status_class"] != "resolved")
got = sorted(num + ip + bl)
sys.exit(0 if got == want else print("partition:", got, "wanted", want))
PYEOF
then ok "next: client-shaped partitions every unresolved child exactly once"; else bad "next: client-shaped partition is wrong"; fi
printf 'no next heading\n' > "$OUT/next-bad.md"
nx malformed 2 "$OUT/next-bad.md" "$NX/state-basic.json"
nx stop-bad 2 "$NX/brief.md" "$NX/state-stop-bad.json" --reason stop STO-72
nx unknown-key 2 "$NX/brief.md" "$NX/state-basic.json" --reason start STO-999
nx wrapped 1 "$NX/brief-wrapped.md" "$NX/state-basic.json"
assert_has "next: a wrapped item keeps its preserved reason" "$OUT/next-wrapped.md" \
  '1. **[STO-71] Cache metrics** — unblocked; STO-70 landed.'
assert_has "next: joining a wrapped item is not drift" "$OUT/next-wrapped.err" 'DRIFT: 0'

# A header Status that disagrees with the live epic is repaired, not merely reported: with
# `## Next` already true nothing else changes, so the rewrite has to be driven by the header
# mismatch itself, and the exit status has to say the brief differs.
sed 's/ Status: open / Status: closed /' "$NX/brief.md" > "$OUT/brief-header-only.md"
nx header-only 1 "$OUT/brief-header-only.md" "$NX/state-basic.json"
assert_has "next: a header-only mismatch is reported as drift" "$OUT/next-header-only.err" \
  'drift: header Status closed, live open'
assert_has "next: a header-only mismatch rewrites the stale header" "$OUT/next-header-only.md" \
  'Status: open · Updated: 2026-09-15 after refresh'

nx comma 0 "$NX/brief-comma.md" "$NX/state-comma.json"
assert_has "next: a comma in an in-progress title keeps its since date" "$OUT/next-comma.md" \
  'In progress: [STO-72] Backfill, v2 — since 2026-09-14'
assert_has "next: a comma in a title is not drift" "$OUT/next-comma.err" 'DRIFT: 0'

sed '/^## Open threads$/,/^## Decisions & constraints$/{/^## Decisions & constraints$/!d}' \
  "$NX/brief.md" > "$OUT/brief-nothreads.md"
nx start-nothreads 1 "$OUT/brief-nothreads.md" "$NX/state-start.json" --reason start STO-71

printf '%s' "$(cat "$NX/brief.md")" > "$OUT/no-nl.md"
nx no-nl 0 "$OUT/no-nl.md" "$NX/state-basic.json"
assert_identical "next: a brief without a trailing newline stays byte-identical" \
  "$OUT/next-no-nl.md" "$OUT/no-nl.md"

nx order 1 "$NX/brief.md" "$NX/state-order.json"
assert_has "next: ordering puts phase 1 before phase 2 (item 1)" "$OUT/next-order.md" '1. **[STO-80]'
assert_has "next: ordering puts phase 2 step 1 before phase 2 step 2 (item 2)" "$OUT/next-order.md" '2. [STO-79]'
assert_has "next: ordering keeps phase 2 step 2 after step 1 (item 3)" "$OUT/next-order.md" '3. [STO-71]'

echo "== lock: mkdir lock on the primary checkout =="
LK=$(mktemp -d)
lk() { # name, expected-exit, args...
  local name=$1 want=$2; shift 2
  python3 "$PY" lock "$@" --root "$LK" > "$OUT/lock-$name.txt" 2>&1; local got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL: lock-$name exited $got, wanted $want"; cat "$OUT/lock-$name.txt"; fails=$((fails+1))
  else echo "ok: lock-$name exit $got"; fi
}
lk status-free 0 status
assert_has "lock: status reports free"                    "$OUT/lock-status-free.txt" 'free'
lk take-a 0 take --run STO-70 --section record --wait 0
assert_has "lock: owner file names the run"               "$LK/primary/owner" 'run: STO-70'
assert_has "lock: owner file names the section"           "$LK/primary/owner" 'section: record'
lk take-b 1 take --run STO-71 --section start --wait 0
assert_has "lock: a second run is told the holder"        "$OUT/lock-take-b.txt" 'held by STO-70 (record) since'
lk take-a-again 0 take --run STO-70 --section record --wait 0
assert_has "lock: the holder re-enters"                   "$OUT/lock-take-a-again.txt" 'reentrant'
lk release-b 1 release --run STO-71
assert_has "lock: release by another run is refused"      "$OUT/lock-release-b.txt" 'held by STO-70'
lk release-a 0 release --run STO-70
lk status-free-2 0 status
assert_has "lock: released reports free"                  "$OUT/lock-status-free-2.txt" 'free'
lk release-none 1 release --run STO-70
assert_has "lock: release when free says not held"        "$OUT/lock-release-none.txt" 'not held'
mkdir -p "$LK/primary"
printf 'run: STO-9\nsection: record\nsince: 2000-01-01T00:00:00Z\n' > "$LK/primary/owner"
lk take-stale 0 take --run STO-71 --section start --wait 0
assert_has "lock: an abandoned owner is broken and named" "$OUT/lock-take-stale.txt" 'stale: run: STO-9'
assert_has "lock: after breaking, the new run holds it"   "$LK/primary/owner" 'run: STO-71'
lk release-71 0 release --run STO-71
mkdir -p "$LK/primary"; : > "$LK/primary/owner"           # empty owner, fresh directory = in creation
lk take-creating 1 take --run STO-71 --section start --wait 0
assert_has "lock: an owner still being written is waited on, not broken" "$OUT/lock-take-creating.txt" 'held by'
touch -d '2000-01-01 00:00:00' "$LK/primary"              # same empty owner, but the directory is old
lk take-orphan 0 take --run STO-71 --section start --wait 0
assert_has "lock: an orphaned empty owner ages out by directory mtime" "$OUT/lock-take-orphan.txt" 'stale: run: ?'
lk release-orphan 0 release --run STO-71
[ -z "$(ls -d "$LK"/primary.stale-* 2>/dev/null)" ] && ok "lock: no stale-break leftovers remain" || bad "lock: stale-break leftovers remain"
rm -rf "$LK"

echo "== write path: a rejected push converges by re-deriving against the fresh brief =="
CV=$(mktemp -d)
G="git -c user.name=t -c user.email=t@t -c init.defaultBranch=main -c commit.gpgsign=false"
$G init -q --bare "$CV/origin.git"
$G clone -q "$CV/origin.git" "$CV/a" 2>/dev/null
mkdir -p "$CV/a/knowledge/epic"; cp "$NX/brief.md" "$CV/a/knowledge/epic/STO-60-wallet-indexing.md"
( cd "$CV/a" && $G add -A && $G commit -q -m seed && $G push -q origin main ) 2>/dev/null
$G clone -q "$CV/origin.git" "$CV/b" 2>/dev/null
B=knowledge/epic/STO-60-wallet-indexing.md
# A: create STO-74 and push
python3 "$PY" next --brief "$CV/a/$B" --state "$NX/state-converge-a.json" --today 2026-09-14 --reason create STO-74 > "$CV/a/out.md" 2>/dev/null
cp "$CV/a/out.md" "$CV/a/$B"
( cd "$CV/a" && $G commit -q --only -m "docs(epic): STO-60 create STO-74" -- "$B" && $G push -q origin main ) 2>/dev/null \
  && ok "write path: A's commit and push land" || bad "write path: A's commit or push failed"

# B, stale clone: start STO-71, push rejected
python3 "$PY" next --brief "$CV/b/$B" --state "$NX/state-converge-b.json" --today 2026-09-15 --reason start STO-71 > "$CV/b/out.md" 2>/dev/null
cp "$CV/b/out.md" "$CV/b/$B"
( cd "$CV/b" && $G commit -q --only -m "docs(epic): STO-60 start STO-71" -- "$B" ) 2>/dev/null
if ( cd "$CV/b" && $G push -q origin main ) 2>/dev/null; then bad "write path: B's stale push should be rejected"; else ok "write path: B's stale push is rejected"; fi
# the recipe: exactly one local commit ahead, fetch, reset --hard, re-derive, commit, push
( cd "$CV/b" && $G fetch -q origin main && n=$($G rev-list origin/main..HEAD | wc -l | tr -d ' ') && [ "$n" -eq 1 ] ) \
  && ok "write path: rev-list shows exactly one local commit before the reset" || bad "write path: rev-list count is not 1"
( cd "$CV/b" && $G reset -q --hard origin/main ) 2>/dev/null
python3 "$PY" next --brief "$CV/b/$B" --state "$NX/state-converge-b.json" --today 2026-09-15 --reason start STO-71 > "$CV/b/out2.md" 2>/dev/null
cp "$CV/b/out2.md" "$CV/b/$B"
( cd "$CV/b" && $G commit -q --only -m "docs(epic): STO-60 start STO-71" -- "$B" && $G push -q origin main ) 2>/dev/null \
  && ok "write path: the re-derived commit pushes (ATTEMPTS: 2)" || bad "write path: second push failed"
$G clone -q "$CV/origin.git" "$CV/c" 2>/dev/null
assert_has "write path: origin carries B's start"          "$CV/c/$B" 'In progress: [STO-71] Cache metrics — since 2026-09-15, [STO-72] Backfill v2 — since 2026-09-14'
assert_has "write path: origin still carries A's created child" "$CV/c/$B" '2. [STO-74] Dashboards — ready'
assert_has "write path: the header names B's start"        "$CV/c/$B" 'after start [STO-71]'
( cd "$CV/c" && $G log --format=%s ) > "$OUT/cv-log.txt"
assert_lacks "write path: no merge commit was manufactured" "$OUT/cv-log.txt" 'Merge'
rm -rf "$CV"

echo
if [ "$fails" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "$fails CHECK(S) FAILED"; fi
exit $(( fails > 0 ? 1 : 0 ))
