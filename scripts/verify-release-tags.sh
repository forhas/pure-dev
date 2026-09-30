#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
fails=0
ok() { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }
. ./scripts/lib/assert.sh
PYBIN=${KNOWLEDGE_PY:-python3}
if PYTHONDONTWRITEBYTECODE=1 $PYBIN -m unittest discover -s scripts/tests -p 'test_release_tags.py'; then
  ok "release tags bind verified commits without overwrites"
else
  bad "release tags bind verified commits without overwrites"
fi
exit $(( fails > 0 ))
