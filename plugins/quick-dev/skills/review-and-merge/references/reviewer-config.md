# Reviewer configuration

quick-dev's GitHub-mode review loop drives a configurable reviewer: `codex` (default) or
`copilot`. The choice is stored per-clone in a gitignored config file and resolved by the
procedure below.

## Config file

- **Path:** `<primary-checkout>/.claude/quick-dev/config.json`
- **Shape:** an object with a `reviewer` key (`"codex"` or `"copilot"`) and an optional
  hand-edited `reviewsCap` key (integer ≥ 1, default 15 — see the review loop's round cap):
  `{ "reviewer": "codex", "reviewsCap": 15 }`. Other keys may exist; treat the file as
  extensible, never as reviewer-only.
- **Tracking:** gitignored, in the primary checkout only (never a feature worktree). It shares
  the self-ignored `.claude/quick-dev/` directory used by the ledger, so it never appears in
  `git status`, is never swept by `git add -A`, and is never committed.

## Reviewer resolution procedure

Run this wherever the reviewer must be known.

1. **Resolve the primary checkout root** — `REPO_ROOT` = the path on the first `worktree ` line
   of `git worktree list --porcelain` (the `--porcelain` form prints `worktree <path>` on its
   own line, so it is unambiguous even when the path contains spaces; the plain `git worktree
   list` columns are not). This is correct whether the caller sits in the primary checkout or in
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
4. **Persist** the resolved value into `REPO_ROOT/.claude/quick-dev/config.json` as a
   **read-modify-write**: read the existing JSON if the file is present, set `reviewer` to the
   resolved value, and write the whole object back, **preserving every other key** — notably a
   hand-edited `reviewsCap`, which a blind overwrite would silently delete. If the file is
   absent, unparseable, or does not parse to a JSON object (e.g. an array or a bare value),
   write `{ "reviewer": "<value>" }`. Ensure the self-ignored directory exists first:
   ```bash
   # self-ignore bootstrap — the ledger's pattern, adapted to target the primary checkout ($REPO_ROOT) rather than the current directory:
   mkdir -p "$REPO_ROOT/.claude/quick-dev" && { [ -f "$REPO_ROOT/.claude/quick-dev/.gitignore" ] || printf '*\n' > "$REPO_ROOT/.claude/quick-dev/.gitignore"; }
   # then read $REPO_ROOT/.claude/quick-dev/config.json (if any), set "reviewer":"<value>",
   # and write the merged object back — every other key preserved
   ```
   The write is side-effect-free with respect to git: the file is gitignored, so it never
   dirties the tree, never enters `git add -A`, and never diverges the base branch.

**Skip conditions:** only run this procedure in **GitHub mode**. In local mode there is no
GitHub reviewer (Codex app / Copilot) — the local fresh-agent reviewer is always used and no
reviewer config is read or written.
