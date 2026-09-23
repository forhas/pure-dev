# knowledge

One OKF v0.2 bundle per repo, owned by this skill: one fact per file, the epic brief as the
bundle's root concept, and exactly one read path into a run. Every operation is **best-effort**
in the `epic-update` sense — a failure never fails the caller's run, never blocks a merge or a
resolution, and is always stated in the caller's final report.

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

**Config.** The `knowledge` block of `.claude/notion-dev.config.json`:

- `dir` — the bundle root, default `knowledge`, carrying the path pattern `epicDocs.dir` had
  (relative, forward slashes, no `..`).
- `retrieveBudget` — the read-time token budget, integer ≥ 1000, default 8000.
- `warnBytes` — the per-concept size above which `check` warns; it never fails, default 8192.
- `extraTypes` — client type directories `check` accepts beyond the canonical set, for example
  `["commitment", "node"]`. Dot-directories (`.mirror/`, `.record/`, `.okf/`) are ignored entirely.

**Branch.** The bundle lives on the branch pull requests merge into — `git.prTargetBranch`,
falling back to `git.baseBranch` — called `<epicBranch>` below, the one name `epic-doc` gives it.
Every read, every commit and every push here uses that one branch. `<baseRefName>`, in the hook
lines `capture` quotes from `/notion-dev:ticket`, is the same branch: `epic-doc record` fails the
run when a PR merged anywhere else.

**Read once.** Each fact enters a run exactly once. The bundle arrives as `KNOWLEDGE_CONTEXT`
from one `retrieve` before any worktree exists, and nothing downstream reads it again: no second
search, no catalog read, no recursive grep over the tree, and never the Notion epic page for what
the brief already holds. The table under `retrieve` is that rule in full, and it is the reason a
caller that already holds `KNOWLEDGE_CONTEXT` passes it in instead of triggering a second fetch.

**Dependencies.** `iwe` ≥ 0.19 on `PATH`, probed at each command's preconditions with
`iwe --version`. Missing or older → the precondition message names both install routes:
`cargo install iwe --root ~/.local` (works wherever Rust does; required on hosts whose GLIBC is
older than 2.39, which includes Ubuntu 22.04 under WSL), and `brew install iwe` /
`npm i -g @iwe-org/iwe` where the prebuilt binary runs. The signature is
`missing-dependency:iwe`. Nothing here depends on the LSP (`iwes`) or the MCP server (`iwec`).
`python3` in every `knowledge.py` line below stands for `knowledge.python` from `$REPO_ROOT/.claude/notion-dev.config.json` (default `python3`; `python` or `py -3` on Windows, as `/notion-dev:init` recorded).
`<knowledge.python>` on `PATH` (default `python3`; `python` or `py -3` on Windows) runs
`${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py` — standard library only, no `pip` step.

**This skill and `scripts/knowledge.py` are the plugin's only iwe callers.** The skill touches
`iwe retrieve`, `iwe find` and `iwe stats similarity`; the script touches `iwe find -f json`
for frontmatter and `iwe schema validate` for shape — four subcommands in all, and no fifth.
Link rewriting on migration is Python in the script, not an iwe subcommand. No command, no
other skill invokes the binary, so the dependency can be swapped by editing one skill and one
script.

## Failure handling

Every operation is best-effort against the ticket flow, and the two directions are not symmetric:
**fail closed on checks, degrade on reads.** A check that fails or cannot run means nothing is
written. A read that fails serves the brief alone and lets the run continue — the ticket body,
not the bundle, is what the work is built from.

Signatures, recorded through `notion-dev:issue-log` at the moment they happen; failing to write
the log never fails the run:

- `partial:knowledge-retrieve` — `iwe` missing or `retrieve` failed; the brief was served alone.
- `partial:knowledge-capture` — `check` failed or the push was rejected; nothing was written, or
  a commit is unpushed.
- `missing-dependency:iwe` — `iwe` absent or below 0.19, at the three places that probe for it:
  `/notion-dev:knowledge`'s preconditions, `/notion-dev:new-info`'s preconditions, and
  `/notion-dev:init`'s preflight. `/notion-dev:ticket` and `/notion-dev:next-task` do not probe —
  they reach the bundle only through `retrieve`, which degrades with `partial:knowledge-retrieve`
  and lets the run continue, so a probe there would abort a run that has no need to stop.
