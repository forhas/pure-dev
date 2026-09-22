#!/usr/bin/env bash
# Shared local/CI entrypoint. A failed (or absent) harness can never report success.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
shopt -s nullglob
scripts=(scripts/verify-*.sh)
if [ "${#scripts[@]}" -eq 0 ]; then
  echo "No verification harnesses found."
  exit 1
fi
failed=0
for harness in "${scripts[@]}"; do
  echo "::group::$harness"
  if bash "$harness"; then
    echo "$harness: OK"
  else
    echo "$harness: FAILED"
    failed=$((failed + 1))
  fi
  echo "::endgroup::"
done
if [ "$failed" -gt 0 ]; then
  echo "$failed harness(es) failed."
  exit 1
fi
echo "All ${#scripts[@]} harness(es) passed."
