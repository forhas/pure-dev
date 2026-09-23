## Output block

Return exactly one block for the caller's report:

```
EPIC-DOC: created | updated | closed | refreshed | unchanged | none | failed
PATH: knowledge/epic/STO-60-wallet-indexing.md              (omit on none)
SEED: docs/STO-67-release-plan.md · last at a1b2c3d         (only when created from a seed)
THREADS: +2 -1                                              (bullets added / removed this run)
NEXT: [STO-70] Backfill historic wallets — <reason>         (or `epic complete`, or `blocked: <thread>`)
IN-PROGRESS: STO-72                                         (keys on the In progress line; `none` when empty)
DRIFT: <one line per repaired finding>                      (or `none`)
COMMIT: <sha> | none
ATTEMPTS: 1                                                 (write-path attempts)
CAUSE: <failed assertion, lock timeout, or push rejection>  (only on failed)
```

`closed` means this run set `Status: closed`. `failed` is the only value that carries `CAUSE`, and it is the only value on which the caller records `partial:epic-doc`. A local commit left behind by a rejected push is named in `CAUSE` so the caller's closeout can find it. `refreshed` and `unchanged` are `refresh`'s two success values.
