"""Sustained pressure needs recent, shared observations, not an old checkout counter."""

import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from limen import host_admission
from limen.vigilia import vitals


@pytest.fixture
def history(tmp_path, monkeypatch):
    path = tmp_path / "vitals-streak.json"
    monkeypatch.setattr(vitals, "_streak_path", lambda: path)
    monkeypatch.setattr(vitals.params, "_load_panel", lambda: {})
    monkeypatch.setattr(vitals, "_boot_identity", lambda: "current-boot", raising=False)
    clock = {"now": 2_000_000.0}
    monkeypatch.setattr(
        vitals,
        "time",
        SimpleNamespace(
            time=lambda: clock["now"], monotonic=__import__("time").monotonic, sleep=__import__("time").sleep
        ),
    )
    return path, clock


def put(path, last, boot="current-boot", streak=3):
    path.write_text(
        json.dumps({"schema": "limen.vitals_warn_streak.v2", "streak": streak, "last": last, "boot_id": boot})
    )
    path.chmod(0o600)


@pytest.mark.parametrize(
    "age,boot", [(53 * 86400, "current-boot"), (601, "current-boot"), (-1, "current-boot"), (10, "previous-boot")]
)
def test_old_future_or_previous_boot_warning_is_not_current_sustained_pressure(history, age, boot):
    path, clock = history
    put(path, clock["now"] - age, boot)
    before = path.read_bytes()
    assert vitals._update_warn_streak(vitals.THROTTLE, update=False) == 0
    assert path.read_bytes() == before


def test_expired_warning_restarts_from_one_real_observation(history):
    path, clock = history
    put(path, clock["now"] - 53 * 86400)
    assert vitals._update_warn_streak(vitals.THROTTLE, update=True) == 1
    assert json.loads(path.read_bytes())["boot_id"] == "current-boot"


def test_recent_warnings_still_accumulate_and_read_only_does_not_increment(history):
    path, clock = history
    assert vitals._update_warn_streak(vitals.THROTTLE, update=True) == 1
    for expected in (2, 3):
        clock["now"] += 61
        assert vitals._update_warn_streak(vitals.THROTTLE, update=True) == expected
    before = path.read_bytes()
    assert vitals._update_warn_streak(vitals.THROTTLE, update=False) == 3
    assert path.read_bytes() == before


def test_competing_rapid_observations_count_once(history):
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: vitals._update_warn_streak(vitals.THROTTLE, update=True), range(4)))
    assert results == [1, 1, 1, 1]
    assert json.loads(history[0].read_bytes())["streak"] == 1


def test_shared_namespace_does_not_follow_checkout_or_tmpdir(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_ROOT", str(tmp_path / "host"))
    monkeypatch.setattr(vitals.params, "_repo_root", lambda: tmp_path / "checkout-one")
    first = vitals._streak_path()
    monkeypatch.setattr(vitals.params, "_repo_root", lambda: tmp_path / "checkout-two")
    monkeypatch.setenv("TMPDIR", str(tmp_path / "other-temp"))
    assert first == vitals._streak_path() == host_admission.default_state_root() / "vitals-streak.json"


def test_read_only_missing_state_creates_nothing(history):
    path, _ = history
    assert vitals._update_warn_streak(vitals.THROTTLE, update=False) == 0
    assert not path.exists()
    assert not list(path.parent.glob("*.lock"))


def test_corrupt_state_is_unmeasured_and_preserved(history):
    path, _ = history
    path.write_bytes(b"broken")
    path.chmod(0o600)
    with pytest.raises(ValueError):
        vitals._update_warn_streak(vitals.THROTTLE, update=True)
    assert path.read_bytes() == b"broken"


def test_symlink_history_cannot_be_reported_as_missing(history):
    path, _ = history
    path.symlink_to(path.parent / "missing")
    with pytest.raises(OSError):
        vitals._update_warn_streak(vitals.THROTTLE, update=False)
    assert path.is_symlink()


def test_explicit_admission_root_contains_its_own_warning_history(tmp_path, monkeypatch):
    observed = []
    original = host_admission.collect_pressure
    controller = host_admission.AdmissionController(root=tmp_path / "isolated")
    monkeypatch.setattr(host_admission, "collect_pressure", lambda **kw: observed.append(kw) or {})
    assert controller.pressure_probe() == {}
    assert observed == [{"state_root": controller.root, "record": True}]
    assert original is not host_admission.collect_pressure


@pytest.mark.parametrize("record", [False, True])
def test_pressure_collection_records_only_explicit_admission_observations(monkeypatch, record):
    calls = []
    monkeypatch.setattr(vitals, "beat_gate", lambda **kw: calls.append(kw) or {"action": "throttle"})
    monkeypatch.setattr(host_admission, "_backblaze_observation", lambda _errors: (0, 0))
    monkeypatch.setattr(host_admission, "_swap_observation", lambda _errors: (0, 16 * 2**30))
    monkeypatch.setattr(host_admission, "_disk_observation", lambda _errors: [0, 0])
    if record:
        result = host_admission.collect_pressure(record=True)
    else:
        result = host_admission.collect_pressure()
    assert result["vitals_action"] == "throttle"
    assert calls == [{"shed": False, "record": record}]
