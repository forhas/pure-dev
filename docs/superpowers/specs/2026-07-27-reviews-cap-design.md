# reviewsCap — design

**Date:** 2026-07-27
**Status:** approved design, not yet implemented
**Scope:** make the PR review loop's round cap configurable in both `quick-dev` and `notion-dev`

## Problem

Both plugins' `review-and-merge` skill hard-codes a cap of **10 rounds** on the PR review
loop, in five places per plugin. The number is a runaway backstop — the loop is expected to
end far earlier on its judgment-based stops — but when a PR genuinely needs more iterations,
the only way to raise the ceiling is to edit the shipped skill.

The cap should be a per-project setting, read from the config file each plugin already has,
with a default of **15**.

## Non-goals

- The `plan-review` skill's 2-round cap. Different loop, different rationale (it caps plan
  review, not code review), left alone.
- The silence windows (`~10 min`, `20×30s` polls). They share the number 10 by coincidence
  only; they bound *waiting*, not rounds.
- Ledger fields. `review_rounds` already records actual rounds run; nothing records the cap,
  and nothing needs to.
- Prompting for the value in any setup flow. See "Setup UX" below.
- Runtime schema validation. Neither plugin validates its config against a JSON Schema today;
  both validate in prose. That does not change here.

## The setting

**Key name: `reviewsCap`, top-level, in both plugins.** camelCase matches notion-dev's
existing convention (`mergeStrategy`, `baseBranch`, `defaultAssignee`) and its schema's
`additionalProperties: false` would make a snake_case outlier conspicuous. quick-dev's config
has no competing convention, so it follows suit — one spelling of the setting across both
plugins.

**Default: 15**, applied whenever the key is absent or unusable.

| | quick-dev | notion-dev |
|---|---|---|
| File | `$REPO_ROOT/.claude/quick-dev/config.json` (gitignored) | `$REPO_ROOT/.claude/notion-dev.config.json` (git-tracked) |
| Placement | top-level, sibling of `reviewer` | top-level, sibling of `reviewer` |
| Schema entry | none — see below | `{"type":"integer","minimum":1,"default":15}` |
| Written by | nobody | nobody |

`$REPO_ROOT` is the **primary checkout** in both cases, resolved by each plugin's existing
procedure — never a feature worktree.

### notion-dev needs a schema entry; quick-dev does not

`notion-dev.config.schema.json` sets `additionalProperties: false`, so `reviewsCap` must be
declared there or the file stops validating in editors the moment a user adds the key. The
entry is required for correctness, not for enforcement — nothing in the plugin runs the
schema; it is an editor affordance reached via the config's `$schema` key.

quick-dev gets no schema file. Its config is gitignored, holds two keys, and no editor would
resolve a schema for it without the resolution procedure also writing a `$schema` key into a
file that is otherwise machine-written. The README table and the prose resolution rule below
are the documentation.

### Setup UX: silent, hand-edited

Neither setup path asks for the value. quick-dev's reviewer-resolution prompt keeps asking
only about the reviewer; `/notion-dev:init` is untouched and does not write `reviewsCap`.
A user who wants a different cap adds the key by hand, guided by the README and (in
notion-dev) the schema description. This adds zero friction to every fresh clone for a knob
most projects will never touch.

Because nothing writes the key, the default lives in the **resolution rule**, not in the
config files. A schema `default` is documentation; it is never materialized.

## Resolution rule

Identical in both plugins, stated once in each `review-and-merge/SKILL.md`, in the review
loop section ahead of the first trigger:

> **Round cap.** Read `reviewsCap` from the config (primary checkout). Use it when it is an
> integer ≥ 1. When the key is absent, the file is missing, or the value is anything else —
> `0`, negative, non-integer, non-numeric — use **15**; if the value was present but
> unusable, say so in the final report. Resolve once, before the first trigger, and use the
> same number for both loops.

Rationale for tolerating bad values rather than stopping: this mirrors how both plugins
already treat an invalid `reviewer` (fall back, note it), and a review loop should not
refuse to run — blocking a merge — over a typo in a knob that has a perfectly good default.
The report line is what makes the fallback visible.

## Cap application

Both loops are capped at `reviewsCap`, **counted independently** — exactly today's structure,
with the constant parameterized. The local fallback loop still restarts its counter at 1 when
the switch happens, so a run that falls back can perform up to `2 × reviewsCap` rounds. That
is unchanged behavior, and it is deliberate: the two loops review with different reviewers,
and the fallback exists precisely because the first one produced nothing usable.

Six sites per plugin, in `plugins/{quick-dev,notion-dev}/skills/review-and-merge/SKILL.md`:

| site | quick-dev | notion-dev | current text |
|---|---|---|---|
| reviewer-loop header | 91 | 106 | "**Hard cap: 10 rounds.** After round 10 is handled…" |
| re-trigger step 5 | 113 | 128 | "If the round counter is below 10 and the round **produced code changes**" |
| reviewer-loop end conditions | 115 | 130 | "…or the **10-round cap**" |
| local-loop header | 119 | 134 | "Round counter starts at 1; **hard cap: 10 rounds**" |
| local-loop termination | 134 | 149 | "Round counter reaches 10 → stop" |
| safety rule | 163 | 183 | "**Never** run more than 10 reviewer rounds or 10 local review rounds" |

Plus one in prose outside the skill: `plugins/quick-dev/README.md:79`, the skills table's
"local review loop (10-round cap, green-CI gates)".

Each becomes a reference to the resolved cap — "the resolved cap", "below the cap", "reaches
the cap" — with the header stating where the value comes from. Line numbers are as of commit
`234153d` and are a locator, not a contract; match on the text.

## Supporting change: quick-dev's config write must preserve unknown keys

`plugins/quick-dev/skills/review-and-merge/references/reviewer-config.md` step 4 currently
directs a whole-file overwrite:

> Persist the resolved value by writing the whole file `{ "reviewer": "<value>" }` …
> (reviewer-only — overwrite or create it; there are no other keys to preserve)

With `reviewsCap` possible in that file, this silently deletes a user's cap on any run that
has to resolve the reviewer. Step 4 becomes a read-modify-write: read the existing JSON if
present, set `reviewer`, write the whole object back, preserving every other key. The
parenthetical asserting there is nothing to preserve is removed.

notion-dev needs no equivalent change — its `review-and-merge` skill is explicitly
write-free (it resolves the reviewer in memory and defers persistence to `/notion-dev:init`),
and `/notion-dev:init` runs in reconfigure mode reading the existing config first.

## Documentation

- `plugins/quick-dev/README.md` — document `reviewsCap` in the "Code reviewer (GitHub mode)"
  section, alongside the config file's shape: default 15, applies to each loop independently,
  hand-edited.
- `plugins/notion-dev/README.md` — same, in the config section that describes
  `.claude/notion-dev.config.json`.
- `plugins/notion-dev/schema/notion-dev.config.schema.json` — the `reviewsCap` property with
  a description covering the default and the both-loops-independently semantics.
- Version bump both `plugin.json` files from `0.6.0` to `0.7.0` (new configurable behavior).

## Verification

No test suite exists for these markdown skills, so verification is grep-based and manual:

1. `grep -n "10" plugins/*/skills/review-and-merge/SKILL.md plugins/*/README.md` returns only
   the unrelated silence-window matches (`~10 min`, `20×30s` polls) — no round-cap `10`
   survives anywhere.
2. Each `SKILL.md` states the resolution rule exactly once and references the resolved cap at
   all six sites — read both files end to end; the two plugins' texts must stay structurally
   parallel, as they are today.
3. A sample config containing `reviewsCap` validates against the updated notion-dev schema,
   and one containing an unknown key still fails (`additionalProperties: false` intact).
4. `reviewer-config.md` step 4 no longer instructs a destructive whole-file write.
5. Both READMEs document the key; both `plugin.json` versions read `0.7.0`.

## Decisions record

| decision | choice | why |
|---|---|---|
| Scope | both plugins | same loop, vendored twice; divergence would be a maintenance trap |
| Key name | `reviewsCap` in both | matches notion-dev's camelCase; one spelling across plugins |
| Which loops | both, independent counters | smallest change; preserves the fallback's deliberate counter reset |
| Setup UX | silent, hand-edited | no friction added to setup for a rarely-touched knob |
| Bad values | fall back to 15, note it in the report | mirrors invalid-`reviewer` handling; never block a merge on a config typo |
| quick-dev schema | none | two keys, gitignored, machine-written; a schema nothing resolves is dead surface |
