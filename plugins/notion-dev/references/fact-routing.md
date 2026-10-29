# Routing cross-epic facts

Read by `references/record.md`'s **Route the facts** step, once, when the run's `NEW-INFO:`
block is non-empty and the primary lock is released. This is the **only** path by which a
model routes a fact through `/notion-dev:new-info`. The slash command keeps
`disable-model-invocation: true`, so the Skill tool refuses it in every session; never try
it, and never read `commands/new-info.md` to route a fact from anywhere but step 4 below.

Why the gate exists: a routed fact writes to every affected epic's brief, its Notion page,
its tickets and the knowledge bundle, which later runs read as true until superseded. So a
fact is routed only after an independent check of its evidence, the decision is computed by
`workflow.py fact-route` rather than by this run, and a human-sourced fact still reaches no
brief without the person whose confirmation it needs.

`python3` below stands for `knowledge.python`, as everywhere in the plugin.

## 1. Write the facts

Write `<runtime dir>/facts.json` from the `NEW-INFO:` block, in its order, exactly as each
fact would be routed:

```json
{"facts": [{"id": "F1", "fact": "<one sentence>", "evidence": "<as in the block>",
            "epics": ["STO-184"]}]}
```

`epics` is `["unknown"]` when the block says `unknown`. `prepare` rejects anything else: an
id twice, an empty field, an epic that is not a logical key.

## 2. Check them independently

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/runtime.py" --state "$RUNTIME_STATE" prepare --role fact-check --file facts=<facts.json>
```

Dispatch one fresh worker for the returned packet under `references/runtime.md`'s
**Dispatch contract**: the compact instruction, runtime path, plugin root, interpreter, the
objective *check each fact's evidence and classify its source*, and its permissions —
**read-only**: `git` and `gh` reads, files at a named commit, a read-only command re-run,
Notion through `notion-dev:ticket-system` reads; never a write, a push, a broadcast or a
mutating API. It gets nothing else from this run: not context.md, not the plan, not this
conversation. Its packet's `fact_rules` are its whole brief, and they are the anti-circularity
rule as well: a document this ticket's own pull request committed proves only what it
mechanically records from a reproducible artefact, never a human decision it reports.

`attach`, then `workflow.py await-worker`, then read the result and `runtime.py accept` it.
`publish` already refused a result that misses a fact, reorders them, or carries a verdict,
source or citation outside the contract.

**When the check cannot finish** — the worker cannot be dispatched, delivers nothing after
one nudge, outlives its timeout, or its result is rejected and one replacement fails the
same way — end it (`end-worker`), hand off **every** fact with reason
`check unavailable — <cause>`, and record `partial:fact-routing` per `notion-dev:issue-log`.
`prepare` refuses a third attempt, and any attempt once one is accepted, so a verdict cannot
be shopped for.
Never check the facts yourself instead: you established them, so that verifies nothing.

## 3. Decide

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow.py" fact-route --state "$RUNTIME_STATE" --worker <id> --own-epic <the ticket's epic key, or none> [--non-interactive] --output <runtime dir>/route.json
```

Pass `--non-interactive` exactly when this ticket run is non-interactive. The command is the
only judge, and its rules are fixed:

- **Handed off**: `epics` unknown, or naming only this ticket's own epic (which `record.md`
  already recorded); an `unsupported` verdict, with the checker's citation as the reason; a
  `human` source in a non-interactive run; anything beyond **3** routed facts.
- **Routed without a gate**: a `reproducible` fact the checker `supported` — or `narrowed`, in
  which case the narrowed wording is what gets routed.
- **Routed through the gate**: a `human` fact in an interactive run. new-info's per-epic
  Apply / Skip / Revise gate shows it with its source and citation, so you confirm it there.

Never edit `route.json`: `route-view` refuses a file whose digest no longer matches the one
`fact-route` recorded in this run's state.

## 4. Route

When `routed` is empty, skip to step 5. Otherwise read `${CLAUDE_PLUGIN_ROOT}/commands/new-info.md`
and execute it inline with the arguments `--route <runtime dir>/route.json` and nothing else.
Its own preconditions, epic guard, lock and gates all apply; its `--route` rules say what
changes. A precondition that stops it — a dirty tree, a held lock, `route-view` refusing —
hands off every routed fact with reason `new-info stopped: <cause>` and records
`partial:fact-routing`.

## 5. Report

Every fact in the `NEW-INFO:` block gets one `route:` line:

- `route: routed — <new-info's per-epic outcome for it>` — resolved; it carries no `run:` line
  and is not a closeout item.
- `route: handed off — <reason>` — keeps its `run:` line, and is the closeout `blocked:` item
  `record.md` describes, awaiting the user.

new-info's own `blocked:` lines — an unpushed note or capture commit — join this run's
closeout unchanged.
