# reviewsCap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-coded 10-round cap in both plugins' PR review loops with a `reviewsCap` config key defaulting to 15.

**Architecture:** These plugins are markdown skill contracts — an agent reads the prose and follows it. There is no runtime code and no test suite, so "implementation" is editing prose so the contract is unambiguous, and "tests" are greps that assert the old constant is gone and the new rule is present exactly once. The cap is read from each plugin's existing config file, resolved once before the first reviewer trigger, and applied to both review loops with independent counters.

**Tech Stack:** Markdown skill files, JSON config, JSON Schema (draft-07), `grep`, `python3 -c` for JSON checks.

**Spec:** `docs/superpowers/specs/2026-07-27-reviews-cap-design.md`

## Global Constraints

- Key name is exactly `reviewsCap` — camelCase, top-level, in both plugins. Never `reviews_cap`.
- Default is exactly **15**, applied when the key is absent, the file is missing, or the value is not an integer ≥ 1.
- A present-but-invalid value falls back to 15 **and** is noted in the run's final report. Never stop the loop over a bad value.
- The two loops (bound reviewer, local fallback) are each capped at `reviewsCap`, counted **independently** — the local loop still restarts its counter at 1. Worst case is `2 × reviewsCap` rounds; that is intended.
- Nothing writes `reviewsCap`. `/notion-dev:init` is not modified. quick-dev's reviewer-resolution prompt is not modified.
- The two plugins' `review-and-merge/SKILL.md` files are near-identical by design. Any wording added to one must be added to the other, adapted only for the config filename and the write-policy sentence.
- Do not touch: the `plan-review` skill's 2-round cap, the `~10 min` / `20×30s` silence windows, ledger fields or schemas.
- Line numbers in this plan are as of commit `234153d` and are locators only. Match on quoted text; if a line number is off, trust the text.

---

### Task 1: Stop quick-dev's config write from destroying unknown keys

`references/reviewer-config.md` step 4 currently tells the agent to overwrite the config file wholesale, justified by "there are no other keys to preserve". That stops being true the moment `reviewsCap` exists, so this lands first — before any doc tells users to add the key.

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md` (lines 10, 33–38)

**Interfaces:**
- Consumes: nothing.
- Produces: the guarantee Task 2 and Task 4 depend on — a `reviewsCap` written into `.claude/quick-dev/config.json` survives a reviewer-resolution run.

- [ ] **Step 1: Write the failing test**

This is a prose contract, so the test is a grep pair. Run both now and record the output:

```bash
cd /home/forhas/dev/pure-dev
# (a) the destructive instruction must be gone
grep -n "there are no other keys to preserve\|writing the whole file" \
  plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md
# (b) the preserving instruction must be present
grep -n "preserving every other key" \
  plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md
```

- [ ] **Step 2: Run test to verify it fails**

Expected right now: (a) prints line 33 (the destructive text is present — wrong), (b) prints nothing and exits 1 (the fix is absent — wrong). Both must flip by Step 4.

- [ ] **Step 3: Write minimal implementation**

In `plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md`, replace the "Shape" bullet on line 10:

```markdown
- **Shape:** `{ "reviewer": "codex" }` or `{ "reviewer": "copilot" }` — reviewer-only.
```

with:

```markdown
- **Shape:** an object with a `reviewer` key (`"codex"` or `"copilot"`) and an optional
  hand-edited `reviewsCap` key (integer ≥ 1, default 15 — see the review loop's round cap):
  `{ "reviewer": "codex", "reviewsCap": 15 }`. Other keys may exist; treat the file as
  extensible, never as reviewer-only.
```

Then replace step 4's opening sentence:

```markdown
4. **Persist** the resolved value by writing the whole file `{ "reviewer": "<value>" }` to `REPO_ROOT/.claude/quick-dev/config.json` (reviewer-only — overwrite or create it; there are no other keys to preserve), after ensuring the self-ignored directory exists:
```

with:

```markdown
4. **Persist** the resolved value into `REPO_ROOT/.claude/quick-dev/config.json` as a
   **read-modify-write**: read the existing JSON if the file is present, set `reviewer` to the
   resolved value, and write the whole object back, **preserving every other key** — notably a
   hand-edited `reviewsCap`, which a blind overwrite would silently delete. If the file is
   absent or unparseable, write `{ "reviewer": "<value>" }`. Ensure the self-ignored directory
   exists first:
```

And replace the comment on line 37:

```markdown
   # then write {"reviewer":"<value>"} to $REPO_ROOT/.claude/quick-dev/config.json
```

with:

```markdown
   # then read $REPO_ROOT/.claude/quick-dev/config.json (if any), set "reviewer":"<value>",
   # and write the merged object back — every other key preserved
```

- [ ] **Step 4: Run test to verify it passes**

Re-run both greps from Step 1. Expected: (a) prints nothing, exits 1. (b) prints the line containing "preserving every other key". Also read the whole file once to confirm it still reads coherently.

- [ ] **Step 5: Commit**

```bash
git add plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md
git commit -m "fix(quick-dev): preserve unknown config keys when persisting reviewer"
```

---

### Task 2: Make quick-dev's review loop read reviewsCap

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md` (add a `### Round cap` subsection at the end of the `## Reviewer` section, after the profile table ending at line 38; then lines 91, 113, 115, 119, 134, 163)

**Interfaces:**
- Consumes: Task 1's preservation guarantee.
- Produces: the exact `### Round cap` block that Task 3 mirrors into notion-dev, and the six replacement phrasings Task 3 reuses verbatim.

- [ ] **Step 1: Write the failing test**

```bash
cd /home/forhas/dev/pure-dev
F=plugins/quick-dev/skills/review-and-merge/SKILL.md
# (a) no round-cap "10" may remain; only the silence-window matches are allowed
grep -n "10" $F | grep -v "~10 min\|20×30s"
# (b) the round-cap rule must appear exactly once
grep -c "^### Round cap$" $F
# (c) the cap must be referenced at the loop sites
grep -c "resolved cap\|the cap\|reviewsCap" $F
```

- [ ] **Step 2: Run test to verify it fails**

Expected right now: (a) prints the six cap lines (91, 113, 115, 119, 134, 163) — must become empty; (b) prints `0` — must become `1`; (c) prints `0` — must become at least `6`.

- [ ] **Step 3: Write minimal implementation**

**3a.** Append this subsection to the end of the `## Reviewer` section — immediately after the reviewer profile table (the row ending `| same |`, line 38) and immediately before `## 1. Load the pull request`:

```markdown
### Round cap

Both review loops in step 4 are capped by `reviewsCap`, read from
`REPO_ROOT/.claude/quick-dev/config.json` — the same primary-checkout file and the same
`REPO_ROOT` resolution as `references/reviewer-config.md` step 1. Resolve it **once**, here,
before the first trigger:

- The value is an integer ≥ 1 → use it.
- The key is absent, the file is missing, or the value is anything else (`0`, negative,
  non-integer, non-numeric) → use **15**. When the value was present but unusable, say so in
  the final report; never stop the loop over it.

The resolved number caps the reviewer loop and the local fallback loop **independently** —
the fallback restarts its counter at 1, so a run that falls back can perform up to twice the
cap in total. Nothing writes this key; it is hand-edited.
```

**3b.** Line 91 — replace:

```markdown
Rounds are counted from the first reviewer trigger. **Hard cap: 10 rounds.** After round 10 is handled, stop looping and go to merge (step 5) regardless of what the reviewer still finds.
```

with:

```markdown
Rounds are counted from the first reviewer trigger. **Hard cap: the resolved `reviewsCap` (default 15).** After the capped round is handled, stop looping and go to merge (step 5) regardless of what the reviewer still finds.
```

**3c.** Line 113 — replace `If the round counter is below 10 and the round **produced code changes**:` with `If the round counter is below the cap and the round **produced code changes**:` (leave the rest of the item untouched).

**3d.** Line 115 — replace `or the **10-round cap**` with `or the **round cap**`.

**3e.** Line 119 — replace `Round counter starts at 1; **hard cap: 10 rounds** — a runaway backstop only;` with `Round counter starts at 1; **hard cap: the same resolved `reviewsCap`, counted independently of the reviewer loop's rounds** — a runaway backstop only;`.

**3f.** Line 134 — replace `   - Round counter reaches 10 → stop; go to merge under the cap semantics.` with `   - Round counter reaches the cap → stop; go to merge under the cap semantics.`.

**3g.** Line 163 — replace `- **Never** run more than 10 reviewer rounds or 10 local review rounds.` with `- **Never** run more than `reviewsCap` reviewer rounds or `reviewsCap` local review rounds (default 15 each, counted independently).`.

- [ ] **Step 4: Run test to verify it passes**

Re-run all three greps. Expected: (a) empty; (b) `1`; (c) `≥ 6`. Then read the `## Reviewer` and `## 4. Review loop` sections end to end and confirm no sentence still implies a fixed 10.

- [ ] **Step 5: Commit**

```bash
git add plugins/quick-dev/skills/review-and-merge/SKILL.md
git commit -m "feat(quick-dev): make the review loop round cap configurable via reviewsCap"
```

---

### Task 3: Make notion-dev's review loop read reviewsCap

Structurally identical to Task 2, adapted for notion-dev's tracked config and its write-free policy. The full text is repeated here — do not read Task 2 to fill gaps.

**Files:**
- Modify: `plugins/notion-dev/skills/review-and-merge/SKILL.md` (add a `### Round cap` subsection at the end of the `## Reviewer` section, after the profile table; then lines 106, 128, 130, 134, 149, 183)

**Interfaces:**
- Consumes: Task 2's wording, mirrored.
- Produces: the `reviewsCap` semantics that Task 5's schema entry and README paragraph describe.

- [ ] **Step 1: Write the failing test**

```bash
cd /home/forhas/dev/pure-dev
F=plugins/notion-dev/skills/review-and-merge/SKILL.md
grep -n "10" $F | grep -v "~10 min\|20×30s"
grep -c "^### Round cap$" $F
grep -c "resolved cap\|the cap\|reviewsCap" $F
```

- [ ] **Step 2: Run test to verify it fails**

Expected right now: the first prints the six cap lines (106, 128, 130, 134, 149, 183); the second prints `0`; the third prints `0`.

- [ ] **Step 3: Write minimal implementation**

**3a.** Append this subsection to the end of the `## Reviewer` section, immediately after the reviewer profile table and immediately before the next `##` heading:

```markdown
### Round cap

Both review loops in step 4 are capped by `reviewsCap`, read from
`.claude/notion-dev.config.json` in the **primary checkout** (`$REPO_ROOT`, resolved as every
other config read in this skill — never the worktree). Resolve it **once**, here, before the
first trigger:

- The value is an integer ≥ 1 → use it.
- The key is absent, the file is missing, or the value is anything else (`0`, negative,
  non-integer, non-numeric) → use **15**. When the value was present but unusable, say so in
  the final report; never stop the loop over it.

The resolved number caps the reviewer loop and the local fallback loop **independently** —
the fallback restarts its counter at 1, so a run that falls back can perform up to twice the
cap in total. As with `reviewer`, this skill never writes the config: `reviewsCap` is
hand-edited, and `/notion-dev:init` does not write it either.
```

**3b.** Line 106 — replace:

```markdown
Rounds are counted from the first reviewer trigger. **Hard cap: 10 rounds.** After round 10 is handled, stop looping and go to merge (step 5) regardless of what the reviewer still finds.
```

with:

```markdown
Rounds are counted from the first reviewer trigger. **Hard cap: the resolved `reviewsCap` (default 15).** After the capped round is handled, stop looping and go to merge (step 5) regardless of what the reviewer still finds.
```

**3c.** Line 128 — replace `If the round counter is below 10 and the round **produced code changes**:` with `If the round counter is below the cap and the round **produced code changes**:` (leave the rest of the item untouched).

**3d.** Line 130 — replace `or the **10-round cap**` with `or the **round cap**`.

**3e.** Line 134 — replace `Round counter starts at 1; **hard cap: 10 rounds** — a runaway backstop only;` with `Round counter starts at 1; **hard cap: the same resolved `reviewsCap`, counted independently of the reviewer loop's rounds** — a runaway backstop only;`.

**3f.** Line 149 — replace `   - Round counter reaches 10 → stop; go to merge under the cap semantics.` with `   - Round counter reaches the cap → stop; go to merge under the cap semantics.`.

**3g.** Line 183 — replace `- **Never** run more than 10 reviewer rounds or 10 local review rounds.` with `- **Never** run more than `reviewsCap` reviewer rounds or `reviewsCap` local review rounds (default 15 each, counted independently).`.

- [ ] **Step 4: Run test to verify it passes**

Re-run all three greps: expected empty, `1`, `≥ 6`. Then diff the two plugins' loop sections against each other and confirm the only differences are the pre-existing ones (config filename, the write-policy sentence, notion-dev's merge-strategy and verify-steps text):

```bash
diff <(sed -n '/^### Round cap$/,/^## /p' plugins/quick-dev/skills/review-and-merge/SKILL.md) \
     <(sed -n '/^### Round cap$/,/^## /p' plugins/notion-dev/skills/review-and-merge/SKILL.md)
```

Expected: differences confined to the config path and the final write-policy sentence.

- [ ] **Step 5: Commit**

```bash
git add plugins/notion-dev/skills/review-and-merge/SKILL.md
git commit -m "feat(notion-dev): make the review loop round cap configurable via reviewsCap"
```

---

### Task 4: Document reviewsCap in quick-dev's README and bump its version

**Files:**
- Modify: `plugins/quick-dev/README.md` (the config JSON block at line 60, the paragraph at line 63, the skills-table row at line 79)
- Modify: `plugins/quick-dev/.claude-plugin/plugin.json` (line 3)

**Interfaces:**
- Consumes: Task 2's resolution rule (the README must not contradict it).
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

```bash
cd /home/forhas/dev/pure-dev
grep -n "reviewsCap" plugins/quick-dev/README.md
grep -n "10-round cap" plugins/quick-dev/README.md
python3 -c "import json;print(json.load(open('plugins/quick-dev/.claude-plugin/plugin.json'))['version'])"
```

- [ ] **Step 2: Run test to verify it fails**

Expected right now: no `reviewsCap` match (exit 1); `10-round cap` matches line 79; version prints `0.6.0`. All three must change.

- [ ] **Step 3: Write minimal implementation**

**3a.** Replace the JSON block at line 60:

```json
{ "reviewer": "codex" }
```

with:

```json
{ "reviewer": "codex", "reviewsCap": 15 }
```

**3b.** Append to the paragraph at line 63 (after "…it always uses the local reviewer)."):

```markdown

`reviewsCap` caps how many review rounds the loop will run — default **15** when the key is
absent or invalid. Nothing writes it; add it by hand to change the ceiling. It applies to the
configured-reviewer loop and the local fallback loop independently, so a run that falls back
can do up to twice that number in total. The cap is a runaway backstop — the loop normally
ends far earlier, when the reviewer reports no meaningful issues or the remaining findings
are declined with reasoning.
```

**3c.** In the skills-table row at line 79, replace `local review loop (10-round cap, green-CI gates)` with `local review loop (`reviewsCap` rounds, default 15; green-CI gates)`.

**3d.** In `plugins/quick-dev/.claude-plugin/plugin.json`, change `"version": "0.6.0"` to `"version": "0.7.0"`.

- [ ] **Step 4: Run test to verify it passes**

Re-run all three commands. Expected: `reviewsCap` matches at least three lines; `10-round cap` prints nothing (exit 1); version prints `0.7.0`.

- [ ] **Step 5: Commit**

```bash
git add plugins/quick-dev/README.md plugins/quick-dev/.claude-plugin/plugin.json
git commit -m "docs(quick-dev): document reviewsCap; bump to 0.7.0"
```

---

### Task 5: Add reviewsCap to notion-dev's schema and README, and bump its version

The schema entry is mandatory, not cosmetic: `notion-dev.config.schema.json` sets `"additionalProperties": false`, so without it a config carrying `reviewsCap` fails validation in the user's editor.

**Files:**
- Modify: `plugins/notion-dev/schema/notion-dev.config.schema.json` (top-level `properties`, as a sibling of the existing `reviewer` property)
- Modify: `plugins/notion-dev/README.md` (the config key list around line 134, the "Reviewer configuration" section at line 136, the status line at line 5)
- Modify: `plugins/notion-dev/.claude-plugin/plugin.json` (line 4)

**Interfaces:**
- Consumes: Task 3's semantics.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

```bash
cd /home/forhas/dev/pure-dev
python3 - <<'PY'
import json
s = json.load(open('plugins/notion-dev/schema/notion-dev.config.schema.json'))
p = s['properties'].get('reviewsCap')
print('schema entry:', p)
print('additionalProperties still false:', s.get('additionalProperties') is False)
print('reviewsCap not required:', 'reviewsCap' not in s.get('required', []))
PY
grep -c "reviewsCap" plugins/notion-dev/README.md
python3 -c "import json;print(json.load(open('plugins/notion-dev/.claude-plugin/plugin.json'))['version'])"
```

- [ ] **Step 2: Run test to verify it fails**

Expected right now: `schema entry: None`; `additionalProperties still false: True`; `reviewsCap not required: True`; README count `0`; version `0.6.0`. The first, fourth and fifth must change; the second and third must stay `True`.

- [ ] **Step 3: Write minimal implementation**

**3a.** In `plugins/notion-dev/schema/notion-dev.config.schema.json`, add this property to the top-level `properties` object, directly after the existing `reviewer` property. Do **not** add it to `required`, and do **not** change `additionalProperties`:

```json
"reviewsCap": {
  "type": "integer",
  "minimum": 1,
  "default": 15,
  "description": "Maximum review rounds the PR review loop will run. Default 15 when absent or invalid. Applies to the configured-reviewer loop and the local fallback loop independently, so a run that falls back can perform up to twice this number of rounds in total. Hand-edited: /notion-dev:init does not write this key and the review loop never writes the config."
}
```

**3b.** In `plugins/notion-dev/README.md`, add a bullet to the config key list immediately after the `reviewer` bullet on line 134:

```markdown
- `reviewsCap` — maximum review rounds the PR review loop runs; default **15** when absent or invalid. Hand-edited (`/notion-dev:init` does not write it). Applies to the configured-reviewer loop and the local fallback loop independently, so a run that falls back can perform up to twice that number in total. It is a runaway backstop — the loop normally ends far earlier.
```

**3c.** Append to the end of the "Reviewer configuration" section (after the paragraph at line 143):

```markdown

The number of rounds either loop will run is capped by `reviewsCap` (default 15). Raise it
for repos where reviews routinely need more iterations; lower it to fail fast. The review
loop never writes this key — edit `.claude/notion-dev.config.json` directly.
```

**3d.** In `plugins/notion-dev/.claude-plugin/plugin.json`, change `"version": "0.6.0"` to `"version": "0.7.0"`.

**3e.** In `plugins/notion-dev/README.md` line 5, change `**Status**: pre-release (0.6.0).` to `**Status**: pre-release (0.7.0).`.

- [ ] **Step 4: Run test to verify it passes**

Re-run the Step 1 block. Expected: the schema entry prints the integer/minimum/default dict; `additionalProperties still false: True`; `reviewsCap not required: True`; README count ≥ 2; version `0.7.0`.

Then validate a sample config both ways. This needs `jsonschema`; if it is not installed, run `pip install jsonschema` first, and if that is unavailable, skip this step and note it in the task report rather than reporting a pass:

```bash
python3 - <<'PY'
import json, jsonschema
schema = json.load(open('plugins/notion-dev/schema/notion-dev.config.schema.json'))
base = {
  "project": {"key": "STO", "name": "demo"},
  "ticketSystem": {"databaseId": "abc"},
  "git": {},
  "verify": {},
  "dependencies": {},
}
ok = dict(base, reviewsCap=15)
jsonschema.validate(ok, schema)
print("valid config with reviewsCap: OK")
for bad, label in ((dict(base, reviewsCap=0), "reviewsCap: 0"),
                   (dict(base, reviewsCap="ten"), "reviewsCap: \"ten\""),
                   (dict(base, bogusKey=1), "unknown key")):
    try:
        jsonschema.validate(bad, schema)
        print("FAIL — schema accepted", label)
    except jsonschema.ValidationError:
        print("correctly rejected:", label)
PY
```

Expected: `valid config with reviewsCap: OK`, then three `correctly rejected:` lines. If `base` itself fails validation, adjust `base` to satisfy the existing `required` keys — the point of the check is `reviewsCap`, not the rest of the config.

- [ ] **Step 5: Commit**

```bash
git add plugins/notion-dev/schema/notion-dev.config.schema.json \
        plugins/notion-dev/README.md \
        plugins/notion-dev/.claude-plugin/plugin.json
git commit -m "docs(notion-dev): add reviewsCap to schema and README; bump to 0.7.0"
```

---

### Task 6: Whole-change verification

Catches anything the per-task greps missed — most importantly a stray round-cap `10` in prose neither task touched, and drift between the two plugins.

**Files:** none modified unless a defect is found.

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: the final verification record.

- [ ] **Step 1: Run the full-repo cap scan**

```bash
cd /home/forhas/dev/pure-dev
grep -rn "10 round\|10-round\|round 10\|below 10\|reaches 10\|10 reviewer rounds\|10 local" \
  plugins/ docs/superpowers/specs/2026-07-27-reviews-cap-design.md
```

Expected: matches **only** inside `docs/superpowers/specs/2026-07-27-reviews-cap-design.md` (which quotes the old text deliberately) and nothing under `plugins/`. Any `plugins/` hit is a missed site — fix it and re-run.

- [ ] **Step 2: Confirm the silence windows were not collateral damage**

```bash
grep -rn "~10 min\|20×30s\|20 polls" plugins/*/skills/review-and-merge/SKILL.md
```

Expected: the same matches as before the change — two plugins × the silence-detection lines. These must be untouched.

- [ ] **Step 3: Confirm both plugins state the rule once, identically in structure**

```bash
grep -c "^### Round cap$" plugins/quick-dev/skills/review-and-merge/SKILL.md \
                         plugins/notion-dev/skills/review-and-merge/SKILL.md
grep -rn "reviews_cap" plugins/ docs/
```

Expected: `1` for each file; `reviews_cap` (snake_case) appears nowhere at all.

- [ ] **Step 4: Read the diff end to end**

```bash
git diff 234153d..HEAD -- plugins/
```

Read every hunk. Confirm: no behavior described beyond the spec, no `/notion-dev:init` change, no ledger change, no `plan-review` change, both versions at `0.7.0`.

- [ ] **Step 5: Record the result**

No commit if everything passes — the work is already committed. If Step 1 or 3 found a missed site, fix it and commit:

```bash
git add -A && git commit -m "fix: replace remaining hard-coded review round cap"
```

---

## Self-Review

**Spec coverage:**

| spec section | task |
|---|---|
| Key name / default / placement | Global Constraints; Tasks 2, 3, 4, 5 |
| notion-dev schema entry required by `additionalProperties: false` | Task 5 (3a) + validation in Step 4 |
| quick-dev gets no schema file | honored by omission — no task creates one |
| Setup UX: silent, hand-edited | honored by omission — no task touches `/notion-dev:init` or the reviewer prompt; asserted in Task 6 Step 4 |
| Resolution rule | Task 2 (3a), Task 3 (3a) |
| Cap application, six sites × 2 plugins | Task 2 (3b–3g), Task 3 (3b–3g) |
| quick-dev README:79 seventh site | Task 4 (3c) |
| Supporting change: preserve unknown keys | Task 1 |
| Documentation (2 READMEs, schema description, 2 version bumps) | Tasks 4, 5 |
| Verification items 1–5 | Tasks 2–5 Step 4, plus Task 6 |

No gaps.

**Placeholder scan:** every step names exact files, exact before/after text, exact commands and expected output. Task 3 repeats Task 2's text in full rather than saying "same as Task 2". The only conditional is Task 5's `jsonschema` availability, which has an explicit instruction for the unavailable case (skip and report, do not claim a pass).

**Type consistency:** the key is `reviewsCap` in all eight files and both greps for `reviews_cap` (Task 6 Step 3) assert the snake_case form appears nowhere. The default `15` and the `integer ≥ 1` rule are stated identically in the two SKILL.md blocks, the schema, and both READMEs. Both `plugin.json` files go `0.6.0` → `0.7.0`.
