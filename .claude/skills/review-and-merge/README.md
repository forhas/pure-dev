# Project-local skill copies — mirroring rule

`review-and-merge/` here is a **verbatim mirror** of
`plugins/quick-dev/skills/review-and-merge/`. It exists so this repository can drive its own
PRs with the same loop it ships.

**When you change `plugins/quick-dev/skills/review-and-merge/`, re-sync this copy in the same
commit:**

```bash
cp -r plugins/quick-dev/skills/review-and-merge/. .claude/skills/review-and-merge/
# keep this README; it has no counterpart in the plugin
./scripts/verify-mirror.sh
```

Any intentional divergence belongs in the plugin, not here — a project-local fork is invisible
to everyone who installs the plugin. `verify-mirror.sh` checks that direction too: a file
present here but absent from the plugin fails.

## Not every directory here is a mirror

`.claude/skills/REPO-LOCAL` declares the directories that are **not** mirrors — maintainer
workflows belonging to neither shipped plugin. They are exempt from parity and from nothing
else; `verify-mirror.sh` still requires them to be tracked, to exist, and to have no plugin
counterpart. A directory in neither set fails.

## Why this is a script and not a rule

This file used to say the mirror was tracked "so it cannot drift unnoticed", and asked
contributors to re-sync in the same commit. It drifted anyway — 167 lines the first time,
then 183 more after the rule was written. Two different prose mechanisms, both ignored, which
is what a claim with nothing enforcing it does.

`scripts/verify-mirror.sh` is the mechanism. `.github/workflows/verify.yml` runs it, and every
other `scripts/verify-*.sh`, on each pull request — so a drifted mirror now fails a check
instead of waiting to be noticed.

Note `.gitignore` keeps `.claude/*` ignored with a `!.claude/skills/` negation, so local
session state (`settings.local.json`, etc.) stays untracked while these skills are versioned.
