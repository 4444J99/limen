from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-sensitive-history-removal.py"


@pytest.fixture()
def mod():
    spec = importlib.util.spec_from_file_location("sensitive_history_removal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sensitive_history_removal"] = module
    spec.loader.exec_module(module)
    return module


def _packet(mod, tmp_path: Path, *, same_device: bool = False) -> dict:
    content = b"private artifact content with one sufficiently long unique line\n"
    sha256 = hashlib.sha256(content).hexdigest()
    blob = mod._git_blob_oid(content)
    copies = []
    for index in (1, 2):
        path = tmp_path / f"copy-{index}.md"
        path.write_bytes(content)
        copies.append(
            {
                "copy_id": f"copy-{index}",
                "device_id": "device-1" if same_device else f"device-{index}",
                "path": str(path),
                "sha256": sha256,
                "restore_verified_at": "2026-08-23T00:00:00Z",
            }
        )
    return {
        "schema": mod.PACKET_SCHEMA,
        "repository": "organvm/limen",
        "pr_number": 2532,
        "original_head_oid": "a" * 40,
        "artifact_blob_oid": blob,
        "artifact_path": "ORIGINAL_REQUEST.md",
        "custody_copies": copies,
        "reachability_scan": {
            "repository": "organvm/limen",
            "pr_number": 2532,
            "original_head_oid": "a" * 40,
            "artifact_blob_oid": blob,
            "observed_at": "2026-08-23T00:00:00Z",
            "reachable_refs": ["refs/pull/2532/head", "refs/heads/contaminated"],
        },
        "deletion_targets": {
            "pull_ref": "refs/pull/2532/head",
            "branch_ref": "refs/heads/contaminated",
            "original_head_oid": "a" * 40,
            "artifact_blob_oid": blob,
        },
        "pages_urls": ["https://organvm.github.io/limen/"],
    }


def test_private_packet_requires_two_distinct_readable_custody_devices(mod, tmp_path):
    context = mod._validate_packet(_packet(mod, tmp_path))
    assert context["custody_copy_count"] == 2
    assert context["custody_device_count"] == 2

    with pytest.raises(mod.VerificationError, match="distinct copy and device"):
        mod._validate_packet(_packet(mod, tmp_path, same_device=True))


def test_pages_probe_detects_private_content_without_printing_it(mod, tmp_path, monkeypatch):
    context = mod._validate_packet(_packet(mod, tmp_path))
    monkeypatch.setattr(mod, "_http_get", lambda _url: (200, b"clean public page"))
    assert mod._pages_clean(context)[0] is True

    monkeypatch.setattr(mod, "_http_get", lambda _url: (200, context["artifact"]))
    assert mod._pages_clean(context)[0] is False


def test_redacted_receipt_contains_no_private_paths_or_artifact_content(mod, tmp_path, monkeypatch):
    packet = _packet(mod, tmp_path)
    context = mod._validate_packet(packet)
    monkeypatch.setattr(
        mod,
        "_pr_state",
        lambda _ctx: {"state": "CLOSED", "mergedAt": None, "headRefOid": context["head"]},
    )
    monkeypatch.setattr(mod, "_public_refs", lambda _ctx: {})
    monkeypatch.setattr(
        mod,
        "_public_object_probes",
        lambda _ctx: {"blob_api": 404, "blob_page": 404, "raw_object": 404},
    )
    monkeypatch.setattr(mod, "_pages_clean", lambda _ctx: (True, {"pages_1": 404}))

    receipt = mod._verify("postflight", packet, "f" * 64)
    rendered = json.dumps(receipt)
    assert str(tmp_path) not in rendered
    assert context["artifact"].decode().strip() not in rendered
    assert receipt["custody_copy_count"] == 2
    assert receipt["result"] == "pass"
