# Live build-flow dependencies

Read once at command preflight. The **current host's available skills are authoritative**;
`dependencies.{superpowers,featureDev}` in notion-dev config are cached setup hints, not
permission or availability gates. Do not send skill bodies to this probe or to children.

For `ticket`, `next-task`, and `init`, require these exact live skill names:
`superpowers:writing-plans`, `superpowers:subagent-driven-development`,
`superpowers:receiving-code-review`, and `feature-dev:feature-dev`.
`finalize` and `new-info --pr` use mode `review`, requiring only `superpowers:receiving-code-review`.
An installed plugin or files in a plugin cache do not prove the host loaded its skills.
If the host cannot expose availability, stop with that uncertainty; do not guess names.

Write the observed names as a JSON array in a local temporary file outside the ticket
worktree. With `python3` meaning the configured `knowledge.python` (including `python`
or `py -3` on Windows), run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dependencies.py" --project "$REPO_ROOT" --live-skills <observed-skills.json> --mode ticket
```

The helper is read-only. Exit 0 means all required skills are live, 1 means skills are
missing, 2 means invalid/unreadable diagnostic input. It reads only dependency hints
and `enabledPlugins` from settings; it never returns permissions or other settings.
No Notion/GitHub writes, installation, enablement, config refresh, or child dispatch.
Init uses its probed interpreter; if none exists, apply these same checks manually
without changing init's existing missing-Python policy.

Report a mismatch **once per command**, naming cached values, actual missing skills,
and any relevant settings paths/values. A false/missing cached hint with live skills
does not abort or force init. A true hint with missing skills does not permit a build.
A live skill with a disabled setting may reflect a pending reload: surface both rather
than silently changing the setting. Recheck live availability immediately before use
if the host reloads plugins during the run.

## Missing skills: diagnose before installing

Default diagnostic precedence is user settings (`CLAUDE_CONFIG_DIR/settings.json`, or
`~/.claude/settings.json`), project `.claude/settings.json`, then
`.claude/settings.local.json`. A local `false` overrides a project `true`. Diagnose
superpowers and feature-dev identically. Preserve marketplace-qualified plugin IDs;
if multiple IDs conflict, inspect which plugin the host actually loaded.

These files do **not** model managed/session overrides or every host worktree setting.
Use the host's `/status` and `/plugin` views when the source is unclear. If its effective
files differ, pass each actual path with repeated `--settings` flags in low-to-high
precedence order (this replaces the helper's defaults). Config remains rooted at the
primary checkout. Do not infer absence of installation from missing live skills.

- **Disabled in an effective scope:** stop and identify the exact `enabledPlugins` key
  and file. Ask the user to enable the intended plugin in that scope, then
  `/reload-plugins` and retry. **Never reinstall over an explicit `false`**, auto-enable
  it, or rewrite user/local/managed settings to defeat it.
- **Installed but not loaded:** report the host's load error if available; request
  reload/repair. Do not enter an install/reload loop.
- **Confirmed not installed:** `init` may install at project scope using its documented
  install-and-reload branch. Other commands stop and direct the user to init.
- **Unknown cause or invalid diagnostic JSON:** report the uncertainty/error and the
  settings path without dumping unrelated settings; stop, do not install speculatively.

Batch all missing-plugin diagnoses into one stop. A `next-task` delegate still checks
its own live skills before side effects; it need not reload full skill instructions to
check names. Never pass this command's catalog as proof of a different agent's catalog.

Host behavior references: [settings scopes and precedence](https://code.claude.com/docs/en/settings)
and [plugin management](https://code.claude.com/docs/en/discover-plugins). The helper
deliberately diagnoses files rather than claiming to reimplement the host's resolver.
