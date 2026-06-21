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

Default CI and local tests exclude real provider calls. Opt-in smoke tests require protected
`DEEPSEEK_API_KEY`, `MESHY_API_KEY`, and `OPENAI_API_KEY` values; see
[`docs/10-validation-debt-and-next-development-plan.md`](docs/10-validation-debt-and-next-development-plan.md).

The desktop shell will talk to the Python core through the stdio JSON-RPC sidecar:

```powershell
uv run bridle sidecar
```

The Tauri v2 desktop MVP lives in `desktop/`. Development and packaging instructions are in
[`docs/09-alpha-development-and-packaging.md`](docs/09-alpha-development-and-packaging.md).
Deferred release validation and the ordered next-development plan are tracked in
[`docs/10-validation-debt-and-next-development-plan.md`](docs/10-validation-debt-and-next-development-plan.md).
The final release gate is recorded in
[`docs/11-alpha-release-checklist.md`](docs/11-alpha-release-checklist.md).

## Roadmap

- v0.1-alpha: desktop-first Godot asset generation workflow with BYOK, async jobs,
  Meshy integration, GLB inspection, and Godot CLI import checks.
- P1: local RAG knowledge base for Godot project context, generated asset records,
  import logs, and Bridle docs. See `docs/08-rag-vector-knowledge-base.md`.
