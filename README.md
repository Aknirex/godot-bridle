# godot-bridle

Desktop-first AI harness for Godot asset generation workflows.

The current repository is in early software-engineering setup. Design documents live in `docs/`; implementation starts with the Python core and then the Tauri desktop shell.

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
