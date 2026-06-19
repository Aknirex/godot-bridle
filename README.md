# godot-bridle

Desktop-first AI harness for Godot asset generation workflows.

The repository contains the Python workflow core and an initial Tauri desktop shell. Design and
delivery documents live in `docs/`.

## Development

```powershell
uv sync --extra dev
uv run pytest
uv run bridle health
```

The desktop shell will talk to the Python core through the stdio JSON-RPC sidecar:

```powershell
uv run bridle sidecar
```

The Tauri v2 desktop MVP lives in `desktop/`. Development and packaging instructions are in
[`docs/09-alpha-development-and-packaging.md`](docs/09-alpha-development-and-packaging.md).

## Roadmap

- v0.1-alpha: desktop-first Godot asset generation workflow with BYOK, async jobs,
  Meshy integration, GLB inspection, and Godot CLI import checks.
- P1: local RAG knowledge base for Godot project context, generated asset records,
  import logs, and Bridle docs. See `docs/08-rag-vector-knowledge-base.md`.
