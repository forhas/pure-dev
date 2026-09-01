# pure-dev

This repository ships two Claude Code plugins — `plugins/quick-dev` and `plugins/notion-dev` —
that are **markdown instruction files, not code**. Nothing here executes. That shapes everything
below.

## The test suite is `scripts/verify-*.sh`

`.github/workflows/verify.yml` discovers them by glob, so a new harness needs no workflow edit.
Run **all** of them before reporting any work as done:

```bash
for h in scripts/verify-*.sh; do "$h" || echo "FAILED: $h"; done
```

Every assertion comes from `scripts/lib/assert.sh`. Never hand-roll one in a harness —
`verify-assertions.sh` fails a harness that sources anything else or defines its own helper, and
that library is where the traps below are already handled.

Harness rules, learned the hard way:

- **Assert the invariant, not the prose.** Grep for the mechanism — command strings, the relative
  order of step lines, the presence of each assertion — never a whole sentence. A harness keyed on
  wording breaks on the next edit and trains people to fix the harness instead of the defect.
  Where prose must be matched, match the shortest distinctive fragment — and remember these
  files are hard-wrapped, so a phrase spanning a line break can never match a line-based grep.
- **An anchor names one place.** `assert_present` requires its regex to match **exactly one** line
  in its region; a second match means the anchor is not pinning the place its label claims. Three
  of the four defects issue #30 was filed for were this. When a document cites the same mechanism
  twice on purpose, say so with `assert_count … <n>` — that is not an allowlist, because it is
  re-checked in both directions on every run and goes red when the document stops.
- **The label is a claim the regex has to honour.** Whatever the label names — a backticked
  literal, an ALL-CAPS key, a `--flag`, a `<placeholder>`, a capitalised mechanism name — must
  appear in the regex whenever the matched line says it too. The fourth #30 defect matched exactly
  one line and still checked less than its label promised.
- **Two silent traps in these harnesses**, both of which produce an assertion that *passes*
  rather than one that errors: `awk -v` performs escape processing, so a written `\|` reaches the
  matcher as bare alternation matching every line (the library passes regexes through `ENVIRON`
  instead, and `verify-assertions.sh` proves it still does); and a hard-wrapped phrase never
  matches. Neither is visible by reading.
- **Prove every check can fail.** Break the file it guards, confirm `FAIL`, restore. Commit your
  own work *before* mutation-testing: a `git checkout -- .` to undo mutations will otherwise
  silently revert it. A harness that passes against a broken file is worse than none. The library's
  own checks are proven both directions on every run by `verify-assertions.sh`, so that discipline
  is mechanical for them; for a new assertion of your own it is still yours to do.

Prefer the standing-invariant model (`verify-mirror.sh`) over change-scoped harnesses with version
floors (`verify-completeness.sh`, `verify-convergence.sh`) — floors rot, invariants do not.

## The `.claude/skills/` mirror

Every directory under `.claude/skills/` is a byte-identical mirror of the same-named directory
under `plugins/quick-dev/skills/`, so this repo drives its own work with the skills it ships.
Edit the plugin copy, then re-sync:

```bash
cp -r plugins/quick-dev/skills/<skill>/. .claude/skills/<skill>/
```

`scripts/verify-mirror.sh` enforces this and discovers the mirror set automatically. It has caught
real drift more than once; do not treat it as a formality.

`plugins/notion-dev` vendors adapted copies of several `quick-dev` skills. They are deliberate
forks, not mirrors — when you change shared behaviour, change both and check the wording that
differs (plugin names, config paths, reviewer defaults).

## Convergence — optimize for time-to-done, not for PR count

**One pull request per session is the default.** Every extra PR pays a whole `review-and-merge`
cycle: its own reviewer trigger, its own multi-minute latency, its own merge and cleanup. That
cycle, not the writing, is the dominant cost of finishing. Splitting requires a *technical*
reason — a dependency that must merge first, a release boundary, or work the user asked to keep
separate. A preference for small diffs is not one.

**Do not file what you are about to fix.** A `file` disposition costs a full extra cycle when the
same session then works the item. This is not hypothetical: PR #24's loop filed three issues, one
of them inside a file that PR had itself created, and two were worked as PR #28 minutes later.
`review-and-merge`'s **final sweep** exists to take that work back before the merge — let it.

**Widening a PR is cheaper than splitting it.** "It touches a file this PR wasn't already
changing" is explicitly *not* a reason to defer a small fix. Take it, and say in the PR body that
the scope widened and why.

## Zero tails

**Invoke the `session-closeout` skill before reporting any session as finished.** Not as a
formality — it queries git and `gh` for loose ends instead of trusting recall, and forces each one
into `resolved`, `tracked: <url>`, or `blocked: <external cause>`. There is no fourth state.

If you are about to write "one thing left", "worth flagging", "remaining open", "one honest
note", or "for a follow-up", the session is not finished. Resolve the item; do not reword the
sentence.

## Versions

Both plugins carry `.claude-plugin/plugin.json`. Bump the manifest `version` **exactly once per
PR**, per the policy in `plugins/quick-dev/skills/develop/SKILL.md`: breaking → major, new
capability → minor, fix/docs/refactor/internal-only → patch. Never merge a plugin PR whose version
equals the base's.
