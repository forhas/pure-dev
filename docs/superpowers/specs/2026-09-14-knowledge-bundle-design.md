# Knowledge bundle — one shared implementation in notion-dev

**Date:** 2026-09-14 · **Plugin:** `notion-dev` 0.23.0 → 0.24.0 · **Status:** approved design

## Problem

Both notion-dev clients (BTC-Gateway, smart-contracts-foundry) keep a `knowledge/` bundle in
OKF v0.2 markdown and capture into it from `git.postMergeHooks`. Everything else about the two
diverged: one reads through `iwe find`/`iwe retrieve` and validates with 224 lines of JavaScript
(a hard 4096-byte cap, a `stale_after` clock); the other reads through a 1,413-line `okf.py`,
mirrors Notion and Slack locally, and re-vouches concepts on a weekly CI sweep. Each has its
own 200-line `knowledge-capture` skill, hardened separately over several review rounds. The
recorded pain is the same kind in both: trim passes against the byte cap, a phantom CRLF
overage, a post-merge hook that aborts on ordinary branch drift, validators that passed when
they could not run, and a tooling-to-content ratio of roughly 2,600 lines of code for 16
concepts.

Neither bundle is linked to the epic brief `notion-dev:epic-doc` writes, although the brief's
`## Decisions & constraints` and `## Open threads` restate what `decision/` concepts hold. And
a ticket run reads overlapping facts twice: the Notion epic page, the brief, and the bundle.

A third client would copy one of the two and diverge again.

## Goal

One implementation of the bundle inside `notion-dev`, consumed by every client through config
alone: the concept schema, capture, retrieval, supersession, dedupe, and migration. A new client
gets a working bundle from `/notion-dev:init` and one binary install. The epic brief becomes the
epic's root concept inside the bundle. Every fact enters a run's context exactly once.

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | **Dependencies: `iwe` binary required, plus one shipped script** (`plugins/notion-dev/scripts/knowledge.py`, Python 3, standard library only). | iwe gives budgeted search-plus-graph retrieval in one call; the script holds only what iwe lacks. Both are per-machine installs like `gh` and `jq`. |
| 2 | **Core only.** Schema, capture, retrieve, supersession, dedupe, migrate. Notion/Slack mirroring, source allowlists, verbatim records, transcript and mail inputs stay client-side and are tolerated by the schema. | That machinery was hardened for one client's needs; the schema leaves room for it without carrying it. |
| 3 | **The brief is the epic's root concept**, at `<knowledge.dir>/epic/<KEY>-<n>-<slug>.md`, six sections unchanged. `epicDocs.dir` is retired. | One writer discipline, one directory, one retrieve. Bullets link concepts instead of restating them. |
| 4 | **Clients migrate in this effort**, one PR each after the plugin PR, via `migrate --dry-run` then `--apply`, and **that PR deletes the client's own implementation** (§13). | "No regression" is only demonstrated on the real bundles, hooks, and CI; a bundle with two writers is the state this work ends. |
| 5 | **Read-once.** Each fact has exactly one read path per run (§4). | Context is the scarce resource; overlap between Notion, brief, and bundle is the waste. |
| 6 | **Valid until superseded.** No `stale_after`, no `reconciled` clock, no scheduled sweep, no source polling. Knowledge changes only when new information arrives: a merge (`capture`) or a fact (`new-info`). | Minimum maintenance. A green cron nobody opens is not a safeguard. |
| 7 | **No hard byte cap.** A per-concept size *warning* (`knowledge.warnBytes`, default 8192) and a read-time token budget on `iwe retrieve`. | The 4096 cap cost seven trim passes on one ticket; the budget it protected is now enforced where it matters. |
| 8 | **Hook precondition** is the three-line check `ticket.md` Phase 9 already uses (primary on `<base>`, merge commit is an ancestor of HEAD, clean tree), never `HEAD == origin/<base>`. | The equality assertion aborted on ordinary drift and needed a manual rebase. |
| 9 | **Fail closed on checks, degrade on reads.** `knowledge.py check` failing or absent means nothing is written; `retrieve` with iwe missing returns the brief alone and the ticket still runs. | Both clients learned that a check which cannot run and says nothing is the worst outcome. |

## 1. Dependencies and install

- **`iwe` ≥ 0.19** on `PATH`. Probed at each command's preconditions with `iwe --version`.
  Missing or older → the precondition message names both install routes:
  `cargo install iwe --root ~/.local` (works wherever Rust does; required on hosts whose GLIBC
  is older than 2.39, which includes Ubuntu 22.04 under WSL), and `brew install iwe` /
  `npm i -g @iwe-org/iwe` where the prebuilt binary runs. Nothing in the plugin depends on the
  LSP (`iwes`) or the MCP server (`iwec`).
- **`python3`** on `PATH` for `knowledge.py`. Standard library only; no `pip` step.
- The plugin touches exactly three iwe commands, all inside `skills/knowledge/SKILL.md` and
  `scripts/knowledge.py`: `iwe find` (dedupe seed, JSON frontmatter), `iwe retrieve` (context
  assembly), `iwe schema validate` (shape). Nothing else in the plugin invokes iwe, so the
  dependency can be swapped by editing one skill and one script.
- `knowledge.py` never parses YAML. It reads frontmatter as JSON from `iwe find -f json` and
  delegates shape validation to `iwe schema validate`.
- `README.md` "Requirements" gains both entries beside `gh` and `jq`.

## 2. Layout and config

```
<knowledge.dir>/                       # default `knowledge`
  .iwe/config.toml                     # plugin-owned; migrate/init install, check compares
  .iwe/schemas/okf.yaml, okf-index.yaml, okf-log.yaml
  index.md                             # hand-curated catalog: one bullet per concept, by type
  log.md                               # append-only, dated
  epic/<KEY>-<n>-<slug>.md             # the brief — the epic's root concept
  ticket/ decision/ gotcha/ component/ spec/ domain/ release/     # canonical types
  <extra>/                             # client extension dirs, declared in knowledge.extraTypes
```

Config, new top-level `knowledge` block in `schema/notion-dev.config.schema.json`:

```json
"knowledge": {
  "dir": "knowledge",
  "retrieveBudget": 8000,
  "warnBytes": 8192,
  "extraTypes": []
}
```

- `dir` carries the same path pattern `epicDocs.dir` had (relative, forward slashes, no `..`).
- `retrieveBudget` is the `--max-tokens` passed to `iwe retrieve` (integer ≥ 1000).
- `warnBytes` is the per-concept size above which `check` warns (never fails).
- `extraTypes` lists client-specific type directories `check` accepts beyond the canonical set
  (for example `["commitment", "node"]`). An undeclared directory containing concepts fails
  `check`; dot-directories (`.mirror/`, `.record/`, `.okf/`) are ignored entirely.
- `epicDocs` is **removed** from the schema. `init` stops writing it; `migrate` drops it from a
  client config; the schema-drift check in `init` reports it as an unknown key like any other.

The plugin-owned files under `.iwe/` are shipped verbatim in
`plugins/notion-dev/skills/knowledge/references/iwe/`. `check` fails when a client's copy
differs, printing the diff, so a client cannot silently loosen the schema; `migrate --apply`
and `init` overwrite them.

## 3. Data model

OKF v0.2 concept, one fact per file, frontmatter validated by `iwe schema validate` against the
shipped `okf.yaml`:

| field | required | values |
|---|---|---|
| `type` | yes | `Epic`, `Ticket`, `Decision`, `Gotcha`, `Component`, `Spec`, `Domain`, `Release`, or a name from `extraTypes` (directory name, capitalised) |
| `title`, `description` | yes | one line each |
| `status` | yes | `current` \| `draft` \| `deprecated` |
| `generated` | yes | `{ by, at }` |
| `sources` | yes, ≥ 1 | `[{ id, resource, title, last_modified? }]` — a ticket URL, PR URL, or repo path |
| `updated` | no | `{ by, at }`, set on every in-place change |
| `ticket`, `epic` | no | `<KEY>-<n>` |
| `applies_to` | no | path globs; a merge touching one triggers re-read (§5) |
| `superseded_by` | when deprecated | relative path of the successor |
| `confidence`, `tags` | no | free |

Dropped, and removed by `migrate`: `stale_after`, `reconciled`, `verified`, `vouch`. Status
`stable` migrates to `current`. Body headings are free except two conventions: a `Ticket`
concept carries `# Problem`, `# Decision`, `# Ruled out`; any concept updated in place carries a
trailing `## Updates` section with one dated line per change (`- 2026-09-14 [STO-140]: …`).

Links are ordinary relative markdown links with the `.md` extension, inside prose (reference
edges). No inclusion links: `iwe retrieve --expand-references` is the expansion the plugin
relies on, and `--expand-includes` is never passed.

**The epic root concept** is the `epic-doc` brief with frontmatter added:

```
---
type: Epic
title: [STO-60] Wallet Indexing
description: <the Goal in one line>
status: current
epic: STO-60
generated: { by: notion-dev:epic-doc, at: 2026-09-13T00:00:00Z }
sources:
  - { id: epic, resource: <notion url>, title: "[STO-60] Wallet Indexing" }
---
# [STO-60] Wallet Indexing
Epic: <notion url> · Status: open | closed · Updated: 2026-09-13 after [STO-67]
## Why … ## Goal … ## Where we stand … ## Open threads … ## Decisions & constraints … ## Next
```

The six sections, their rules of content, the 120-line soft budget, and the header line are
unchanged from `epic-doc`. A bullet under `## Decisions & constraints` or `## Open threads` may
be a link to a concept plus one clause (`- [Offline deploy](../decision/offline-deploy.md) —
binds STO-70.`); `record` and `note` write the link form whenever a concept for the fact exists,
and the prose form otherwise.

## 4. Read-once and `retrieve`

Each fact has exactly one read path per run:

| fact | read from | never from |
|---|---|---|
| requirements | the ticket body, `fetchTicket` | bundle, brief |
| children statuses | `listEpicChildren` | bundle, brief (neither stores status) |
| epic identity (key, title, url) | `fetchTicket(<epic-id>)`, properties only | the Notion epic page body |
| why / where we stand / threads / decisions / next | the brief, as the root of the retrieve | Notion epic page |
| ruled-out approaches, gotchas, constraints | the retrieve result | `grep -r`, `index.md`, a second query |
| the merge's content | `git show <merge-sha>`, `gh pr view` | Notion |

**`retrieve(<epic-id>, <ticket-title>?, <ticket-id>?)` → `KNOWLEDGE_CONTEXT` or `null`.**
Read-only, writes nothing, runs before any worktree exists.

1. `fetchTicket(<epic-id>)`, epic predicate as `epic-doc read` step 1. Not an epic → `null`.
2. `git fetch origin`; locate the root on `origin/<epicBranch>` with
   `git ls-tree -r --name-only origin/<epicBranch> -- <knowledge.dir>/epic/` filtered to
   `<KEY>-<n>-*.md`. Missing → bootstrap in memory exactly as `epic-doc` "Bootstrap" describes
   (seed search now also covers `<knowledge.dir>/epic/`), return the brief alone with
   `BOOTSTRAP: true`, and skip step 3.
3. One call, run from a temporary export of the bundle at `origin/<epicBranch>` so a stale local
   checkout never answers (`git archive origin/<epicBranch> <knowledge.dir> | tar -x -C <tmp>`):

   ```
   iwe retrieve -k epic/<KEY>-<n>-<slug> --expand-references 1 \
       --lexical "<ticket title>" --filter 'status: current' \
       --max-tokens <knowledge.retrieveBudget> -f markdown
   ```

   The root is always first and never trimmed; the lexical seed is omitted when no ticket title
   is given (`next-task`, `new-info`). `status: deprecated` and `draft` are excluded by the
   filter.
4. Return `KNOWLEDGE_CONTEXT` (the retrieve output verbatim), plus the fields `epic-doc read`
   returns today, parsed from the root: `EPIC_CONTEXT` (the root document), `NEXT`, `BLOCKED`,
   `STATUS`, `CHILDREN` (one `listEpicChildren` call), `BOOTSTRAP`, `SEED`.
5. iwe missing or failing → `EPIC_CONTEXT` from `git show origin/<epicBranch>:<root path>`,
   `KNOWLEDGE_CONTEXT: unavailable`, signature `partial:knowledge-retrieve`. The run continues.

`epic-doc read` becomes a thin name for step 4's parse over a retrieve result, so a caller that
already holds `KNOWLEDGE_CONTEXT` never fetches twice. Callers treat the whole block as
background, not requirements, exactly as `EPIC_CONTEXT` is treated today.

**Budget.** `retrieveBudget` bounds the bundle's share of a run's context. The root is ≤ 120
lines by `epic-doc`'s rule; the remainder is the concepts one reference hop away plus the
lexical seeds, periphery trimmed first by iwe.

## 5. `capture` — the writer

Invoked two ways, one procedure:

- **As the post-merge hook.** A client's `git.postMergeHooks` names `notion-dev:knowledge`;
  the hook contract in `ticket.md` Phase 9 and `finalize.md` runs the skill's `capture`
  operation with `<ticket-id>` and `<merge-sha>`. Preconditions are decision 8's three lines,
  plus a clean `<knowledge.dir>/` (`git status --porcelain -- <knowledge.dir>` empty).
- **From `/notion-dev:new-info`**, as `capture --fact <fact> <epic-id>`, after the brief note is
  applied for that epic (§8).

Inputs come from the session, never from Notion: the ticket body, `KNOWLEDGE_CONTEXT`, the
review report and `PLAN_REVIEW` when present, `gh pr view <n> --json body,comments` plus the
review threads, and `git show <merge-sha>`. For `--fact`, the inputs are the fact text and the
epic's `KNOWLEDGE_CONTEXT` only.

1. **Filter.** For each candidate: *would an engineer reading the merged code still not know
   this?* Keep rejected approaches and why, traps that cost time, decisions and what they rule
   out, constraints that must hold. Drop what the code says, the diff, the ticket text, status,
   style. An empty capture is a correct outcome: log one dated `- <date> [<KEY>-<n>]: nothing
   durable` line and return `KNOWLEDGE: empty`.
2. **Verify before citing.** A specific claim (a count, an order, a location) is checked against
   the file it names before it is written. `sources[]` cites the PR and the ticket by URL and
   any code path by relative path.
3. **Collide.** Dedupe against `KNOWLEDGE_CONTEXT` first, then one
   `iwe find --lexical "<key phrase>" --filter 'status: current' -f json` per candidate.
   Outcome per candidate:
   - **untouched** — an existing concept already says it;
   - **updated** — an existing concept is refined, not contradicted: edit in place, set
     `updated`, append one `## Updates` line;
   - **superseded** — an existing concept is contradicted: write the new concept, set the old
     one `status: deprecated` and `superseded_by: <new path>`, add the `## Updates` line naming
     the ticket or fact that retired it;
   - **created** — nothing collides: new file under its type directory.
4. **Re-read touched concepts** (hook only). `python3 knowledge.py touched <merge-sha>` lists
   every `current` concept whose `applies_to` globs intersect the merge's changed paths. Each is
   read against the diff and resolved with the same four outcomes. Nothing else in the bundle is
   examined.
5. **Index and log.** Every created or superseded concept gets its `index.md` bullet added,
   moved, or marked; `log.md` gets one dated entry per capture.
6. **Check, commit, push.** `python3 knowledge.py check` must exit 0 — otherwise write nothing
   (`git checkout -- <knowledge.dir>` of the working changes), record `partial:knowledge-capture`
   with the check's first error, and return `KNOWLEDGE: failed`. Then
   `git add -- <knowledge.dir>` and `git commit --only -m "docs(knowledge): capture <KEY>-<n>" --
   <knowledge.dir>` (`--fact`: `docs(knowledge): note <KEY>-<n> — <short fact>`), then push as
   `epic-doc record` does. A rejected push is reported the way `record` reports it.

Output block:

```
KNOWLEDGE: captured | empty | failed | unavailable
CREATED: <paths> · UPDATED: <paths> · SUPERSEDED: <old → new> · UNTOUCHED: <n>
COMMIT: <sha> | none
```

## 6. `curate` — dedupe only

User-invoked, `/notion-dev:knowledge curate`. Runs `knowledge.py check`, then
`knowledge.py clusters` (a wrapper over `iwe stats similarity`, same-type concepts above a
similarity threshold). Each cluster is presented with both bodies side by side; the user names
the survivor or `keep both`; the loser is superseded as in §5 step 3. Then index, log, check,
commit `docs(knowledge): curate — <n> clusters resolved`. Nothing runs on a schedule; the
command does not read Notion.

## 7. `migrate` — once per client

`/notion-dev:knowledge migrate [--apply]`. Without `--apply` it prints the complete diff and
writes nothing.

1. Preconditions: primary on `<epicBranch>`, clean tree, iwe and python3 present.
2. Install `.iwe/config.toml` and `.iwe/schemas/` from the plugin copy (overwriting).
3. For every concept under `<knowledge.dir>` outside dot-directories: map `status: stable →
   current`; drop `stale_after`, `reconciled`, `verified`, `vouch`; add `sources` when missing
   (from a `ticket`/PR reference in the body, else `{ id: migrated, resource: <own path> }`
   with `status: draft`); collect `## Reconciliation notes` under `## Updates`; leave every
   other field and all prose alone.
4. Move the brief: `docs/epics/<KEY>-<n>-<slug>.md` (or `epicDocs.dir`) → `epic/`, with the
   frontmatter of §3 added. A hand-written seed plan is left for `next-task`'s bootstrap, which
   now writes into `epic/`.
5. Rewrite relative links that the moves broke (`iwe rename` per moved file).
6. Drop `epicDocs` from `.claude/notion-dev.config.json`, add the `knowledge` block with
   `extraTypes` set to the non-canonical directories found; replace the `postMergeHooks` entry
   `knowledge-capture` with `notion-dev:knowledge`.
7. `knowledge.py check` must exit 0 on the result, or `--apply` reverts everything it wrote.
8. Print the removal checklist for this client (§13), derived from what it found: the skill
   directory the old `postMergeHooks` entry named, every script under `scripts/knowledge/`,
   every workflow and Makefile target that invokes one, and the CLAUDE.md lines that route to
   them. The command never deletes client code; the client PR does (§13), and the checklist is
   pasted into that PR's body with each line ticked.

## 8. Changes to existing commands and skills

- **`skills/epic-doc/SKILL.md`**: path becomes `<knowledge.dir>/epic/<KEY>-<n>-<slug>.md`;
  every `epicDocs.dir` reference goes; `read` is defined as the parse over a `retrieve` result
  (§4 step 4) and a caller holding `KNOWLEDGE_CONTEXT` passes it in instead of triggering a
  fetch; `record` and `note` write the frontmatter of §3 on create and the link form of bullets
  when a concept exists; `record --bootstrap` writes into `epic/`.
- **`commands/ticket.md` 1.1**: replaces the `epic-doc read` invocation with
  `notion-dev:knowledge retrieve(<epic-id>, <ticket title>, <id>)`, records `KNOWLEDGE_CONTEXT`
  and `EPIC_CONTEXT`; 1.3 and Phase 4 pass `KNOWLEDGE_CONTEXT` where they pass `EPIC_CONTEXT`
  today, under the same "background, not requirements" label. Phase 9's hook paragraph names
  `notion-dev:knowledge` as the example hook and states the inputs it receives from the run.
- **`commands/next-task.md` 1**: calls `retrieve(<epic-id>)`; the delegated `ticket` run
  receives `KNOWLEDGE_CONTEXT` so it does not retrieve again (`ticket.md` 1.1 skips the fetch
  when the caller supplied it).
- **`commands/new-info.md`**: Read calls `retrieve(<epic-id>)` once per epic; Apply, after the
  `note --apply` commit for an epic, runs `capture --fact <fact> <epic-id>` and reports its
  `KNOWLEDGE:` line per epic. The README sentence "knowledge bundles are not touched" goes.
- **`commands/init.md`**: preflight probes `iwe` and `python3`; step 9 scaffolds
  `<knowledge.dir>/` with `.iwe/`, `index.md`, `log.md`, and the empty type directories, writes
  the `knowledge` block, and sets `postMergeHooks: ["notion-dev:knowledge"]`; `epicDocs` is no
  longer written.
- **`commands/finalize.md`**: hook paragraph as `ticket.md`.
- **`skills/ticket-system/SKILL.md`**: `getEpicContext` is marked superseded by `retrieve` and
  no command calls it.
- **`commands/knowledge.md`** (new): `/notion-dev:knowledge migrate [--apply] | curate`.

## 9. `scripts/knowledge.py`

Single file, Python 3.8+, standard library only, `argparse` subcommands, exit 0 on success,
1 on findings, 2 on inability to run (iwe missing, not a bundle, git error). **Exit 2 is never
downgraded**: a check that cannot run says so and fails.

| subcommand | does |
|---|---|
| `check [--dir]` | `iwe schema validate`; every relative link resolves; every `superseded_by` target exists and is not itself deprecated; every `current` concept has an `index.md` bullet and every bullet resolves; type directory is canonical or in `extraTypes`; `.iwe/` matches the plugin copy; per-file size over `warnBytes` → warning line, not failure. Prints one line per finding, `path: rule: detail`. |
| `touched <sha> [--dir]` | changed paths of `<sha>` (`git show --name-only`) intersected with every `current` concept's `applies_to` globs; prints matching concept paths. |
| `clusters [--dir] [--threshold]` | `iwe stats similarity -f json`, grouped by type, above the threshold; prints groups. |
| `migrate [--apply] [--dir] [--config]` | §7 steps 2–7; without `--apply` prints the unified diff of every file it would write. |

Frontmatter is obtained from `iwe find --filter '' -f json`; the script reads and writes files
only in `migrate`, and there it writes bytes with `\n` line endings regardless of host.

## 10. Failure handling and signatures

Every operation is best-effort against the ticket flow: a failure never blocks a merge, a
report, or a resolution. New rows in `skills/issue-log/references/signatures.md`:

| signature | site | condition |
|---|---|---|
| `partial:knowledge-retrieve` | `knowledge/SKILL.md` | iwe missing or `retrieve` failed; brief served alone |
| `partial:knowledge-capture` | `knowledge/SKILL.md` | `check` failed or push rejected; nothing written or commit unpushed |
| `missing-dependency:iwe` | preconditions of `ticket`, `next-task`, `new-info`, `knowledge` | `iwe` absent or below 0.19 |

## 11. Verification

**`scripts/verify-knowledge.sh`** on `scripts/lib/assert.sh`, regions by heading, every check
mutation-proven: skill operation headings; the single `iwe retrieve` line with `-k epic/`,
`--expand-references 1`, `--filter 'status: current'`, `--max-tokens`; `assert_lacks
'--expand-includes'`; the read-once table rows; the four collision outcomes; `knowledge.py
check` before commit and the write-nothing rule; the by-pathspec commit line; the three
precondition lines and `assert_absent … 'HEAD == origin'`; `stale_after` absent from the skill
except the migrate drop line (`assert_count`); config schema keys present and `epicDocs`
absent; `epic-doc` path line and no `epicDocs.dir`; `ticket.md` 1.1 calls `retrieve` and
`assert_count 'epic-doc.*read(' 0`; `new-info` calls `capture --fact`; `init` scaffold lines;
signature rows; README rows; `assert_version_above … 0.23.0`.

**`scripts/verify-knowledge-py.sh`**: runs `python3 plugins/notion-dev/scripts/knowledge.py
check` against fixtures under `scripts/fixtures/knowledge/`: `valid/` must exit 0; each
`broken-<rule>/` (missing frontmatter field, dangling link, dangling `superseded_by`,
deprecated-to-deprecated `superseded_by`, index gap, undeclared type dir, drifted `.iwe/`) must
exit 1 with that rule named; `touched` against a fixture git repo built in a temp dir must list
exactly the intersecting concept; `migrate` without `--apply` must leave the fixture
byte-identical and print a diff, with `--apply` must produce the checked-in `expected/` tree.
Skips with a clear FAIL, not a pass, when `iwe` or `python3` is absent, since CI installs both
(`verify.yml` gains the two install steps).

**Regression proof per client**, in that client's PR body: the `migrate --dry-run` diff was
reviewed; `check` exits 0 after `--apply`; `iwe retrieve` from the epic root returns the brief
plus its linked concepts under budget (line count in the PR body); the client's old validator
rules are listed one by one against the `check` rule that covers each, and only then are the
validator, the `knowledge-capture` skill, and the sweep deleted; one real post-merge capture is
observed on the next ticket.

## 12. Docs and release

- `README.md`: Requirements (`iwe`, `python3`), command table row for `/notion-dev:knowledge`,
  a "Knowledge bundle" section replacing the epic-docs paragraph's location claim, and the
  `new-info` sentence about bundles.
- `plugin.json` `0.23.0 → 0.24.0` (new capability). After the squash merge, tag it
  `notion-dev-v0.24.0` and push the tag: client CI fetches `knowledge.py` by that ref (§13).
- `docs/superpowers/specs/2026-09-13-epic-doc-design.md` gains one line at the top pointing
  here for the path change.

## Files touched (pure-dev)

Create: `plugins/notion-dev/skills/knowledge/SKILL.md`,
`plugins/notion-dev/skills/knowledge/references/iwe/{config.toml,schemas/*.yaml}`,
`plugins/notion-dev/scripts/knowledge.py`, `plugins/notion-dev/commands/knowledge.md`,
`scripts/verify-knowledge.sh`, `scripts/verify-knowledge-py.sh`, `scripts/fixtures/knowledge/**`,
`docs/superpowers/plans/2026-09-14-knowledge-bundle.md`.
Modify: `skills/epic-doc/SKILL.md`, `commands/{ticket,next-task,new-info,init,finalize}.md`,
`skills/ticket-system/SKILL.md`, `skills/issue-log/references/signatures.md`,
`schema/notion-dev.config.schema.json`, `README.md`, `.claude-plugin/plugin.json`,
`.github/workflows/verify.yml`, `scripts/verify-epic-doc.sh`, `scripts/verify-new-info.sh`.

## 13. Client removal — nothing exists twice

Once 0.24.0 is installed in a client, the client's own implementation is deleted **in the same
client PR that migrates the bundle**. A migrated bundle beside a live `knowledge-capture`
skill is two writers and two schemas, which is the state this spec exists to end. The PR is
not done while any line of the inventory below survives, and its body carries the inventory
with each line ticked and, for every retired check, the `knowledge.py check` rule that covers
it now.

**Client CI keeps a validate gate.** `knowledge.py` is fetched, not vendored, so it cannot
diverge: pure-dev is public, and the plugin PR tags its merge commit `notion-dev-v0.24.0`
(the first tag in this repository; every later notion-dev minor gets one). A client workflow
step is:

```yaml
- run: |
    curl -fsSL https://raw.githubusercontent.com/forhas/pure-dev/notion-dev-v0.24.0/plugins/notion-dev/scripts/knowledge.py -o /tmp/knowledge.py
    python3 /tmp/knowledge.py check
```

pinned to the tag the client's installed plugin version matches. The same one-liner replaces a
local pre-commit hook where a client had one.

**BTC-Gateway** (`~/win-home/dev/playza/BTC-Gateway`, epic STO-67):

| remove | replaced by |
|---|---|
| `.claude/skills/knowledge-capture/` | `notion-dev:knowledge` `capture` via the hook |
| `scripts/knowledge/check.cli.js`, `check.js`, `check.test.js` | `knowledge.py check` (schema, links, index, type dirs; byte cap → `warnBytes` warning) |
| `scripts/knowledge/report.cli.js`, `report.js`, `report.test.js` | `check` (orphans are index gaps) and `curate` (near-duplicates); staleness has no successor by decision 6 |
| `package.json` scripts `knowledge:check`, `knowledge:report`; the `scripts/knowledge/*.test.js` glob in `test:scripts` | a `knowledge-check` CI job on the fetched script |
| `.claude/skills/dream/SKILL.md` bundle half (its `knowledge/` orientation, `iwe find`/`retrieve` reads, `knowledge:report` worklist, index pruning) | `/notion-dev:knowledge curate`; the memory-directory half and the mail/transcript inputs stay |
| `CLAUDE.md` "Tool Routing" bundle paragraphs (`iwe find`/`retrieve`, deprecated-filter guidance) | one line: the bundle reaches a run through `notion-dev:knowledge retrieve`; do not query it again |
| `.claude/commands/maintain.md` step 13 and `release.md` step 10: the 4096-byte cap and `iwe extract` instructions | "write the concept, then `knowledge.py check`"; those steps keep writing `node/` and `release/` concepts, declared in `extraTypes: ["commitment", "node"]` |
| `.claude/notion-dev.config.json`: `postMergeHooks: ["knowledge-capture"]` | `["notion-dev:knowledge"]`, plus the `knowledge` block |
| `knowledge/ticket/STO-67.md` stays; it is the epic's `Ticket` concept (its `# Ruled out` has no home in the brief template) and the new `epic/STO-67-…` root links it under `## Decisions & constraints` | — |
| `scripts/knowledge/mail-extract.js` stays (dream input, client-side by decision 2) | — |

**smart-contracts-foundry** (`~/dev/oinc/LAST/smart-contracts-foundry`, epic STO-306):

| remove | replaced by |
|---|---|
| `.claude/skills/knowledge-capture/`, `.claude/skills/knowledge-curate/` | `capture` via the hook; `curate` |
| `scripts/knowledge/okf.py` | `knowledge.py`; before deletion the three helpers `mirror.py` imports (`notion_page_id`, `source_class`, `registry_problem`/`load_registry`) are inlined into `mirror.py`, which stays by decision 2 |
| `scripts/hooks/pre-commit` `okf.py validate` call; `Makefile` targets `knowledge`, `knowledge-stale`, `knowledge-reconcile` | pre-commit and `make knowledge` run the fetched `knowledge.py check`; the stale and reconcile targets have no successor by decision 6; `knowledge-mirror` stays |
| `.github/workflows/knowledge-sweep.yml` `sweep` job (weekly cron, issue-opening) and every `okf.py` line | the `validate` job on the fetched script; `mirror.py status/check` may keep a schedule if wanted, as client-only tooling |
| `knowledge/.okf/schema.yaml` | the shipped `.iwe/schemas/okf.yaml`; the shipped schema permits additional frontmatter fields, so `sources[].author`, `sources[].last_modified`, `applies_to`, `open_questions` remain valid; `knowledge/.okf/sources.yaml` stays as `mirror.py`'s registry |
| `CLAUDE.md` "## Knowledge Bundle" section and the `okf.py query` instruction | the same one line as BTC-Gateway |
| `knowledge/index.md` "Optional: query over MCP" section | deleted; the plugin reads through the CLI |
| `.claude/notion-dev.config.json`: `postMergeHooks: ["knowledge-capture"]` | `["notion-dev:knowledge"]`, plus the `knowledge` block (`extraTypes: []`) |
| `docs/sto-306-completion-plan.md` | untouched here; `next-task`'s bootstrap distils it into `epic/` and removes the seed, as today |

**Order.** Plugin PR merges and is tagged → client updates the plugin → `migrate --dry-run`
reviewed → `migrate --apply` → removals above → `knowledge.py check` exits 0 and the client's
own suite passes → PR through the client's normal flow → one real post-merge capture observed
on the next ticket. Each client is one session and one PR.

## Out of scope

Notion/Slack mirroring and source allowlists; verbatim records; transcript or mail inputs;
embeddings or any search beyond iwe's; a scheduled sweep; editing Notion pages from the bundle.
The client PRs are planned here (§7, §11, §13) and executed in their own sessions.
