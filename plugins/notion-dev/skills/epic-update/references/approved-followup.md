# Approved follow-up creation, without another interview

Only for a lean run with a complete accepted independent finding AND an authorized `file`
decision. Missing history/answers or legacy FAILED packets use `with-followups.md` instead.
An uncertain outcome with a retained approved JSON packet stays on THIS path and reconciles its
existing child journal. Never map it to a legacy Markdown packet name or a new operation identity.
A model-written `decision: file` field does not itself grant authority.
Keep the existing parent lock and record journal; no nested agent, new scheduler or lock.
Use configured `knowledge.python` for `python3` below.

1. Reuse the validated epic, accepted finding and filing decision. Preserve the existing
   provenance convention: `Follow-up-of: <ticket-key> · finding-hash: <first 12 hex of SHA-1
   of the original raw finding text>`. Derive the title once, persist both before any write.
   Read live epic children; fetch only title-matching candidates and confirm the exact marker
   in their Context. A title alone is not a match. A confirmed match is ALREADY-FILED, not a create.
   On recovery inspect the original journal first. Confirmed children are skipped; attempted/
   unknown children reconcile their frozen payload and exact provenance against live effects.
   Finding an existing page must reconcile the original operation, not create a second write
   identity. Retry only after proving no effect and recording failure through the existing protocol.
2. Save a JSON packet outside git under the runtime, keyed by the finding identity:
   `title`, `goal`, `scope`, `evidence`, `provenance`, `source` (source ticket/PR references),
   `decision: "file"`, nonempty `requirements` and `acceptance` arrays, and explicit arrays
   `edge_cases`, `dependencies`, `open_questions`. Empty means explicitly established empty,
   not unread. Keep the raw accepted finding and approval reference beside it. Unknown answers
   take the normal clarification path; never invent them to satisfy the builder.
3. Load ticket-system **createTicket**'s live schema/parent/assignee rules. Save an approved
   create recipe (one page) with `name`, `target`, `tool: "mcp__notion__notion-create-pages"`,
   `title_property: "<configured title key>"`, and `input` containing actual parent and page
   properties. Omit title/content: the builder fills those exact slots without a Python pipe.
   `workflow.py followup-body --packet <packet.json> --recipe <recipe.json> --output <writes.json>`
   writes UTF-8/LF directly and returns its path/hash. Pass that file directly to
   `record-children --writes <writes.json>`; do not read stdout through inline Python, retype
   the rendered content, or pass a large JSON object as a shell argument.
   Use the generated title/body, validated parent epic,
   configured epic property and normal Backlog mapping. Carry the resolved ticket's assignee
   when present; otherwise honor configured defaultAssignee after live eligibility validation.
   Load only createTicket and needed schema/assignee references, not create-task/input-source/
   interviewer. Preserve required project properties and return/report the created id/title/url.
4. Declare the exact create call as a child of the existing epic-record operation and begin
   BEFORE dispatch. Parent relation and provenance are in that SAME create call, not appended
   later. Capture the real exchange; fetch the new page and verify title, body/provenance,
   parent, project/status/assignee before confirming. Never claim success from the launch alone.
   Lost response → reconcile title candidates plus exact marker; no blind create retry.
   Failure/unknown → retain packet path, journal and cause; do not treat as user-dropped.
5. Return FILED/ALREADY-FILED with verified URLs, explicit failed/unknown items and packet
   paths. Continue epic-update with a NEW child list after creates; it refreshes Tasks, checks
   closure, logs resolution once. The enclosing epic brief uses the lifecycle retrieval planner:
   no additional create-time refresh or sibling-body scan.

This renderer saves elaboration work, not validation or provider authority. Unknown effects
and conflicting human content retain the existing reconcile/failure behavior.
