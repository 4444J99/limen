from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from limen.growth_admission import inspect_growth
from limen.host_admission import AdmissionController
from limen.storage_headroom import StorageAdmissionError, require_storage_headroom


def _controller(root: Path) -> AdmissionController:
    return AdmissionController(
        root,
        clock=lambda: 100.0,
        alive=lambda pid: pid > 0,
        identity=lambda pid: f"start-{pid}",
        descendant=lambda _pid, _ancestor: False,
        pressure_probe=lambda: {
            "swap_used_bytes": 8 * 1024**3,
            "memory_bytes": 16 * 1024**3,
            "backblaze_cpu_percent": 0,
            "backblaze_rss_bytes": 0,
            "disk_mib_per_second_samples": [0, 0],
            "vitals_action": "shed",
            "sensor_errors": [],
        },
    )


def _override(monkeypatch, checks: str = "none", until: str = "1970-01-01T00:03:20Z") -> None:
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_PRESSURE_CHECKS", checks)
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_OVERRIDE_REASON", "operator-bounded-custody")
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_OVERRIDE_UNTIL", until)


def test_pressure_override_preserves_measurements_and_records_suppressed_checks(tmp_path, monkeypatch):
    _override(monkeypatch)
    result = _controller(tmp_path / "admission").acquire("heavy", owner="operator", surface="test", pid=1)
    assert result["allowed"] is True
    assert result["pressure"]["swap_fraction"] == 0.5
    assert result["pressure_policy"]["overridden_reasons"] == ["swap-fraction", "vitals-shed"]
    assert result["pressure_policy"]["override_reason"] == "operator-bounded-custody"


def test_pressure_override_is_selective(tmp_path, monkeypatch):
    _override(monkeypatch, "vitals-shed")
    result = _controller(tmp_path / "admission").status()
    assert result["allowed"] is False
    assert result["reasons"] == ["vitals-shed"]
    assert result["pressure_policy"]["overridden_reasons"] == ["swap-fraction"]


@pytest.mark.parametrize("until", ["1970-01-01T00:01:40Z", "1970-01-01T00:01:39Z", "tomorrow", "inf"])
def test_expired_or_invalid_override_keeps_checks_enforced(tmp_path, monkeypatch, until):
    _override(monkeypatch, until=until)
    result = _controller(tmp_path / "admission").status()
    assert result["allowed"] is False
    assert "swap-fraction" in result["reasons"]
    assert result["pressure_policy"]["overridden_reasons"] == []


def test_override_requires_a_reason(tmp_path, monkeypatch):
    _override(monkeypatch)
    monkeypatch.delenv("LIMEN_HOST_ADMISSION_OVERRIDE_REASON")
    result = _controller(tmp_path / "admission").status()
    assert result["allowed"] is False
    assert "pressure-policy-invalid" in result["reasons"]


def test_unknown_pressure_check_fails_closed(tmp_path, monkeypatch):
    _override(monkeypatch, "swap-fractoin")
    result = _controller(tmp_path / "admission").status()
    assert result["allowed"] is False
    assert "pressure-policy-invalid" in result["reasons"]


def test_pressure_override_cannot_take_another_heavy_lease(tmp_path, monkeypatch):
    _override(monkeypatch)
    admission = _controller(tmp_path / "admission")
    first = admission.acquire("heavy", owner="first", surface="test", pid=1)
    second = admission.acquire("heavy", owner="second", surface="test", pid=2)
    assert first["allowed"] is True
    assert second["allowed"] is False
    assert second["reasons"] == ["heavy-lease-held"]
    assert second["lease"]["owner"] == "first"


def test_growth_limits_use_declared_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_GROWTH_MAX_NEW_TEXT_FILE_BYTES", "3")
    monkeypatch.setattr("limen.growth_admission._relative_git_paths", lambda _root: ["new.txt"])
    (tmp_path / "new.txt").write_text("four")
    result = inspect_growth(tmp_path)
    assert result.allowed is False
    assert result.oversized_text_paths == ("new.txt",)
    assert (tmp_path / "new.txt").read_text() == "four"


def test_explicit_growth_limit_takes_precedence_over_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_GROWTH_MAX_NEW_TEXT_FILE_BYTES", "3")
    monkeypatch.setattr("limen.growth_admission._relative_git_paths", lambda _root: ["new.txt"])
    (tmp_path / "new.txt").write_text("four")
    assert inspect_growth(tmp_path, max_new_text_file_bytes=4).allowed is True


def test_storage_hysteresis_uses_configured_thresholds(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LIMEN_STORAGE_BLOCK_BELOW_BYTES", "5")
    monkeypatch.setenv("LIMEN_STORAGE_REENABLE_AT_BYTES", "20")
    monkeypatch.setattr("limen.storage_headroom.storage_identity", lambda _path: "internal")
    available = [4]
    monkeypatch.setattr(
        "limen.storage_headroom.os.statvfs", lambda _path: SimpleNamespace(f_bavail=available[0], f_frsize=1)
    )
    with pytest.raises(StorageAdmissionError):
        require_storage_headroom(tmp_path)
    available[0] = 10
    with pytest.raises(StorageAdmissionError):
        require_storage_headroom(tmp_path)
    available[0] = 20
    require_storage_headroom(tmp_path)


def test_invalid_storage_threshold_order_is_rejected_before_writing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LIMEN_STORAGE_BLOCK_BELOW_BYTES", "20")
    monkeypatch.setenv("LIMEN_STORAGE_REENABLE_AT_BYTES", "5")
    with pytest.raises(StorageAdmissionError, match="storage-thresholds-invalid"):
        require_storage_headroom(tmp_path)
    assert not (tmp_path / "state").exists()
