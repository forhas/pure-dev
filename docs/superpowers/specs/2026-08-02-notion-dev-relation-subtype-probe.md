Determine whether Notion relation **subtype** (one-way vs two-way) is detectable through the
available API surface, and whether a two-way relation reproduces the reverse-edge report that
started this work. Read-only against the real tickets DB; all writes go to a throwaway database.

Do not change the plugin, its config, or anything in the real database. Observe and report.

## Why this matters

notion-dev 0.11.0 removed `dependsOnProperty` and justifies it with this claim:

> The adapter cannot tell a one-way relation from a two-way one — the Notion MCP schema surface
> does not expose a relation's subtype.

> **OUTCOME (recorded after this probe ran): the claim above was DISPROVEN.** `propertyUrl` does
> reveal subtype — absent on every `single_property` relation, present on every `dual_property`
> half. But it reports how a column was *created*, not how a write to it will *behave*: an
> orphaned two-way half keeps `propertyUrl` and behaves one-way. See the "Second falsification"
> and "Third falsification" sections of `2026-08-02-notion-dev-dependency-direction-design.md`.
> This file is retained as the test protocol, not as an open question.

**That claim is load-bearing and under-evidenced.** It came from one agent noticing that a
`propertyUrl` field was absent on a scratch `single_property` column and present on both halves
of a `dual_property` pair. Nobody has dumped a complete relation property definition to check
whether subtype is exposed directly, and nobody has tested whether `propertyUrl` behaves as a
subtype signal or is incidental.

Two outcomes, both useful:

- **Subtype IS detectable** → 0.11.0's stated rationale is wrong and must be corrected (for the
  second time), and restoring `dependsOnProperty` behind a subtype guard becomes a real option.
- **Subtype is NOT detectable** → the rationale is confirmed by deliberate evidence instead of
  an incidental observation, and the door stays shut for a reason that will hold up.

A separate question rides along: the original reverse-edge report is still unexplained. The
leading lead is that the client's `Depends on` was a two-way relation whose companion-column
edges were misread as symmetry. Test 3 reproduces that directly.

## Hard rules

1. **Never write to the real tickets database.** Test 4 is strictly read-only.
2. **Record the scratch database id the instant you create it**, before anything else.
3. **Cleanup is mandatory and runs even on failure or interruption.**
4. Report raw field names and values verbatim. Do not normalize, summarize, or omit fields you
   judge irrelevant — the whole point is finding a field nobody thought to look for.

---

## Test 1 — Full schema dump (the decisive test)

1. Create a scratch database `ZZTEST-subtype-<date>`. **Record its id and data source id now.**
2. Add four self-referential relations via schema update, so subtype and name vary independently:
   - `OneWayA` — `single_property`
   - `OneWayB` — `single_property`
   - `TwoWayA` — `dual_property`
   - `TwoWayB` — `dual_property`
3. **Dump the complete, unfiltered property definition for every property in the database.** Not
   a summary — every key and value the API returns for each one, including any companion columns
   Notion created on its own.
4. Compare the four relations field by field. Report **any** field that separates the two
   `single_property` columns from the two `dual_property` columns — whether that is an explicit
   `type` discriminator, the presence or absence of `propertyUrl`, the shape of the `relation`
   object, or anything else.
5. Try more than one read path if they differ, and say which you used: the Notion MCP tools, and
   a direct REST call to `GET /v1/databases/<id>` or the data-source equivalent if you can make
   one. **If the raw API exposes subtype but the MCP tool strips it, that is a finding, not a
   footnote** — say so explicitly, because the plugin's rationale rests on the MCP surface
   specifically.

**Decisive question: is there any field that reliably tells the two subtypes apart?**

## Test 2 — Negative control for `propertyUrl`

The `propertyUrl` heuristic is only meaningful if it tracks subtype rather than something else.

1. In the same scratch DB, add non-relation properties: a `select`, a `number`, a `date`, a
   `checkbox`, and a `rich_text`.
2. Report which of them carry `propertyUrl`.

If non-relation properties also carry it, `propertyUrl` is not a subtype signal and the heuristic
is dead — say so plainly. Report what you observe either way; do not adjust the conclusion to fit
the hypothesis.

## Test 3 — Reproduce the original misread

1. In the same scratch DB, add a `dual_property` self-relation named exactly `Depends on`.
2. Note the companion column Notion creates and its exact name.
3. Create rows `A` and `B`. Set `A."Depends on" = [B]`.
4. **Fetch page B and dump its complete property map**, exactly as an agent inspecting the target
   page would see it — every property, including the companion.
5. Report whether `[A]` appears anywhere in B's properties, and under which property name.

This is the hypothesis under test: an agent writing `A → B` and then reading B's full property
map sees an edge back to `A` under a *different* property name, and reasonably concludes the
relation is symmetric. Report whether the observed output would support that conclusion.

Then repeat with a **`single_property`** relation named `DependsOneWay`: write `A → B`, dump B in
full, and confirm nothing appears. The contrast is the point.

## Test 4 — Real DB, read-only

1. Dump the complete property definition of the live `Depends on` column (`propertyUrl` is
   `PE1CSQ`; the DB is `25bfdf83-c417-809d-bd93-e60e12327627`).
2. Do the same for both native Sub-items halves, `Parent-task` and `Sub-tasks`.
3. Using whatever discriminator Test 1 found, classify the live `Depends on`: one-way, two-way,
   or undeterminable.
4. If it classifies as two-way, look for its companion column in the schema and report whether
   one exists, is hidden, or appears to have been deleted.

**No writes. No property edits. Schema and page reads only.**

---

## Cleanup — mandatory

1. Archive (trash) the scratch database and every page in it.
2. **Verify** by re-fetching the scratch database id and confirming it reads as archived. Do not
   claim cleanup succeeded without this check.
3. Confirm explicitly that zero writes reached the real tickets database.
4. Note that the API can only trash, not purge — tell the user the scratch DB sits in Notion's
   trash and can be permanently deleted from the UI.

If any cleanup step fails, say so loudly and give the exact id left behind.

---

## Report format

```
TEST 1 — SCHEMA DUMP
  read path(s) used:            <MCP tool / raw REST / both>
  fields differing single vs dual:
      <field>: single=<value>  dual=<value>
      ...
  explicit subtype discriminator present:  <YES: field=<name> | NO>
  MCP strips a field the raw API exposes:  <YES: which | NO | could not test raw>
  VERDICT: subtype detectable?             <YES | NO | ONLY VIA RAW API>

TEST 2 — propertyUrl NEGATIVE CONTROL
  relations with propertyUrl:       <list>
  NON-relations with propertyUrl:   <list>
  VERDICT: propertyUrl tracks subtype?  <YES | NO — it appears on non-relations too>

TEST 3 — MISREAD REPRODUCTION
  dual: companion column name:      <name>
  dual: B's properties after A→B:   <full map>
  [A] appears in B under:           <property name | nowhere>
  single: [A] appears in B under:   <property name | nowhere>
  VERDICT: reproduces the report?   <YES | NO | PARTIAL — explain>

TEST 4 — REAL DB (read-only)
  "Depends on" full definition:     <verbatim>
  classified as:                    <one-way | two-way | undeterminable>
  companion column:                 <name | none found | appears deleted>
  Parent-task / Sub-tasks:          <verbatim>

CLEANUP
  scratch db id:                    <id>
  archived and verified:            <YES | NO — details>
  writes to real tickets DB:        <NONE | details>
```

Report exactly what you observed. A result that contradicts the hypothesis is the most valuable
outcome here — the last two rounds of this investigation were both plausible theories that turned
out to be wrong, and both were caught only because the evidence was allowed to contradict them.
