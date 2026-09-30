# pure-dev

A [Claude Code plugin marketplace](https://docs.claude.com/en/docs/claude-code/plugin-marketplaces) hosting opinionated, end-to-end development flows.

## Plugins

| Plugin | What it does |
|---|---|
| [`quick-dev`](plugins/quick-dev/) | One-command feature development. `/quick-dev:develop <description>` takes a feature from a single sentence to a squash-merged commit on main — built in an isolated git worktree, driven through a PR review loop, then fully cleaned up. |
| [`notion-dev`](plugins/notion-dev/) | Standardized development workflow with Notion-backed tickets: `create-task` → `ticket` → `finalize`, with pluggable input sources, dual build flows (feature-dev / superpowers), and a Codex-with-local-fallback review loop. |

Each plugin's README covers its prerequisites, configuration, and usage in detail.

## Install

Inside Claude Code:

```
/plugin marketplace add forhas/pure-dev
/plugin install quick-dev@pure-dev
/plugin install notion-dev@pure-dev
```

Or from a local clone:

```
/plugin marketplace add /absolute/path/to/pure-dev
```

Run `/reload-plugins` (or restart Claude Code) after installing.

## notion-dev release tags

After a version-bumping push to `main`, the existing verification workflow publishes
an annotated `notion-dev-v<version>` tag only after Ubuntu, Windows Git Bash and
Python 3.8 checks pass. The tag identifies the exact tested push SHA, not a later
`main` tip. PR runs never publish tags; only the tagging job has write permission.

Rerunning a successful release is safe: an existing tag at the same commit is a
no-op; a conflicting tag fails and is never moved. A push with no notion-dev changes
does not create a tag. Changed plugin files require a version bump; versions must
increase. A batched push tags its final verified version, not intermediate commits.
The helper requires available history and a normal ancestor-to-descendant push;
missing history or a force-push boundary fails closed. Retry a failed tagging job
using the original Actions run after correcting permissions/connectivity.

Clients should use a full commit SHA to fetch code and a separate `PLUGIN_VERSION`
label. Tags provide discoverability; they do not replace immutable SHA pins.
Verify the fetched plugin manifest matches the expected version. No GitHub Release
objects or automatic client upgrades are created by this workflow.

The missing historical versions are not automatically backfilled. This automation
starts with 0.45.2; 0.45.1 was restored at `0c06798` after its
[merged-commit CI passed](https://github.com/forhas/pure-dev/actions/runs/36586450346).

Workflow gating follows GitHub's [job dependencies and permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

## Repository layout

```
.claude-plugin/marketplace.json   # marketplace manifest
plugins/
  quick-dev/                      # plugin: skills only
  notion-dev/                     # plugin: commands + skills + config schema
```

## License

MIT — see each plugin's LICENSE file.
