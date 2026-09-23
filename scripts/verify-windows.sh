#!/usr/bin/env bash
# Historical contracts below cover opt-in legacy flows; verify-lean-workflow.sh covers the new default.
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
. ./scripts/lib/instruction-view.sh

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
for f in commands/ticket.md commands/next-task.md commands/new-info.md commands/finalize.md commands/create-task.md commands/knowledge.md skills/knowledge/references/common.md skills/epic-doc/references/refresh.md; do
  n=$(total_lines "$ND/$f")
  case "$f" in commands/ticket.md|commands/next-task.md|commands/finalize.md)
    assert_has "$f: interpreter comes from configuration" "$ND/$f" 'knowledge.python'
    continue ;;
  esac
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
# A line-based diff of the brief is a Windows defect, not a nicety. Git for Windows checks
# the brief out CRLF while knowledge.py forces LF on stdout, so `diff` reports 100% changed
# whatever the repair — measured as `1,137c1,137` in a client run, ~5k tokens to report a
# two-line drift. The file is hard-wrapped, so each assertion matches inside one line.
ED=$(instruction_view epic-doc); EDL=$(total_lines "$ED")
assert_present "epic-doc: the brief's change list is the stderr listing, never a diff of the rendered brief" \
  "$ED" 1 "$EDL" 'Never diff the rendered brief against the old one to see what changed'
assert_present "epic-doc: a CRLF checkout against LF stdout is why a line diff reports every line" \
  "$ED" 1 "$EDL" 'CRLF \(`core\.autocrlf=true`\) while `knowledge\.py` forces LF on its stdout'

assert_has "gitattributes: LF everywhere" .gitattributes '* text=auto eol=lf'
assert_has "workflow: a windows-latest job runs the harnesses under bash" "$WF" 'runs-on: windows-latest'
WFL=$(total_lines "$WF"); WJ0=$(find_line "$WF" 1 "$WFL" '^  verify-windows:$')
# The Windows leg runs the WHOLE suite, discovered by glob, not one named harness. Pinning the
# glob rather than a filename is what keeps a new scripts/verify-*.sh covered on Windows the
# day it is added: a job listing harnesses by name silently leaves each new one Ubuntu-only,
# which is exactly the gap this job had while it invoked verify-knowledge-py.sh alone.
assert_present "workflow: Windows uses the shared run-verifications.sh runner" "$WF" "$WJ0" "$WFL" 'run: bash scripts/run-verifications[.]sh'
assert_count "workflow: both platform jobs use run-verifications.sh" "$WF" 1 "$WFL" 'run: bash scripts/run-verifications[.]sh' 2
assert_has "runner discovers scripts/verify-*.sh" scripts/run-verifications.sh 'scripts=(scripts/verify-*.sh)'
assert_has "runner tests each harness exit status" scripts/run-verifications.sh 'if bash "$harness"; then'
assert_has "runner checks aggregate failures" scripts/run-verifications.sh 'if [ "$failed" -gt 0 ]; then'
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
LE=$(total_lines "$ED")
assert_present "epic-doc: Windows rename note on the lock" "$ED" 1 "$LE" 'On Windows.*renaming the lock directory can fail while another process holds a handle'

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

# Runtime/telemetry use the same interpreter contract; behavioral fixtures are
# discovered by the existing Windows job through verify-runtime.sh.
for helper in runtime telemetry dependencies workflow; do
  assert_has "$helper forces UTF-8 and LF output" "$ND/scripts/$helper.py" 'stream.reconfigure(encoding="utf-8", newline="\n")'
done
assert_has "runtime protocol uses the configured interpreter" "$ND/references/legacy/runtime.md" '`knowledge.python` interpreter'
assert_has "runtime harness supports Windows interpreter selection" scripts/verify-runtime.sh 'PYBIN=${KNOWLEDGE_PY:-python3}'

# A bare `bash` is not the Git for Windows bash. Windows `CreateProcess` — what
# `subprocess.run` uses with `shell=False` — searches System32 BEFORE PATH, so the name
# resolves to the WSL launcher stub, which exits 1 without running anything. Both Python
# spawn sites resolve the interpreter instead, or the runtime records a verification that
# never ran as a failure and the Stop-guard regression fails on Windows alone.
assert_has  "runtime resolves the bash interpreter rather than trusting the bare name" "$ND/scripts/runtime.py" 'shutil.which("bash")'
assert_has  "runtime verification spawns the resolved interpreter" "$ND/scripts/runtime.py" 'subprocess.run([bash_exe(),'
assert_lacks "runtime takes no bare \`bash\` spawn" "$ND/scripts/runtime.py" 'subprocess.run(["bash"'
assert_lacks "the runtime regression takes no bare \`bash\` spawn" scripts/tests/test_runtime.py 'subprocess.run(["bash"'
assert_has  "runtime rejects the System32 stub through \`_wsl_stub\`" "$ND/scripts/runtime.py" '_wsl_stub(found)'
assert_has  "runtime walks PATH itself when the stub is what PATH resolved to" "$ND/scripts/runtime.py" 'os.environ.get("PATH", "").split(os.pathsep)'
assert_has  "runtime falls back to the bare name, never to the rejected stub" "$ND/scripts/runtime.py" '_BASH_EXE = found or "bash"'

# A verification receipt is reusable only under the same toolchain, so the signature is
# computed in Python from values both platforms have. Shelling out to `uname` would make
# the signature depend on a tool Windows does not ship, and `stat -c`/`date -d` would
# make it depend on GNU coreutils; neither is available in Git Bash's minimal set the way
# it is on Ubuntu, and a receipt that cannot be fingerprinted is a receipt reused blind.
assert_has  "the environment signature is computed in Python, not by shelling out" \
  "$ND/scripts/runtime.py" '"platform": sys.platform'
assert_has  "the signature names the shell by basename, so an absolute path never splits it" \
  "$ND/scripts/runtime.py" 'os.path.basename(bash_exe())'
assert_lacks "the runtime takes no \`uname\` dependency" "$ND/scripts/runtime.py" 'uname'
assert_lacks "the runtime takes no \`stat -c\`" "$ND/scripts/runtime.py" 'stat -c'
assert_lacks "the runtime takes no \`date -d\`" "$ND/scripts/runtime.py" 'date -d'
# Delta artifacts are named relative to one directory, which is also what keeps a
# Windows absolute path (drive letter, backslashes) out of five separate index entries.
assert_has  "delta artifacts resolve against the index's own directory" \
  "$ND/scripts/runtime.py" 'Path(index["directory"]) / reference["file"]'
# The evaluation fixture's oracle is plain Python run through the configured interpreter:
# a fixture that only reproduces its defects on one platform cannot be the thing both
# CI legs compare against.
assert_has  "the evaluation oracle is selected by an environment variable, not a shell path" \
  scripts/fixtures/evaluation/oracle/test_scheduler.py 'os.environ["EVAL_SCHEDULER"]'
assert_has  "verify-evidence.sh supports Windows interpreter selection" \
  scripts/verify-evidence.sh 'PYBIN=${KNOWLEDGE_PY:-python3}'
# The probe compares BYTES, so the expectation file it is given must be LF. Python's
# default text mode writes CRLF on Windows, which would make a correctly delivered
# payload read as `mangled` on that leg alone -- it did, on this change's first CI run.
assert_has  "the protocol requires an LF expectation file for the probe" \
  "$ND/references/legacy/runtime.md" '**Write the expectation file as UTF-8 with LF**'
assert_has  "the probe regression writes its expectation without newline translation" \
  scripts/tests/test_runtime_evidence.py 'with path.open("w", encoding="utf-8", newline="") as stream'
# `tempfile` hands back Windows' 8.3 short path (`C:\Users\RUNNER~1\...`) while
# `Path.resolve()` — which the runtime applies to every path it stores — returns the long
# one, so any test comparing a raw fixture path against a stored one fails on the Windows
# leg alone against correct code. Fixing it per-site did not hold: it recurred in the next
# test that stored a path. Resolving the fixture root kills the whole class at its source,
# so this pins the ROOT, not the individual comparisons.
assert_has  "the shared fixture root is resolved, so no derived path is a short name" \
  scripts/tests/test_runtime.py 'Path(self.temp.name).resolve()'
assert_has  "the citation regression compares resolved paths on both platforms" \
  scripts/tests/test_runtime_evidence.py 'str(Path(second).resolve())'
assert_has "the host hook and capture CLI round-trip native paths and UTF-8" \
  scripts/tests/test_boundaries.py 'def test_session_hook_and_capture_cli_preserve_native_paths_and_utf8(self):'
assert_has "both platform suites execute the host boundary regressions" \
  scripts/verify-lean-workflow.sh "-p 'test_boundaries.py'"

if [ "$fails" -gt 0 ]; then echo "verify-windows: $fails FAIL"; exit 1; fi
echo "verify-windows: all PASS"
