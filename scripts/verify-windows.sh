#!/usr/bin/env bash
# Windows CLI support — notion-dev works from a Windows-native Claude Code session (Git Bash)
# exactly as it does from WSL: the `knowledge.python` config key `/notion-dev:init` writes and
# every command reads, LF-forced knowledge.py output, a repo-wide .gitattributes, a
# windows-latest CI job for the script harness, and README prerequisites.
#
# Spec: this PR's brief (Windows CLI support for notion-dev).
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev; SCHEMA=$ND/schema/notion-dev.config.schema.json; INIT=$ND/commands/init.md; README=$ND/README.md; KPY=$ND/scripts/knowledge.py; WF=.github/workflows/verify.yml
assert_has "schema: knowledge.python key with default python3" "$SCHEMA" '"python": { "type": "string", "default": "python3"'
L=$(total_lines "$INIT")
assert_present "init: probes python3, python, py -3 in order and records PYTHON_CMD" "$INIT" 1 "$L" 'python3 --version.*python --version.*py -3 --version.*PYTHON_CMD'
assert_present "init: detects Git Bash via uname -s (MINGW/MSYS) and names the Windows install routes" "$INIT" 1 "$L" 'uname -s.*MINGW.*MSYS.*Git for Windows.*Git Bash.*npm i -g @iwe-org/iwe.*winget install Python'
assert_present "init: writes python: <PYTHON_CMD> into the knowledge block" "$INIT" 1 "$L" 'python: <PYTHON_CMD>'
# The omit rules are the mechanism, not the write: a placeholder written when the probe
# found nothing fails the schema's minLength and outlives the missing interpreter.
assert_present "init: writes \`python: <PYTHON_CMD>\` only when the probe recorded one, omitting it when no interpreter was found" \
  "$INIT" 1 "$L" 'python: <PYTHON_CMD>.*only when step 1.s probe actually recorded .PYTHON_CMD.*omitted when no interpreter was found'
assert_present "init: omits it again when the recorded value equals the default \`python3\`" \
  "$INIT" 1 "$L" 'omitted again when the recorded value equals that default .python3.'
for f in commands/ticket.md commands/next-task.md commands/new-info.md commands/finalize.md commands/create-task.md commands/knowledge.md skills/knowledge/SKILL.md skills/epic-doc/SKILL.md; do
  n=$(total_lines "$ND/$f")
  assert_present "$f: python3 stands for knowledge.python" "$ND/$f" 1 "$n" '`python3` in every `knowledge.py` line below stands for `knowledge.python`'
done
assert_has "knowledge.py: forces LF and UTF-8 on stdout and stderr" "$KPY" 'reconfigure(newline="\n", encoding="utf-8")'
KPYL=$(total_lines "$KPY")
KI0=$(find_line "$KPY" 1 "$KPYL" '^def iwe\(args, cwd, violations_exit=\(\)\):$')
KI1=$(find_line "$KPY" "$KI0" "$KPYL" '^def iwe_json\(')
assert_present "knowledge.py: the iwe capture decodes the child's output as \`encoding="utf-8"\`, not the locale code page" "$KPY" "$KI0" "$KI1" 'encoding="utf-8"\)$'
# The Windows retry must not be a blanket OSError catch: a vanished directory (a breaker
# retired this lock as stale) and a sharing violation need opposite answers, and retrying
# the first one can move a successor's lock aside.
assert_has "knowledge.py: a vanished lock directory has its own handler, never the retry" "$KPY" 'except FileNotFoundError:'
assert_has "knowledge.py: only a \`PermissionError\` retries the release rename" "$KPY" 'except PermissionError:'
assert_present "knowledge.py: the retry re-reads the owner before renaming again" "$KPY" "$KI0" "$KPYL" '_read_owner\(d\).get\("run"\) != a.run'
assert_has "gitattributes: LF everywhere" .gitattributes '* text=auto eol=lf'
assert_has "workflow: a windows-latest job runs the harnesses under bash" "$WF" 'runs-on: windows-latest'
WFL=$(total_lines "$WF"); WJ0=$(find_line "$WF" 1 "$WFL" '^  verify-windows:$')
# The Windows leg runs the WHOLE suite, discovered by glob, not one named harness. Pinning the
# glob rather than a filename is what keeps a new scripts/verify-*.sh covered on Windows the
# day it is added: a job listing harnesses by name silently leaves each new one Ubuntu-only,
# which is exactly the gap this job had while it invoked verify-knowledge-py.sh alone.
assert_present "workflow: the windows-latest job discovers the harnesses with scripts/verify-*.sh" "$WF" "$WJ0" "$WFL" 'scripts=\(scripts/verify-[*][.]sh\)'
assert_present "workflow: the windows-latest job runs each discovered harness with bash" "$WF" "$WJ0" "$WFL" 'if bash "\$s"; then'
assert_present "workflow: the windows-latest job fails when any harness fails" "$WF" "$WJ0" "$WFL" 'harness\(es\) failed'
assert_present "workflow: the windows-latest job runs under \`shell: bash\`" "$WF" "$WJ0" "$WFL" 'shell: bash'
assert_has "workflow: the Windows job sets KNOWLEDGE_PY" "$WF" 'KNOWLEDGE_PY: python'
assert_has "verify-knowledge-py.sh: interpreter overridable via KNOWLEDGE_PY" scripts/verify-knowledge-py.sh 'PYBIN=${KNOWLEDGE_PY:-python3}'
KPS=scripts/verify-knowledge-py.sh
assert_lacks "verify-knowledge-py.sh: no hardcoded python3 invocation remains" "$KPS" 'python3 "$PY"'
assert_lacks "verify-knowledge-py.sh: no hardcoded python3 invocation of \$PYABS remains" "$KPS" 'python3 "$PYABS"'
assert_lacks "verify-knowledge-py.sh: no hardcoded python3 invocation via \$OLDPWD remains" "$KPS" 'python3 "$OLDPWD/'
assert_lacks "verify-knowledge-py.sh: no hardcoded python3 heredoc invocation remains" "$KPS" 'python3 -'
assert_has "README: Git for Windows prerequisite" "$README" 'Git for Windows'
assert_has "README: knowledge.python documented" "$README" 'knowledge.python'
LE=$(total_lines "$ND/skills/epic-doc/SKILL.md")
assert_present "epic-doc: Windows rename note on the lock" "$ND/skills/epic-doc/SKILL.md" 1 "$LE" 'On Windows.*renaming the lock directory can fail while another process holds a handle'

# The Stop guard runs on EVERY stop in every session, on both platforms, and a
# hook that errors on one of them is a hook nobody sees fail. Its behaviour is
# exercised by verify-stop-guard.sh; what belongs here is the platform contract.
GUARD=$ND/hooks/stop-guard.sh
GUARDCODE=$(mktemp)
sed 's/^[[:space:]]*#.*$//' "$GUARD" > "$GUARDCODE"
assert_has  "stop-guard: runs under \`#!/usr/bin/env bash\`, not a Windows shell" "$GUARD" '#!/usr/bin/env bash'
assert_lacks "stop-guard: no \`date -d\` (GNU-only date arithmetic)"   "$GUARDCODE" 'date -d'
assert_lacks "stop-guard: no \`stat -c\`"                              "$GUARDCODE" 'stat -c'
assert_lacks "stop-guard: no \`readlink -f\`"                          "$GUARDCODE" 'readlink -f'
assert_has  "stop-guard: freshness from file mtime via \`-mmin\`, never a parsed timestamp" "$GUARDCODE" '-mmin'
assert_lacks "stop-guard: takes no \`jq\` dependency"                  "$GUARDCODE" 'jq '
assert_has  "hooks.json: the command is invoked through \`bash\` so Windows does not pick the interpreter" \
  "$ND/hooks/hooks.json" '"command": "bash '
rm -f "$GUARDCODE"

if [ "$fails" -gt 0 ]; then echo "verify-windows: $fails FAIL"; exit 1; fi
echo "verify-windows: all PASS"
