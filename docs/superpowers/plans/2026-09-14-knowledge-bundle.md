# Knowledge Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship one shared knowledge-bundle implementation inside `plugins/notion-dev` — a `knowledge` skill, a `knowledge.py` script, and the call-site changes that make the epic brief the bundle's root and every fact enter a run once — as notion-dev 0.24.0.

**Architecture:** A new skill `skills/knowledge/SKILL.md` owns four operations (`retrieve`, `capture`, `curate`, `migrate`) and is the only place besides `scripts/knowledge.py` that invokes `iwe`. `epic-doc` keeps its operations but moves its file under `<knowledge.dir>/epic/`. `ticket`, `next-task`, and `new-info` call `retrieve` once and pass `KNOWLEDGE_CONTEXT` down. Two harnesses guard it: `verify-knowledge.sh` pins the markdown mechanisms; `verify-knowledge-py.sh` runs the script against fixtures.

**Tech Stack:** Markdown instruction files; bash harnesses on `scripts/lib/assert.sh`; Python 3.8+ standard library; `iwe` 0.19+ CLI (`find`, `retrieve`, `schema validate`, `stats similarity`, `init --okf`).

**Spec:** `docs/superpowers/specs/2026-09-14-knowledge-bundle-design.md` — the authority; every literal below comes from it.

## Global Constraints

- **CLAUDE.md harness rules** bind every assertion: assert mechanisms not prose; `assert_present` matches exactly one line per region; a backticked literal in a label must appear in the regex (A2); declared duplicates use `assert_count`; files are hard-wrapped so no regex spans a line; every check is proven to fail by mutation; commit before mutating; mutation scripts live in the scratchpad, never the repo.
- **Only `scripts/lib/assert.sh` helpers** in harnesses (`verify-assertions.sh` rejects anything else). `verify-knowledge-py.sh` may run `python3`/`iwe` and compare exit codes with `assert_*` on captured output files.
- **Version bump exactly once**: `plugins/notion-dev/.claude-plugin/plugin.json` `0.23.0 → 0.24.0`, in Task 6.
- **`notion-dev` has no `.claude/skills` mirror.** Nothing under `.claude/skills/` changes.
- **iwe is invoked from exactly two files**: `plugins/notion-dev/skills/knowledge/SKILL.md` and `plugins/notion-dev/scripts/knowledge.py`. No other plugin file may contain the string `iwe ` followed by a subcommand (the harness asserts this with `assert_lacks` on every other changed file).
- **Read-once**: no command reads the Notion epic page body, `index.md`, or runs `grep -r` over the bundle; `ticket.md` calls `retrieve` at most once per run and skips it when the caller supplied `KNOWLEDGE_CONTEXT`.
- **Status vocabulary** is `stable | draft | deprecated`. The string `status: current` must not appear in any plugin file except the spec.
- **Commit trailer** on every commit: `Claude-Session: https://claude.ai/code/session_014WgcLXWYFooDsYZCax4zXm`.
- **Pinned literals.** Tasks 2–6 write these lines verbatim and Task 2's harness asserts them. A task that needs to deviate stops and reports.

| id | file | literal (one line, must not wrap) |
|---|---|---|
| L1 | knowledge/SKILL.md | `## \`retrieve(<epic-id>, <ticket-title>?, <ticket-id>?)\` → \`KNOWLEDGE_CONTEXT\` or \`null\`` |
| L2 | knowledge/SKILL.md | `iwe retrieve -k epic/<KEY>-<n>-<slug> --expand-references 1 --lexical "<ticket title>" --filter 'status: stable' --max-tokens <knowledge.retrieveBudget> -f markdown` (inside a fenced block, split over two lines with a trailing `\` after `--expand-references 1`) |
| L3 | knowledge/SKILL.md | `git archive origin/<epicBranch> <knowledge.dir> \| tar -x -C <tmp>` |
| L4 | knowledge/SKILL.md | `## \`capture(<ticket-id>, <merge-sha>)\` and \`capture --fact <fact> <epic-id>\`` |
| L5 | knowledge/SKILL.md | four outcome bullets starting `- **untouched**`, `- **updated**`, `- **superseded**`, `- **created**` |
| L6 | knowledge/SKILL.md | `iwe find --lexical "<key phrase>" --filter 'status: stable' -f json` |
| L7 | knowledge/SKILL.md | `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" touched <merge-sha>` |
| L8 | knowledge/SKILL.md | `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" check` (appears exactly 3 times: capture, curate, migrate) |
| L9 | knowledge/SKILL.md | `git commit --only -m "docs(knowledge): capture <KEY>-<n>" -- <knowledge.dir>` |
| L10 | knowledge/SKILL.md | `git commit --only -m "docs(knowledge): note <KEY>-<n> — <short fact>" -- <knowledge.dir>` |
| L11 | knowledge/SKILL.md | `KNOWLEDGE: captured \| empty \| failed \| unavailable` |
| L12 | knowledge/SKILL.md | `iwe stats similarity -t <threshold>` |
| L13 | knowledge/SKILL.md | `## \`migrate [--apply]\`` and `## \`curate\`` |
| L14 | knowledge/SKILL.md | `**Write nothing** when \`check\` exits non-zero` |
| L15 | knowledge/SKILL.md | three precondition bullets: `git -C $REPO_ROOT rev-parse --abbrev-ref HEAD` equals `<base>`; `git -C $REPO_ROOT merge-base --is-ancestor <merge-sha> HEAD`; `git -C $REPO_ROOT status --porcelain -- <knowledge.dir>` empty |
| L16 | epic-doc/SKILL.md | `**Path:** \`<knowledge.dir>/epic/<KEY>-<n>-<slug>.md\`.` |
| L17 | ticket.md | `invoke the \`notion-dev:knowledge\` skill, operation \`retrieve(metadata.parentTaskProperty, <title>, <id>)\`` |
| L18 | ticket.md | `**skip the fetch when the caller supplied \`KNOWLEDGE_CONTEXT\`**` |
| L19 | next-task.md | `invoke the \`notion-dev:knowledge\` skill, operation \`retrieve(<epic-id>)\`` |
| L20 | new-info.md | `operation \`capture --fact <fact> <epic-id>\`` |
| L21 | config schema | `"knowledge": {` block with `"dir"`, `"retrieveBudget"`, `"warnBytes"`, `"extraTypes"` |
| L22 | init.md | `postMergeHooks: ["notion-dev:knowledge"]` |
| L23 | signatures.md | rows `partial:knowledge-retrieve`, `partial:knowledge-capture`, `missing-dependency:iwe` |
| L24 | knowledge.md (command) | `# /notion-dev:knowledge` with `## \`migrate\`` and `## \`curate\`` |

---

## File structure

| path | responsibility |
|---|---|
| `plugins/notion-dev/scripts/knowledge.py` | new — `check`, `touched`, `migrate`; stdlib only; consumes `iwe` JSON |
| `plugins/notion-dev/skills/knowledge/SKILL.md` | new — the four operations, preconditions, output blocks |
| `plugins/notion-dev/skills/knowledge/references/iwe/config.toml`, `schemas/okf.yaml`, `schemas/okf-index.yaml`, `schemas/okf-log.yaml` | new — the plugin-owned bundle config; `check` diffs against it |
| `plugins/notion-dev/commands/knowledge.md` | new — `/notion-dev:knowledge migrate [--apply] \| curate` |
| `scripts/fixtures/knowledge/**` | new — fixture bundles for `verify-knowledge-py.sh` |
| `scripts/verify-knowledge-py.sh` | new — runs the script against fixtures |
| `scripts/verify-knowledge.sh` | new — pins the markdown mechanisms |
| `.github/workflows/verify.yml` | modify — install `iwe` before the harness loop |
| `plugins/notion-dev/skills/epic-doc/SKILL.md` | modify — path, `read` as parse over retrieve, frontmatter on create, link-form bullets |
| `plugins/notion-dev/schema/notion-dev.config.schema.json` | modify — add `knowledge`, remove `epicDocs` |
| `plugins/notion-dev/commands/{ticket,next-task,new-info,init,finalize}.md` | modify — call sites (§8 of the spec) |
| `plugins/notion-dev/skills/ticket-system/SKILL.md` | modify — `getEpicContext` marked superseded |
| `plugins/notion-dev/skills/issue-log/references/signatures.md` | modify — three rows |
| `plugins/notion-dev/README.md`, `.claude-plugin/plugin.json` | modify — docs, version |
| `scripts/verify-epic-doc.sh`, `scripts/verify-new-info.sh` | modify — anchors that named `epicDocs` |
| `docs/superpowers/specs/2026-09-13-epic-doc-design.md` | modify — one pointer line at the top |

---

### Task 1: `knowledge.py`, the shipped `.iwe/` files, fixtures, and `verify-knowledge-py.sh`

**Files:**
- Create: `plugins/notion-dev/scripts/knowledge.py`
- Create: `plugins/notion-dev/skills/knowledge/references/iwe/config.toml`
- Create: `plugins/notion-dev/skills/knowledge/references/iwe/schemas/okf.yaml`, `okf-index.yaml`, `okf-log.yaml`
- Create: `scripts/fixtures/knowledge/valid/**`, `scripts/fixtures/knowledge/broken-*/**`, `scripts/fixtures/knowledge/migrate-input/**`, `scripts/fixtures/knowledge/migrate-expected/**`
- Create: `scripts/verify-knowledge-py.sh`
- Modify: `.github/workflows/verify.yml`

**Interfaces:**
- Produces: `python3 knowledge.py check [--dir D] [--plugin-root P] [--extra-types a,b] [--warn-bytes N]`, `python3 knowledge.py touched <sha> [--dir D]`, `python3 knowledge.py migrate [--apply] [--dir D] [--config PATH] [--plugin-root P]`. Exit codes: 0 clean, 1 findings, 2 cannot run. Finding lines are `<path>: <rule>: <detail>`; warnings are `<path>: warn: <detail>` and never change the exit code.
- Produces: the shipped `.iwe/` tree that Task 3's `migrate`/`init` prose installs, and that `check` diffs.

- [ ] **Step 1: Write the shipped `.iwe/` files**

Run `iwe init --okf` in a scratch dir and copy its output, then trim `config.toml` to exactly this (no `[templates]`, `[commands]`, `[actions]` blocks — they configure AI actions the plugin does not use):

```toml
format = "markdown"
version = 3

[library]
date_format = "%Y-%m-%d"
path = ""

[markdown]
date_format = "%b %d, %Y"
refs_extension = ".md"
refs_path = "relative"
refs_text = "preserve"
wiki_link_path = "preserve"

[markdown.formatting]

[completion]
link_format = "markdown"

[search]
language = "english"

[schemas]

[schemas.okf]
match = ["**", "!index", "!**/index", "!log", "!**/log"]

[schemas.okf-index]
match = ["index", "**/index"]

[schemas.okf-log]
match = ["log", "**/log"]
```

Edit `schemas/okf.yaml` from the scaffold to the spec §3 model. Keep the scaffold's `$schema` line and structure; the `frontmatter` block becomes:

```yaml
frontmatter:
  type: object
  required: [type, title, description, status, generated, sources]
  properties:
    type: { type: string, minLength: 1 }
    title: { type: string, minLength: 1 }
    description: { type: string, minLength: 1 }
    status:
      enum: [stable, draft, deprecated]
      description: OKF lifecycle (SPEC §5.4)
    generated:
      type: object
      required: [by, at]
      properties:
        by: { type: string }
        at: { type: string }
    updated:
      type: object
      required: [by, at]
      properties:
        by: { type: string }
        at: { type: string }
    sources:
      type: array
      minItems: 1
      items:
        type: object
        required: [id, resource]
        properties:
          id: { type: string }
          resource: { type: string }
          title: { type: string }
          last_modified: { type: string }
    ticket: { type: string }
    epic: { type: string }
    applies_to: { type: array, items: { type: string } }
    superseded_by: { type: string }
    confidence: { type: string }
    tags: { type: array, items: { type: string } }
```

No `additionalProperties: false` anywhere in `okf.yaml` (client extension fields must validate). Leave `okf-index.yaml` and `okf-log.yaml` exactly as scaffolded.

- [ ] **Step 2: Write the fixtures**

`scripts/fixtures/knowledge/valid/` is a complete bundle: the four `.iwe/` files copied from step 1, `index.md`, `log.md`, `epic/STO-1-demo-epic.md`, `decision/keep-cache.md`, `gotcha/old-trap.md` (deprecated, `superseded_by: ../gotcha/new-trap.md`), `gotcha/new-trap.md`, `commitment/promise.md` (extra type). Every `stable` concept has a bullet in `index.md`; `decision/keep-cache.md` has `applies_to: ["src/cache/**"]`.

`index.md`:

```markdown
---
okf_version: "0.2"
---
# Index

## epic/
- [[STO-1] Demo epic](epic/STO-1-demo-epic.md) — the fixture epic

## decision/
- [Keep the cache](decision/keep-cache.md) — cache stays positive-only

## gotcha/
- [The new trap](gotcha/new-trap.md) — replaces the old trap

## commitment/
- [A promise](commitment/promise.md) — client extension type
```

`log.md`:

```markdown
# Update log

## 2026-09-14
- [STO-1]: fixture bundle created
```

`epic/STO-1-demo-epic.md` uses the spec §3 epic frontmatter (`type: Epic`, `status: stable`, `epic: STO-1`, one source) and the six brief sections with one line each; its `## Decisions & constraints` bullet is `- [Keep the cache](../decision/keep-cache.md) — binds STO-2.`

Each `broken-<rule>/` is a copy of `valid/` with one defect; the expected finding rule name is the directory suffix:

| dir | defect | expected line contains |
|---|---|---|
| `broken-schema` | `decision/keep-cache.md` has no `sources` | `decision/keep-cache.md: schema:` |
| `broken-link` | `epic/STO-1-demo-epic.md` links `../decision/missing.md` | `epic/STO-1-demo-epic.md: link: decision/missing` |
| `broken-superseded` | `gotcha/old-trap.md` `superseded_by: ../gotcha/nope.md` | `gotcha/old-trap.md: superseded_by: gotcha/nope` |
| `broken-superseded-chain` | `gotcha/new-trap.md` is also `deprecated` with a valid `superseded_by` | `gotcha/old-trap.md: superseded_by: target is deprecated` |
| `broken-index` | `decision/keep-cache.md` bullet removed from `index.md` | `index.md: index: decision/keep-cache` |
| `broken-type` | `commitment/` present but `--extra-types` not passed | `commitment/promise.md: type: undeclared directory commitment` |
| `broken-iwe` | `.iwe/schemas/okf.yaml` has one extra comment line | `.iwe/schemas/okf.yaml: iwe: differs from plugin copy` |
| `broken-log` | `log.md` has a `### ` subsection under a date | `log.md: schema:` |

`migrate-input/` is a pre-migration bundle: `.iwe/config.toml` from the raw `iwe init --okf` scaffold (untrimmed), no schemas dir, `ticket/STO-9.md` with `status: current`, `stale_after: 2026-01-01`, `verified: {by: x, at: y}`, `reconciled: {at: z}`, a `## Reconciliation notes` section with one dated paragraph, no `sources`; `log.md` in the smart-contracts shape (`**Creation** 2026-09-01 — …` lines with no date headings); a brief at `docs/epics/STO-9-demo.md` in the epic-doc template with no frontmatter; a config at `migrate-input/.claude/notion-dev.config.json` containing `"epicDocs": {"dir": "docs/epics"}` and `"git": {"postMergeHooks": ["knowledge-capture"]}`. `migrate-expected/` is the byte-exact result: trimmed `.iwe/`, `ticket/STO-9.md` with `status: stable`, the three fields dropped, `sources: [{id: migrated, resource: ticket/STO-9.md}]`, `status: draft` (because sources were synthesised), the notes moved under `## Updates`; `log.md` reshaped to `# Update log` + `## 2026-09-01` + bullet; `epic/STO-9-demo.md` with frontmatter; the config with `epicDocs` gone, `"knowledge": {"extraTypes": []}` added, and the hook renamed.

- [ ] **Step 3: Write `verify-knowledge-py.sh`**

```bash
#!/usr/bin/env bash
# verify-knowledge-py.sh — runs plugins/notion-dev/scripts/knowledge.py against fixture
# bundles and asserts its exit codes and finding lines. A missing iwe or python3 is a FAIL,
# never a skip: CI installs both, and a check that cannot run must say so.
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/lib/assert.sh

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
assert_has "broken-log names the schema rule"         "$OUT/broken-log.txt"        'log.md: schema:'

echo "== check: warnBytes warns, never fails =="
run warn 0 check --dir "$FX/valid" --plugin-root "$ROOT" --extra-types commitment --warn-bytes 10
assert_has "a tiny warn-bytes produces warn lines" "$OUT/warn.txt" ': warn: '

echo "== check: iwe missing is exit 2 =="
PATH=/nonexistent run noiwe 2 check --dir "$FX/valid" --plugin-root "$ROOT"

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
M=$(mktemp -d); cp -r "$FX/migrate-input/." "$M/"
run migrate-dry 0 migrate --dir "$M/knowledge" --config "$M/.claude/notion-dev.config.json" --plugin-root "$ROOT"
diff -r "$FX/migrate-input" "$M" >/dev/null && echo "ok: dry run left the tree byte-identical" \
  || { echo "FAIL: dry run modified the tree"; fails=$((fails+1)); }
assert_has "dry run prints a unified diff" "$OUT/migrate-dry.txt" '^+++ '
run migrate-apply 0 migrate --apply --dir "$M/knowledge" --config "$M/.claude/notion-dev.config.json" --plugin-root "$ROOT"
diff -r "$FX/migrate-expected" "$M" && echo "ok: apply produced the expected tree" \
  || { echo "FAIL: apply differs from expected"; fails=$((fails+1)); }
run migrate-check 0 check --dir "$M/knowledge" --plugin-root "$ROOT"
rm -rf "$M"

echo
if [ "$fails" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "$fails CHECK(S) FAILED"; fi
exit $(( fails > 0 ? 1 : 0 ))
```

`fails` is the counter `scripts/lib/assert.sh` maintains for its own `assert_*` helpers; the `run` helper above increments the same variable so one summary covers both. Copy the closing lines from `scripts/verify-new-info.sh` for the exact wording.

- [ ] **Step 4: Run the harness — expect FAIL (script missing)**

Run: `bash scripts/verify-knowledge-py.sh`
Expected: FAIL lines because `knowledge.py` does not exist.

- [ ] **Step 5: Write `knowledge.py`**

Module layout (single file, ~400 lines, Python 3.8+, `import argparse, json, os, re, subprocess, sys, difflib, fnmatch, shutil` only):

```python
#!/usr/bin/env python3
"""knowledge.py — the mechanical checks notion-dev's knowledge skill needs and iwe lacks.

Subcommands: check | touched | migrate. Exit 0 clean, 1 findings, 2 cannot run.
Never parses YAML: frontmatter comes from `iwe find -f json`; shape from `iwe schema validate`.
Exit 2 is never downgraded: a check that cannot run says so and fails.
"""

CANONICAL_TYPES = ["epic", "ticket", "decision", "gotcha", "component", "spec", "domain", "release"]
IWE_FILES = ["config.toml", "schemas/okf.yaml", "schemas/okf-index.yaml", "schemas/okf-log.yaml"]

def die(msg): print(f"error: {msg}", file=sys.stderr); sys.exit(2)

def iwe(args, cwd):
    """Run iwe; exit 2 if the binary is missing or the call fails."""
    try:
        p = subprocess.run(["iwe", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        die("iwe is not on PATH — install: cargo install iwe --root ~/.local (or brew/npm where GLIBC >= 2.39)")
    if p.returncode not in (0, 1):
        die(f"iwe {' '.join(args)} failed: {p.stderr.strip()}")
    return p

def docs(bundle):
    """[{key, type, status, references:[{key}], superseded_by, applies_to, ...}] via iwe find."""
    p = iwe(["find", "--filter", "", "-f", "json"], bundle)
    return json.loads(p.stdout or "[]")

def concept_dirs(bundle):
    """Top-level non-dot directories that contain .md files."""

def cmd_check(a):
    findings, warnings = [], []
    # 1. iwe copy drift: difflib.unified_diff of each IWE_FILES against plugin copy → "iwe: differs from plugin copy"
    # 2. iwe schema validate -f json → one finding per violation: f"{key}.md: schema: {message} ({breadcrumb})"
    # 3. type dirs: every concept dir must be in CANONICAL_TYPES or a.extra_types → "type: undeclared directory X"
    # 4. links: for d in docs: for r in d["references"]: r["key"] not in keys → f"{d.key}.md: link: {r.key}"
    # 5. superseded_by: deprecated docs must name a key that exists and is not deprecated
    # 6. index: every stable doc key (except index/log) appears as a link target in index.md; every index link resolves
    # 7. size: os.path.getsize > a.warn_bytes → warnings
    # print findings then warnings; sys.exit(1 if findings else 0)

def cmd_touched(a):
    # git show --name-only --pretty=format: <sha> → changed paths (relative to repo root, so the
    # bundle dir must be resolved against `git rev-parse --show-toplevel`)
    # for every stable doc with applies_to: any fnmatch → print f"{key}.md"

def cmd_migrate(a):
    # Build the full post-migration tree in memory as {relpath: bytes}; compute the unified diff
    # against the current files; print it. With --apply: write bytes with "\n" endings, run
    # cmd_check on the result, and on findings restore every file from the in-memory backup
    # and exit 1. Steps are spec §7 2–6; frontmatter edits use regex on the leading '---' block
    # (line-based: drop keys stale_after/reconciled/verified/vouch, rewrite `status: current`,
    # append a sources block when absent and set status: draft). Move docs/epics/*.md (or the
    # config's epicDocs.dir) into epic/, prepending the Epic frontmatter derived from the H1.
    # log.md: parse "**Creation|Update|Deprecation** YYYY-MM-DD — text" lines into date groups.
    # Config: json.load → del epicDocs; knowledge = {"extraTypes": extras}; rename the hook entry.
```

Write every branch the fixtures exercise. The frontmatter mutation in `migrate` is line-based on the leading `---` block and must not touch the body except the two documented moves (`## Reconciliation notes` → `## Updates`, and the log/index reshapes).

- [ ] **Step 6: Run the harness — expect PASS**

Run: `bash scripts/verify-knowledge-py.sh`
Expected: every `ok:` line, exit 0. Iterate on the script until it passes; adjust `migrate-expected/` only when the spec, not the script, says the expected output is wrong.

- [ ] **Step 7: Add the iwe install step to CI**

In `.github/workflows/verify.yml`, before "Run every verification harness":

```yaml
      # verify-knowledge-py.sh runs plugins/notion-dev/scripts/knowledge.py, which shells out
      # to iwe. ubuntu-latest ships GLIBC 2.39, so the prebuilt npm binary runs. Pinned to the
      # version the plugin's flags were verified against (the plugin requires >= 0.19), so a
      # CI break is a change we made, not one upstream made.
      - name: Install iwe
        run: npm i -g @iwe-org/iwe@0.19.1 && iwe --version
```

Update the header comment's "needs no setup step" sentence to say the one exception.

- [ ] **Step 8: Run the whole suite and commit**

Run: `for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done`
Expected: all pass (`verify-assertions.sh` must accept the new harness).

```bash
git add plugins/notion-dev/scripts/knowledge.py plugins/notion-dev/skills/knowledge/references scripts/fixtures/knowledge scripts/verify-knowledge-py.sh .github/workflows/verify.yml
git commit -m "feat(notion-dev): knowledge.py — check, touched, migrate over iwe JSON, with fixture harness

Claude-Session: https://claude.ai/code/session_014WgcLXWYFooDsYZCax4zXm"
```

---

### Task 2: `verify-knowledge.sh` — red first

**Files:**
- Create: `scripts/verify-knowledge.sh`

**Interfaces:**
- Consumes: the pinned literals L1–L24 and the spec's mechanism lines.
- Produces: the harness Tasks 3–6 turn green.

- [ ] **Step 1: Write the harness**

Header and file variables as `verify-new-info.sh` does (`set -uo pipefail`, `cd` to repo root, source `assert.sh`). Files: `KS=plugins/notion-dev/skills/knowledge/SKILL.md`, `KC=plugins/notion-dev/commands/knowledge.md`, `ED=plugins/notion-dev/skills/epic-doc/SKILL.md`, `TK=plugins/notion-dev/commands/ticket.md`, `NT=plugins/notion-dev/commands/next-task.md`, `NI=plugins/notion-dev/commands/new-info.md`, `IN=plugins/notion-dev/commands/init.md`, `FZ=plugins/notion-dev/commands/finalize.md`, `TS=plugins/notion-dev/skills/ticket-system/SKILL.md`, `SG=plugins/notion-dev/skills/issue-log/references/signatures.md`, `SCHEMA=plugins/notion-dev/schema/notion-dev.config.schema.json`, `README=plugins/notion-dev/README.md`, `MANIFEST=plugins/notion-dev/.claude-plugin/plugin.json`. Every file must exist (`[ -f ]` else FAIL, as other harnesses do).

Regions in `$KS`: `R0=$(find_line "$KS" '^## `retrieve(')`, `C0=$(find_line "$KS" '^## `capture(')`, `U0=$(find_line "$KS" '^## `curate`')`, `M0=$(find_line "$KS" '^## `migrate')`, `L=$(total_lines "$KS")`. Assertions, grouped (labels are yours; each regex must honour A2):

`== knowledge skill: retrieve ==` (region R0..C0)
- `assert_present` L1 heading; the single `iwe retrieve -k epic/<KEY>-<n>-<slug> --expand-references 1 \\$` line; the continuation line `--lexical "<ticket title>" --filter 'status: stable' --max-tokens <knowledge.retrieveBudget> -f markdown`; L3 `git archive origin/<epicBranch> <knowledge.dir> | tar -x -C <tmp>` (escape `|`); `git ls-tree -r --name-only origin/<epicBranch> -- <knowledge.dir>/epic/`; `git fetch origin`; `KNOWLEDGE_CONTEXT: unavailable`; `partial:knowledge-retrieve`; `BOOTSTRAP: true`; the read-once table rows — one `assert_present` per row's first cell (`^\| requirements \|`, `^\| children statuses \|`, `^\| epic identity`, `^\| why / where we stand`, `^\| ruled-out approaches`, `^\| the merge's content`).
- `assert_absent` R0..C0 `--expand-includes`; `assert_absent` 1..L `grep -r`; `assert_absent` 1..L `index\.md` **except** the index-maintenance lines in capture/migrate → use `assert_count 1..L 'index\.md' <n>` with the count the skill actually needs, stated in the label as "index.md is written, never read for context".

`== knowledge skill: capture ==` (region C0..U0)
- L4 heading; the three precondition lines (L15) each as `assert_present`; `assert_absent` 1..L `HEAD == origin`; `assert_absent` 1..L `HEAD==origin`; the filter question `would an engineer reading the merged code still not know this`; `nothing durable`; `KNOWLEDGE: empty`; L6; the four L5 outcome bullets (`^- \*\*untouched\*\*`, etc.); `superseded_by: <new path>`; `## Updates`; L7; L8 counted 3 across 1..L (`assert_count`); L14; `git checkout -- <knowledge.dir>`; `partial:knowledge-capture`; L9; L10; `git add -- <knowledge.dir>`; L11; `^COMMIT: <sha> \| none`; the input line stating inputs come from the session (`assert_present` on `never from Notion`).

`== knowledge skill: curate and migrate ==` (U0..L)
- L12; `keep both`; `docs(knowledge): curate`; L13 both headings; `--dry-run` absent (the flag is `[--apply]`, dry-run is the default: `assert_present` on `Without \`--apply\` it prints the complete diff and writes nothing`); `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" migrate`; `postMergeHooks`; `removal checklist`; `never deletes client code`.

`== knowledge skill: iwe surface ==`
- `assert_count` 1..L `'^[^`]*iwe (find|retrieve|schema validate|stats similarity|init --okf)'`… simpler: `assert_lacks` on each *other* changed file for `iwe find`, `iwe retrieve`, `iwe schema`, `iwe stats`: `$ED $TK $NT $NI $IN $FZ $TS $KC`. `$IN` is allowed the probe `iwe --version` only — assert `assert_has "$IN" 'iwe --version'` and `assert_lacks "$IN" 'iwe retrieve'`.

`== command: knowledge.md ==`
- `^# /notion-dev:knowledge`; `^## \`migrate\``; `^## \`curate\``; `disable-model-invocation: true` in frontmatter; `assert_has` `notion-dev:knowledge` skill invocation for each.

`== epic-doc ==`
- L16; `assert_lacks "$ED" 'epicDocs'`; `assert_lacks "$ED" 'docs/epics'`; `assert_has "$ED" 'KNOWLEDGE_CONTEXT'`; `assert_has "$ED" 'type: Epic'`; `assert_has "$ED" 'status: stable'`; the link-form bullet rule (`assert_has` on `write the link form whenever a concept for the fact exists`); `record --bootstrap` writes into `epic/` (`assert_has` `<knowledge.dir>/epic/`, counted with `assert_count` if it appears more than once — it will; pick the count and say so).

`== config schema ==`
- `assert_has` `"knowledge": {`; `"dir"` with `"default": "knowledge"`; `"retrieveBudget"` with `"default": 8000`; `"warnBytes"` with `"default": 8192`; `"extraTypes"`; `assert_lacks "$SCHEMA" '"epicDocs"'`.

`== call sites ==`
- `$TK`: L17; L18; `assert_lacks "$TK" 'epic-doc.* operation .read('` — write as `assert_lacks "$TK" 'operation `read(metadata.parentTaskProperty'`; `assert_has "$TK" 'KNOWLEDGE_CONTEXT'`; `assert_lacks "$TK" 'getEpicContext('` (kept from verify-epic-doc); Phase 9 hook paragraph names `notion-dev:knowledge` (`assert_has`).
- `$NT`: L19; `assert_has "$NT" 'KNOWLEDGE_CONTEXT'`; `assert_lacks "$NT" 'operation `read(<epic-id>)`'`.
- `$NI`: L20; `assert_has "$NI" 'KNOWLEDGE:'`; `assert_lacks "$NI" 'epicDocs'`; `assert_has "$NI" 'operation `retrieve(<epic-id>)`'`.
- `$IN`: `iwe --version`; `python3`; L22; `assert_lacks "$IN" 'epicDocs'`; scaffold lines `index.md`, `log.md`, `.iwe/`.
- `$FZ`: `notion-dev:knowledge`; `assert_lacks "$FZ" 'HEAD == origin'`.
- `$TS`: `assert_has "$TS" 'superseded by `notion-dev:knowledge` `retrieve`'`.

`== signatures, README, version ==`
- three L23 rows as `assert_has` on `| \`partial:knowledge-retrieve\` |` etc.; README: `| \`/notion-dev:knowledge`, `**\`iwe\`**`, `**\`python3\`**`, `knowledge.dir`, `assert_lacks "$README" 'epicDocs'`, `assert_lacks "$README" 'Knowledge bundles are not touched'`; `assert_version_above "$MANIFEST" 0.23.0` (same call shape as `verify-new-info.sh`).

`== status vocabulary ==`
- `assert_lacks` `status: current` on `$KS $ED $KC $NI $TK $NT $IN`.

- [ ] **Step 2: Run it — expect FAIL on nearly everything**

Run: `bash scripts/verify-knowledge.sh; echo "exit $?"`
Expected: many FAIL lines, non-zero exit.

- [ ] **Step 3: Run `verify-assertions.sh` — must accept the harness**

Run: `bash scripts/verify-assertions.sh`
Expected: PASS (the new harness sources only `assert.sh`).

- [ ] **Step 4: Commit**

```bash
git add scripts/verify-knowledge.sh
git commit -m "test(notion-dev): verify-knowledge.sh — red harness for the knowledge skill and its call sites

Claude-Session: https://claude.ai/code/session_014WgcLXWYFooDsYZCax4zXm"
```

---

### Task 3: `skills/knowledge/SKILL.md` and `commands/knowledge.md`

**Files:**
- Create: `plugins/notion-dev/skills/knowledge/SKILL.md`
- Create: `plugins/notion-dev/commands/knowledge.md`

**Interfaces:**
- Consumes: `knowledge.py` CLI (Task 1); `notion-dev:ticket-system` `fetchTicket`, `listEpicChildren`; `notion-dev:epic-doc` "Bootstrap" (in-memory) and the brief parse; `notion-dev:issue-log` signatures (Task 6 adds the rows; write the names now).
- Produces: `retrieve(...)` → `KNOWLEDGE_CONTEXT`, `EPIC_CONTEXT`, `NEXT`, `BLOCKED`, `STATUS`, `CHILDREN`, `BOOTSTRAP`, `SEED`; `capture(...)` → the `KNOWLEDGE:` block; `curate`, `migrate [--apply]`.

- [ ] **Step 1: Write `SKILL.md`**

Frontmatter: `name: knowledge`, `description:` one sentence naming the four operations and that it is the only skill that invokes `iwe` besides `scripts/knowledge.py`. Sections, in order, hard-wrapped at 100 columns:

1. `# knowledge` — intro: what the bundle is (spec §2 layout block verbatim), config keys, the read-once rule in one paragraph, the dependency line (`iwe` ≥ 0.19 and `python3`; both install routes from spec §1 verbatim), and the sentence that this skill and `scripts/knowledge.py` are the only iwe callers.
2. `## Read-once` — the spec §4 table verbatim.
3. L1 heading — spec §4 steps 1–5 verbatim, with L2 in a fenced block and L3 in the step-3 sentence; the "parse of the root" paragraph that defines `EPIC_CONTEXT` as the first fenced document of the retrieve output (iwe emits each document as a ```` ````markdown #<key> ```` fence) with its frontmatter stripped; the budget paragraph.
4. L4 heading — invocation (hook and `--fact`), the three preconditions as bullets (L15), the inputs paragraph containing `never from Notion`, steps 1–6 from spec §5 with L5, L6, L7, L8, L14, `git checkout -- <knowledge.dir>`, `git add -- <knowledge.dir>`, L9, L10, and the output block (L11 and `COMMIT: <sha> | none`) in a fence.
5. `## \`curate\`` — spec §6 with L12, `keep both`, L8, `docs(knowledge): curate — <n> clusters resolved`.
6. `## \`migrate [--apply]\`` — spec §7 steps 1–8 with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" migrate` / `migrate --apply`, L8, `Without \`--apply\` it prints the complete diff and writes nothing`, `removal checklist`, `never deletes client code`, `postMergeHooks`.
7. `## Failure handling` — spec §10 in prose: best-effort against the flow; signatures `partial:knowledge-retrieve`, `partial:knowledge-capture`, `missing-dependency:iwe`.

- [ ] **Step 2: Write `commands/knowledge.md`**

Frontmatter as `new-info.md` (`description`, `argument-hint: migrate [--apply] | curate`, `disable-model-invocation: true`). Body: `# /notion-dev:knowledge`; `## Preconditions` (REPO_ROOT, config, `iwe --version` ≥ 0.19 with the install message, `python3`, primary on `<epicBranch>` with a clean tree — reuse `new-info.md`'s precondition wording by reference); `## \`migrate\`` → invoke `notion-dev:knowledge` operation `migrate` (with `--apply` when given), print the diff, and under `--apply` the removal checklist; `## \`curate\`` → operation `curate`; `## Report` (the `KNOWLEDGE:` line, the commit, the closeout workspace pass as `new-info.md`'s Report does).

- [ ] **Step 3: Run the harness — skill and command sections green**

Run: `bash scripts/verify-knowledge.sh 2>&1 | grep -E 'knowledge skill|command: knowledge|FAIL' | head -40`
Expected: no FAIL under the `knowledge skill:` and `command: knowledge.md` groups; other groups still red.

- [ ] **Step 4: Commit**

```bash
git add plugins/notion-dev/skills/knowledge/SKILL.md plugins/notion-dev/commands/knowledge.md
git commit -m "feat(notion-dev): knowledge skill — retrieve, capture, curate, migrate; /notion-dev:knowledge

Claude-Session: https://claude.ai/code/session_014WgcLXWYFooDsYZCax4zXm"
```

---

### Task 4: `epic-doc`, the config schema, `ticket-system`, and `verify-epic-doc.sh`

**Files:**
- Modify: `plugins/notion-dev/skills/epic-doc/SKILL.md`
- Modify: `plugins/notion-dev/schema/notion-dev.config.schema.json`
- Modify: `plugins/notion-dev/skills/ticket-system/SKILL.md` (the `## getEpicContext(` section's first paragraph)
- Modify: `scripts/verify-epic-doc.sh`

**Interfaces:**
- Consumes: `retrieve` (Task 3).
- Produces: `epic-doc read(<epic-id>, <current-ticket-id>?, KNOWLEDGE_CONTEXT?)` — with `KNOWLEDGE_CONTEXT` supplied it fetches nothing; `record`/`note` writing the Epic frontmatter and link-form bullets; `record --bootstrap` writing into `<knowledge.dir>/epic/`.

- [ ] **Step 1: Edit `epic-doc/SKILL.md`**

- Line 14 `**Path:**` paragraph → L16, then: `knowledge.dir` comes from `.claude/notion-dev.config.json` (default `knowledge`); the rest of the paragraph unchanged.
- Template block: add the spec §3 frontmatter above the H1 (`type: Epic`, `title`, `description`, `status: stable`, `epic`, `generated`, `sources`). Add one sentence after the template: bullets under `## Decisions & constraints` and `## Open threads` may link a concept (example from spec §3), and `record` and `note` write the link form whenever a concept for the fact exists.
- `## read(...)`: retitle to `read(<epic-id>, <current-ticket-id>?, KNOWLEDGE_CONTEXT?)`. Step 2 becomes: when `KNOWLEDGE_CONTEXT` is supplied, take the root document from it (the first fenced document) and skip the fetch; otherwise invoke `notion-dev:knowledge` `retrieve(<epic-id>, <current-ticket-id>)` and take its root. Steps 3–4 unchanged except the `ls-tree` path → `<knowledge.dir>/epic/`.
- Bootstrap step 1: seed search also lists `<knowledge.dir>/epic/`; step 3's `getEpicContext` sentence stays (it is the Notion-source bootstrap).
- `record` and `record --bootstrap`: every `<epicDocs.dir>` → `<knowledge.dir>/epic/`; the "creating the dir if absent" line → `creating <knowledge.dir>/epic/ if absent`; the write step adds "with the frontmatter of the template when creating; preserve existing frontmatter verbatim otherwise, updating only `updated` and the `Status:` header".
- `note --apply`: same path substitution.
- Search the file for `epicDocs` and `docs/epics` — zero must remain.

- [ ] **Step 2: Edit the config schema**

Remove the `"epicDocs"` property entirely. Add, at the same position:

```json
"knowledge": {
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "dir": {
      "type": "string",
      "default": "knowledge",
      "minLength": 1,
      "pattern": "<copy the epicDocs.dir pattern verbatim>",
      "description": "Directory, relative to the repo root, holding the OKF knowledge bundle notion-dev:knowledge reads and writes. The epic brief lives at <dir>/epic/<KEY>-<n>-<slug>.md."
    },
    "retrieveBudget": { "type": "integer", "minimum": 1000, "default": 8000, "description": "--max-tokens passed to iwe retrieve: the bundle's share of a run's context." },
    "warnBytes": { "type": "integer", "minimum": 1024, "default": 8192, "description": "Per-concept size above which knowledge.py check warns. Never fails." },
    "extraTypes": { "type": "array", "items": { "type": "string", "pattern": "^[a-z][a-z0-9-]*$" }, "default": [], "description": "Client-specific concept directories accepted beyond the canonical set." }
  }
}
```

Validate the file with `python3 -c 'import json,sys; json.load(open(sys.argv[1]))' plugins/notion-dev/schema/notion-dev.config.schema.json`.

- [ ] **Step 3: Edit `ticket-system/SKILL.md`**

In `## getEpicContext(epicId, currentTicketId)`'s first paragraph, replace the sentence beginning `/notion-dev:ticket no longer calls this` with: `Superseded by \`notion-dev:knowledge\` \`retrieve\` for every context read; only \`notion-dev:epic-doc\`'s Notion-source bootstrap still calls it.` Keep the rest.

- [ ] **Step 4: Update `verify-epic-doc.sh`**

Lines 97–100: the `epicDocs.dir` block → `assert_lacks "schema no longer declares \`epicDocs\`" "$SCHEMA" '"epicDocs"'` and `assert_has "schema declares \`knowledge.dir\` default \`knowledge\`" "$SCHEMA" '"default": "knowledge"'`. Line 165–166: keep `## getEpicContext(` present; change the second label/regex to the new "Superseded by" sentence fragment `notion-dev:epic-doc.'s Notion-source bootstrap`. Line 196: `README documents \`knowledge.dir\`` with regex `` `knowledge.dir` ``. Any anchor on `<epicDocs.dir>` in the epic-doc region → `<knowledge.dir>/epic/`, with `assert_count` where it now appears more than once (state the count in the label).

- [ ] **Step 5: Run the harnesses**

Run: `bash scripts/verify-epic-doc.sh && bash scripts/verify-knowledge.sh 2>&1 | grep -E '== |FAIL' | head -60`
Expected: `verify-epic-doc.sh` passes; `verify-knowledge.sh` has no FAIL under `epic-doc`, `config schema`, and the `$TS` line.

- [ ] **Step 6: Commit**

```bash
git add plugins/notion-dev/skills/epic-doc/SKILL.md plugins/notion-dev/schema/notion-dev.config.schema.json plugins/notion-dev/skills/ticket-system/SKILL.md scripts/verify-epic-doc.sh
git commit -m "feat(notion-dev): epic brief becomes the bundle's epic root; knowledge config block replaces epicDocs

Claude-Session: https://claude.ai/code/session_014WgcLXWYFooDsYZCax4zXm"
```

---

### Task 5: Call sites — `ticket`, `next-task`, `new-info`, `init`, `finalize`, and `verify-new-info.sh`

**Files:**
- Modify: `plugins/notion-dev/commands/ticket.md` (1.1 epic-context paragraph, 1.3, 4.2/4.3 context passing, Phase 9 hook paragraph)
- Modify: `plugins/notion-dev/commands/next-task.md` (§1 Read the brief, §3 Delegate)
- Modify: `plugins/notion-dev/commands/new-info.md` (Preconditions, Read, Apply, Report)
- Modify: `plugins/notion-dev/commands/init.md` (1 Preflight, 9 Write files, 11 Report)
- Modify: `plugins/notion-dev/commands/finalize.md` (hook paragraph)
- Modify: `plugins/notion-dev/skills/epic-update/SKILL.md`, `plugins/notion-dev/skills/issue-log/SKILL.md` — only if `grep -n 'epicDocs\|docs/epics'` hits; replace with `knowledge.dir` / `<knowledge.dir>/epic/`
- Modify: `scripts/verify-new-info.sh` line 64 anchor

**Interfaces:**
- Consumes: `retrieve` (Task 3), `capture --fact` (Task 3), `epic-doc read` with `KNOWLEDGE_CONTEXT` (Task 4).

- [ ] **Step 1: `ticket.md`**

- 1.1 "Epic context" paragraph → `**Epic context.** When \`metadata.parentTaskProperty\` is non-empty, ` + L17 + `, and record the result as \`KNOWLEDGE_CONTEXT\` and \`EPIC_CONTEXT\` (its root). ` + L18 + ` — \`/notion-dev:next-task\` passes it so the bundle is read once per run. It reads the epic's root concept and its linked concepts from \`origin/<epicBranch>\` under \`knowledge.retrieveBudget\` — **never the Notion epic page** — and \`KNOWLEDGE_CONTEXT: unavailable\` when \`iwe\` is missing.` Keep the following "background, not requirements" paragraph, adding `KNOWLEDGE_CONTEXT` beside `EPIC_CONTEXT`.
- Every later `EPIC_CONTEXT` mention in 1.3, 4.2, 4.3 (lines ~110, 166, 192, 204): pass `KNOWLEDGE_CONTEXT` instead, keeping the `--- EPIC CONTEXT (background, not requirements) ---` label text unchanged (harness `verify-epic-doc.sh` may pin it — check before editing; if pinned, keep the label and change only what follows it).
- Phase 9 "Post-merge hooks" paragraph: `a hook such as \`notion-dev:knowledge\` commits and pushes…`; add one sentence: the hook receives `<ticket-id>`, `<merge-sha>`, the ticket body, `KNOWLEDGE_CONTEXT`, and the review report from this run, and reads nothing from Notion.

- [ ] **Step 2: `next-task.md`**

§1: `Invoke the \`notion-dev:epic-doc\` skill, operation \`read(<epic-id>)\`` → L19 + `. It returns \`KNOWLEDGE_CONTEXT\`, \`EPIC_CONTEXT\`, \`NEXT\`, \`BLOCKED\`, \`STATUS\`, \`CHILDREN\`, \`BOOTSTRAP\`, and \`SEED\`.` §3 Delegate: pass `KNOWLEDGE_CONTEXT` to the `ticket` run so its 1.1 skips the fetch.

- [ ] **Step 3: `new-info.md`**

- Preconditions: add `iwe --version` ≥ 0.19 (`missing-dependency:iwe`) and `python3` beside `gh`+`jq`.
- Read: `operation \`retrieve(<epic-id>)\`` replacing the `epic-doc read` invocation; returns list gains `KNOWLEDGE_CONTEXT`; `ls-tree` anchor path → `<knowledge.dir>/epic/`.
- Apply: after the `note --apply` outcome bullets, a new paragraph: `Then invoke the \`notion-dev:knowledge\` skill, ` + L20 + `, passing \`KNOWLEDGE_CONTEXT\`, \`REPO_ROOT\`, and \`<epicBranch>\` (under \`--pr\`, \`--branch <noteBranch>\`). Record its \`KNOWLEDGE:\` line; \`failed\` records \`partial:knowledge-capture\` and does not stop the loop.`
- Report: per-epic line gains ` · knowledge: <captured|empty|failed|unavailable>`; delete the `knowledge bundle: not touched — <hooks> run at the next ticket merge` line (and its harness anchor in `verify-new-info.sh` — replace with `assert_present` on `knowledge: <captured`).
- `--pr` section: the note branch commit list now includes the capture commit; `git push -u origin <noteBranch>` happens once after both.

- [ ] **Step 4: `init.md`**

- Preflight: after the `gh` probe add `Probe \`iwe --version\` (≥ 0.19) and \`python3 --version\`. Record both; missing → the warning text names \`cargo install iwe --root ~/.local\` and the GLIBC 2.39 note for npm/brew.`
- Step 9: after `.mcp.json`, add: `Scaffold \`<knowledge.dir>/\` when absent: copy \`${CLAUDE_PLUGIN_ROOT}/skills/knowledge/references/iwe/\` to \`<knowledge.dir>/.iwe/\`, write \`index.md\` (\`okf_version: "0.2"\` frontmatter, \`# Index\`) and \`log.md\` (\`# Update log\`), create the canonical type directories, and set ` + L22 + ` in the config. Never overwrite an existing bundle's \`index.md\` or \`log.md\`.` Remove the `preMergeChecks: [], postMergeHooks: []` sentence at line ~312 for the hook (keep `preMergeChecks: []`).
- Report: one line for the scaffold.

- [ ] **Step 5: `finalize.md`**

Hook paragraph: `knowledge-capture` → `notion-dev:knowledge`, same inputs sentence as ticket.md. Confirm `HEAD == origin` does not appear.

- [ ] **Step 6: Sweep `epicDocs` / `docs/epics` across the plugin**

Run: `grep -rn 'epicDocs\|docs/epics' plugins/notion-dev --include=*.md --include=*.json`
Expected: zero hits. Fix any remaining (`epic-update/SKILL.md`, `issue-log/SKILL.md`, `signatures.md` if it cites `epicDocs`).

- [ ] **Step 7: Run all harnesses**

Run: `for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done 2>&1 | grep -E 'FAILED|FAIL:' | head`
Expected: only `verify-knowledge.sh` failures remaining, and only under `signatures, README, version`.

- [ ] **Step 8: Commit**

```bash
git add plugins/notion-dev/commands scripts/verify-new-info.sh plugins/notion-dev/skills
git commit -m "feat(notion-dev): ticket, next-task, new-info read the bundle once via retrieve; init scaffolds it; hooks named notion-dev:knowledge

Claude-Session: https://claude.ai/code/session_014WgcLXWYFooDsYZCax4zXm"
```

---

### Task 6: Signatures, README, version, spec pointer, mutation proof

**Files:**
- Modify: `plugins/notion-dev/skills/issue-log/references/signatures.md`
- Modify: `plugins/notion-dev/README.md`
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json`
- Modify: `docs/superpowers/specs/2026-09-13-epic-doc-design.md` (one line)
- Create (scratchpad only): `mutate-knowledge.sh`

- [ ] **Step 1: Signature rows**

Append to the registry table, in the existing column format:

```
| `partial:knowledge-retrieve` | degraded | `knowledge/SKILL.md` | `iwe` missing or `retrieve` failed; brief served alone | once/run |
| `partial:knowledge-capture` | degraded | `knowledge/SKILL.md` | `check` failed or push rejected; nothing written or commit unpushed | once/run |
| `missing-dependency:iwe` | precondition | `ticket.md`, `next-task.md`, `new-info.md`, `knowledge.md` | `iwe` absent or below 0.19 | once/run |
```

Match the `Kind` vocabulary the table already uses (read the existing rows; `degraded` is what `partial:new-info` uses).

- [ ] **Step 2: README**

- Prerequisites: two bullets after `jq`: `- **\`iwe\` ≥ 0.19 on \`PATH\`** — **required**. …both install routes…`; `- **\`python3\`** — **required** for \`scripts/knowledge.py\`…`.
- Commands table: `| \`/notion-dev:knowledge migrate [--apply] \| curate\` | … |` (escape the pipe inside the cell as the table already does elsewhere, or write `migrate` and `curate` as two rows).
- Configuration list: replace the `epicDocs.dir` bullet with `knowledge.dir`, `knowledge.retrieveBudget`, `knowledge.warnBytes`, `knowledge.extraTypes`.
- `## Epics` → the `### Epic docs` subsection becomes `### Knowledge bundle`: the brief is the epic's root concept at `<knowledge.dir>/epic/…`; what a concept is; valid until superseded; one retrieve per run; the hook; `migrate` for existing clients with a pointer to the spec §13 removal inventory.
- The `new-info` bullet's last sentence (`Knowledge bundles are not touched…`) → `The same fact reaches the knowledge bundle through \`capture --fact\`.`
- Layout tree: add `skills/knowledge/`, `scripts/knowledge.py`, `commands/knowledge.md`.
- Post-merge hooks paragraph (Phase-2 seams): `knowledge-capture` example → `notion-dev:knowledge`.

- [ ] **Step 3: Version and spec pointer**

`plugin.json`: `"version": "0.24.0"`. Top of `2026-09-13-epic-doc-design.md`, after the title: `> Superseded in part by \`2026-09-14-knowledge-bundle-design.md\` (0.24.0): the brief now lives at \`<knowledge.dir>/epic/\` as the bundle's root concept.`

- [ ] **Step 4: Full suite green, then commit**

Run: `for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done 2>&1 | grep -E 'FAILED|FAIL:'`
Expected: no output.

```bash
git add -A
git commit -m "docs(notion-dev): knowledge bundle — signatures, README, 0.24.0

Claude-Session: https://claude.ai/code/session_014WgcLXWYFooDsYZCax4zXm"
```

- [ ] **Step 5: Mutation-test both new harnesses (after the commit)**

Write `<scratchpad>/mutate-knowledge.sh`: for every `assert_*` line in `scripts/verify-knowledge.sh`, apply the smallest edit to the guarded file that should flip it (delete the matched line with `sed -i`, or append a duplicate for `assert_present`/`assert_count`, or insert the forbidden literal for `assert_absent`/`assert_lacks`), run the harness, record `HIT` if it fails and `MISS` if it passes, then `git checkout -- <file>`. For `verify-knowledge-py.sh`, mutate `knowledge.py` (comment out each rule's `findings.append`) and each fixture (restore the defect in `valid/`) and expect FAIL. Report: `<hits> HIT / <misses> MISS`; a MISS is a defect in the assertion — fix it in the harness, re-run, commit the fix. The script stays in the scratchpad.

---

### Task 7: Ship

- [ ] **Step 1: Push and open the PR**

```bash
git push -u origin knowledge-bundle
gh pr create --base main --title "feat(notion-dev): knowledge bundle — one shared implementation, brief as epic root (0.24.0)" --body-file <scratchpad>/pr-body-knowledge.md
```

PR body: summary; the nine decisions with 6, 7, 8 called out as behaviour changes for clients; the read-once table; what clients must do next (spec §13); harness counts and the mutation result; ends with `https://claude.ai/code/session_014WgcLXWYFooDsYZCax4zXm`.

- [ ] **Step 2: Review and merge**

Invoke `notion-dev:review-and-merge <pr> --pre-merge-check "the completion pass of session-closeout must come back with no tails and the full verify suite (for h in scripts/verify-*.sh; do \"$h\" || echo FAILED; done) must pass on this branch"`.

- [ ] **Step 3: Tag**

After the squash merge lands on `main`: `git checkout main && git pull --ff-only && git tag notion-dev-v0.24.0 && git push origin notion-dev-v0.24.0`. Client CI fetches `knowledge.py` by this tag (spec §13).

- [ ] **Step 4: Closeout**

Delete the local branch and the SDD workspace; run `session-closeout`'s workspace pass; report with the `CLOSEOUT:` block.
