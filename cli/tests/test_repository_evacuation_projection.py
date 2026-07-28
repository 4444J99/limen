from __future__ import annotations

import json
import re
from pathlib import Path


def test_tracked_repository_projection_contains_no_private_inventory() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "docs" / "repository-evacuation-inventory-20260727.json"
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)

    assert payload["schema"] == "limen.repository_evacuation_projection.v2"
    assert payload["projection_privacy"] == {
        "contains_private_paths": False,
        "contains_private_names": False,
        "contains_device_identities": False,
        "contains_plaintext_content_digests": False,
        "private_inventory_required_for_reclaim": True,
    }
    assert "roots" not in payload
    assert "custody_devices" not in payload
    assert "/Users/" not in text
    assert "/Volumes/" not in text
    assert "/dev/disk" not in text
    assert "volume_uuid" not in text
    assert not re.search(r"https?://", text)
