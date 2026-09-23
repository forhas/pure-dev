Read `common.md` once per invocation. Other operations are not prerequisites.

## `curate`

Dedupe only, user-invoked through `/notion-dev:knowledge curate`. Nothing runs on a schedule and
nothing here reads Notion.

1. Run the check:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/knowledge.py" check --dir <knowledge.dir> \
     --plugin-root "${CLAUDE_PLUGIN_ROOT}" \
     --extra-types <knowledge.extraTypes joined with commas> \
     --warn-bytes <knowledge.warnBytes>
   ```

   The same four flags `capture` step 6 passes, comma-joined the same way: a client with
   `extraTypes` gets a finding its bundle does not have when they are left off.
   Non-zero → stop and print the findings; a bundle that fails its own rules is not one to merge
   concepts in.
2. `iwe stats similarity -t <threshold>` directly — text output, one pair per line; the script
   wraps nothing here because the command has no structured output. `<threshold>` starts at `0.8`
   and is lowered only when the user asks for a wider net.
3. Present each cluster with both bodies side by side and let the user name the survivor, or
   `keep both`. `keep both` is a real answer: two concepts that read alike may hold two facts.
4. The loser is superseded exactly as `capture` step 3 supersedes — `status: deprecated`,
   `superseded_by`, one dated line — and its links are left pointing at a live successor.
5. Index, log, check again, then commit `docs(knowledge): curate — <n> clusters resolved` by
   pathspec and push, as `capture` step 6 does, through the same five steps. Returns `capture`'s
   output block, with `SUPERSEDED` naming each resolved cluster.
