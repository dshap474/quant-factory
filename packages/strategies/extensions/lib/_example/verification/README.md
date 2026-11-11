# Verification

The family's only checks: independent goldens for the code `src/` runs, plus end-to-end tests of
the production entry point. No unit tests ([package rules](../../../../AGENTS.md#4-family-src-ownership)).
Reviewers independent of the code under test author and maintain these checks; anyone changing
the family's code runs them but never edits them to pass a candidate.

```bash
uv run pytest packages/strategies/extensions/lib/<family>/verification -q
```

## Layout

```
verification/
  README.md               index: check -> oracle -> code it covers
  conftest.py             mounts the family src
  e2e/                    end-to-end runs of the production entry point
  <area>/                 one folder per part of src the checks verify
    test_<check>.py       the check; its docstring names the oracle
    <check>.json          frozen golden, when the oracle is data
    derive_<check>.py     how the golden was derived, when scripted
    <check>.md            record (oracle, provenance, tolerances), when the docstring is not enough
    <scope>.md            a record covering several checks in the area, named for its scope
    fixtures/             small frozen inputs
```

A check is one stem: its test and whichever of golden, derivation and record it needs share a
name and a folder. Only the test is required. Every check names its oracle: a book or paper
known answer in `references/`, an exact or hand derivation, or a reference implementation, never
the code's own output. The e2e tests are the exception: they run the production entry point end to end (here, every
version's rerun builds its presets and the book weights are valid) and show wiring, not correctness.

A new check goes in the area of the code it verifies; add an area folder only when none fits.
Bulk run artifacts never live here. Here `e2e/test_runner.py` is the worked example.
