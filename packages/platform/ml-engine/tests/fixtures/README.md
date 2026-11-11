# Synthetic regression fixture

`synthetic_regression.csv` is a deterministic, domain-neutral dataset for manually exercising
the ML Engine training, tracked-run, artifact-save, and inference paths.

It contains 96 ordered daily observations with:

- `row_id`: stable unique caller identity;
- `timestamp`: chronological split input;
- `feature_trend`, `feature_cycle`, and `feature_binary`: model inputs;
- `target`: a deterministic linear combination of the three features plus a small repeating
  perturbation.

Load it with:

```python
from pathlib import Path

import pandas as pd

path = Path("packages/platform/ml-engine/tests/fixtures/synthetic_regression.csv")
frame = pd.read_csv(path, parse_dates=["timestamp"])
```

Run a real tracked LightGBM training, artifact save, and trusted inference round trip with:

```bash
uv run python packages/platform/ml-engine/tests/manual/run_synthetic_lightgbm.py
```

The fixture contains no production, strategy, or market data. Generated inference artifacts remain
local and untracked; do not commit model binaries.
