# quant-factory

Production work flows `data -> features -> signals -> strategies`; promote through each layer, never around one. Build a missing input upstream-first. Deployment is a separate downstream step, `strategies -> production -> execution`, and a tracked deployment definition is not proof that anything is deployed or live.

Investigation, implementation, publication, deployment and live trading are separate scopes; never infer one from another.

The lake under `db/` is the interface between layers. Each layer writes only its own surface and reads upstream's published artifacts, never upstream's runtime. Code that produces an artifact lives in the owning package. Do not hand-edit generated artifacts; change the producer. Tests write temporary artifacts, never `db/`.

Data stamps availability: row `T` is what was known at `T`'s close. Never add a lag in features, signals or strategies; fix the stamp in the data layer.

Read lake parquet lazily: `data.query` for ad hoc, inspection and serving reads, or `pl.scan_parquet(...)` with the columns and filters you need in family code; never eagerly `pl.read_parquet` a large file to use a slice of it.

Every package except `packages/research` (local-only workspaces) and `packages/platform` (shared core only) separates `src/` from `extensions/`: `src/` is the generalized core, `extensions/` holds your families, venues and deployments. Extensions import the core; the core never imports a named extension and must work with `extensions/` absent. To add a family, copy the matching example (see the root README).

Credentials come only from environment variables; never put values in `.env`, Git, argv, logs or chat.

Use the shared environment: `uv sync --frozen --group dev`, then `uv run ...`. Add dependencies with `uv add --package <member>`.

`packages/strategies` owns alpha and portfolio intent; `packages/execution` implements execution mechanics and must not invent alpha. `packages/research` holds evidence and candidates, which are not canonical until promoted into the owning layer. `apps/api` and `apps/viz` are read-only over the lake, except that the API can start the strategies package's backtest-update job, which writes only under `db/research/strategies/<family>/<version>/updated/`.

`packages/platform` holds shared tooling; code earns its place there by being needed twice. Where a platform system exists it is mandatory, never rebuilt locally: `backtest`, `clients`, `ml-engine`.

Each package's rules live in its root `AGENTS.md` (`packages/<pkg>/AGENTS.md`, `apps/<app>/AGENTS.md`). Read it before working on a package. Precedence: this file, then the package `AGENTS.md`, then the nearest `AGENTS.md` below it; nearer may be stricter, never weaker. `AGENTS.md` files instruct, `README.md` files explain; if they disagree with each other or the code, fix the docs.

Run the owning package's checks first. Use `just ci` as the repository-wide gate for changes that cross a package boundary.
