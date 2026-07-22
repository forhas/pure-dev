# quick-dev Configurable Reviewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make quick-dev's GitHub-mode review loop drive a configurable reviewer — `codex` (default) or `copilot` — persisted per-clone, with the flow otherwise unchanged.

**Architecture:** A gitignored per-clone config file (`<primary-checkout>/.claude/quick-dev/config.json`) holds `{"reviewer": "..."}`. A shared "read-or-prompt-and-persist" procedure (new reference doc) resolves the value; `develop` runs it early (GitHub mode) and `review-and-merge` runs it at its start and binds a per-reviewer **profile** (trigger / re-trigger / response-author / unavailability detection) ported from the merged notion-dev design. Copilot is a drop-in for Codex.

**Tech Stack:** Markdown instruction files (Claude Code plugin skills). No executable code; "tests" are static consistency checks (`grep`, `python3 -m json.tool`) plus dogfooding. `gh` CLI + GitHub GraphQL for the runtime behavior the docs describe.

## Global Constraints

- Scope is `plugins/quick-dev/` only. Do not touch `plugins/notion-dev/`.
- Config file is **gitignored**, primary-checkout-only, reviewer-only: `{"reviewer": "codex"}` or `{"reviewer": "copilot"}`. No other keys (YAGNI).
- Config path: `<primary-checkout>/.claude/quick-dev/config.json`; primary checkout = first entry of `git worktree list`.
- Self-ignore bootstrap: adapt the ledger's self-ignore pattern, `$REPO_ROOT`-relative (review-and-merge runs in a worktree, so it must target the primary checkout, not cwd): `mkdir -p "$REPO_ROOT/.claude/quick-dev" && { [ -f "$REPO_ROOT/.claude/quick-dev/.gitignore" ] || printf '*\n' > "$REPO_ROOT/.claude/quick-dev/.gitignore"; }`.
- Reviewer values: exactly `codex` (default) and `copilot`. Response-author logins (exact match, never substring): `chatgpt-codex-connector[bot]` (codex), `copilot-pull-request-reviewer[bot]` (copilot).
- Prompting happens only in **GitHub mode** and only in **interactive** mode. Local mode and `--non-interactive` never prompt; non-interactive defaults to `codex` and records it.
- The review flow, gates, round cap (10), merge, and local-fallback loop are unchanged except for the reviewer-identity swap.
- Frequent commits: one commit per task.

---

### Task 1: Shared reviewer-config resolution reference

Creates the single source of truth for the config location + resolution procedure, consumed by both `review-and-merge` (Task 2) and `develop` (Task 3). Do this first.

**Files:**
- Create: `plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md`

**Interfaces:**
- Produces: a reference doc other skills cite by path. Defines the term **"reviewer resolution procedure"** (resolve `REPO_ROOT`, read config, prompt-or-default, persist) and the config path/shape used verbatim by Tasks 2–4.

- [ ] **Step 1: Create the reference file**

Create `plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md` with exactly:

````markdown
# Reviewer configuration

quick-dev's GitHub-mode review loop drives a configurable reviewer: `codex` (default) or
`copilot`. The choice is stored per-clone in a gitignored config file and resolved by the
procedure below.

## Config file

- **Path:** `<primary-checkout>/.claude/quick-dev/config.json`
- **Shape:** `{ "reviewer": "codex" }` or `{ "reviewer": "copilot" }` — reviewer-only.
- **Tracking:** gitignored, in the primary checkout only (never a feature worktree). It shares
  the self-ignored `.claude/quick-dev/` directory used by the ledger, so it never appears in
  `git status`, is never swept by `git add -A`, and is never committed.

## Reviewer resolution procedure

Run this wherever the reviewer must be known.

1. **Resolve the primary checkout root** — `REPO_ROOT` = the first path printed by
   `git worktree list`. This is correct whether the caller sits in the primary checkout or in
   a feature worktree (the gitignored config lives only in the primary checkout).
2. **Read** `REPO_ROOT/.claude/quick-dev/config.json` if it exists.
   - Valid `reviewer` (`codex` or `copilot`) present → use it. Done.
   - File missing, no `reviewer` key, or an invalid value → go to step 3.
3. **Resolve a value:**
   - **Interactive mode:** ask via `AskUserQuestion` — "Which code reviewer should the review
     loop use?" with options **Codex** and **Copilot** (default/prefill **Codex**). Use the
     answer.
   - **Non-interactive mode:** use `codex` and record in the run report that the reviewer was
     defaulted (not chosen).
4. **Persist** the resolved value to `REPO_ROOT/.claude/quick-dev/config.json`, preserving any
   other keys already in the file:
   ```bash
   mkdir -p "$REPO_ROOT/.claude/quick-dev"
   [ -f "$REPO_ROOT/.claude/quick-dev/.gitignore" ] || printf '*\n' > "$REPO_ROOT/.claude/quick-dev/.gitignore"
   # write {"reviewer":"<value>"} into $REPO_ROOT/.claude/quick-dev/config.json (merge, don't clobber other keys)
   ```
   The write is side-effect-free with respect to git: the file is gitignored, so it never
   dirties the tree, never enters `git add -A`, and never diverges the base branch.

**Skip conditions:** only run this procedure in **GitHub mode**. In local mode there is no
GitHub reviewer (Codex app / Copilot) — the local fresh-agent reviewer is always used and no
reviewer config is read or written.
````

- [ ] **Step 2: Verify the file is well-formed and complete**

Run:
```bash
cd /home/forhas/dev/pure-dev
test -f plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md && echo EXISTS
grep -c "reviewer resolution procedure" plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md
grep -q "git worktree list" plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md && echo "HAS repo-root resolution"
grep -q "printf '\*\\\\n'" plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md && echo "HAS self-ignore bootstrap"
```
Expected: `EXISTS`, a count `>= 1`, `HAS repo-root resolution`, `HAS self-ignore bootstrap`.

- [ ] **Step 3: Commit**

```bash
cd /home/forhas/dev/pure-dev
git add plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md
git commit -m "feat(quick-dev): add shared reviewer-config resolution reference

Claude-Session: https://claude.ai/code/session_01SuR5SUzx67bD6riqPE51st"
```

---

### Task 2: Parameterize `review-and-merge` for the configured reviewer

Adds a `## Reviewer` section (resolution + profile table) and swaps every Codex-only reference in the trigger/loop/report for the bound profile. This is the behavioral core.

**Files:**
- Modify: `plugins/quick-dev/skills/review-and-merge/SKILL.md`

**Interfaces:**
- Consumes: the reviewer resolution procedure and config path from Task 1 (`references/reviewer-config.md`).
- Produces: a "bound reviewer profile" concept referenced throughout steps 3–5; the terms **trigger timestamp**, **response-author login**, **reason=not-configured/quota/error/silent** used unchanged by the existing local-fallback loop.

- [ ] **Step 1: Update the frontmatter description**

Replace (line 3):
```
description: This skill should be used when the user asks to "review and merge" a pull request, "merge PR after review", "run the review loop on PR", "drive PR to merge", or when the quick-dev develop flow reaches its review phase. Resolves existing review comments, loops Codex reviews — falling back to a local fresh-agent review loop when Codex is unavailable (quota, not configured, erroring, or silent) — then squash-merges and deletes the remote branch.
```
with:
```
description: This skill should be used when the user asks to "review and merge" a pull request, "merge PR after review", "run the review loop on PR", "drive PR to merge", or when the quick-dev develop flow reaches its review phase. Resolves existing review comments, loops the configured code reviewer (Codex or Copilot) — falling back to a local fresh-agent review loop when the reviewer is unavailable (quota, not configured, erroring, or silent) — then squash-merges and deletes the remote branch.
```

- [ ] **Step 2: Insert the `## Reviewer` section**

Insert immediately **after** line 19 (the paragraph ending "If closed/merged/draft, stop and report.") and **before** `## 1. Load the pull request`, this block:

````markdown

## Reviewer

This skill drives one of two configured reviewers — `codex` (default) or `copilot`. Resolve which **before step 3**, then bind its profile:

1. Run the **reviewer resolution procedure** in `references/reviewer-config.md` to obtain the value (`codex` | `copilot`). It reads the gitignored per-clone config from the primary checkout and, when the key is absent, prompts (interactive) or defaults to `codex` (non-interactive) and persists the choice. The skill itself never writes any tracked file.
2. Bind the **reviewer profile** below; every trigger / re-trigger / reviewer-response / unavailability reference in steps 3–5 means the bound profile's row.

| aspect | **codex** (default) | **copilot** |
|---|---|---|
| trigger | comment `@codex review` | request the bot reviewer: `gh api --method POST "repos/{owner}/{repo}/pulls/<pr>/requested_reviewers" -f 'reviewers[]=copilot-pull-request-reviewer[bot]'` (gh substitutes `{owner}`/`{repo}`) |
| re-trigger each round | re-comment `@codex review` | re-run the same reviewer-request command (the bot is auto-removed once it submits) |
| response author (exact login) | `chatgpt-codex-connector[bot]` | `copilot-pull-request-reviewer[bot]` |
| review shape | `COMMENTED` review; actionable findings are inline threads (+ a summary body) | `COMMENTED` review whose findings are **often in the summary body only** — Copilot frequently generates zero inline comments (suppresses low-confidence ones), so the body is a first-class finding source; inline threads appear only when it has line-level findings |
| non-actionable boilerplate to ignore | Codex "About" block | the review body's per-file `<details>` summary table and the "Add Copilot custom instructions" footer |
| "no meaningful issues" | review says no major issues / equivalent | a review whose body is only the overview/per-file summary with no actionable findings and no (or only resolved) inline comments |
| not-configured signal | a message from the Codex app that is *exclusively* an inability-to-review notice (no `Reviewed commit` marker, no findings) | the reviewer-request command exits non-zero (e.g. HTTP 422 → Copilot code review not enabled for the repo/org) |
| quota signal | body contains the case-insensitive substring `reached your codex usage limit` | n/a — Copilot has no comment-based quota notice; a persistent request failure is treated as `not-configured` |
| silence | no response within ~10 min (20×30s polls) → re-trigger once → `reason=silent` | same |
````

- [ ] **Step 3: Parameterize the Codex "About" boilerplate mention in step 2**

Replace (in the "Non-inline feedback" paragraph, line 49):
```
Track them by comment ID — that tracking is their only "resolved" marker. Ignore non-actionable bot boilerplate (e.g. Codex "About" blocks).
```
with:
```
Track them by comment ID — that tracking is their only "resolved" marker. Ignore non-actionable bot boilerplate per the bound reviewer's profile (e.g. the Codex "About" block, or Copilot's per-file summary table and custom-instructions footer).
```

- [ ] **Step 4: Rewrite step 3 (Trigger) for the bound profile + trigger timestamp**

Replace the whole `## 3. Trigger a Codex review` section (lines 54–56) with:

````markdown
## 3. Trigger a review

After all current comments are handled, trigger the bound reviewer per its profile:
- **codex** → `gh pr comment <pr> --body "@codex review"`.
- **copilot** → run the reviewer-request command. If it **exits non-zero** (Copilot code
  review not enabled for this repo/org), treat it as `reason=not-configured` immediately:
  post the unavailability note (step 4) and enter the local review loop — do not count a round.

**Record the trigger timestamp** — the poll baseline used in step 4. It must be well-defined for both reviewers, since only codex leaves a comment to key off:
- **codex** → the `created_at` of the `@codex review` comment just posted.
- **copilot** → the current UTC time captured **immediately before** the reviewer-request call (the REST request creates no comment). Capture it before the call so a review that lands during the request is not excluded.

Every re-trigger (the silence retry in step 4, and the next-round trigger in the loop) **refreshes** this timestamp per the same rule.

Set the round counter to **1** when posting this first trigger (also when the PR had no reviews at all: run the green-CI gate first, then trigger).
````

- [ ] **Step 5: Parameterize the round-loop heading and poll filter (step 4)**

Replace (line 60):
```
Rounds are counted from the first `@codex review` trigger. **Hard cap: 10 rounds.** After round 10 is handled, stop looping and go to merge (step 5) regardless of what Codex still finds.
```
with:
```
Rounds are counted from the first reviewer trigger. **Hard cap: 10 rounds.** After round 10 is handled, stop looping and go to merge (step 5) regardless of what the reviewer still finds.
```

Replace the poll paragraph (line 64):
```
Poll for a **new** Codex review every 30 seconds (`sleep 30` — do not busy-loop), reading reviews, issue comments, and inline comments with `--paginate`, acting only on items newer than the newest already seen. A **Codex response** is a review or comment whose author login is exactly `chatgpt-codex-connector[bot]` (the Codex GitHub App's identity — an exact match, never a substring test: any repo member or bot with `codex` in its login could otherwise end the loop or fake an unavailability signal), created after the trigger comment's timestamp. Non-Codex comments (humans, CI bots) arriving mid-loop: handle per the step-2 rules, but they neither end the poll nor count as a Codex round.
```
with:
```
Poll for a **new** reviewer response every 30 seconds (`sleep 30` — do not busy-loop), reading reviews, issue comments, and inline comments with `--paginate`, acting only on items newer than the newest already seen. A **reviewer response** is a review or comment whose author login **exactly equals** the bound profile's response-author login — `chatgpt-codex-connector[bot]` (codex) or `copilot-pull-request-reviewer[bot]` (copilot) — created after the round's **trigger timestamp** (step 3: the `@codex review` comment's timestamp for codex, the captured request-start time for copilot). An exact match, never a substring test. Any other author (humans, CI bots, the *other* reviewer bot) is handled per step-2 rules but neither ends the poll nor counts as a round.
```

- [ ] **Step 6: Parameterize the unavailability-detection subsection**

Replace the `### Codex unavailability detection` heading and its intro + bullets (lines 66–72) with:

````markdown
### Reviewer unavailability detection

While polling, watch for signals that the bound reviewer cannot review. Detection is active at **every** poll in **every** round — mid-loop quota exhaustion routes here too. On any signal below: capture the `reason`; **first handle any reviewer content already received** (a real review can arrive in the same poll as a quota notice — process it per the step-2 rules, reply and resolve its threads); then post a brief PR note (`gh pr comment <pr> --body "..."`) stating the reviewer is unavailable (with the reason) and the local review fallback is engaging, and switch **permanently** to the **local review loop** below — never re-trigger the reviewer again this run.

- **Quota** (codex only) — a new bot message whose body contains the case-insensitive substring `reached your codex usage limit`. `reason=quota`. Not applicable to copilot — copilot has no comment-based quota notice.
- **Not-configured / error / refusal**:
  - **codex** — a message from the Codex app itself (author login exactly `chatgpt-codex-connector[bot]`, matching the response filter above) or explicitly about Codex (e.g. a workflow notice that Codex is disabled or not installed) that is *exclusively* an inability-to-review notice: it carries **no** `Reviewed commit` marker and **no** findings. Two guards matter here: the exclusivity guard — a normal review that merely mentions an error while still carrying findings or a reviewed-commit marker is a normal round, not an unavailability signal — and the author guard — another review/CI app's failure notice is never a codex signal. `reason=not-configured` when the message says Codex is disabled / not set up / no app installed; otherwise `reason=error`.
  - **copilot** — the reviewer-request command exits non-zero (e.g. HTTP 422 → Copilot code review not enabled for the repo/org). `reason=not-configured`. A persistent request failure is treated as `not-configured`, not `error`.
- **Silence** — no new reviewer response within **~10 minutes (20 polls)** of a trigger. Do not stall: **re-trigger the bound reviewer once per its profile** (codex: re-comment `@codex review`; copilot: re-run the reviewer-request command), re-poll one more ~10-minute window — this re-trigger does not increment the round counter. If a review lands on the retry, continue normally. If the retry window is also silent: `reason=silent`.
````

- [ ] **Step 7: Parameterize "When a new Codex review appears" (step 4 body)**

Replace the `### When a new Codex review appears` heading + items 1 and 5 (lines 74–80). Change the heading to `### When a new reviewer response appears`, and:

Replace item 1:
```
1. Read all new comments from it.
```
with:
```
1. Read all new comments from it. **Copilot only**: because Copilot findings are often body-only (it frequently generates zero inline comments), treat the review's summary body as an actionable finding source, parsed via the existing step-2 "non-inline feedback" path (tracked by comment ID — no thread-resolution state). Skip the boilerplate named in the reviewer profile (the per-file `<details>` summary table and the "Add Copilot custom instructions" footer).
```

Replace item 5:
```
5. If the round counter is below 10 and the round **produced code changes**: increment the counter, re-trigger `@codex review`, return to the top of the loop. Do **not** re-trigger when nothing changed: if every finding in the round was rejected with rationale — including rounds whose findings were only theoretical or insignificant, declined under the step-2 judgment bar — Codex would repeat the same findings; resolve the threads and treat the loop as ended.
```
with:
```
5. If the round counter is below 10 and the round **produced code changes**: increment the counter, re-trigger the bound reviewer per its profile (codex: re-comment `@codex review`; copilot: re-run the reviewer-request command), return to the top of the loop. Do **not** re-trigger when nothing changed: if every finding in the round was rejected with rationale — including rounds whose findings were only theoretical or insignificant, declined under the step-2 judgment bar — the reviewer would repeat the same findings; resolve the threads and treat the loop as ended.
```

- [ ] **Step 8: Parameterize the loop-end paragraph, local-loop mention, step-5 report, and safety rules**

Replace (line 82):
```
The Codex loop ends on whichever comes first: **Codex reports no meaningful issues** (e.g. "Didn't find any major issues" or equivalent wording), the **judgment-based stop** in item 5 above, or the **10-round cap**. Then merge (step 5). If unavailability was detected instead, the local review loop below takes over with its own termination rules.
```
with:
```
The reviewer loop ends on whichever comes first: **the reviewer reports no meaningful issues** per its profile's "no meaningful issues" row, the **judgment-based stop** in item 5 above, or the **10-round cap**. Then merge (step 5). If unavailability was detected instead, the local review loop below takes over with its own termination rules.
```

Replace (line 86, the local-loop intro clause):
```
Entered only from unavailability detection — the Codex loop's structural twin, with "spawn a fresh reviewer agent" replacing "post `@codex review`".
```
with:
```
Entered only from unavailability detection — the reviewer loop's structural twin, with "spawn a fresh reviewer agent" replacing "trigger the bound reviewer".
```

Replace (line 90, the late-arrival clause):
```
Also check for new comments since the last round — from humans, other bots, or a late-arriving Codex review from a pre-switch trigger — and handle them per the step-2 rules; they do not count as local rounds, and a late Codex arrival never un-does the permanent switch (do not re-trigger).
```
with:
```
Also check for new comments since the last round — from humans, other bots, or a late-arriving reviewer response from a pre-switch trigger — and handle them per the step-2 rules; they do not count as local rounds, and a late reviewer arrival never un-does the permanent switch (do not re-trigger).
```

Replace (line 105, the last paragraph of the local loop):
```
Local-reviewer output consists of plain PR comments — no GraphQL thread resolution applies to them. The all-threads-resolved merge gate in step 5 still applies to all review threads — pre-existing, human, and any Codex threads, including late arrivals from pre-switch triggers.
```
with:
```
Local-reviewer output consists of plain PR comments — no GraphQL thread resolution applies to them. The all-threads-resolved merge gate in step 5 still applies to all review threads — pre-existing, human, and any reviewer threads, including late arrivals from pre-switch triggers.
```

Replace (line 124, the step-5 report sentence):
```
Confirm `gh pr view <pr> --json state` reports `MERGED` before declaring success. The final report states: which loop ran (Codex, or the local fallback), rounds run, findings applied vs. declined (with reasons), and any judgment calls resolved autonomously in non-interactive mode.
```
with:
```
Confirm `gh pr view <pr> --json state` reports `MERGED` before declaring success. The final report states: which loop ran (the configured reviewer — Codex or Copilot — or the local fallback), rounds run, findings applied vs. declined (with reasons), and any judgment calls resolved autonomously in non-interactive mode.
```

Replace (line 124, end of that paragraph):
```
**When the local fallback ran, state prominently that no cross-model (Codex) review validated this PR**, and why (`quota` / `not-configured` / `error` / `silent`).
```
with:
```
**When the local fallback ran, state prominently that no cross-model reviewer validated this PR**, and why (`quota` / `not-configured` / `error` / `silent`).
```

In `## Safety rules`, replace the two Codex-specific bullets (lines 130–131):
```
- **Never** run more than 10 Codex rounds or 10 local review rounds.
- **Never** post `@codex review` again after unavailability was detected — the switch to the local loop is permanent for the run.
```
with:
```
- **Never** run more than 10 reviewer rounds or 10 local review rounds.
- **Never** re-trigger the bound reviewer again after unavailability was detected — the switch to the local loop is permanent for the run.
```

- [ ] **Step 9: Verify no stray Codex-only hard-coding remains in the trigger/loop paths, and structure is intact**

Run:
```bash
cd /home/forhas/dev/pure-dev
f=plugins/quick-dev/skills/review-and-merge/SKILL.md
echo "--- must exist ---"
grep -q "^## Reviewer$" "$f" && echo "HAS Reviewer section"
grep -q "copilot-pull-request-reviewer\[bot\]" "$f" && echo "HAS copilot login"
grep -q "trigger timestamp" "$f" && echo "HAS trigger timestamp"
grep -q "reviewer-config.md" "$f" && echo "REFERENCES config doc"
echo "--- must NOT remain (Codex-only phrasings that were parameterized) ---"
grep -n "Trigger a Codex review\|a \*\*Codex response\*\*\|Codex unavailability detection\|first \`@codex review\` trigger\|no cross-model (Codex)" "$f" || echo "CLEAN: no stale Codex-only headings/phrases"
```
Expected: all four `HAS`/`REFERENCES` lines print; the final check prints `CLEAN: ...`.

- [ ] **Step 10: Commit**

```bash
cd /home/forhas/dev/pure-dev
git add plugins/quick-dev/skills/review-and-merge/SKILL.md
git commit -m "feat(quick-dev): configurable reviewer profile in review-and-merge

Claude-Session: https://claude.ai/code/session_01SuR5SUzx67bD6riqPE51st"
```

---

### Task 3: Front-load reviewer resolution in `develop` Phase 0

Adds a GitHub-mode-only preflight step so the reviewer is chosen before the long build, and generalizes the Phase 4 wording. `develop`'s local-mode path is untouched (no reviewer config).

**Files:**
- Modify: `plugins/quick-dev/skills/develop/SKILL.md`

**Interfaces:**
- Consumes: the reviewer resolution procedure from Task 1 (cited by path) and the config semantics from Task 2.

- [ ] **Step 1: Add the Phase 0 reviewer-resolution step**

In `## Phase 0 — Preflight`, after step 5 (the "Build-flow plugins" block, ending "consult `references/environment-setup.md`.") and before `## Phase 1 — Branch and worktree`, insert:

````markdown
6. **Reviewer (GitHub mode only)**: run the **reviewer resolution procedure** in `skills/review-and-merge/references/reviewer-config.md` now, so the choice is made before the build rather than mid-review. It reads the gitignored per-clone config (`$REPO_ROOT/.claude/quick-dev/config.json`); if `reviewer` is unset it prompts (interactive) or defaults to `codex` (non-interactive) and persists it. Record the resolved reviewer for the final summary. **Skip entirely in local mode** — there is no GitHub reviewer to configure; the local fresh-agent reviewer is always used.
````

- [ ] **Step 2: Generalize the Phase 4 GitHub-mode wording**

In `## Phase 4 — Review and merge`, replace the first paragraph of the **GitHub mode** bullet:
```
**GitHub mode**: invoke the `quick-dev:review-and-merge` skill via the Skill tool with args `<pr-number>` (append `--non-interactive` if set). It handles review comments, Codex review rounds with a local-reviewer fallback, the squash-merge, and remote branch deletion. Remain in `$WORKTREE` while it runs so review fixes land on the branch.
```
with:
```
**GitHub mode**: invoke the `quick-dev:review-and-merge` skill via the Skill tool with args `<pr-number>` (append `--non-interactive` if set). It resolves the configured reviewer (Codex or Copilot — already set in Phase 0 for this flow), handles review comments, reviewer rounds with a local-reviewer fallback, the squash-merge, and remote branch deletion. Remain in `$WORKTREE` while it runs so review fixes land on the branch.
```

- [ ] **Step 3: Verify**

Run:
```bash
cd /home/forhas/dev/pure-dev
f=plugins/quick-dev/skills/develop/SKILL.md
grep -q "reviewer-config.md" "$f" && echo "REFERENCES config doc"
grep -q "Reviewer (GitHub mode only)" "$f" && echo "HAS Phase 0 step"
grep -q "Skip entirely in local mode" "$f" && echo "HAS local-mode skip"
grep -q "reviewer rounds with a local-reviewer fallback" "$f" && echo "PHASE 4 generalized"
```
Expected: all four lines print.

- [ ] **Step 4: Commit**

```bash
cd /home/forhas/dev/pure-dev
git add plugins/quick-dev/skills/develop/SKILL.md
git commit -m "feat(quick-dev): resolve reviewer in develop Phase 0 (GitHub mode)

Claude-Session: https://claude.ai/code/session_01SuR5SUzx67bD6riqPE51st"
```

---

### Task 4: Document the reviewer config and bump the manifest

**Files:**
- Modify: `plugins/quick-dev/README.md`
- Modify: `plugins/quick-dev/.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: config path/values from Tasks 1–2.

- [ ] **Step 1: Add a `## Code reviewer` section after `## Usage`**

Insert the block below **between** the `## Usage` section (which ends at the standalone `/quick-dev:review-and-merge <pr-number>` code fence) and the `## Requirements` heading. Concretely, insert it immediately before the line `## Requirements`:

````markdown
## Code reviewer (GitHub mode)

In GitHub mode the review loop drives a configurable reviewer:

- **`codex`** (default) — triggers a review via an `@codex review` comment (requires the Codex GitHub app).
- **`copilot`** — requests the `copilot-pull-request-reviewer[bot]` reviewer via the GitHub API (requires Copilot code review enabled for the repo/org).

Either falls back to the local fresh-agent reviewer when the chosen reviewer is unavailable.

The choice is stored per-clone in `.claude/quick-dev/config.json` (gitignored, alongside the ledger):

```json
{ "reviewer": "codex" }
```

The first `/develop` or `/quick-dev:review-and-merge` run in a repo prompts for it (interactive) or defaults to `codex` (non-interactive) and saves it. To change it later, edit the file — or delete the `reviewer` key (or the file) to be prompted again on the next run. Local mode ignores this setting (it always uses the local reviewer).
````

- [ ] **Step 2: Generalize the Requirements bullet about the reviewer**

In `## Requirements`, replace:
```
- Optional: the Codex GitHub app for `@codex review` rounds. Without it (or when Codex is out of quota, misconfigured, or silent), the review loop falls back to a local review loop — a fresh agent per round applying the plugin's `local-code-review` skill.
```
with:
```
- Optional: a GitHub code reviewer — the Codex app (`@codex review` rounds, the default) or Copilot code review (`reviewer: copilot`). See [Code reviewer](#code-reviewer-github-mode). Without one (or when the chosen reviewer is out of quota, misconfigured, or silent), the review loop falls back to a local review loop — a fresh agent per round applying the plugin's `local-code-review` skill.
```

- [ ] **Step 3: Bump the manifest version**

Replace in `plugins/quick-dev/.claude-plugin/plugin.json`:
```
  "version": "0.4.0",
```
with:
```
  "version": "0.5.0",
```
(Minor bump — new capability. Note: if this branch is ultimately shipped via a `/develop` run, its Phase 3 auto-bump would also fire; `review-and-merge`'s plugin stale-bump `--pre-merge-check` reconciles that. Do not double-bump beyond 0.5.0 here.)

- [ ] **Step 4: Verify README + JSON**

Run:
```bash
cd /home/forhas/dev/pure-dev
python3 -m json.tool plugins/quick-dev/.claude-plugin/plugin.json > /dev/null && echo "JSON valid"
grep -q '"version": "0.5.0"' plugins/quick-dev/.claude-plugin/plugin.json && echo "VERSION 0.5.0"
grep -q ".claude/quick-dev/config.json" plugins/quick-dev/README.md && echo "README documents config path"
grep -qi "copilot" plugins/quick-dev/README.md && echo "README mentions copilot"
```
Expected: `JSON valid`, `VERSION 0.5.0`, `README documents config path`, `README mentions copilot`.

- [ ] **Step 5: Commit**

```bash
cd /home/forhas/dev/pure-dev
git add plugins/quick-dev/README.md plugins/quick-dev/.claude-plugin/plugin.json
git commit -m "docs(quick-dev): document configurable reviewer; bump manifest to 0.5.0

Claude-Session: https://claude.ai/code/session_01SuR5SUzx67bD6riqPE51st"
```

---

## Final verification (after all tasks)

- [ ] **Cross-file consistency sweep**

```bash
cd /home/forhas/dev/pure-dev
echo "=== both skills reference the shared config doc ==="
grep -l "reviewer-config.md" plugins/quick-dev/skills/develop/SKILL.md plugins/quick-dev/skills/review-and-merge/SKILL.md
echo "=== reviewer values consistent everywhere ==="
grep -rn "copilot-pull-request-reviewer\[bot\]\|chatgpt-codex-connector\[bot\]" plugins/quick-dev | wc -l
echo "=== no residual Codex-only trigger/loop headings ==="
grep -rn "Trigger a Codex review\|Codex unavailability detection" plugins/quick-dev/skills/review-and-merge/SKILL.md || echo "CLEAN"
```
Expected: both file paths listed; a non-zero login count; `CLEAN`.

- [ ] **Dogfood (manual, GitHub mode, codex path):** on a repo with `reviewer` unset, confirm the first run prompts once, writes `.claude/quick-dev/config.json`, and the file does not appear in `git status`. Then confirm a normal Codex round behaves as before.

- [ ] **Dogfood (copilot path):** set `{"reviewer":"copilot"}`; confirm `review-and-merge` requests the Copilot reviewer via REST, detects its response by exact login, and processes body-only findings. On a repo without Copilot review enabled, confirm the HTTP 422 routes to the local fallback (`reason=not-configured`).

## Spec coverage check

- Config file (gitignored, reviewer-only, primary-checkout): Task 1 + Task 4 docs.
- Resolution procedure (repo-root, read, prompt/default, persist): Task 1.
- Entry points (develop Phase 0 GitHub-only; review-and-merge start; standalone): Task 3 + Task 2 §Reviewer.
- Reviewer profile (trigger/re-trigger/author/detection/poll-baseline): Task 2.
- Local mode / non-interactive never prompt: Task 1 skip conditions + Task 3 Step 1.
- Docs + version bump: Task 4.
