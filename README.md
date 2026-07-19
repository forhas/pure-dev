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

## Repository layout

```
.claude-plugin/marketplace.json   # marketplace manifest
plugins/
  quick-dev/                      # plugin: skills only
  notion-dev/                     # plugin: commands + skills + config schema
```

## License

MIT — see each plugin's LICENSE file.
