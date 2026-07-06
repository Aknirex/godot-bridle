# godot-bridle

Functional pipeline tooling for turning game asset requirements into provider requests and
Godot-ready project assets.

The repository contains the Python workflow core and an initial Tauri desktop shell. The product
focus is the middle path between LLM/Agent planning, 3D asset-generation vendors, and Godot game
projects. Design and delivery documents live in `docs/`.

## Development

```powershell
uv sync --extra dev
uv run pytest
uv run bridle health
```

Default CI and local tests exclude real provider calls. Opt-in smoke tests require protected
`DEEPSEEK_API_KEY`, `MESHY_API_KEY`, and `EMBEDDING_API_KEY` values plus the
`EMBEDDING_API_BASE` and `EMBEDDING_MODEL` environment variables.

The desktop now starts a small Rust `bridled` service and renders immediately. Python is launched
only when an AI, knowledge, or asset workflow needs it, and is reaped after 60 idle seconds. The
stdio JSON Lines adapter remains available for tests and CLI clients:

```powershell
uv run bridle sidecar
```

The Tauri v2 desktop MVP lives in `desktop/`. Development and packaging instructions are in
[`docs/09-alpha-development-and-packaging.md`](docs/09-alpha-development-and-packaging.md).
The current development direction is tracked in
[`docs/12-functional-pipeline-reset-and-roadmap.md`](docs/12-functional-pipeline-reset-and-roadmap.md).
Archived alpha release validation material is under `docs/archive/`.

## Roadmap

- v0.1-alpha: keep the existing BYOK, async job, Meshy mock/real, GLB inspection,
  Godot CLI import-check, and RAG foundations.
- P0 reset: prove the functional pipeline from requirement document to structured asset
  production request to provider execution to Godot import manifest.
- P1: turn successful runs and failures into reusable workflow recipes and diagnostics.
