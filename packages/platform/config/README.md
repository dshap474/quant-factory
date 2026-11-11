# config

Non-secret runtime configuration and schema-index utilities for standalone `quant-factory`.

## Installation

From the repository root:

```bash
uv sync --frozen --group dev
```

## What It Owns

- Path constants (`ROOT_QUANT_FACTORY`, `QUANT_DB_ROOT`, `QUANT_SIGNALS_DIR`)
- Schema index utilities (`load_schema_index`, `get_domain_index`)
- Shared logger helper (`get_logger`)

## Usage

```python
from config import QUANT_DB_ROOT

print(QUANT_DB_ROOT)
```

## Environment Contract

- Settings come only from the existing process environment.
- Provider credentials come from the process environment.
- Repository `.env` files are not read.
- `QUANT_DB_ROOT` defaults to `<repo>/db` when unset
