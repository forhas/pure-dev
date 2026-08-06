# Project-local skill copies — mirroring rule

`review-and-merge/` here is a **verbatim mirror** of
`plugins/quick-dev/skills/review-and-merge/`. It exists so this repository can drive its own
PRs with the same loop it ships, and it is tracked (not gitignored) so it cannot drift
unnoticed the way it did before — at one point it had diverged 167 diff lines from the plugin,
still hard-coding a Codex-only workflow and a 10-round cap while the plugin had gained the
configurable reviewer, `reviewsCap`, and the Copilot fixes.

**When you change `plugins/quick-dev/skills/review-and-merge/`, re-sync this copy in the same
commit:**

```bash
cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/
# keep this README; it has no counterpart in the plugin
diff -r --exclude=README.md plugins/quick-dev/skills/review-and-merge/ .claude/skills/review-and-merge/
```

The `diff` must be empty. Any intentional divergence belongs in the plugin, not here — a
project-local fork is invisible to everyone who installs the plugin.

Note `.gitignore` keeps `.claude/*` ignored with a `!.claude/skills/` negation, so local
session state (`settings.local.json`, etc.) stays untracked while these skills are versioned.
