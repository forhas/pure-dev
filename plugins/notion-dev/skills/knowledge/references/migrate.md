Read `common.md` once per invocation. Other operations are not prerequisites.

## `migrate [--apply]`

Once per client, through `/notion-dev:knowledge migrate [--apply]`.
Without `--apply` it prints the complete diff and writes nothing.

1. **Preconditions.** The primary on `<epicBranch>`, a clean tree, `iwe` and `<knowledge.python>` present —
   the command's precondition block, which is where a missing binary is reported.
2. **Install the plugin-owned files.** `.iwe/config.toml` and `.iwe/schemas/` are copied from
   `${CLAUDE_PLUGIN_ROOT}/skills/knowledge/references/iwe/`, overwriting whatever the client had:
   a bundle cannot silently loosen the schema it is checked against.
3. **Rewrite every concept** under `<knowledge.dir>` outside dot-directories: map the `current`
   status — one client's local vocabulary — to `stable`; drop `stale_after`, `reconciled`,
   `verified` and `vouch`, **each together with its wrapped or nested continuation lines**, since
   a key dropped one physical line at a time leaves an orphan that costs the document its whole
   frontmatter; normalise a `superseded_by` written from the repo root so it reads from the
   bundle root; add `sources` when missing, from a ticket or PR reference in the body, else
   `{ id: migrated, resource: <own path> }` with `status: draft`; collect any
   `## Reconciliation notes` under `## Updates`. Every other field and all prose are left alone,
   and a CRLF or BOM-prefixed concept is migrated like any other — the output is always `\n`.
   Reshape `log.md` to the shipped `okf-log.yaml` form (one title section, `## YYYY-MM-DD` groups
   newest first, bullets only) and `index.md` to `okf-index.yaml` (sections of link bullets only)
   — both clients' logs fail that schema today. **The reshape reshapes; it never deletes.** Every
   log line survives: a dated heading keeps its title as the group's first bullet, a wrapped
   bullet keeps its continuation, a sub-section the log schema's depth limit forbids becomes a
   bullet of its own, and a log with no dated content at all is left exactly as it was rather
   than emitted empty. The index drops a section that ends up with no bullets — the shipped
   schema rejects one — and gains a bullet for every `stable` concept the client never
   catalogued, because `check` requires one. A bundle with no `index.md` or `log.md` is given the
   same seed `/notion-dev:init` writes.
4. **Move the brief.** `docs/epics/<KEY>-<n>-<slug>.md`, or whatever `epicDocs.dir` named, moves
   to `<knowledge.dir>/epic/` with the `type: Epic` frontmatter added — `status: stable`, since
   `retrieve` seeds on this document under `--filter 'status: stable'`, citing the Notion URL on
   its own `Epic:` header line. **`epicDocs.dir` is optional**: absent, the documented default
   `docs/epics` is used, and a move that finds nothing to move says so in a `note:` line rather
   than passing silently. A hand-written seed plan is left where it is, for `next-task`'s
   bootstrap, which now writes into `epic/`.
5. **Rewrite the links the moves broke** — in Python, relative to each linking file: every
   relative link inside the moved brief recomputed for its new depth, and every tracked `*.md`
   outside the bundle that pointed at the old brief path repointed. No relative link is repaired
   by hand, and no fifth iwe subcommand is involved.
6. **Config.** Drop `epicDocs` from `.claude/notion-dev.config.json`, add the `knowledge` block
   with `dir` and with `extraTypes` set to the non-canonical directories found — `dir` because a
   config that omits it silently points `check` at the default bundle path — carrying through any
   `retrieveBudget` or `warnBytes` the client had already set, and replace the client's own
   `postMergeHooks` entry with `notion-dev:knowledge`.
7. **Check the result:**

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" check --dir <knowledge.dir> \
     --plugin-root "${CLAUDE_PLUGIN_ROOT}" \
     --extra-types <the extraTypes step 6 wrote, joined with commas> \
     --warn-bytes <knowledge.warnBytes>
   ```

   Non-zero under `--apply` → revert everything this operation wrote, restoring the bundle to the
   state it started from, and report the findings. The migration is all-or-nothing.
8. **Print the removal checklist** for this client, derived from what step 3 found: the skill
   directory the old hook entry named, every script under `scripts/knowledge/`, every workflow and
   Makefile target that invokes one, and the CLAUDE.md lines that route to them. This operation
   **never deletes client code** — the client's own migration PR does, pasting this checklist into
   its body with each line ticked and, for every retired check, the `check` rule that covers it
   now.

The invocation is one call:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" migrate [--apply] --dir <knowledge.dir> \
  --config .claude/notion-dev.config.json --plugin-root "${CLAUDE_PLUGIN_ROOT}"
```

Step 8 is this skill's work over what the script reports; steps 2 through 7 are the script's.
Returns `capture`'s output block with `COMMIT: none` — `migrate` stages nothing and commits
nothing; the client's migration PR carries the diff.
