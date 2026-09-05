# feedback-harvest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `feedback-harvest`, a repo-local maintainer skill that reads the `notion-dev` runtime issue logs out of client repos, forces every signature into one of five dispositions, applies the warranted fixes in a single PR, archives the redacted evidence here, and resets the client logs after the merge.

**Architecture:** Nothing in this repo executes — the plugins are markdown instruction files and the test suite is `scripts/verify-*.sh`. So the TDD cycle is: **write the assertion, run the harness and watch it FAIL, write the markdown, run it and watch it PASS, mutate the markdown and watch it FAIL again, restore, commit.** The deliverable is one `SKILL.md`, one new harness, an extension to `verify-mirror.sh`, and a tracked manifest that makes a repo-local skill legal under the mirror invariant.

**Tech Stack:** Bash (`scripts/lib/assert.sh`), Markdown, git, `gh`.

**Spec:** `docs/superpowers/specs/2026-09-04-feedback-harvest-design.md` — read it before starting. Every task argues from it.

## Global Constraints

- **Skill path:** `.claude/skills/feedback-harvest/SKILL.md`. Manifest: `.claude/skills/REPO-LOCAL`.
- **Assertions come only from `scripts/lib/assert.sh`.** Never hand-roll one — `verify-assertions.sh` A3 fails any harness that sources anything else or defines its own helper.
- **A label is a claim the regex must honour.** `assert_covers` extracts five literal classes from every label: a `` `backticked` `` span (required unconditionally in the regex), plus ALLCAPS, `--flag`, `<placeholder>`, and Capitalized words (required when the matched line also contains them; the label's *first* word is exempt from the Capitalized class only). A label saying "Phase 5" whose matched line says `Phase` needs `Phase` in the regex.
- **An anchor names one place.** `assert_present` requires exactly one matching line in its region. Two matches is a failure, not a pass. Use `assert_count … <n>` only where the document cites the mechanism `<n>` times on purpose.
- **Never match a phrase that spans a line break.** These files are hard-wrapped; `assert_has` rejects a multi-line literal outright, but a hand-written regex spanning a wrap silently matches nothing. Match the shortest distinctive fragment on one line.
- **Region idiom:** `L=$(total_lines "$F")`, then pass `"$F" 1 "$L"`. Immune to line shifts.
- **No plugin version bump in this PR.** CLAUDE.md's "bump exactly once per PR" governs *plugin* PRs — those touching `plugins/`. This PR touches only `.claude/`, `scripts/`, and `docs/`, so neither `plugin.json` changes. Do not bump either; a bump here would be a lie about what shipped.
- **One PR for the whole plan**, per CLAUDE.md convergence. Widening is cheaper than splitting.
- **Commit before mutation-testing.** A `git checkout -- .` to undo a mutation silently reverts uncommitted work.
- **Run the whole suite before reporting done:**
  ```bash
  for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done
  ```
- **Branch:** `feat/feedback-harvest` already exists and holds the spec commit. Work on it.

---

### Task 1: The repo-local carve-out

Makes a non-mirrored skill legal under `verify-mirror.sh` without weakening it. Must land first: creating the skill directory before this rule exists turns the suite red.

**Files:**
- Create: `.claude/skills/REPO-LOCAL`
- Create: `.claude/skills/feedback-harvest/SKILL.md` (stub — filled in by Tasks 2-8)
- Modify: `scripts/verify-mirror.sh`
- Modify: `CLAUDE.md` (the `## The .claude/skills/ mirror` section)
- Modify: `.claude/skills/review-and-merge/README.md`

**Interfaces:**
- Produces: `.claude/skills/feedback-harvest/SKILL.md` at a path every later task appends to; `REPO-LOCAL` as the one place a repo-local skill is declared.

- [ ] **Step 1: Confirm the manifest path is trackable**

`.gitignore` ignores `.claude/*` and re-includes only `!.claude/skills/`. Verify a file directly under that directory is visible to git before relying on it:

```bash
touch .claude/skills/PROBE && git check-ignore -v .claude/skills/PROBE; echo "ignored=$?"
git status --porcelain .claude/skills/PROBE
rm .claude/skills/PROBE
```

Expected: `ignored=1` (not ignored) and a `?? .claude/skills/PROBE` line. If it is ignored, stop — the manifest needs a different home (`scripts/repo-local-skills.txt`) and the plan needs revising.

- [ ] **Step 2: Write the failing assertions in `verify-mirror.sh`**

Insert immediately after the `. ./scripts/lib/assert.sh` line, before the `mirrored=0` loop:

```bash
# ---------------------------------------------------------------------------
# Repo-local skills — the one documented exception to mirror parity
# ---------------------------------------------------------------------------
#
# `feedback-harvest` is a maintainer workflow for this marketplace. It belongs to
# neither shipped plugin: putting it in quick-dev would ship a notion-dev-specific
# harvester to everyone installing a generic feature-development plugin, and
# notion-dev's skills are not mirrored, so it would not be invocable here at all.
#
# The exemption is a TRACKED MANIFEST, never a naming convention. A directory
# under the mirror root that is in neither set still FAILs, which is the property
# .gitignore's comment depends on — the whole mirror directory is un-ignored, and
# this loop is what makes that exposure safe.
LOCAL_MANIFEST=$MIRROR_ROOT/REPO-LOCAL

is_repo_local() {
  [ -f "$LOCAL_MANIFEST" ] || return 1
  grep -qxF -- "$1" <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' "$LOCAL_MANIFEST")
}

echo "== repo-local skill manifest =="

if [ -f "$LOCAL_MANIFEST" ]; then
  ok "REPO-LOCAL manifest present"
else
  bad "REPO-LOCAL manifest missing at $LOCAL_MANIFEST"
fi

if [ "$IN_GIT" = yes ]; then
  if git ls-files --error-unmatch "$LOCAL_MANIFEST" >/dev/null 2>&1; then
    ok "REPO-LOCAL manifest is tracked by git"
  else
    bad "REPO-LOCAL manifest is NOT tracked by git (check .gitignore)"
  fi
fi

# Every declared name must exist, and must NOT have a plugin counterpart. The
# second half is the guard that matters: without it a drifted mirror could be
# relabelled repo-local and skip parity entirely.
while IFS= read -r name; do
  [ -n "$name" ] || continue
  if [ -d "$MIRROR_ROOT/$name" ]; then
    ok "repo-local '$name' exists on disk"
  else
    bad "repo-local '$name' is declared in REPO-LOCAL but absent from $MIRROR_ROOT"
  fi
  if [ -d "$PLUGIN_SKILLS/$name" ]; then
    bad "repo-local '$name' also exists in $PLUGIN_SKILLS — a mirror cannot declare itself repo-local"
  else
    ok "repo-local '$name' has no plugin counterpart"
  fi
done < <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' "$LOCAL_MANIFEST" 2>/dev/null | grep -v '^$')
```

Then change the mirror loop's "exists only in the mirror" branch. Replace:

```bash
  if [ ! -d "$src" ]; then
    bad "$skill exists only in the mirror (project-local fork)"
    continue
  fi
```

with:

```bash
  if [ ! -d "$src" ]; then
    if is_repo_local "$skill"; then
      ok "$skill is a declared repo-local skill (no mirror parity expected)"
      # Content parity is meaningless without a counterpart, but *tracked-ness*
      # is not — that is the failure a fresh checkout caught once already.
      if [ "$IN_GIT" = yes ]; then
        while IFS= read -r f; do
          if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
            ok "$skill: ${f#"$MIRROR_ROOT"/} is tracked by git"
          else
            bad "$skill: ${f#"$MIRROR_ROOT"/} is NOT tracked by git (check .gitignore)"
          fi
        done < <(find "$mdir" -type f | sort)
      fi
    else
      bad "$skill exists only in the mirror and is not declared in REPO-LOCAL (project-local fork)"
    fi
    continue
  fi
```

Finally, `mirrored=$((mirrored + 1))` currently counts repo-local dirs toward the "mirror set cannot be empty" check. Move it below the repo-local branch so it counts only true mirrors.

- [ ] **Step 3: Run it and watch it fail**

Run: `./scripts/verify-mirror.sh`
Expected: `FAIL  REPO-LOCAL manifest missing at .claude/skills/REPO-LOCAL`, and a non-zero exit.

- [ ] **Step 4: Create the manifest**

```bash
cat > .claude/skills/REPO-LOCAL <<'EOF'
# Skills under .claude/skills/ that are NOT mirrors of plugins/quick-dev/skills/.
#
# A directory here is exempt from mirror parity and from nothing else — it is
# still checked for git-trackedness, it still must exist on disk, and it still
# must NOT have a plugin counterpart (a mirror cannot relabel itself local to
# dodge parity). A directory in neither set fails, which is what keeps the
# un-ignored mirror root safe to `git add -A` into.
#
# One name per line. Anything after `#` is a comment.

feedback-harvest
EOF
```

- [ ] **Step 5: Create the skill stub**

```bash
mkdir -p .claude/skills/feedback-harvest
cat > .claude/skills/feedback-harvest/SKILL.md <<'EOF'
---
name: feedback-harvest
description: Use when picking up the notion-dev runtime issue logs from client repos and acting on them — "harvest client feedback", "apply the plugin feedback", "process notion-dev-issues", "pick up feedback from the clients". Reads each client's `.claude/notion-dev/notion-dev-issues.md`, forces every signature into one of five dispositions, applies the warranted fixes in a single pull request, archives the redacted evidence in this repo, and resets the client logs after the merge.
---

# feedback-harvest — read the issue logs by mechanism, not by recall

`notion-dev:issue-log` writes a runtime deviation into every client repo at the moment it
happens. Nothing reads those logs by mechanism. The one harvest that has happened was by hand,
and its fingerprint is still in the tree — `plugins/notion-dev/commands/ticket.md` cites
"Measured on `notion-dev` 0.20.2: BTC-Gateway STO-77 wrote no `review-report-STO-77.md` at
all" — while every other entry in that same file went unread.

The cost of that asymmetry is not lost feedback. It is **feedback harvested selectively and
invisibly**: nothing records which entries were considered and rejected, so a well-reasoned
rejection and an entry nobody ever opened are indistinguishable, and both get re-read forever.
EOF
```

- [ ] **Step 6: Run it and watch it pass**

Run: `./scripts/verify-mirror.sh`
Expected: `ALL CHECKS PASSED`, including `PASS  feedback-harvest is a declared repo-local skill (no mirror parity expected)`.

- [ ] **Step 7: Update `CLAUDE.md`**

The section currently opens "Every directory under `.claude/skills/` is a byte-identical mirror" — now false. Replace that opening paragraph with:

```markdown
Every directory under `.claude/skills/` is one of two kinds, and `scripts/verify-mirror.sh`
rejects anything that is neither. Most are **byte-identical mirrors** of the same-named
directory under `plugins/quick-dev/skills/`, so this repo drives its own work with the skills
it ships. Edit the plugin copy, then re-sync:
```

Then, after the existing `cp -r` block and its `verify-mirror.sh` paragraph, add:

```markdown
The other kind is a **repo-local skill** — a maintainer workflow that belongs to neither
shipped plugin, declared by name in `.claude/skills/REPO-LOCAL`. `feedback-harvest` is the
one that exists. A repo-local skill is exempt from mirror parity and from nothing else: it
must be tracked by git, it must exist on disk, and it must **not** have a `quick-dev`
counterpart — a mirror that relabelled itself repo-local would otherwise skip parity silently.
An undeclared directory still fails, which is what keeps the un-ignored mirror root safe.
```

- [ ] **Step 8: Update the mirror README**

`.claude/skills/review-and-merge/README.md` claims the rule for the whole directory. Append before the "Why this is a script and not a rule" heading:

```markdown
## Not every directory here is a mirror

`.claude/skills/REPO-LOCAL` declares the directories that are **not** mirrors — maintainer
workflows belonging to neither shipped plugin. They are exempt from parity and from nothing
else; `verify-mirror.sh` still requires them to be tracked, to exist, and to have no plugin
counterpart. A directory in neither set fails.
```

- [ ] **Step 9: Commit**

```bash
git add .claude/skills/REPO-LOCAL .claude/skills/feedback-harvest/SKILL.md \
        scripts/verify-mirror.sh CLAUDE.md .claude/skills/review-and-merge/README.md
git commit -m "feat: admit declared repo-local skills under the mirror invariant

A maintainer workflow belongs to neither shipped plugin, but .claude/skills/
is where a skill has to live to be invocable here. Rather than shipping
feedback-harvest inside quick-dev, verify-mirror.sh now recognises a tracked
REPO-LOCAL manifest.

The exemption is parity only. A declared name must exist on disk, must be
tracked by git, and must NOT have a quick-dev counterpart — without that last
guard a drifted mirror could relabel itself repo-local and skip parity. An
undeclared directory still fails, which is the property .gitignore's comment
depends on.

Claude-Session: https://claude.ai/code/session_01LWfJ1kDJk8ByDVzYA3rBAi"
```

- [ ] **Step 10: Prove each new check can fail**

```bash
# guard 1 — undeclared directory
mkdir -p .claude/skills/scratch && echo x > .claude/skills/scratch/SKILL.md
./scripts/verify-mirror.sh    # expect FAIL "not declared in REPO-LOCAL"
rm -rf .claude/skills/scratch

# guard 2 — declared but absent
echo 'ghost' >> .claude/skills/REPO-LOCAL
./scripts/verify-mirror.sh    # expect FAIL "absent from .claude/skills"
git checkout -- .claude/skills/REPO-LOCAL

# guard 3 — a mirror relabelling itself repo-local
echo 'review-and-merge' >> .claude/skills/REPO-LOCAL
./scripts/verify-mirror.sh    # expect FAIL "a mirror cannot declare itself repo-local"
git checkout -- .claude/skills/REPO-LOCAL

# guard 4 — manifest missing
mv .claude/skills/REPO-LOCAL /tmp/rl
./scripts/verify-mirror.sh    # expect FAIL "REPO-LOCAL manifest missing"
mv /tmp/rl .claude/skills/REPO-LOCAL

./scripts/verify-mirror.sh    # expect ALL CHECKS PASSED
```

---

### Task 2: The harness, and the five dispositions

**Files:**
- Create: `scripts/verify-feedback-harvest.sh`
- Modify: `.claude/skills/feedback-harvest/SKILL.md`

**Interfaces:**
- Produces: the harness skeleton (`SK`, `L`, `ok`/`bad`, the library source line) every later task appends assertions to; the `## Sources` and `### Phase 3 — Triage` sections.

- [ ] **Step 1: Write the harness skeleton and the failing disposition assertions**

```bash
cat > scripts/verify-feedback-harvest.sh <<'SH'
#!/usr/bin/env bash
# Standing invariant: the harvest reaches a decision about every signature it
# reads, redacts before anything leaves the client repo, and resets a client log
# only after the fixes have merged.
#
# Why an invariant and not a change-scoped check: the failure this skill exists
# to remove is a harvest that reads selectively and records nothing about what it
# skipped. That failure is silent — a well-reasoned rejection and an unread entry
# look identical afterwards — so the only defence is that the disposition set is
# closed and the orderings are pinned. Neither has a baseline to go stale
# against.
#
# Every check pins a MECHANISM: the presence of each disposition in the table,
# the externality bound on `blocked`, the relative order of the phases whose
# order is load-bearing, and the matching rule the reset uses.
#
# Run from anywhere: ./scripts/verify-feedback-harvest.sh
set -uo pipefail
cd "$(dirname "$0")/.."

SK=.claude/skills/feedback-harvest/SKILL.md
fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

. ./scripts/lib/assert.sh

if [ ! -f "$SK" ]; then
  bad "$SK is missing — nothing below can mean anything"
  echo "1 CHECK(S) FAILED"
  exit 1
fi
L=$(total_lines "$SK")

# ---------------------------------------------------------------------------
# The disposition set is closed
# ---------------------------------------------------------------------------
echo "== the five dispositions =="

assert_present "the set is closed at five and admits no sixth" \
  "$SK" 1 "$L" 'exactly \*\*one\*\* of five dispositions.*There is no sixth'

for d in apply stale decline track blocked; do
  assert_present "the disposition table carries \`$d\`" \
    "$SK" 1 "$L" "^\\| \`$d\` \\|"
done

# The externality bound is the whole load-bearing part of `blocked`. Without it,
# every item a harvest finds inconvenient becomes blocked, which is how the
# three-state rule is defeated everywhere else in this repo.
assert_present "\`blocked\` requires an external cause" \
  "$SK" 1 "$L" '\*\*The cause must be external\.\*\*'
assert_present "\`blocked\` excludes a plugin-internal cause" \
  "$SK" 1 "$L" 'A plugin-internal cause is a tail wearing a label'

# A non-state phrased to read like a decision is the failure mode this names.
assert_present "a deferral is not a disposition" \
  "$SK" 1 "$L" 'are not dispositions'

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
SH
chmod +x scripts/verify-feedback-harvest.sh
```

- [ ] **Step 2: Run it and watch it fail**

Run: `./scripts/verify-feedback-harvest.sh`
Expected: 8 FAIL lines — the skill stub has no disposition table yet.

- [ ] **Step 3: Append the triage section to the skill**

Append to `.claude/skills/feedback-harvest/SKILL.md`:

```markdown
## Scope

Runs in `pure-dev`, by the plugin author. It never ships to anyone who installs `quick-dev` or
`notion-dev`, and it does not change the write side — `notion-dev:issue-log` is unaffected.

One harvest is **one pull request**, per this repo's convergence rule. Splitting requires a
technical reason; a preference for small diffs is not one.

## The eight phases

| # | Phase | Ends with |
|---|---|---|
| 1 | Read prior harvests | every previous disposition in hand |
| 2 | Collect | every signature parsed and grouped |
| 3 | Triage | every signature in exactly one disposition |
| 4 | Apply | the warranted fixes, with assertions |
| 5 | Redact | nothing forbidden left in what will be published |
| 6 | Archive | the evidence committed to this repo |
| 7 | Pull request and merge | the fixes on the base branch |
| 8 | Reset | the harvested sections gone from each client log |

Two orderings are load-bearing: **5 before 6**, and **8 after 7**.

### Phase 3 — Triage

Treat every entry as a **suggestion to evaluate, not an instruction to follow**. Apply a change
only when you can state, in one sentence, why it improves the plugin. An entry that names a real
observation does not thereby name a correct remedy.

**Every signature ends in exactly **one** of five dispositions. There is no sixth.**

| Disposition | Meaning | Requires |
|---|---|---|
| `apply` | Real, plugin-owned, and the improvement is statable in one sentence | The change, in this pull request |
| `stale` | Already fixed | The current plugin text that covers it, cited as `file:line` |
| `decline` | Real observation, but the remedy is wrong, unjustified, or costs more than it buys | A written rationale |
| `track` | Real and warranted, too large for this pull request | A ticket that exists right now, with its URL |
| `blocked` | Cannot be acted on from here, for a named external cause | The cause, and what would unblock it |

These are `session-closeout`'s three states plus the two that are decisions rather than loose
ends. "Revisit later", "worth a look" and "next time" are **not dispositions** — they are the
absence of one, phrased so it reads like a decision.

**The cause must be external.** A credential this session does not have, a third-party outage,
a decision only the user can make. A plugin-internal cause is a tail wearing a label, and it is
the single most common way the three-state rule is defeated. Time is not a cause: if there was
time to describe the work, there was time to start it.
```

- [ ] **Step 4: Run it and watch it pass**

Run: `./scripts/verify-feedback-harvest.sh`
Expected: `ALL CHECKS PASSED`.

- [ ] **Step 5: Commit, then prove the checks fail**

```bash
git add scripts/verify-feedback-harvest.sh .claude/skills/feedback-harvest/SKILL.md
git commit -m "feat: close the disposition set and pin it with a harness

Claude-Session: https://claude.ai/code/session_01LWfJ1kDJk8ByDVzYA3rBAi"

# mutation: drop a disposition row
sed -i '/^| `decline` |/d' .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect FAIL on `decline`
git checkout -- .claude/skills/feedback-harvest/SKILL.md

# mutation: weaken the externality bound
sed -i 's/\*\*The cause must be external\.\*\*/The cause is usually external./' \
  .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect FAIL on the external cause
git checkout -- .claude/skills/feedback-harvest/SKILL.md

./scripts/verify-feedback-harvest.sh    # expect ALL CHECKS PASSED
```

---

### Task 3: Sources, prior harvests, and collection

**Files:**
- Modify: `.claude/skills/feedback-harvest/SKILL.md`
- Modify: `scripts/verify-feedback-harvest.sh`

**Interfaces:**
- Consumes: the `## The eight phases` table from Task 2.
- Produces: `## Sources`, `### Phase 1 — Read prior harvests`, `### Phase 2 — Collect`. Task 6 relies on the archive path `docs/feedback/` named here.

- [ ] **Step 1: Write the failing assertions**

Append before the closing `echo` in `scripts/verify-feedback-harvest.sh`:

```bash
# ---------------------------------------------------------------------------
# Sources and collection
# ---------------------------------------------------------------------------
echo "== sources and collection =="

assert_present "the client list is an untracked local file" \
  "$SK" 1 "$L" '`\.claude/notion-dev/clients\.txt`'
assert_present "an unreadable client is reported, never silently skipped" \
  "$SK" 1 "$L" 'reported and skipped.*never silently dropped'

# Phase 1 is what makes `decline` durable rather than a per-run coin flip. Drop
# it and every rejection is re-argued from scratch on the next harvest, with the
# reasoning written last time never read.
assert_present "prior harvests are read before any client log" \
  "$SK" 1 "$L" 'Read every `docs/feedback/\*\.md` archive \*\*before\*\* reading any client log'
assert_present "a reappearing signature is re-evaluated, not re-declined by rote" \
  "$SK" 1 "$L" 're-evaluated against the \*\*new\*\* evidence'

# issue-log dedups per repo, so one signature in two logs may be two conditions.
assert_present "cross-client grouping is a candidate, confirmed by reading both entries" \
  "$SK" 1 "$L" 'then \*\*confirm or split\*\* by reading both `Observed` fields'
```

- [ ] **Step 2: Run it and watch it fail**

Run: `./scripts/verify-feedback-harvest.sh`
Expected: 5 new FAIL lines.

- [ ] **Step 3: Append the sections**

```markdown
## Sources

Client repo paths come from `$REPO_ROOT/.claude/notion-dev/clients.txt` — one absolute path
per line, `#` for comments. The file is untracked: `.gitignore` ignores `.claude/*` and
re-includes only `!.claude/skills/`, and the paths are machine-specific while this repo is
public.

- Explicit paths passed as arguments override the file entirely.
- No file and no arguments → ask for the paths, and offer to write the file.
- A path that is not a directory, or holds no `.claude/notion-dev/notion-dev-issues.md`, is
  **reported and skipped** — never silently dropped. A client that quietly stops being
  harvested is the failure this skill was built to end.

### Phase 1 — Read prior harvests

Read every `docs/feedback/*.md` archive **before** reading any client log.

This is what makes `decline` a durable decision. A signature that reappears is matched against
its prior disposition and rationale and **re-evaluated against the **new** evidence** — a
higher occurrence count, a newer version range, a different `Observed`. Skip this and a
rejection is re-argued from scratch every harvest, with last time's reasoning never read.

### Phase 2 — Collect

For each client, parse the `## <signature>` sections. Record per section: the signature,
`Kind`, `Occurrences`, `First seen` and `Last seen` (timestamp **and** plugin version),
`Where`, `Expected`, `Observed`, `Effect`, `Context`, every free-form recurrence or correction
subsection appended below them, and the client's repo name.

**Read the whole section, not its first ten lines.** A recurrence appended later routinely
carries more than the original: one entry's third recurrence reports a *second consumer* of the
same defect and a wider exposure window than when it was filed.

Group across clients by signature, **then **confirm or split** by reading both `Observed`
fields.** `issue-log` dedups per repo, so the same signature in two logs may be one condition
or two. `mcp-unavailable:notion` is the live example: in one client the server registered and
its tool listing timed out; in the other no tool was ever registered at all. Same name, two
conditions.
```

- [ ] **Step 4: Run it and watch it pass**

Run: `./scripts/verify-feedback-harvest.sh` → `ALL CHECKS PASSED`.

- [ ] **Step 5: Commit and mutation-test**

```bash
git add -A && git commit -m "feat: sources, prior-harvest read, and cross-client grouping

Claude-Session: https://claude.ai/code/session_01LWfJ1kDJk8ByDVzYA3rBAi"

sed -i 's/\*\*before\*\* reading any client log/after reading the client logs/' \
  .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect FAIL on the prior-harvest order
git checkout -- .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect ALL CHECKS PASSED
```

---

### Task 4: The four triage rules

The rules the live client data forces, each of which a naive reading gets wrong.

**Files:**
- Modify: `.claude/skills/feedback-harvest/SKILL.md`
- Modify: `scripts/verify-feedback-harvest.sh`

**Interfaces:**
- Consumes: `### Phase 3 — Triage` from Task 2; appends to it.

- [ ] **Step 1: Write the failing assertions**

```bash
echo "== the triage rules =="

# Each rule exists because a specific live entry defeats the obvious reading.
assert_present "a host-caused entry is still evaluated for a documentation fix" \
  "$SK" 1 "$L" 'is not the same as \*\*no plugin change\*\*'
assert_present "an entry-s stated cause is evidence, never an inherited finding" \
  "$SK" 1 "$L" 'Triage re-derives the cause; it never inherits'
assert_present "an old first-seen version is a candidate, not a verdict" \
  "$SK" 1 "$L" 'is a `stale` \*\*candidate\*\*, never a `stale` verdict'
assert_present "a recurrence outranks the original entry" \
  "$SK" 1 "$L" 'A recurrence subsection \*\*outranks\*\* the original'

# Order: the rules qualify the table, so they must follow it. A rule hoisted
# above the disposition set reads as the primary instruction, which inverts it.
assert_order "triage: the closed set precedes the table precedes the rules that qualify it" \
  "$SK" 1 "$L" \
  "closed set"  'There is no sixth' \
  "table row"   '^\| `blocked` \|' \
  "first rule"  'is not the same as \*\*no plugin change\*\*'
```

- [ ] **Step 2: Run it and watch it fail** — 5 new FAIL lines.

- [ ] **Step 3: Append the rules to Phase 3**

```markdown
**Four rules the live client data forces.** Each is here because the obvious reading of a real
entry produces the wrong disposition.

1. **"Not the plugin's bug" is not the same as **no plugin change**.** One entry says outright
   that the worktree is created correctly and that gitignored files are gitignored by design —
   *and* that a one-line note in `ticket.md` Phase 2.1 would remove the ambiguity cheaply,
   because the failure looks like a deploy regression right before a merge gate. Evaluate every
   host-caused or client-setup-caused entry for a documentation fix before dismissing it.

2. **An entry's stated cause is evidence, not a finding.** One entry recorded a mechanism
   ("self-relations are inherently symmetric") that was later disproved, and its own correction
   notes the drop-and-recreate it rested on never took effect. Triage re-derives the cause; it
   never inherits the entry's conclusion.

3. **An old `First seen` version is a `stale` **candidate**, never a `stale` verdict.** Confirm
   by reading the current plugin text and citing it as `file:line`. Entries recorded against
   `0.12.2` against a plugin now past `0.21.0` include defects that are still present.

4. **A recurrence subsection **outranks** the original.** Recurrences are appended below the
   five fixed fields and routinely carry the sharper finding — a second consumer of the same
   defect, a wider window, or a prediction the later occurrence confirmed.
```

- [ ] **Step 4: Run it and watch it pass.**

- [ ] **Step 5: Commit and mutation-test**

```bash
git add -A && git commit -m "feat: the four triage rules the live client logs force

Claude-Session: https://claude.ai/code/session_01LWfJ1kDJk8ByDVzYA3rBAi"

# move a rule above the table — the order assertion must catch it
python3 - <<'PY'
import re,pathlib
p=pathlib.Path('.claude/skills/feedback-harvest/SKILL.md'); t=p.read_text()
r='1. **"Not the plugin\'s bug"'
i=t.index(r); j=t.index('\n\n2. **An entry')
block=t[i:j]; t=t[:i]+t[j:]
k=t.index('| Disposition | Meaning | Requires |')
p.write_text(t[:k]+block+'\n\n'+t[k:])
PY
./scripts/verify-feedback-harvest.sh    # expect FAIL on the triage order
git checkout -- .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect ALL CHECKS PASSED
```

---

### Task 5: Phase 4 — Apply

**Files:**
- Modify: `.claude/skills/feedback-harvest/SKILL.md`
- Modify: `scripts/verify-feedback-harvest.sh`

- [ ] **Step 1: Write the failing assertions**

```bash
echo "== applying the fixes =="

assert_present "every applied fix is covered by an assertion in a verify harness" \
  "$SK" 1 "$L" 'covered by an assertion in some `scripts/verify-\*\.sh`'
assert_present "a standing invariant is preferred over a change-scoped harness" \
  "$SK" 1 "$L" 'rather than minting a change-scoped one with a version floor'
assert_present "each new assertion is mutation-tested against the file it guards" \
  "$SK" 1 "$L" 'break the file it guards, confirm `FAIL`, restore'
assert_present "the work is committed before any mutation" \
  "$SK" 1 "$L" 'Commit \*\*first\*\*'
# notion-dev vendors adapted forks of several quick-dev skills; a fix to shared
# behaviour that lands in one copy silently diverges the other.
assert_present "a shared-behaviour fix lands in both plugins" \
  "$SK" 1 "$L" 'change both copies and check the wording that differs'
assert_present "a fix is widened into this pull request rather than deferred" \
  "$SK" 1 "$L" 'is explicitly \*not\* a reason to defer'
```

- [ ] **Step 2: Run it and watch it fail** — 6 new FAIL lines.

- [ ] **Step 3: Append Phase 4**

```markdown
### Phase 4 — Apply

Every `apply` item becomes a change under `plugins/`.

- **One pull request.** Widening it is cheaper than splitting it, and "it touches a file this
  pull request was not already changing" is explicitly *not* a reason to defer a small fix. Say
  in the body that the scope widened, and why.
- **Do not file what you are about to fix.** `track` is for what genuinely cannot land here,
  never for what would be tidier in its own pull request. A filed item that the same session
  then works costs a whole extra review-and-merge cycle.
- **Shared behaviour changes in both plugins.** `plugins/notion-dev` vendors adapted forks of
  several `quick-dev` skills. When a fix touches shared behaviour, change both copies and check
  the wording that differs — plugin names, config paths, reviewer defaults.
- **Re-sync any mirrored skill you edit**, then run `scripts/verify-mirror.sh`.
- **Bump each touched plugin's manifest version exactly once**, per the policy in
  `plugins/quick-dev/skills/develop/SKILL.md`: breaking → major, new capability → minor,
  fix/docs/refactor → patch. A harvest that changes no plugin file bumps nothing.
- **Every applied fix is covered by an assertion in some `scripts/verify-*.sh`** — extend an
  existing standing-invariant harness where one fits, rather than minting a change-scoped one
  with a version floor. Floors rot; invariants do not.
- **Mutation-test every new assertion**: break the file it guards, confirm `FAIL`, restore.
  Commit **first** — a `git checkout -- .` to undo the mutation otherwise reverts the work
  silently, and a harness that passes against a broken file is worse than none.
```

- [ ] **Step 4: Run it and watch it pass.**

- [ ] **Step 5: Commit and mutation-test**

```bash
git add -A && git commit -m "feat: the apply phase, with its verification and convergence rules

Claude-Session: https://claude.ai/code/session_01LWfJ1kDJk8ByDVzYA3rBAi"

sed -i 's/Commit \*\*first\*\*/Commit at some point/' .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect FAIL on commit-first
git checkout -- .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect ALL CHECKS PASSED
```

---

### Task 6: Phases 5 and 6 — Redact, then archive

The ordering here is the task's whole point: this repo is public and the client logs do not honour `issue-log`'s own redaction contract.

**Files:**
- Modify: `.claude/skills/feedback-harvest/SKILL.md`
- Modify: `scripts/verify-feedback-harvest.sh`

- [ ] **Step 1: Write the failing assertions**

```bash
echo "== redaction gate, then archive =="

assert_present "redaction is a gate before publication, not a cleanup after it" \
  "$SK" 1 "$L" 'Nothing is written to `docs/feedback/` until this gate has passed'
assert_present "the gate applies the issue-log forbidden list verbatim" \
  "$SK" 1 "$L" 'applies `notion-dev:issue-log`.s \*\*Forbidden, without exception\*\* list'
assert_present "the client logs are known to violate that list today" \
  "$SK" 1 "$L" 'This is measured, not hypothetical'
assert_present "an unredactable finding is paraphrased, never reproduced" \
  "$SK" 1 "$L" 'paraphrase the finding and do not reproduce the original'
assert_present "the archive is the durable record once a client log is reset" \
  "$SK" 1 "$L" 'the only place the occurrence counts'

# THE ordering this task exists for. A cleanup pass after publication is not a
# gate: the bytes have already been committed to a public repo by then.
assert_order "the redaction gate precedes the archive write" \
  "$SK" 1 "$L" \
  "redact heading"  '^### Phase 5 — Redact' \
  "gate rule"       'Nothing is written to `docs/feedback/` until this gate has passed' \
  "archive heading" '^### Phase 6 — Archive'
```

- [ ] **Step 2: Run it and watch it fail** — 6 new FAIL lines.

- [ ] **Step 3: Append Phases 5 and 6**

```markdown
### Phase 5 — Redact

**Nothing is written to `docs/feedback/` until this gate has passed.** Redaction is a gate
before publication, never a cleanup after it — once the bytes are committed to a public repo,
a later pass is not a fix.

`issue-log`'s redaction contract binds the *write* side, and the client logs do not honour it.
**This is measured, not hypothetical** — every row below is in a live client log today:

| Forbidden by `issue-log` | Present in a client log |
|---|---|
| Full database and page ids | a full 32-hex database id, and a `collection://` reference |
| Email addresses | the maintainer's own address |
| Personal names | a Notion workspace named after a person |
| Absolute filesystem paths | a Windows checkout path |
| URLs of any kind | the `collection://` reference above |

The gate applies `notion-dev:issue-log`'s **Forbidden, without exception** list verbatim:
ticket titles, ticket bodies, any part of a ticket's content, pull request titles, descriptions
or contents, diffs, code, Notion user ids, email addresses, personal names, full database ids,
full page ids, absolute filesystem paths, and URLs of any kind.

**The forbidden list is the gate, not the per-field whitelist.** So these are kept: the
signature, `Kind`, occurrence counts, timestamps and plugin versions, ticket keys, truncated
database ids in the `db=…a41f9c` form, client repo names, bare pull request numbers, and commit
shas. Truncate a full database id to its last six characters rather than removing it, so it
still groups.

If an entry cannot be redacted without destroying what it found, **paraphrase the finding and
do not reproduce the original**.

### Phase 6 — Archive

Write `docs/feedback/YYYY-MM-DD-harvest.md`, committed with the pull request. On a same-day
collision, suffix `-2`, `-3`.

One `##` section per triaged signature, carrying: the signature; every client that observed it,
with that client's occurrence count and version range; the redacted entry text; the
disposition; the rationale; and the resulting change — `file:line`, a commit sha, or a ticket
URL.

Once a client log is reset this archive is **the only place the occurrence counts**, first-seen
versions, and rejection rationales still exist. It is also what Phase 1 reads next time.
```

- [ ] **Step 4: Run it and watch it pass.**

- [ ] **Step 5: Commit and mutation-test the ordering**

```bash
git add -A && git commit -m "feat: redact as a gate before the archive write

The client logs carry a full database id, an email address, a personal name
and an absolute Windows path today — all five on issue-log's own 'Forbidden,
without exception' list. This repo is public, so redaction cannot be a pass
that runs after the commit.

Claude-Session: https://claude.ai/code/session_01LWfJ1kDJk8ByDVzYA3rBAi"

# swap the two phase headings — the order assertion must catch it
python3 - <<'PY'
import pathlib
p=pathlib.Path('.claude/skills/feedback-harvest/SKILL.md'); t=p.read_text()
a=t.index('### Phase 5 — Redact'); b=t.index('### Phase 6 — Archive')
c=t.index('### Phase 7', b) if '### Phase 7' in t[b:] else len(t)
p.write_text(t[:a]+t[b:c]+t[a:b]+t[c:])
PY
./scripts/verify-feedback-harvest.sh    # expect FAIL on the redact-before-archive order
git checkout -- .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect ALL CHECKS PASSED
```

---

### Task 7: Phases 7 and 8 — Merge, then reset

**Files:**
- Modify: `.claude/skills/feedback-harvest/SKILL.md`
- Modify: `scripts/verify-feedback-harvest.sh`

- [ ] **Step 1: Write the failing assertions**

```bash
echo "== merge, then reset =="

assert_present "the pull request is driven by the existing review loop" \
  "$SK" 1 "$L" 'Hand the branch to `review-and-merge`'
assert_present "the body names every disposition, including the ones with no diff" \
  "$SK" 1 "$L" 'invisible in a diff-shaped review'

# The reset destroys the client's only copy. Doing it before the merge loses the
# feedback for a pull request that then does not land.
assert_present "the reset runs only after the merge has landed" \
  "$SK" 1 "$L" '\*\*only after the merge has landed\*\*'
assert_present "removal matches on signature and occurrence count as harvested" \
  "$SK" 1 "$L" 'signature \*\*and\*\* occurrence count as harvested'
assert_present "a mismatched section is left in place and reported" \
  "$SK" 1 "$L" 'leave the section in place and report it'
assert_present "the file is never truncated and never deleted" \
  "$SK" 1 "$L" 'Never truncate the file and never delete it'
assert_present "all five dispositions are removed, not only the applied ones" \
  "$SK" 1 "$L" 'All five dispositions are removed'
assert_present "the reset is an untracked file edit with no commit in the client repo" \
  "$SK" 1 "$L" 'no commit and no push into a client repo'

assert_order "the merge precedes the reset" \
  "$SK" 1 "$L" \
  "merge heading" '^### Phase 7 — Pull request and merge' \
  "reset heading" '^### Phase 8 — Reset' \
  "after rule"    '\*\*only after the merge has landed\*\*'
```

- [ ] **Step 2: Run it and watch it fail** — 9 new FAIL lines.

- [ ] **Step 3: Append Phases 7 and 8**

```markdown
### Phase 7 — Pull request and merge

Hand the branch to `review-and-merge` rather than reimplementing a review or merge loop. Its
**final sweep** is where anything the harvest was tempted to file as `track` gets taken back
into this pull request instead, and its `--pre-merge-check` hook is where `session-closeout`'s
completion pass runs.

The body names **every** disposition and its count — not only what produced a diff. `stale` and
`decline` items change no file, so they are otherwise **invisible in a diff-shaped review**,
and they are exactly the decisions a reader needs to see recorded.

### Phase 8 — Reset

The reset runs **only after the merge has landed**. Before it, the client log is the only copy
of this feedback, and a pull request that does not land would take it with it.

Removal is surgical, matched on **signature **and** occurrence count as harvested**:

1. Locate `## <signature>` in the client log. Confirm its `**Occurrences**` integer and its
   `**Last seen**` line still match what Phase 2 recorded.
2. Match → delete the section, from its `##` heading to the line before the next `##` heading
   or end of file.
3. Mismatch → **leave the section in place and report it.** The client appended to or
   incremented that signature after the harvest read it, and the new evidence is untriaged.
4. **All five dispositions are removed**, `decline` and `track` included. Their durable home is
   the archive and the ticket; leaving them means re-triaging them next harvest, which is the
   waste Phase 1 and this step exist to end together.
5. Keep the file header. **Never truncate the file and never delete it** — truncation discards
   whatever the client wrote between the harvest and now, which is precisely the material step 3
   protects.

`.claude/notion-dev/` is self-gitignored in the client repo, so the issue log is untracked
there: the reset is a plain file edit, with **no commit and no push into a client repo**.
```

- [ ] **Step 4: Run it and watch it pass.**

- [ ] **Step 5: Commit and mutation-test**

```bash
git add -A && git commit -m "feat: merge before reset, and a surgical reset that never truncates

Claude-Session: https://claude.ai/code/session_01LWfJ1kDJk8ByDVzYA3rBAi"

sed -i 's/\*\*only after the merge has landed\*\*/once the fixes are written/' \
  .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect FAIL on the reset ordering (twice: rule + order)
git checkout -- .claude/skills/feedback-harvest/SKILL.md

sed -i 's/Never truncate the file and never delete it/Clear the file/' \
  .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect FAIL on truncation
git checkout -- .claude/skills/feedback-harvest/SKILL.md
./scripts/verify-feedback-harvest.sh    # expect ALL CHECKS PASSED
```

---

### Task 8: Closeout, limitations, and the full suite

**Files:**
- Modify: `.claude/skills/feedback-harvest/SKILL.md`
- Modify: `scripts/verify-feedback-harvest.sh`

- [ ] **Step 1: Write the failing assertions**

```bash
echo "== closeout and honesty about limits =="

assert_present "closeout confirms the reset ran for every client that was read" \
  "$SK" 1 "$L" 'confirm the reset ran for \*\*every\*\* client this harvest read'
assert_present "a short client log is not evidence of a healthy client" \
  "$SK" 1 "$L" 'A short log is not evidence of a healthy client'
assert_present "a concurrent increment can be lost, and that is accepted" \
  "$SK" 1 "$L" 'diagnostics, not accounting'
```

- [ ] **Step 2: Run it and watch it fail** — 3 new FAIL lines.

- [ ] **Step 3: Append the closing sections**

```markdown
## Closeout

Invoke `session-closeout` before reporting the harvest finished. Its workspace pass has one
addition here: **confirm the reset ran for **every** client this harvest read.** A harvest that
merged its pull request and left a client log untouched has silently guaranteed that the next
harvest re-triages everything it just decided — the exact waste this skill exists to end,
reintroduced at the last step.

## Accepted limitations

- **A concurrent increment can be lost.** If a client run increments a harvested signature's
  `Occurrences` between Phase 2 and Phase 8, the mismatch branch fires and the section
  survives. If the counts happen to match anyway, the increment is dropped. This mirrors
  `issue-log`'s own accepted read-modify-write race: the log is **diagnostics, not accounting**.
- **The harvest cannot see runs that died.** `issue-log` records what an agent was still
  running to record; a killed run leaves nothing behind. **A short log is not evidence of a
  healthy client**, and the archive inherits that limit — never read it as a complete account.
- **Cumulative occurrence history is lost for a re-declined item.** Phase 1 carries the previous
  count and rationale forward, but a signature that reappears starts counting from 1 in the
  client log.
```

- [ ] **Step 4: Run it and watch it pass.**

- [ ] **Step 5: Run the whole suite**

```bash
for h in scripts/verify-*.sh; do "$h" >/dev/null 2>&1 || echo "FAILED: $h"; done; echo "sweep done"
```

Expected: `sweep done` with no `FAILED:` line. `verify-assertions.sh` A3 must pass — it globs `scripts/verify-*.sh` and will now include the new harness, checking that it sources the shared library and defines no helper of its own.

- [ ] **Step 6: Confirm the skill is discoverable**

```bash
head -4 .claude/skills/feedback-harvest/SKILL.md   # name + description frontmatter present
grep -c . .claude/skills/REPO-LOCAL                # manifest non-empty
git status --porcelain                             # clean after commit
```

- [ ] **Step 7: Commit and open the pull request**

```bash
git add -A && git commit -m "feat: closeout, accepted limitations, and the full-suite gate

Claude-Session: https://claude.ai/code/session_01LWfJ1kDJk8ByDVzYA3rBAi"
git push -u origin feat/feedback-harvest
```

Write the body to a file and use `--body-file` — `gh pr create` does **not** support `@-` for `--body`, and takes it literally, producing a pull request whose entire description is two characters. Read the body back after creating to confirm it landed.

```bash
gh pr create --title "feat: feedback-harvest — read the client issue logs by mechanism" \
             --body-file /tmp/pr-body.md
gh pr view --json body --jq '.body | length'   # expect a realistic length, not 2
```

- [ ] **Step 8: Drive it to merge**

Invoke `review-and-merge` on the pull request. Then `session-closeout` before reporting done.

---

## Self-Review

**Spec coverage.** §1 placement and the three guards → Task 1. §2 client discovery → Task 3. §3 Phase 1 → Task 3; Phase 2 → Task 3; Phase 3 dispositions → Task 2, its four rules → Task 4; Phase 4 → Task 5; Phases 5-6 → Task 6; Phases 7-8 → Task 7; closeout → Task 8. §4 verification: `verify-feedback-harvest.sh` is built across Tasks 2-8, `verify-mirror.sh` in Task 1, A3 coverage confirmed in Task 8 Step 5. §5 accepted limitations → Task 8.

**Two gaps found and closed while reviewing.** The spec's Phase 4 lists a version bump but the plan's Global Constraints say not to bump — these are consistent only because this PR touches no plugin file; Task 5's skill text states the general rule and the constraint states this PR's case, and both now say so explicitly. And `verify-assertions.sh` A3 auto-includes the new harness the moment it exists, so Task 2 must source the library from its first commit or the suite goes red before Task 8 — Task 2 Step 1 includes the `. ./scripts/lib/assert.sh` line for that reason.

**One risk the executor must watch.** `assert_covers` requires every backticked span in a label to appear in the regex, and every Capitalized word in a label to appear when the matched line has it. Several labels here name `` `blocked` ``, `` `stale` ``, `` `apply` `` and `Phase`. If an assertion fails with *"label names 'X' but the regex does not check it"*, the fix is the regex or the label — never deleting the check.
