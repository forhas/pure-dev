Use the shared guards in `../SKILL.md` and `config.md`. Before any data-source query read `query.md`; before resolving a page read `fetch-ticket.md`.

## listEpicChildren(epicId)

Read-only.

1. If `parentTaskProperty` is **unusable** on the live DB — absent, **or present but not a self-referential Relation** — warn once and return `[]`, **without proceeding to step 3's query**. Both states degrade identically (see this property under "Property type handling"): step 3 filters with a relation-`contains` predicate, and against a non-relation column that is an MCP query error, not an empty result — the same trap the "Marker usability rule" closes for `epicMarkerProperty`. Record `missing-property:parentTaskProperty` when the property is **absent**, or `wrong-type:parentTaskProperty` when it is present but not a self-referential Relation, per `notion-dev:issue-log` — identical behavior, separate conditions, separate signatures.
2. Resolve `epicId` to a page ID via `fetchTicket`.
3. Query the DB — in the call shape in `query.md` — for pages whose `parentTaskProperty` contains that page ID.
4. Return `[{ id, key, title, status, url }]` ordered ascending by `id` — `key` the logical ticket key (`"STO-67"`) for display, `title` prefix-stripped, `status` the live option name verbatim (not a logical key; callers compare it against the resolved set).
