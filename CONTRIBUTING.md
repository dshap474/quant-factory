# Contributing

Thanks for your interest in quant-factory. This file covers the mechanics: getting set up,
running the gates, and submitting a change. For what the system *is* and where things belong,
read `README.md` first, then the `README.md` of the package you are touching.

## Setup

You need [uv](https://docs.astral.sh/uv/) for Python and [pnpm](https://pnpm.io/) for the web app.
Python 3.12; Node 22.13+ (not 23) or 24+.

```bash
uv sync --frozen --group dev          # one shared environment for the whole workspace
cd apps/viz/web && pnpm install       # only if you are touching the frontend
```

This is a uv workspace, so there is a single environment at the root. Run everything through
`uv run ...`, and add dependencies with `uv add --package <member>` rather than editing a
member `pyproject.toml` by hand.

No credentials are needed to build, test, or run the example bundle. Provider clients need
credentials only when you point them at a live provider; each client reads its key from an
environment variable (for example `FRED_API_KEY`); export it in your shell or use your own secret
manager. Never put credentials in Git, on a command line, or in a log.

## Verify your change

The primary local gate:

```bash
just ci
```

That runs the type check plus the boundary, workflow, and production suites. Useful
narrower targets while iterating:

```bash
uv run pytest <path/to/test_file.py>::<test_name> -q   # one test
just test                                              # boundary + workflow
just test-all                                          # every root lane (packages run their own suites)
```

If you touched a specific package, run its own suite too — for example
`uv run pytest packages/features/tests -q`. If you changed a layer's contracts, run that layer's
validator: `uv run qf-data schema-validate`, `uv run qf-features validate`,
`uv run qf-signals validate`, `uv run qf-strategies validate`.

Frontend changes, from `apps/viz/web`:

```bash
pnpm run gate:fast    # lint + typecheck + unit tests
pnpm run gate:full    # the above plus build and end-to-end smokes
```

`pnpm run gate:full` is expected to pass before you submit anything that touches UI surface or
build configuration.

## Making changes

A few conventions that reviewers will look for:

- **Respect the layer order.** Production work flows `data -> features -> signals -> strategies`.
  Do not skip a layer, and do not import an upstream package's runtime to recompute something the
  lake already publishes. If an input does not exist yet, land it upstream first.
- **Write only to your own surface.** A layer writes its own `db/` scope and nothing above it.
- **Stamp availability in the data layer.** Row `T` is what was known at `T`'s close. Never add a
  lag in features, signals or strategies; if a stamp is wrong, fix it in the data layer.
- **Copy the example bundle.** `packages/features/extensions/lib/example`,
  `packages/signals/extensions/lib/example`, and `packages/strategies/extensions/lib/_example`
  are the reference implementations of each layer's contract. Starting from one of them is the
  fastest way to get the shape right.
- **Match the file conventions.** Code files open with a header docstring stating purpose and
  usage, group their contents under banner sections, and put the entry point last.
- **Keep docs honest.** `README.md` explains what a thing is; `AGENTS.md` gives working rules for
  that directory; durable local memory goes in the git-ignored `AGENTS.local.md` beside it. If your
  change makes either wrong,
  fix it in the same commit.

## Submitting

Open a pull request against `main` with a clear description of what changed and why, plus the
gate output you ran. Keep commits scoped to one logical change. Run the existing checks for what
you changed; if a new test is warranted, say why in the pull request so reviewers can weigh it.
