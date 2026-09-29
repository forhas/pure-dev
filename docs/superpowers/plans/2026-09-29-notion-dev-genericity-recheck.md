# Genericity recheck — implementation plan

Baseline: `36717f6`, notion-dev 0.45.0 (PR #88). The supplied 2026-09-28 audit
prompt targets 0.44.0; its extension points have already shipped. Do not implement
them again. Client repositories and Notion remain read-only, as the prompt requires.

## Confirmed remaining work

1. Harden existing project extension points: validate failure-mode lists and contain
   reference paths within the project (including symlinks); preserve their precedence.
2. Use NUL-delimited Git numstat for generated-path exclusions, so Unicode, tabs and
   Git-quoted filenames match configured paths on Windows and WSL2.
3. Preserve off-product-epic routing for `meta` findings even when a configured route
   or meta destination points back to the source epic. Keep explicit label-rule
   precedence for valid destinations; do not interpret domain labels.
4. Repair fold semantics: distinguish prerequisite (`land before`) from co-delivery;
   recognize Notion-escaped brackets; report conflicting/negated declarations as
   leads requiring judgment. A declaration is not authority to close another ticket.
   Do not claim a title search proves absence of a body declaration or fetch all
   siblings to compensate. Reuse known references; body search is capability-dependent.
5. Carry a spec-change stop through epic closure, not just next-task selection. Check
   changes from the current resolution before evaluating closure; pending changes
   must not produce an executable re-home list.
6. Remove the arbitrary eight-file split rule and blanket context duplication from
   task-breakdown. Preserve complete per-task requirements, constraints and criteria.
   Align spec-citation and brief-byte-budget documentation with shipped behavior.
7. Publish a tracked audit/transfer report with current dispositions, exact client
   destinations, suggested optional config and incremental context costs. Keep native
   dependency-relation writes out: current adapter deliberately uses `Blocked by`,
   and no client maps a supported native relation. Do not expand into #86.

## Verification and delivery

- Add failing regressions for the executable gaps before fixing them, plus instruction
  assertions for routing/authority/decomposition boundaries.
- Run targeted tests, then all verification harnesses. Prove representative guards
  fail with mutations in an isolated copy; never restore the working implementation.
- Bump notion-dev once to 0.45.1. No new config keys, review seats, mandatory provider
  scans or base commits. Keep command entrypoint size within the existing cap.
- Open one unmerged pure-dev PR; run Ubuntu, Windows/Git Bash and Python 3.8 CI.
  Client transfers are recommendations only, so no empty/client PRs are warranted.

Live savings are unmeasured. Tests establish correctness and bounded work, not a
token reduction claim. The requested writing-plans skill is unavailable in this
environment; this document records the equivalent ordered plan directly.
