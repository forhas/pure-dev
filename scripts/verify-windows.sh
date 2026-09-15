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
for f in commands/ticket.md commands/next-task.md commands/new-info.md commands/finalize.md commands/create-task.md commands/knowledge.md skills/knowledge/SKILL.md skills/epic-doc/SKILL.md; do
  n=$(total_lines "$ND/$f")
  assert_present "$f: python3 stands for knowledge.python" "$ND/$f" 1 "$n" '`python3` in every `knowledge.py` line below stands for `knowledge.python`'
done
assert_has "knowledge.py: forces LF and UTF-8 on stdout and stderr" "$KPY" 'reconfigure(newline="\n", encoding="utf-8")'
assert_has "gitattributes: LF everywhere" .gitattributes '* text=auto eol=lf'
assert_has "workflow: a windows-latest job runs verify-knowledge-py.sh under bash" "$WF" 'runs-on: windows-latest'
WFL=$(total_lines "$WF"); WJ0=$(find_line "$WF" 1 "$WFL" '^  verify-windows:$')
assert_present "workflow: the windows-latest job's run line invokes verify-knowledge-py.sh" "$WF" "$WJ0" "$WFL" 'run: bash scripts/verify-knowledge-py.sh'
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

if [ "$fails" -gt 0 ]; then echo "verify-windows: $fails FAIL"; exit 1; fi
echo "verify-windows: all PASS"
