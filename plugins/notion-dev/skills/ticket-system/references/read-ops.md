# Ticket read operation router (legacy entry point)

Read shared guards in `../SKILL.md` and `config.md` once. Load only the requested operation:
`fetch-ticket.md`, `find-epics.md`, `epic-context.md`, or `list-children.md`.
Before a data-source query load `query.md`; direct page fetches do not need query instructions.
No full-catalog read is required. `operations.md` is only an on-demand return-shape reference.
