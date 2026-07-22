# quick-dev: configurable code reviewer (Codex | Copilot)

**Date:** 2026-07-22
**Status:** Design — approved for planning
**Scope:** `plugins/quick-dev` only

## Summary

Make quick-dev's GitHub-mode review loop drive a **configurable** code reviewer —
`codex` (default) or `copilot` — instead of Codex only. Copilot is a pure drop-in for
Codex: same trigger point, same round loop, same local-reviewer fallback, same merge gates.
The only differences are the reviewer's identity, how a review is triggered, and how its
responses/unavailability are detected — all selected from a per-reviewer **profile** keyed
off one config value.

This mirrors the design already merged into the sibling `notion-dev` plugin
(PR forhas/pure-dev#2), including that PR's final "resolve-only for the run" lesson — but
adapted to quick-dev's zero-config, gitignored-state architecture, which lets the choice be
**persisted safely** without the hazards that made notion-dev's tracked-config persistence
painful.

## Motivation

- quick-dev currently hard-codes Codex as the GitHub reviewer. Teams standardized on GitHub
  Copilot code review cannot use it.
- notion-dev already gained this capability; quick-dev should match for consistency.
- Unlike notion-dev (whose `.claude/notion-dev.config.json` is **git-tracked** and committed
  by `/notion-dev:init`), quick-dev has **no config file and no init command**. It already
  maintains a **self-ignored** `.claude/quick-dev/` directory in the primary checkout (for
  its ledger). Storing the reviewer choice there as a **gitignored** file makes
  prompt-once/persist/reuse safe: a gitignored file in the primary checkout never dirties
  `git status`, is never swept by `git add -A`, is never committed, and never diverges the
  base branch — so the entire class of failures notion-dev hit does not arise.

## Non-goals

- No change to the flow, phases, gates, or the local-mode / local-reviewer path beyond the
  reviewer-identity swap.
- No shared/team-wide reviewer setting via git (config is per-clone, gitignored). YAGNI.
- No additional config keys. The file holds `reviewer` only for now.
- No new `init`-style command for quick-dev.

## Design

### 1. Config file

- **Path:** `<primary-checkout>/.claude/quick-dev/config.json`
- **Shape:** `{ "reviewer": "codex" }` or `{ "reviewer": "copilot" }` — reviewer-only.
- **Tracking:** gitignored, reusing the existing self-ignored directory. On first write:
  ```bash
  mkdir -p .claude/quick-dev
  [ -f .claude/quick-dev/.gitignore ] || printf '*\n' > .claude/quick-dev/.gitignore
  ```
  (Identical to the ledger's self-ignore bootstrap in
  `skills/flow-triage/references/ledger.md`.)
- **Primary-checkout only:** the file lives in the primary checkout and is read/written
  there. It is deliberately absent from feature worktrees (gitignored, worktree-local working
  dirs do not carry it).

### 2. Reviewer resolution (shared procedure)

A single "read-or-prompt-and-persist" procedure, invoked at each entry point:

1. Resolve the **primary checkout root** = first entry of `git worktree list` (works whether
   the caller is in the primary checkout or a feature worktree). Call it `REPO_ROOT`.
2. Read `REPO_ROOT/.claude/quick-dev/config.json`.
   - If it exists and has a valid `reviewer` (`codex` | `copilot`) → use it.
   - If missing / no `reviewer` / invalid value:
     - **interactive:** `AskUserQuestion` — "Which code reviewer should the review loop use?"
       (**Codex** / **Copilot**), default/prefill Codex → write the choice (creating the dir +
       self-ignore as above), preserving any other keys.
     - **non-interactive:** default to `codex`, persist it, and note in the report that the
       choice was defaulted.
3. Carry the resolved value forward to bind the reviewer profile (§3).

Because the file is gitignored and primary-checkout-local, the write is side-effect-free with
respect to git — no clean-tree-gate, worktree, or base-branch concerns.

### 3. Entry points

- **`develop` (GitHub mode only):** a new Phase 0 preflight step runs the resolution
  procedure up front — after mode detection (so it is skipped in local mode) and before the
  build — so the user answers early rather than being interrupted after a long build. In
  local mode the step is skipped entirely (no GitHub reviewer exists). In non-interactive
  mode it defaults without prompting.
- **`review-and-merge`:** runs the same resolution at its start. In a `/develop` run the
  value is already set (no-op read); when invoked standalone it is the asker. This is the
  canonical home of the resolution logic; `develop`'s early call is a front-loading
  convenience, not a duplicate implementation.

### 4. Reviewer profile (ported from notion-dev's merged `review-and-merge`)

Parameterize every reviewer-specific reference in the review loop by the bound profile:

| aspect | **codex** (default) | **copilot** |
|---|---|---|
| trigger | comment `@codex review` | REST request: `gh api --method POST "repos/{owner}/{repo}/pulls/<pr>/requested_reviewers" -f 'reviewers[]=copilot-pull-request-reviewer[bot]'` |
| re-trigger each round | re-comment `@codex review` | re-run the same request (bot is auto-removed after it submits) |
| response author (exact login) | `chatgpt-codex-connector[bot]` | `copilot-pull-request-reviewer[bot]` |
| review shape | `COMMENTED` review; findings as inline threads (+ summary body) | `COMMENTED` review; findings **often body-only** (Copilot frequently emits zero inline comments) — treat the summary body as a first-class finding source; inline threads appear only for line-level findings |
| boilerplate to ignore | Codex "About" block | per-file `<details>` summary table + "Add Copilot custom instructions" footer |
| "no meaningful issues" | review says no major issues / equivalent | body is only overview/per-file summary, no actionable findings, no (or only resolved) inline comments |
| not-configured signal | Codex-app message that is *exclusively* an inability-to-review notice (no `Reviewed commit`, no findings) | the request command exits non-zero (e.g. HTTP 422 → Copilot code review not enabled) → `reason=not-configured` |
| quota signal | body contains case-insensitive `reached your codex usage limit` | n/a (no comment-based quota); a persistent request failure is treated as `not-configured` |
| silence | no response within ~10 min (20×30s polls) → re-trigger once → `reason=silent` | same |

Additional profile-agnostic rules carried over from the notion-dev fix history:

- **Poll baseline = the round's trigger timestamp**, well-defined for both reviewers: the
  `@codex review` comment's timestamp (codex) or a UTC time captured **immediately before**
  the REST request call (copilot, which leaves no comment). Refreshed on every re-trigger.
- **Response detection** uses an **exact** author-login match, never a substring test.
- Copilot body-only findings are handled via the existing "non-inline feedback" path
  (tracked by comment id; no thread-resolution state).
- On any unavailability signal, the loop switches **permanently** to the local fresh-agent
  review loop (unchanged) and never re-triggers the bound reviewer again that run.

Everything else in `review-and-merge` — existing-comment processing, the judgment bar,
thread resolution, the 10-round cap, merge gates, squash-merge, branch deletion, and the
local-fallback loop — is **unchanged**. quick-dev's own skill references
(`quick-dev:receiving-code-review`, `quick-dev:local-code-review`) are preserved.

### 5. Docs + version

- `plugins/quick-dev/README.md`: document the reviewer config — where it lives, the two
  values, that Codex is the default, that it is gitignored/per-clone, and how to change it
  (edit the file, or delete the `reviewer` key / file to be re-prompted on the next run).
- `plugins/quick-dev/.claude-plugin/plugin.json`: bump `version` `0.4.0 → 0.5.0` (minor — new
  capability). Note: a `/develop` run on this very repo would also bump it via Phase 3; the
  manual bump here is for a direct edit/PR. Reconcile to a single bump at implementation time.

## Files touched

- `plugins/quick-dev/skills/review-and-merge/SKILL.md` — add the **Reviewer** section
  (resolution + profile table) and parameterize the trigger/re-trigger/response/detection
  references in "Trigger a review" and the review loop.
- `plugins/quick-dev/skills/develop/SKILL.md` — add the Phase 0 (GitHub-mode) reviewer
  resolution step.
- `plugins/quick-dev/README.md` — document the reviewer config.
- `plugins/quick-dev/.claude-plugin/plugin.json` — version bump.

## Behavior matrix

| Scenario | Behavior |
|---|---|
| GitHub mode, config unset, interactive | Prompt once in `develop` Phase 0; persist; reuse thereafter |
| GitHub mode, config unset, non-interactive | Default `codex`, persist, note in report; no prompt |
| GitHub mode, config set | Read and use; no prompt |
| Local mode | No prompt, no reviewer config read; local reviewer only (unchanged) |
| Standalone `review-and-merge`, config unset | `review-and-merge` prompts (interactive) / defaults (non-interactive) and persists |
| `copilot` configured but not enabled on repo (HTTP 422) | `reason=not-configured` → permanent switch to local fallback loop |

## Testing / verification

quick-dev skills are Markdown instruction sets (no unit tests). Verification is by review and
by dogfooding:

- **Static consistency:** the profile table and every parameterized reference are internally
  consistent; no residual "Codex-only" hard-coding remains in the trigger/detection paths;
  README, schema-of-behavior, and the two skills agree.
- **Dogfood (codex path):** a `/develop` run (or standalone `review-and-merge`) on a repo with
  `reviewer` unset prompts once, persists `codex`, and drives a normal Codex round — identical
  to today.
- **Dogfood (copilot path):** with `reviewer: copilot` on a repo where Copilot review is
  enabled, a review is requested via REST, the response is detected by exact login, body-only
  findings are processed, and the loop/merge behave as with Codex.
- **Fallback:** with `reviewer: copilot` on a repo where Copilot is not enabled, the 422 routes
  to the local fallback loop.

## Open questions

None. (Storage = gitignored local config; prompt at both entry points; reviewer-only config —
all confirmed.)
