# Signal analysis

Read [platform rules](../AGENTS.md) and [SPEC.md](docs/SPEC.md).

- Keep this an import-first public library with no dependencies on repository
  domains, private implementations, data stores, training, or backtesting.
- Public operations live in their documented concept modules; the package root
  exposes version metadata only. No import-time I/O or pass-through API registry.
- Model-independent partition arithmetic lives here. `ml-engine` owns training
  configuration, model fitting, fold-local preprocessing, artifacts, and tracking;
  it delegates shared arithmetic through this package's public functions. Preserve
  its existing pre-evaluation-gap semantics when integrating post-test embargo.
- Model importance accepts supplied fitted-model statistics, explicit prediction
  callables, or supplied predictions. Never fit models inside this library.
- Record metric definitions, direction, sample scope, missingness, and raw repeat
  or fold results. Descriptive dispersion is not automatically an inferential
  standard error. Evidence validates declarations, not historical truth.
- Enforce schemas, identity, timestamps, and availability at calculation boundaries.
  Retain coverage losses and undefined metrics; never silently infer target timing.
- Numerical changes require independent known answers and invariants through public
  operations.
- Follow the repository's purpose/usage docstrings and code-section banners.
- Run the package's full pytest suite, Ruff, and ty checks. Registration/boundary
  changes also run `tests/contracts` and `tests/boundary`. Build/install checks use
  temporary destinations. Do not edit sealed consumer artifacts.
