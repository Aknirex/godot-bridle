from __future__ import annotations

import json
from pathlib import Path

from bridle.app.sidecar import METHOD_ALIASES, PROTOCOL_VERSION

ROOT = Path(__file__).parents[1]


def test_protocol_schema_covers_python_dispatch_and_plugin_methods() -> None:
    schema = json.loads((ROOT / "protocol/v1.schema.json").read_text(encoding="utf-8"))
    methods = set(schema["properties"]["method"]["enum"])
    plugin = (ROOT / "addons/bridle/bridle_editor.gd").read_text(encoding="utf-8")

    assert PROTOCOL_VERSION == "2026-06-22"
    assert set(METHOD_ALIASES.values()) <= methods
    for method in ("system.health", "workflows.submit", "jobs.get"):
        assert f'&"{method}"' in plugin


def test_protocol_schema_exposes_versioned_workflow_and_manifest_models() -> None:
    schema = json.loads((ROOT / "protocol/v1.schema.json").read_text(encoding="utf-8"))
    definitions = schema["$defs"]

    assert set(definitions["workflowRequest"]["properties"]["input_type"]["enum"]) == {
        "text",
        "image",
        "retexture",
        "auto_rig",
    }
    assert {
        "inspection",
        "repairs",
        "materials",
        "rigging",
        "provenance",
        "godot_validation",
    } <= set(definitions["assetManifest"]["properties"])
