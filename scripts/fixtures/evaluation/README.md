# EVAL-1 — the generic evaluation fixture

A synthetic ticket, a defective implementation, a corrected twin, and a hidden oracle.
It exists so a change to the notion-dev workflow can be measured against a task that
has a known right answer, instead of against whichever real ticket happened to be next.

Nothing here comes from a client. What was preserved from the case that motivated it is
the **classes** of defect, not any source, ticket number, algorithm or provider ID.

## Layout

| Path | What it is |
|---|---|
| `ticket.md` | The authoritative requirement source. Two mandatory constraints sit in `## Notes`, outside the acceptance list, and one acceptance criterion is ticked while unimplemented. |
| `requirements.json` | The intake oracle: the inventory a correct reading of the whole ticket produces. Loads through `runtime.py requirements`. |
| `project/scheduler.py` | The candidate under review. **Carries seeded defects on purpose — do not fix it.** |
| `reference/scheduler.py` | The corrected twin. The oracle passes against this one. |
| `oracle/test_scheduler.py` | The hidden regression suite, specified from the ticket rather than from either implementation. |
| `pr-body.md` | A pull request body containing one false quantitative claim. |
| `expected-findings.json` | Every finding a competent independent review must produce, and why each one survives a weak review. |

## Running the oracle

```bash
EVAL_SCHEDULER=scripts/fixtures/evaluation/reference python3 scripts/fixtures/evaluation/oracle/test_scheduler.py   # passes
EVAL_SCHEDULER=scripts/fixtures/evaluation/project   python3 scripts/fixtures/evaluation/oracle/test_scheduler.py   # fails, by design
```

`scripts/tests/test_evaluation_fixture.py` asserts both directions on every run, plus
the inventory hash and the finding-to-oracle links. A fixture whose defects have
silently stopped being defects is worse than no fixture, so that is mechanical rather
than remembered.

## Using it to compare a baseline against a candidate

1. Copy `project/` and `ticket.md` into a disposable repository.
   **Never run a candidate workflow against this directory in place.**
   The comparison must not be able to edit the fixture, and a `git checkout -- .` to
   undo it would take your own uncommitted work with it.
2. Run the baseline workflow and the candidate workflow on identical copies, with the
   same host, model and effort, and disclose whether each ran warm or cold.
3. Score both against `expected-findings.json` and the oracle: findings reported,
   findings missed, false findings, and whether the seeded defects reached the merge
   gate. Compare cost only between runs that scored the same.
4. Report fresh I/O, cache-read traffic, peak context and wall time separately, from
   `runtime.py summary` and `telemetry.py`. A cheaper run that missed a defect is not
   a better run, and a token figure without a quality figure beside it says nothing.
