## Calling `mcp__notion__notion-query-data-sources`

**Every data-source query in this skill uses this one call shape. Use it verbatim.** That is the
operations below *and* the two in `create-ops.md` — `createTicket`'s max-plus-one next-id lookup on
a Number-typed `idProperty`, and `setDependencies` resolving a title reference — neither of which
goes through `fetchTicket`, so neither inherits this contract by being downstream of it. A caller
on the create path reads this section before its first query. Measured on a client
run (BTC-Gateway, notion-dev 0.29.0): 5 of the 13 data-source calls in one ticket were the run
rediscovering this contract, and two of the five failed in ways that do not look like failures.

```
mcp__notion__notion-query-data-sources({
  "data": {
    "data_source_urls": ["collection://<dataSourceId>"],
    "query": "SELECT \"userDefined:<idProperty>\" AS id, \"<live title property>\" AS title, \"<statusProperty>\" AS status FROM \"collection://<dataSourceId>\" WHERE \"userDefined:<idProperty>\" = 142"
  }
})
```

Four things about it, each of which cost that run a round trip:

- **The arguments are wrapped in `data`, and the table name is the quoted collection URL.** Three
  other shapes are rejected with the same unhelpful `Input validation error: Invalid arguments for
  tool notion-query-data-sources: data: Invalid input`, which names no field: a top-level
  `data_source_url` + `query_type` + `sql_query`; a `data_sources` JSON *string*; and a
  `data: { mode, data_source_url, filter }` structured-filter form. None of them is this tool.
- **Never use `params` with `?` placeholders. Inline the literal value instead.** This is the one
  that does not announce itself: `WHERE "ID" = ?` with `params: [142]` returns
  `{"results":[],"has_more":false}` — **HTTP 200, no error, and an empty result set that is
  indistinguishable from a ticket that does not exist.** A run that reads it as "no such ticket"
  goes on to the wrong branch with nothing to say it guessed. Later in the same run the same
  `params` form drew a `400 validation_error` instead, so the failure mode is not even stable.
- **Column names come from `.claude/notion-dev.config.json`, never from a `SELECT *` probe.**
  `/notion-dev:init` records every one this file needs — `idProperty`, `statusProperty`,
  `phaseProperty`, `stepProperty`, `epicProperty`, `parentTaskProperty`, `epicMarkerProperty` —
  so `SELECT * FROM "collection://…" LIMIT 1` to learn them reads a row the caller already has the
  schema for. The client run ran that probe twice, the second time only because a compaction had
  dropped the first one's answer.

  **The title is the one exception, and it is not configured at all.** There is no
  `ticketSystem.titleProperty`: every Notion database has exactly one `title`-typed property and
  the adapter discovers it by scanning the live schema, because its *name* is free — `Name`,
  `Title` and `Task name` are all in use. So resolve it the way `config.md` "Title" says, and
  **select it only in queries that actually need the title**; a lookup that just resolves a page
  omits the column rather than guessing a name, since a wrong guess is the same hard `400` as
  `name`. Discovering one property from the live schema is not the `SELECT *` probe this bullet
  forbids — that probe was re-reading columns the config already names.
- **There is no bare `name` column**, and guessing one is a hard `400`
  (`Failed to execute query: no such column: name`). Every property is queried under its own
  **configured** name — `statusProperty`, `phaseProperty` and the rest — with two exceptions: the
  title, which has no configured key at all (see the bullet above), and **the id column, which
  takes a `userDefined:` prefix, `"userDefined:<idProperty>"`.**
  That prefix is a namespace, not a fixed column name: on a database whose `idProperty` is the
  default `ID` it reads `"userDefined:ID"`, and on one where `/notion-dev:init` bound
  `idProperty` to something else it takes that name instead. **Hardcoding `"userDefined:ID"`
  queries a column that does not exist on such a database**, and the logical-key lookup fails
  before the page is ever fetched. No other property observed on a live database needed the
  prefix; if the prefixed form is rejected, retry once with the bare configured name and record
  the fallback per `notion-dev:issue-log`. See `../SKILL.md` for why the prefix exists and why
  this tool returns the bare integer where `notion-fetch` returns `"userDefined:ID": "PDS-1"`.

`dataSourceId` is `ticketSystem.dataSourceId` when configured, otherwise derive the collection URL
from `ticketSystem.databaseId`. Everything else in this file that says "query the database" **or
"Query the DB"** means this call — both wordings are in use, and a clause naming only the first
leaves `listEpicChildren` step 3 uncovered, which is a site that queries the data source directly.
