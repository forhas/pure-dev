Run an empirical test of Notion self-referential relation behavior and report the results.
Do not fix anything. Do not modify the notion-dev plugin or its config. Observe and report only.

## Why

notion-dev's `setDependencies` used to write a self-referential Relation to express
"A depends on B". A client reported the relation is symmetric — every write also created
the reverse edge — so direction could not be represented. That path was removed in 0.10.0.

`parentTaskProperty` (epic containment) is the SAME construct and was deliberately left
unchanged pending this test. If single-column self-relations are symmetric in general, then
`findEpics` has a latent bug: it selects epics whose own `parentTaskProperty` is EMPTY, so an
epic would silently vanish from discovery the moment it gains its first child.

This test decides whether that bug is real.

## Hard rules

1. **Never write to the configured tickets database.** Test A is strictly read-only against it.
   All writes go to a throwaway database you create.
2. **Never run `/notion-dev:init`** — it would rewrite the project config.
3. **Record the scratch database id the instant you create it**, before anything else, so
   cleanup can run even if a later step fails.
4. **Cleanup is mandatory and runs even on failure or interruption.** If you cannot complete
   the tests, still clean up, then report what you managed to observe.

---

## Test A — read-only, against the real tickets DB (do this first)

This directly answers whether the bug is live in production. No writes.

1. Read `.claude/notion-dev.config.json` for `ticketSystem.databaseId` / `dataSourceId`, and the
   configured `parentTaskProperty` (default `"Parent task"`) and `epicMarkerProperty`
   (default `"Is Epic"`).
2. Fetch the database schema. Report the `parentTaskProperty` column's exact type, and — this is
   the key detail — whether the schema contains **one** self-referential relation column or a
   **pair** (e.g. `Parent item` + `Sub-item`, which is Notion's native Sub-items and IS directional).
3. Query for pages where `epicMarkerProperty` is true. For each epic found, report:
   - its title
   - whether its OWN `parentTaskProperty` is empty or populated
   - if populated, how many entries and whether those entries are its children
4. Separately, query for pages whose `parentTaskProperty` contains one of those epics (i.e. real
   children). Confirm at least one epic in your list actually has children.

**Interpretation — state this explicitly in your report:**
- An epic that HAS children but whose own `parentTaskProperty` is EMPTY → directional. No bug.
- An epic that has children AND whose own `parentTaskProperty` lists those children → symmetric.
  The bug is live: that epic is already invisible to `findEpics`.
- If no epic has any children yet, say so — the test is inconclusive from this DB alone,
  and Tests B/C carry the whole answer.

---

## Test B — API-created one-way self-relation (the decisive mechanism test)

This is the exact code path `/notion-dev:init` takes when a user picks
"Create `Parent task` (Relation)", so it is the branch that matters.

1. Create a scratch database titled `ZZTEST-selfrel-<today's date>`. Put it wherever the
   integration can write — a private page is ideal. **Record its id and data source id now.**
2. Add a self-referential relation property `RelOneWay` via a schema update pointing the
   relation at the scratch database itself. Use the **one-way** form —
   `single_property` in the API (`{"type":"relation","relation":{"data_source_id":"<self>",
   "type":"single_property","single_property":{}}}`; adapt if the MCP tool's shape differs).
   A self-relation cannot be declared at creation time because the database's own id does not
   exist yet — that ordering constraint is itself part of what we are testing.
3. **Immediately re-read the schema.** Report every property now present. Did adding `RelOneWay`
   create ONE column, or did Notion also add a second synced column?
4. Create two rows, `A` and `B`.
5. Set `A.RelOneWay = [B]`.
6. Re-fetch **B** and report the literal contents of `B.RelOneWay`.

**This is the decisive question: does `B.RelOneWay` contain `A`?**

---

## Test C — two-way self-relation

1. In the same scratch DB, add `RelTwoWay` as a **two-way** self-relation
   (`dual_property`).
2. Re-read the schema. Report whether Notion created a second, synced column, and its exact name.
3. Set `A.RelTwoWay = [B]`.
4. Re-fetch B. Report where the reverse edge landed: in the synced companion column, or in
   `RelTwoWay` itself?

---

## Test D — native Sub-items (needs a human; skip if you cannot)

Sub-items cannot be enabled through the API. If you can drive the UI, do it; otherwise mark
this SKIPPED and say why — do not guess or infer the answer.

1. Enable Sub-items on the scratch DB (⋯ → Customize → Sub-items).
2. Report how many columns it added and their names.
3. Set `A`'s Sub-item to `B`. Check that `B`'s Parent item is `A` **and** that `B`'s Sub-item
   is EMPTY.

---

## Cleanup — mandatory

1. Archive (move to trash) the scratch database and every page in it.
2. **Verify** by re-fetching the scratch database id and confirming it reads as archived/in-trash.
   Do not claim cleanup succeeded without this check.
3. Confirm explicitly that you made **zero writes** to the real tickets database.
4. Note that the Notion API can only move items to trash, not purge them. Tell the user the
   scratch DB is in Notion's trash and can be permanently deleted from the UI if they want.

If any cleanup step fails, say so loudly and report the exact database id left behind so it can
be removed by hand. Never report a clean state you did not verify.

---

## Report format

```
TEST A (real DB, read-only)
  parentTaskProperty type:     <type>
  relation columns in schema:  <one column | pair: name1 + name2>
  epics found:                 <n>
  epics with children:         <n>
  epic own-parent populated:   <yes/no, with an example>
  VERDICT:                     <directional | symmetric | inconclusive>

TEST B (API single_property)
  columns after adding:        <one | two: names>
  B.RelOneWay contains A:      <YES | NO>
  VERDICT:                     <symmetric | directional>

TEST C (dual_property)
  columns after adding:        <one | two: names>
  reverse edge landed in:      <companion column | same column>

TEST D (Sub-items)
  <result | SKIPPED: reason>

CLEANUP
  scratch db id:               <id>
  archived and verified:       <YES | NO — details>
  writes to real tickets DB:   <NONE | details>
```

Report exactly what you observed. If a result contradicts what this prompt led you to expect,
say so plainly — a surprising result is the most valuable outcome here.
