#!/usr/bin/env bash
# The knowledge bundle — one shared implementation of the OKF v0.2 bundle,
# consumed by every notion-dev client through config alone.
#
# Spec: docs/superpowers/specs/2026-09-14-knowledge-bundle-design.md
#
# This harness is written BEFORE the markdown it guards exists (Task 1 landed
# only plugins/notion-dev/scripts/knowledge.py and its references/iwe/ shipped
# files). skills/knowledge/SKILL.md and commands/knowledge.md do not exist yet
# — every assertion that touches them fails with "missing file" until Task 3
# lands, and stays partially red through Tasks 4-6 as each call site is
# rewritten. That is deliberate: every group below is meant to flip PASS
# independently as its own task lands, never all at once at the end.
#
# Like verify-epic-doc.sh and verify-new-info.sh this asserts a standing
# invariant: no baseline, no version floor beyond the one release this change
# ships in.
#
# Run from anywhere: ./scripts/verify-knowledge.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
KS=$ND/skills/knowledge/SKILL.md
KC=$ND/commands/knowledge.md
ED=$ND/skills/epic-doc/SKILL.md
TK=$ND/commands/ticket.md
RK=$ND/references/record.md
NT=$ND/commands/next-task.md
NI=$ND/commands/new-info.md
IN=$ND/commands/init.md
FZ=$ND/commands/finalize.md
TS=$ND/skills/ticket-system/SKILL.md
SG=$ND/skills/issue-log/references/signatures.md
SCHEMA=$ND/schema/notion-dev.config.schema.json
README=$ND/README.md
MANIFEST=$ND/.claude-plugin/plugin.json

# ---------------------------------------------------------------------------
echo "== knowledge skill: retrieve =="
# ---------------------------------------------------------------------------
if [ -f "$KS" ]; then
  L=$(total_lines "$KS")
  R0=$(find_line "$KS" 1 "$L" '^## `retrieve\(')
  C0=$(find_line "$KS" 1 "$L" '^## `capture\(')
  U0=$(find_line "$KS" 1 "$L" '^## `curate`')
  M0=$(find_line "$KS" 1 "$L" '^## `migrate')

  if [ -n "$R0" ] && [ -n "$C0" ] && [ -n "$U0" ]; then

    assert_present "knowledge skill: \`retrieve(\` heading returns \`KNOWLEDGE_CONTEXT\` or \`null\`" \
      "$KS" "$R0" "$C0" '^## `retrieve\(<epic-id>, <ticket-title>\?, <ticket-id>\?\)` → `KNOWLEDGE_CONTEXT` or `null`$'
    assert_present "retrieve: \`iwe retrieve -k epic/<KEY>-<n>-<slug> --expand-references 1\` opens the fenced command, continued by backslash" \
      "$KS" "$R0" "$C0" 'iwe retrieve -k epic/<KEY>-<n>-<slug> --expand-references 1 \\$'
    assert_present "retrieve: continuation line carries \`--lexical\`, \`--filter 'status: stable'\`, and \`--max-tokens <knowledge.retrieveBudget>\`" \
      "$KS" "$R0" "$C0" '--lexical "<ticket title>" --filter '\''status: stable'\'' --max-tokens <knowledge\.retrieveBudget> -f markdown'
    assert_present "retrieve: \`git archive origin/<epicBranch> <knowledge.dir>\` piped to \`tar -x -C <tmp>\`" \
      "$KS" "$R0" "$C0" 'git archive origin/<epicBranch> <knowledge\.dir> \| tar -x -C <tmp>'
    assert_present "retrieve: locates the root via \`git ls-tree -r --name-only origin/<epicBranch> -- <knowledge.dir>/epic/\`" \
      "$KS" "$R0" "$C0" 'git ls-tree -r --name-only origin/<epicBranch> -- <knowledge\.dir>/epic/'
    assert_present "retrieve: \`git fetch origin\` before locating the root" \
      "$KS" "$R0" "$C0" 'git fetch origin'
    assert_present "retrieve: iwe failure degrades to \`KNOWLEDGE_CONTEXT: unavailable\`" \
      "$KS" "$R0" "$C0" 'KNOWLEDGE_CONTEXT: unavailable'
    assert_present "retrieve: records \`partial:knowledge-retrieve\` on iwe failure" \
      "$KS" "$R0" "$C0" 'partial:knowledge-retrieve'
    assert_present "retrieve: missing root bootstraps in memory with \`BOOTSTRAP: true\`" \
      "$KS" "$R0" "$C0" 'BOOTSTRAP: true'

    assert_present "retrieve: read-once table names \`requirements\` as a row" \
      "$KS" "$R0" "$C0" '^\| requirements \|'
    assert_present "retrieve: read-once table names \`children statuses\` as a row" \
      "$KS" "$R0" "$C0" '^\| children statuses \|'
    assert_present "retrieve: read-once table names \`epic identity\` as a row" \
      "$KS" "$R0" "$C0" '^\| epic identity'
    assert_present "retrieve: read-once table names \`why / where we stand\` as a row" \
      "$KS" "$R0" "$C0" '^\| why / where we stand'
    assert_present "retrieve: read-once table names \`ruled-out approaches\` as a row" \
      "$KS" "$R0" "$C0" '^\| ruled-out approaches'
    assert_present "retrieve: read-once table names \`the merge's content\` as a row" \
      "$KS" "$R0" "$C0" '^\| the merge'\''s content'

    assert_absent "retrieve: never passes \`--expand-includes\`" \
      "$KS" "$R0" "$C0" '--expand-includes'
    assert_absent "knowledge skill: never runs \`grep -r\` over the bundle" \
      "$KS" 1 "$L" 'grep -r'
    assert_count "knowledge skill: \`index.md\` is written, never read for context (cited 5 times: the layout block, the read-once table's never-from column, capture's index update, migrate's reshape, and migrate's seed for a bundle that has none — tune this count in the same commit that writes the section, per CLAUDE.md)" \
      "$KS" 1 "$L" 'index\.md' 5

    # -------------------------------------------------------------------
    echo "== knowledge skill: capture =="
    # -------------------------------------------------------------------
    assert_present "knowledge skill: \`capture(\` heading covers both the hook and \`--fact\` forms" \
      "$KS" "$C0" "$U0" '^## `capture\(<ticket-id>, <merge-sha>\)` and `capture --fact <fact> <epic-id>`$'
    assert_present "capture: precondition asserts \`git -C \$REPO_ROOT rev-parse --abbrev-ref HEAD\` equals \`<baseRefName>\`" \
      "$KS" "$C0" "$U0" 'git -C \$REPO_ROOT rev-parse --abbrev-ref HEAD +# must equal <baseRefName>'
    assert_present "capture: precondition asserts HEAD equals \`origin/<baseRefName>\` — the remote-equality line decision 8 keeps, anchored on the second line of the wrapped test, since these files are hard-wrapped" \
      "$KS" "$C0" "$U0" '"\$\(git -C \$REPO_ROOT rev-parse origin/<baseRefName>\)"'
    assert_present "capture: precondition asserts \`git -C \$REPO_ROOT merge-base --is-ancestor <merge-sha> HEAD\`" \
      "$KS" "$C0" "$U0" 'git -C \$REPO_ROOT merge-base --is-ancestor <merge-sha> HEAD'
    assert_present "capture: precondition asserts \`git -C \$REPO_ROOT status --porcelain -- <knowledge.dir>\` is empty" \
      "$KS" "$C0" "$U0" 'git -C \$REPO_ROOT status --porcelain -- <knowledge\.dir>'
    assert_absent "knowledge skill: the remote-equality check decision 8 KEEPS is never written as the unassertable prose shorthand \`HEAD == origin\` — the \`test\` form is pinned above" \
      "$KS" 1 "$L" 'HEAD == origin'
    assert_absent "knowledge skill: the same shorthand in its unspaced form \`HEAD==origin\`" \
      "$KS" 1 "$L" 'HEAD==origin'
    assert_present "capture: filter question — \`would an engineer reading the merged code\`" \
      "$KS" "$C0" "$U0" 'would an engineer reading the merged code'
    assert_present "capture: an empty capture logs \`nothing durable\`" \
      "$KS" "$C0" "$U0" 'nothing durable'
    assert_present "capture: an empty capture returns \`KNOWLEDGE: empty\`" \
      "$KS" "$C0" "$U0" 'KNOWLEDGE: empty'
    assert_present "capture: dedup seed carries \`iwe find --lexical\`, \`--filter 'status: stable'\`, and \`-f json\`" \
      "$KS" "$C0" "$U0" 'iwe find --lexical "<key phrase>" --filter '\''status: stable'\'' -f json'
    assert_present "capture: collision outcome \`untouched\`" \
      "$KS" "$C0" "$U0" '^- \*\*untouched\*\*'
    assert_present "capture: collision outcome \`updated\`" \
      "$KS" "$C0" "$U0" '^- \*\*updated\*\*'
    assert_present "capture: collision outcome \`superseded\`" \
      "$KS" "$C0" "$U0" '^- \*\*superseded\*\*'
    assert_present "capture: collision outcome \`created\`" \
      "$KS" "$C0" "$U0" '^- \*\*created\*\*'
    assert_present "capture: superseded outcome sets \`superseded_by: <new path>\`" \
      "$KS" "$C0" "$U0" 'superseded_by: <new path>'
    assert_present "capture: in-place edits append a trailing \`## Updates\` section" \
      "$KS" "$C0" "$U0" '## Updates'
    assert_present "capture: re-reads touched concepts via \`knowledge.py touched <merge-sha>\`" \
      "$KS" "$C0" "$U0" 'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/knowledge\.py" touched <merge-sha>'
    assert_count "knowledge skill: \`knowledge.py check\` gates capture, curate, and migrate (cited 3 times)" \
      "$KS" 1 "$L" 'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/knowledge\.py" check' 3
    assert_present "capture: \`Write nothing\` when \`check\` exits non-zero" \
      "$KS" "$C0" "$U0" '\*\*Write nothing\*\* when `check` exits non-zero'
    assert_present "capture: \`check\` failing reverts via \`git checkout -- <knowledge.dir>\`" \
      "$KS" "$C0" "$U0" 'git checkout -- <knowledge\.dir>'
    assert_present "capture: records \`partial:knowledge-capture\` on check failure or push rejection" \
      "$KS" "$C0" "$U0" 'partial:knowledge-capture'
    assert_present "capture: commits by pathspec with \`git commit --only -m\` \`docs(knowledge): capture <KEY>-<n>\` -- \`<knowledge.dir>\`" \
      "$KS" "$C0" "$U0" 'git commit --only -m "docs\(knowledge\): capture <KEY>-<n>" -- <knowledge\.dir>'
    assert_present "capture: the fact-note form commits \`docs(knowledge): note <KEY>-<n>\` ... -- \`<knowledge.dir>\` (regex bridges the em dash and short-fact text with .* since they are not the load-bearing part of the claim)" \
      "$KS" "$C0" "$U0" 'git commit --only -m "docs\(knowledge\): note <KEY>-<n> .*-- <knowledge\.dir>'
    assert_present "capture: stages with \`git add -- <knowledge.dir>\`" \
      "$KS" "$C0" "$U0" 'git add -- <knowledge\.dir>'
    assert_present "capture: output block states all four \`KNOWLEDGE:\` values" \
      "$KS" "$C0" "$U0" '^KNOWLEDGE: captured \| empty \| failed \| unavailable'
    assert_present "capture: output block's \`COMMIT: <sha> | none\` line" \
      "$KS" "$C0" "$U0" '^COMMIT: <sha> \| none'
    assert_present "capture: inputs come from the session, \`never from Notion\`" \
      "$KS" "$C0" "$U0" 'never from Notion'

    # -------------------------------------------------------------------
    echo "== knowledge skill: curate and migrate =="
    # -------------------------------------------------------------------
    assert_present "knowledge skill: \`curate\` heading" \
      "$KS" "$U0" "$L" '^## `curate`$'
    assert_present "knowledge skill: \`migrate [--apply]\` heading" \
      "$KS" "$U0" "$L" '^## `migrate \[--apply\]`$'
    assert_present "curate: runs \`iwe stats similarity -t <threshold>\`" \
      "$KS" "$U0" "$L" 'iwe stats similarity -t <threshold>'
    assert_present "curate: the user may choose \`keep both\`" \
      "$KS" "$U0" "$L" 'keep both'
    assert_present "curate: commits \`docs(knowledge): curate\`" \
      "$KS" "$U0" "$L" 'docs\(knowledge\): curate'
    assert_absent "knowledge skill: no \`--dry-run\` flag anywhere (the default IS the dry run; the flag is \`[--apply]\`)" \
      "$KS" 1 "$L" '\-\-dry\-run'
    assert_present "migrate: without \`--apply\` it prints the complete diff and writes nothing" \
      "$KS" "$U0" "$L" '\-\-apply.*it prints the complete diff and writes nothing'
    assert_present "migrate: runs \`knowledge.py migrate\`" \
      "$KS" "$U0" "$L" 'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/knowledge\.py" migrate'
    assert_present "migrate: touches \`postMergeHooks\`" \
      "$KS" "$U0" "$L" 'postMergeHooks'
    assert_present "migrate: prints the \`removal checklist\`" \
      "$KS" "$U0" "$L" 'removal checklist'
    assert_present "migrate: \`never deletes client code\`" \
      "$KS" "$U0" "$L" 'never deletes client code'
  else
    bad "knowledge skill: could not locate the retrieve/capture/curate operation headings"
  fi
else
  bad "knowledge skill missing: $KS"
fi

# ---------------------------------------------------------------------------
echo "== knowledge skill: iwe surface =="
# ---------------------------------------------------------------------------
# Global Constraints: iwe is invoked from exactly two files — knowledge/SKILL.md
# and scripts/knowledge.py (Task 1, already landed, out of scope here). No
# other plugin file may contain an iwe subcommand.
for spec in "$ED:epic-doc/SKILL.md" "$TK:ticket.md" "$NT:next-task.md" "$NI:new-info.md" \
            "$IN:init.md" "$FZ:finalize.md" "$TS:ticket-system/SKILL.md" "$KC:knowledge.md"; do
  f=${spec%%:*}
  name=${spec#*:}
  for lit in "iwe find" "iwe retrieve" "iwe schema" "iwe stats" "iwe rename"; do
    assert_lacks "iwe surface: $name never invokes \`$lit\`" "$f" "$lit"
  done
done
assert_has "iwe surface: init.md probes \`iwe --version\` only" "$IN" 'iwe --version'
assert_lacks "iwe surface: init.md never invokes \`iwe retrieve\`" "$IN" 'iwe retrieve'
assert_lacks "iwe surface: the knowledge skill never claims \`iwe rename\` — migrate rewrites links in Python" \
  "$KS" 'iwe rename'

# ---------------------------------------------------------------------------
echo "== command: knowledge.md =="
# ---------------------------------------------------------------------------
if [ -f "$KC" ]; then
  L=$(total_lines "$KC")
  assert_present "knowledge.md: \`disable-model-invocation: true\` frontmatter" \
    "$KC" 1 5 '^disable-model-invocation: true$'
  assert_present "knowledge.md: \`# /notion-dev:knowledge\` title" \
    "$KC" 1 "$L" '^# /notion-dev:knowledge$'
  assert_present "knowledge.md: \`migrate\` heading" \
    "$KC" 1 "$L" '^## `migrate`$'
  assert_present "knowledge.md: \`curate\` heading" \
    "$KC" 1 "$L" '^## `curate`$'

  KH=$(find_line "$KC" 1 "$L" '^## `capture')
  if [ -n "$KH" ]; then
    # The section runs to the next `## ` heading, whatever order the three modes
    # are written in; without its own region the third mode had no coverage at all.
    KE=$(find_line "$KC" $((KH + 1)) "$L" '^## ')
    [ -n "$KE" ] || KE=$L
    assert_present "knowledge.md: \`capture <ticket-id> <merge-sha>\` heading" \
      "$KC" "$KH" "$KE" '^## `capture <ticket-id> <merge-sha>`$'
    assert_present "knowledge.md: capture invokes the \`notion-dev:knowledge\` skill, operation \`capture(<ticket-id>, <merge-sha>)\`" \
      "$KC" "$KH" "$KE" 'the skill `notion-dev:knowledge`, operation `capture\(<ticket-id>, <merge-sha>\)`'
    assert_present "knowledge.md: the hand re-run reads its inputs from \`fetchTicket\` and \`gh pr view\`, there being no session to draw on" \
      "$KC" "$KH" "$KE" 'fetchTicket\(<ticket-id>\).*gh pr view'
  else
    bad "knowledge.md: could not locate the \`capture\` heading"
  fi

  MH=$(find_line "$KC" 1 "$L" '^## `migrate`$')
  CH=$(find_line "$KC" 1 "$L" '^## `curate`$')
  if [ -n "$MH" ] && [ -n "$CH" ]; then
    if [ "$MH" -lt "$CH" ]; then
      assert_present "knowledge.md: migrate invokes the \`notion-dev:knowledge\` skill" \
        "$KC" "$MH" "$CH" 'notion-dev:knowledge'
      assert_present "knowledge.md: curate invokes the \`notion-dev:knowledge\` skill" \
        "$KC" "$CH" "$L" 'notion-dev:knowledge'
    else
      assert_present "knowledge.md: curate invokes the \`notion-dev:knowledge\` skill" \
        "$KC" "$CH" "$MH" 'notion-dev:knowledge'
      assert_present "knowledge.md: migrate invokes the \`notion-dev:knowledge\` skill" \
        "$KC" "$MH" "$L" 'notion-dev:knowledge'
    fi
  else
    bad "knowledge.md: could not locate migrate/curate headings for the skill-invocation check"
  fi
else
  bad "knowledge.md missing: $KC"
fi

# ---------------------------------------------------------------------------
echo "== epic-doc =="
# ---------------------------------------------------------------------------
if [ -f "$ED" ]; then
  L=$(total_lines "$ED")
  assert_present "epic-doc: \`Path:\` line moves to \`<knowledge.dir>/epic/<KEY>-<n>-<slug>.md\`" \
    "$ED" 1 "$L" '^\*\*Path:\*\* `<knowledge\.dir>/epic/<KEY>-<n>-<slug>\.md`\.'
  assert_lacks "epic-doc: no leftover \`epicDocs\` reference" "$ED" 'epicDocs'
  assert_lacks "epic-doc: no leftover \`docs/epics\` reference" "$ED" 'docs/epics'
  assert_has "epic-doc: carries \`KNOWLEDGE_CONTEXT\`" "$ED" 'KNOWLEDGE_CONTEXT'
  assert_has "epic-doc: frontmatter shows \`type: Epic\`" "$ED" 'type: Epic'
  assert_has "epic-doc: frontmatter shows \`status: stable\`" "$ED" 'status: stable'
  # The template's title must be QUOTED. Unquoted, `[STO-60] …` opens a YAML flow sequence
  # and the document has no parseable frontmatter at all, so `check` reports all six
  # required properties missing and the next `capture` writes nothing.
  assert_present "epic-doc: the template's \`title\` is quoted — \`title: \"[STO-60] Wallet Indexing\"\`" \
    "$ED" 1 "$L" '^title: "\[STO-60\] Wallet Indexing"$'
  assert_absent "epic-doc: no unquoted \`title: [STO-60]\` anywhere — that spelling costs the brief its frontmatter" \
    "$ED" 1 "$L" 'title: \[STO-60\]'
  # The brief is `status: stable`, so check rule 6 requires an index.md bullet for it.
  assert_present "epic-doc: the brief's \`index.md\` bullet is written by every operation that writes the brief" \
    "$ED" 1 "$L" 'no bullet in `index\.md` resolves to'
  assert_count "epic-doc: \`<knowledge.dir>/index.md\` is written and committed by every operation that writes the brief (cited on 8 lines: twice in the catalog rule, once in the dirty-path guard, once in record's step 4 (its no-op test and pathspec share that line), once in the bootstrap's, three times in note-apply — its no-op test, add and commit — tune this count in the same commit that changes the section, per CLAUDE.md)" \
    "$ED" 1 "$L" '<knowledge\.dir>/index\.md' 8
  assert_has "epic-doc: bullets \`write the link form whenever a concept for the fact exists\`" \
    "$ED" 'write the link form whenever a concept for the fact exists'
  assert_count "epic-doc: the brief lives under \`<knowledge.dir>/epic/\` (cited 3 times: the path line, the seed-search exclusion, and the bootstrap description — tune this count in the same commit that writes the section, per CLAUDE.md)" \
    "$ED" 1 "$L" '<knowledge\.dir>/epic/' 3
else
  bad "epic-doc skill missing: $ED"
fi

# ---------------------------------------------------------------------------
echo "== config schema =="
# ---------------------------------------------------------------------------
assert_has "config schema: \`\"knowledge\": {\` block opens" "$SCHEMA" '"knowledge": {'
assert_has "config schema: has the \`\"dir\"\` key" "$SCHEMA" '"dir"'
assert_has "config schema: dir's default is \`\"knowledge\"\`" "$SCHEMA" '"default": "knowledge"'
assert_has "config schema: has the \`\"retrieveBudget\"\` key" "$SCHEMA" '"retrieveBudget"'
assert_has "config schema: retrieveBudget's default is \`8000\`" "$SCHEMA" '"default": 8000'
assert_has "config schema: has the \`\"warnBytes\"\` key" "$SCHEMA" '"warnBytes"'
assert_has "config schema: warnBytes's default is \`8192\`" "$SCHEMA" '"default": 8192'
assert_has "config schema: has the \`\"extraTypes\"\` key" "$SCHEMA" '"extraTypes"'
assert_lacks "config schema: \`epicDocs\` key removed" "$SCHEMA" '"epicDocs"'

# ---------------------------------------------------------------------------
echo "== call sites: ticket.md =="
# ---------------------------------------------------------------------------
if [ -f "$TK" ]; then
  L=$(total_lines "$TK")
  S11=$(find_line "$TK" 1 "$L" '^### 1\.1 ')
  S12=$(find_line "$TK" 1 "$L" '^### 1\.2 ')

  if [ -n "$S11" ] && [ -n "$S12" ]; then
    assert_present "ticket.md 1.1: invokes \`notion-dev:knowledge\`, operation \`retrieve(metadata.parentTaskProperty, <title>, <id>)\`" \
      "$TK" "$S11" "$S12" 'invoke the `notion-dev:knowledge` skill, operation `retrieve\(metadata\.parentTaskProperty, <title>, <id>\)`'
    assert_present "ticket.md 1.1: \`skip the fetch when the caller supplied KNOWLEDGE_CONTEXT\`" \
      "$TK" "$S11" "$S12" '\*\*skip the fetch when the caller supplied `KNOWLEDGE_CONTEXT`\*\*'
  else
    bad "ticket.md: could not locate the 1.1/1.2 headings"
  fi
  assert_lacks "ticket.md: no leftover \`epic-doc\` \`read(metadata.parentTaskProperty\` call" \
    "$TK" 'operation `read(metadata.parentTaskProperty'
  assert_has "ticket.md: carries \`KNOWLEDGE_CONTEXT\`" "$TK" 'KNOWLEDGE_CONTEXT'
  assert_lacks "ticket.md: no leftover \`getEpicContext(\` call" "$TK" 'getEpicContext('

  # Phase 9 (including the post-merge-hooks paragraph) moved into
  # references/record.md with the rest of the record unit (Task 8).
  if [ -f "$RK" ]; then
    LR=$(total_lines "$RK")
    PH0=$(find_line "$RK" 1 "$LR" '^### Post-merge hooks$')
    if [ -n "$PH0" ]; then
      assert_count "record.md Phase 9 hook paragraph names \`notion-dev:knowledge\` (cited twice on purpose: the hook name, and the ordering rationale's example)" \
        "$RK" "$PH0" "$LR" 'notion-dev:knowledge' 2
    else
      bad "record.md: could not locate the Phase 9 post-merge-hooks paragraph"
    fi
  else
    bad "missing: $RK"
  fi
else
  bad "missing: $TK"
fi

# ---------------------------------------------------------------------------
echo "== call sites: next-task.md =="
# ---------------------------------------------------------------------------
if [ -f "$NT" ]; then
  L=$(total_lines "$NT")
  assert_has "next-task.md: invokes \`notion-dev:knowledge\`, operation \`retrieve(<epic-id>)\`" \
    "$NT" 'the `notion-dev:knowledge` skill, operation `retrieve(<epic-id>)`'
  assert_has "next-task.md: carries \`KNOWLEDGE_CONTEXT\`" "$NT" 'KNOWLEDGE_CONTEXT'
  assert_lacks "next-task.md: no leftover \`epic-doc\` \`read(<epic-id>)\` call" \
    "$NT" 'operation `read(<epic-id>)`'
else
  bad "missing: $NT"
fi

# ---------------------------------------------------------------------------
echo "== call sites: new-info.md =="
# ---------------------------------------------------------------------------
if [ -f "$NI" ]; then
  assert_has "new-info.md: invokes \`notion-dev:knowledge\`, operation \`capture --fact <fact> <epic-id>\`, after \`note --apply\`'s outcome bullets" \
    "$NI" "unless this epic's \`note --apply\` outcome above was \`failed\`, invoke the \`notion-dev:knowledge\` skill, operation \`capture --fact <fact> <epic-id>\`"
  assert_has "new-info.md: reports a \`KNOWLEDGE:\` line per epic" "$NI" 'KNOWLEDGE:'
  assert_lacks "new-info.md: no leftover \`epicDocs\` reference" "$NI" 'epicDocs'
  assert_has "new-info.md: invokes \`notion-dev:knowledge\`, operation \`retrieve(<epic-id>)\`" \
    "$NI" 'the `notion-dev:knowledge` skill, operation `retrieve(<epic-id>)`'
else
  bad "missing: $NI"
fi

# ---------------------------------------------------------------------------
echo "== call sites: init.md =="
# ---------------------------------------------------------------------------
if [ -f "$IN" ]; then
  L=$(total_lines "$IN")
  PF=$(find_line "$IN" 1 "$L" '^### 1\. Preflight$')
  PF_END=$(find_line "$IN" $((PF + 1)) "$L" '^### ')
  [ -n "$PF_END" ] || PF_END=$L
  assert_present "init.md preflight, region-scoped to step 1, probes \`iwe --version\`" \
    "$IN" "$PF" "$PF_END" 'Probe `iwe --version`'
  assert_present "init.md preflight, same region, probes the interpreter in order starting with \`python3 --version\`" \
    "$IN" "$PF" "$PF_END" 'python3 --version.*python --version.*py -3 --version'
  assert_has "init.md: writes \`postMergeHooks: [\"notion-dev:knowledge\"]\`" \
    "$IN" 'postMergeHooks: ["notion-dev:knowledge"]'
  assert_lacks "init.md: no leftover \`epicDocs\` reference" "$IN" 'epicDocs'
  assert_has "init.md: scaffolds \`index.md\`" "$IN" 'index.md'
  assert_has "init.md: scaffolds \`log.md\`" "$IN" 'log.md'
  assert_has "init.md: scaffolds \`.iwe/\`" "$IN" '.iwe/'
  # A scaffold of bare headings fails the shipped okf-index/okf-log schemas, so the very
  # first post-merge capture on a new project returns KNOWLEDGE: failed.
  assert_has "init.md: the scaffolded catalog carries one seed bullet pointing at \`log.md\`, not just a heading" \
    "$IN" '- [Update log](log.md) — this'
  assert_has "init.md: the scaffolded log carries one dated \`- bundle created\` entry" \
    "$IN" '- bundle created'
  assert_has "init.md: type directories are NOT created — git cannot track an empty directory" \
    "$IN" 'Type directories are not created'
  assert_lacks "init.md: no leftover \"create the canonical type directories\" promise" \
    "$IN" 'create the canonical type directories'
else
  bad "missing: $IN"
fi

# ---------------------------------------------------------------------------
echo "== call sites: finalize.md =="
# ---------------------------------------------------------------------------
if [ -f "$FZ" ]; then
  assert_has "finalize.md: hook paragraph names \`notion-dev:knowledge\`" "$FZ" 'notion-dev:knowledge'
  assert_lacks "finalize.md: the remote-equality check decision 8 KEEPS is never written as the prose shorthand \`HEAD == origin\`" "$FZ" 'HEAD == origin'
else
  bad "missing: $FZ"
fi

# ---------------------------------------------------------------------------
echo "== call sites: ticket-system SKILL.md =="
# ---------------------------------------------------------------------------
assert_has "ticket-system: getEpicContext is marked superseded by \`notion-dev:knowledge\` \`retrieve\`" \
  "$TS" 'superseded by `notion-dev:knowledge` `retrieve`'

# ---------------------------------------------------------------------------
echo "== signatures, README, version =="
# ---------------------------------------------------------------------------
assert_has "signature registry has the \`partial:knowledge-retrieve\` row" "$SG" '| `partial:knowledge-retrieve` |'
assert_has "signature registry has the \`partial:knowledge-capture\` row" "$SG" '| `partial:knowledge-capture` |'
assert_has "signature registry has the \`missing-dependency:iwe\` row" "$SG" '| `missing-dependency:iwe` |'

assert_has "README documents \`/notion-dev:knowledge\`" "$README" '| `/notion-dev:knowledge'
RL=$(total_lines "$README")
PR0=$(find_line "$README" 1 "$RL" '^## Prerequisites$')
PR1=$(find_line "$README" $((PR0 + 1)) "$RL" '^## ')
[ -n "$PR1" ] || PR1=$RL
assert_present "README prerequisites, region-scoped to that section, list \`iwe\` as required" \
  "$README" "$PR0" "$PR1" '^- [*][*]`iwe` . 0[.]19 on `PATH`[*][*] . [*][*]required[*][*]'
assert_present "README prerequisites, same region, list Python 3.8+ as required" \
  "$README" "$PR0" "$PR1" '^- [*][*]Python 3[.]8[+][*][*] . [*][*]required[*][*]'
assert_has "README documents \`knowledge.dir\`" "$README" 'knowledge.dir'
assert_lacks "README: no leftover \`epicDocs\` reference" "$README" 'epicDocs'
assert_lacks "README: no leftover \"Knowledge bundles are not touched\" sentence" \
  "$README" 'Knowledge bundles are not touched'
assert_version_above "notion-dev version bumped above the pre-change 0.23.0" "$MANIFEST" 0.23.0

# ---------------------------------------------------------------------------
echo "== status vocabulary =="
# ---------------------------------------------------------------------------
# Decisions: status is stable | draft | deprecated. "status: current" (the
# smart-contracts client's local vocabulary) must not appear in any plugin
# file except the spec, which this harness never touches.
for f in "$KS" "$ED" "$KC" "$NI" "$TK" "$NT" "$IN"; do
  assert_lacks "status vocabulary: $f never writes \`status: current\`" "$f" 'status: current'
done

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
  echo
  echo "This harness pins the knowledge-bundle contract (spec:"
  echo "docs/superpowers/specs/2026-09-14-knowledge-bundle-design.md). It is meant to be"
  echo "red until Tasks 3-6 land skills/knowledge/SKILL.md, commands/knowledge.md, and the"
  echo "call-site edits — each group above should turn green independently as its task"
  echo "lands. If a failure is a deliberate change to the contract, change the assertion"
  echo "with it, in the same commit, with the reasoning."
fi
exit $(( fails > 0 ? 1 : 0 ))
