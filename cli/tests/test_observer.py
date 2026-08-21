import json
from pathlib import Path

from limen import observer


def test_observer_writes_counts_only_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(
        observer,
        "_run",
        lambda *args, **kwargs: {"status": "passed", "returncode": 0, "duration_ms": 1, "output_bytes": 3},
    )
    monkeypatch.setattr(observer, "_boot_identity", lambda: "boot")
    monkeypatch.setenv("LIMEN_OBSERVE_RECEIPT", str(tmp_path / "receipt.json"))
    receipt = observer.observe_once(tmp_path, "all")
    assert receipt["counts"] == {"passed": 4, "failed": 0, "timed_out": 0}
    assert "results" not in receipt
    assert json.loads((tmp_path / "receipt.json").read_text()) == receipt


def test_observer_declares_no_mutating_probe():
    source = Path(observer.__file__).read_text()
    for forbidden in ("dispatch --", "--apply", "rerun", "sync-release"):
        assert forbidden not in source
