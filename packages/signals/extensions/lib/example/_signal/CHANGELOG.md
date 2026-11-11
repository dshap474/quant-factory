# example — production changelog

Changes to the registered runner and presets only: the production surface whose history lives
under `db/signals/<signal_id>/`. Sealed research versions are recorded in
`optimization/version/vNNN/` and `optimization/vNNN/`; the operator action that promotes a sealed version into the
registered runner is recorded here.

## 2026-01-02 — scaffold runner

**Change:** `src/example_signal/runner.py` registers a working `ExampleRunner` with
`status="planned"` (never listed, smoked, or published; `save=False` by default). `presets/default.yaml` now
loads. No history written.

## 2026-01-01 — scaffold

**Change:** Family scaffold created; no runner registered, no preset loaded, no history written.
