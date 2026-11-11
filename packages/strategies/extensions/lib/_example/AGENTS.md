# example — family addendum

Read `packages/strategies/AGENTS.md` in full first; this addendum is stricter, never
weaker.

- This family is a reference scaffold. It carries no capital, no baseline, and no live surface;
  nothing here may be promoted to production.
- Write boundaries are ownership boundaries (see README table). In particular:
  `verification/**` changes only through an independent reviewer. A change to the family's
  code that also modifies `verification/**` is rejected.
- Every check added under `verification/` must name its oracle (sealed artifact, `references/`
  known answer, or reference implementation) and, for gates, the planted defect it was shown to
  catch.
- `references/` is read-only input material; never edit source material to match an
  implementation.
