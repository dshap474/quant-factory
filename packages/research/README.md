# Research

`packages/research` is the exploratory schema of `quant-factory`. It holds evidence, experiments, and
promotion candidates without pretending they are production contracts.

## Surfaces

| Surface | Purpose |
| --- | --- |
| `src/` | Reusable research utilities (empty in a fresh clone) |
| `corpus/` | Local-only user knowledge pipeline: `inbox → sources → wiki` |
| `sandbox/` | Local-only user experiments — one directory per project |
| `docs/` | Tracked documentation for using the research package (empty in a fresh clone) |
| `.dev/` | Local-only personal notes, prompts, drafts, guides, and attachments |

The root `pyproject.toml` is a dependency environment for sandbox projects, not an importable
Python package.

## Corpus

`corpus/sources/` holds one folder per work, `<kind>s/<Name>/`, with the original document in
`original/` beside its extracted text, chapters, and compressed facts (the operator's drop zone is
`corpus/inbox/`), and `corpus/wiki/` holds distilled
evergreen notes. The local `corpus/INDEX.md` catalogs the library. Their contents are
gitignored, so licensed material stays on the local machine; only the three directory placeholders are tracked. Never implement
in the corpus — adaptations of source code get rewritten in `sandbox/`.

## Sandbox

Flat: `sandbox/<project>/`. No category subdirectories, ever. Inside a project the layout is
freeform, with two conventions:

- `README.md` is required — one paragraph: what it is, status, verdict if dead.
- `viz.json` is optional and opts the project into the frontend. `/api/research/packages`
  enumerates `sandbox/*/viz.json`; projects without one simply do not appear in the UI.

```json
{ "id": "example-lab", "title": "Example Research Lab", "subtitle": "...", "surface": "lab_db" }
```

The manifest governs discovery, not rendering; bespoke endpoints stay bespoke.

## Research Outputs

Persistent run artifacts live under `db/research/`, not in this package. `db/research/**` is a
separate namespace and does not mirror the sandbox layout one-for-one.

## Promotion

Real strategies go straight to `packages/strategies`, where the versioning infrastructure lives.
Otherwise:

- reusable source data -> `packages/data`
- model-ready transforms -> `packages/features`
- validated predictive scores -> `packages/signals`
- portfolio and execution behavior -> `packages/strategies`
- mechanics reused across package boundaries -> `packages/platform` (only once two packages need them)

Production flow is `data -> features -> signals -> strategies`; do not skip layers.

See [AGENTS.md](AGENTS.md) for the normative placement rules.
