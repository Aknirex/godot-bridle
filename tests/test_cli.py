from __future__ import annotations

import json

from bridle.app.cli import health_payload


def test_health_payload_is_json_serializable() -> None:
    payload = health_payload()

    encoded = json.dumps(payload)

    assert json.loads(encoded)["status"] == "ok"
