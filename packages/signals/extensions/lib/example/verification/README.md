# verification/

Checks the family's code is judged by, kept apart from that code. This scaffold ships the layout
only: every subdirectory is empty until the family adds checks.

Layout:

- `certification/` — functions that certify any implementation of the family contract through the
  runner seam (called exactly as `SignalRunner` calls `load_data` and `compute`), each raising a
  named error that cites the contract clause it enforces: point-in-time labeling (no shift), the
  prediction-frame schema, sign conventions.
- `goldens/` — golden tests pinning promoted code to a sealed version's recorded prediction frames.
- `fixtures/` — the frozen inputs the cases run against.
- `evidence/` — the recorded reason for every relaxed comparison, plus planted-defect
  demonstrations for each gate.

Rules:

1. Every check names its ground truth. No invented expected values.
2. Exact comparison by default; relaxations are per case and recorded in `evidence/`.
3. Checks may grow; they never weaken to accommodate a failing candidate. A wrong check is
   corrected against its ground truth, with the reason recorded.
4. A gate is not done until it has caught a planted defect.
