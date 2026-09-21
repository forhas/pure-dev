#!/usr/bin/env bash
# Standing invariant: the Python version floor this plugin ADVERTISES is the floor
# its shipped scripts are actually CHECKED against, by a harness rather than by
# someone remembering.
#
# Why this exists (issue #69): the README declared "Python 3.8+" and pull requests
# asserted that "Python 3.8 grammar checks passed", but `grep -rn feature_version
# scripts/` returned nothing -- no harness ran one. The claim was re-checked by
# whoever remembered, which by this repo's standard is not re-checked at all.
#
# Two distinct things are needed and this file provides the first, while asserting
# the second is wired:
#
#   GRAMMAR (here, every platform, every push) -- a CHEAP EARLY FILTER whose reach is
#   both narrower than the name suggests AND NOT FIXED: it depends on the interpreter
#   running this harness. Measured with ast.parse(feature_version=(3,8)) on real releases:
#
#                                    3.10    3.11    3.12    3.13
#     match statement      (3.10)    REJECT  REJECT  REJECT  REJECT
#     parenthesized with   (3.9)     REJECT  accept  accept  accept
#     except*              (3.11)    REJECT  REJECT  REJECT  REJECT
#     X | Y annotation     (3.10)    accept  accept  accept  accept
#     list[str] annotation (3.9)     accept  accept  accept  accept
#     str.removeprefix     (3.9)     accept  accept  accept  accept
#
#   So it reliably catches `match` and `except*`, reliably misses the annotation forms,
#   and its verdict on parenthesized context managers CHANGES WITH THE RUNNER. Whatever
#   Python CI ships tomorrow may shift that row again. This is a smoke test, not the
#   authority, and it must not be described as one.
#
#   (An earlier revision of this comment had two of those rows inverted, because they were
#   measured on a 3.11.0rc1 build that disagrees with every released CPython. Re-measure
#   against releases before editing the table.)
#
#   EXECUTION (the workflow job, a real 3.8 interpreter) -- THE AUTHORITY, for two
#   reasons. Under 3.8 itself, `ast.parse` simply is the 3.8 grammar, so it catches the
#   whole syntax surface this harness cannot. And syntax is not runtime:
#   `str.removeprefix`, `functools.cache`, `math.lcm`, `itertools.pairwise` and `zoneinfo`
#   all parse on 3.8 and die when called. Only the interpreter sees those.
#
#   This harness therefore asserts that job is still wired, which is the check that
#   actually protects the floor.
#
# The floor is READ FROM THE README, never hardcoded here. Hardcoding it would
# recreate the drift this file exists to stop: the doc could say 3.9 while the check
# kept testing 3.8, and both would be green.
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

. ./scripts/lib/assert.sh

# python3, python, or "py -3" — the same value /notion-dev:init records as
# knowledge.python, and the same convention verify-knowledge-py.sh uses, so this
# harness runs on the Windows leg where `python3` may not resolve.
PYBIN=${KNOWLEDGE_PY:-python3}
$PYBIN --version >/dev/null 2>&1 || { echo "FAIL: $PYBIN not runnable"; exit 1; }

README=plugins/notion-dev/README.md
WORKFLOW=.github/workflows/verify.yml

echo "== the floor is declared once, in the README =="
assert_has "README declares the Python floor as a requirement" \
  "$README" '**Python 3.8+** — **required**'

echo "== smoke filter: no clearly-newer syntax in any shipped script ==" 
$PYBIN - "$README" <<'PY'
import ast, pathlib, re, sys

readme = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
m = re.search(r"\*\*Python (\d+)\.(\d+)\+\*\* — \*\*required\*\*", readme)
if not m:
    print("  FAIL  could not read the declared floor out of the README")
    raise SystemExit(1)
floor = (int(m.group(1)), int(m.group(2)))
print("  PASS  floor read from the README: %d.%d" % floor)

# Shipped scripts are what the claim is about. Test files are included because the
# execution job below runs them: if a test used newer syntax the job would fail for
# a reason that says nothing about the shipped code.
targets = sorted(pathlib.Path("plugins").rglob("*.py")) + sorted(pathlib.Path("scripts/tests").glob("*.py"))
targets = [p for p in targets if "__pycache__" not in p.parts]
if not targets:
    print("  FAIL  no Python files discovered — the glob is wrong, not the code")
    raise SystemExit(1)

bad = 0
for p in targets:
    try:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p), feature_version=floor)
        print("  PASS  %s clears the %d.%d smoke filter" % (p, *floor))
    except SyntaxError as e:
        print("  FAIL  %s does not parse at %d.%d: %s" % (p, *floor, e))
        bad += 1
raise SystemExit(1 if bad else 0)
PY
[ $? -eq 0 ] || fails=$((fails + 1))

echo "== grammar is not execution: the interpreter job stays wired =="
# Without this, the expensive half of #69 could be deleted from the workflow and
# every check here would still pass, leaving the README's claim resting on a
# grammar check that cannot see a 3.9-only method call.
assert_has "the workflow runs the suite on a real interpreter at the floor" \
  "$WORKFLOW" 'python-version: "3.8"'
assert_has "that job is named for the floor it enforces" \
  "$WORKFLOW" 'verify-python-floor:'
# Name + version alone is not enough: deleting only the run step leaves a job that sets up
# 3.8 and executes nothing, with every check above still green. Pin the work itself.
assert_has "the floor job runs the test suite on that interpreter" \
  "$WORKFLOW" "unittest discover -s scripts/tests"
assert_has "the floor job runs knowledge.py, which the README names for the floor" \
  "$WORKFLOW" 'bash scripts/verify-knowledge-py.sh'
assert_has "the floor job asserts the interpreter it actually got" \
  "$WORKFLOW" 'expected a 3.8 interpreter'
# This harness calls Python, so it must itself run on the floor. The other two jobs only
# ever run it on the runner's newer interpreter, so without this line that compatibility
# is verified by hand or not at all.
assert_has "the floor job runs this harness on the floor interpreter too" \
  "$WORKFLOW" 'bash scripts/verify-python-floor.sh'

echo
if [ "$fails" -eq 0 ]; then
  echo "All checks passed."
else
  echo "$fails CHECK(S) FAILED"
fi
exit $((fails > 0))
