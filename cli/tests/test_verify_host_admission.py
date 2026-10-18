from __future__ import annotations

import importlib.util
from contextlib import contextmanager, nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify.py"


def load_verify():
    spec = importlib.util.spec_from_file_location("verify_host_admission_uut", VERIFY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def registry() -> dict:
    return {
        "file_sets": {},
        "deploy_triggers": {},
        "gates": {
            "cheap": {"note": "cheap", "tier": "cheap", "command": "true"},
            "heavy": {"note": "heavy", "tier": "heavy", "command": "true"},
            "serialized": {
                "note": "serialized",
                "tier": "heavy",
                "serialize": True,
                "command": "true",
            },
        },
    }


def test_scoped_verifier_acquires_once_for_heavy_and_serialized_tail(tmp_path, monkeypatch) -> None:
    verify = load_verify()
    events: list[str] = []

    @contextmanager
    def held(*, owner: str, surface: str):
        assert owner.startswith("limen-verify-")
        assert surface == "verify-scoped"
        events.append("acquire")
        yield
        events.append("release")

    monkeypatch.setattr(verify, "changed_set", lambda _base: ["changed.py"])
    monkeypatch.setattr(
        verify,
        "select",
        lambda _registry, _changed: (["cheap", "heavy", "serialized"], []),
    )
    monkeypatch.setattr(
        verify,
        "run_gate",
        lambda gate_id, *_args, **_kwargs: not events.append(f"gate:{gate_id}"),
    )
    monkeypatch.setattr(verify, "heavy_admission", held)
    monkeypatch.setenv("LIMEN_VERIFY_LOCK_FILE", str(tmp_path / "verify.lock"))

    assert verify.cmd_changed(registry(), None, jobs=1, gate_timeout_seconds=300.0, gate_output_bytes=1024 * 1024) == 0
    assert events == ["gate:cheap", "acquire", "gate:heavy", "gate:serialized", "release"]


def test_scoped_verifier_returns_temporary_failure_on_admission_denial(monkeypatch) -> None:
    verify = load_verify()

    @contextmanager
    def denied(*_args, **_kwargs):
        raise verify.HostAdmissionFailure("vitals-shed")
        yield  # pragma: no cover

    monkeypatch.setattr(verify, "changed_set", lambda _base: ["changed.py"])
    monkeypatch.setattr(verify, "select", lambda _registry, _changed: (["heavy"], []))
    monkeypatch.setattr(verify, "run_gate", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(verify, "heavy_admission", denied)

    assert verify.cmd_changed(registry(), None, jobs=1, gate_timeout_seconds=300.0, gate_output_bytes=1024 * 1024) == 75


def test_scoped_verifier_returns_temporary_failure_when_process_identity_is_unavailable(monkeypatch) -> None:
    verify = load_verify()
    from limen import host_admission

    @contextmanager
    def identity_unavailable(*_args, **_kwargs):
        raise ValueError("lease owner PID/start identity is unavailable")
        yield  # pragma: no cover

    monkeypatch.setattr(host_admission, "hold_lease", identity_unavailable)
    monkeypatch.setattr(verify, "changed_set", lambda _base: ["changed.py"])
    monkeypatch.setattr(verify, "select", lambda _registry, _changed: (["heavy"], []))
    monkeypatch.setattr(verify, "run_gate", lambda *_args, **_kwargs: True)

    assert verify.cmd_changed(registry(), None, jobs=1, gate_timeout_seconds=300.0, gate_output_bytes=1024 * 1024) == 75


def test_verify_whole_takes_legacy_flock_before_host_admission() -> None:
    text = (ROOT / "scripts" / "verify-whole.sh").read_text(encoding="utf-8")
    assert text.index("fcntl.flock") < text.index('host_admission_acquire "verify-whole"')
    assert "trap host_admission_exit_trap EXIT" in text


def test_verify_scoped_remains_contractual_thin_wrapper() -> None:
    lines = (ROOT / "scripts" / "verify-scoped.sh").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 20
    # The interpreter is resolved once by scripts/lib/gate-python.sh (PyYAML-capable, PATH-independent).
    assert any('exec "$LIMEN_GATE_PYTHON" "$ROOT/scripts/verify.py" --changed' in line for line in lines)
    assert any("scripts/lib/gate-python.sh" in line for line in lines)


def test_explicit_ci_batch_budget_is_not_silently_clamped_to_ten_minutes(monkeypatch):
    verify = load_verify()
    observed = []
    monkeypatch.setattr(verify.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(verify, "changed_set", lambda _base: ["changed.py"])
    monkeypatch.setattr(verify, "select", lambda *_args: (["cheap"], []))
    monkeypatch.setattr(verify, "run_gate_wave", lambda *_args, **kw: not observed.append(kw["aggregate_deadline"]))
    monkeypatch.delenv("LIMEN_WORK_KEY", raising=False)
    for seconds, expected in [(600, 700), (1800, 1900), (5000, 1900)]:
        observed.clear()
        assert (
            verify.cmd_changed(
                registry(),
                None,
                jobs=1,
                gate_timeout_seconds=1500,
                gate_output_bytes=1024,
                total_timeout_seconds=seconds,
            )
            == 0
        )
        assert observed and set(observed) == {expected}


def test_larger_ci_budget_never_extends_an_authenticated_keeper_window(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import Mock
    from limen.conduct import client

    verify = load_verify()
    observed = []
    monkeypatch.setattr(verify.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(verify, "changed_set", lambda _base: ["changed.py"])
    monkeypatch.setattr(verify, "select", lambda *_args: (["cheap"], []))
    monkeypatch.setattr(verify, "run_gate_wave", lambda *_args, **kw: not observed.append(kw["aggregate_deadline"]))
    keeper = Mock()
    keeper.reserve_growth.return_value = {"deadline": (datetime.now(timezone.utc) + timedelta(seconds=40)).isoformat()}
    monkeypatch.setattr(client, "client_from_env", lambda: keeper)
    monkeypatch.setenv("LIMEN_WORK_KEY", "approved-fixture")
    assert (
        verify.cmd_changed(
            registry(), None, jobs=1, gate_timeout_seconds=1500, gate_output_bytes=1024, total_timeout_seconds=1800
        )
        == 0
    )
    assert observed and all(100 < stamp <= 140 for stamp in observed)
    keeper.reserve_growth.assert_called_once()


def test_gate_budget_registry_extends_by_default_and_operator_value_is_a_ceiling():
    verify = load_verify()
    # No operator value: the registry budget is the default and may exceed the generic 300 s.
    assert verify.gate_budget(1500, None) == 1500.0
    assert verify.gate_budget(None, None) == verify.DEFAULT_GATE_TIMEOUT_SECONDS == 300.0
    # An explicit operator value is a ceiling over a declared budget, and the value for an undeclared one.
    assert verify.gate_budget(1500, 60.0) == 60.0
    assert verify.gate_budget(100, 1500.0) == 100.0
    assert verify.gate_budget(None, 45.0) == 45.0


def test_default_total_timeout_covers_the_largest_implicated_budget_within_the_cap():
    verify = load_verify()
    gates = {"a": {"timeout_seconds": 100}, "b": {"timeout_seconds": 1500}, "c": {}}
    assert verify.default_total_timeout(gates, []) == 600.0
    assert verify.default_total_timeout(gates, ["a", "c"]) == 600.0
    assert verify.default_total_timeout(gates, ["b"]) == 1800.0  # 1500 + 300 margin, at the cap
    assert verify.default_total_timeout({"x": {"timeout_seconds": 1800}}, ["x"]) == 1800.0


def _wave_deadlines(verify, monkeypatch, tmp_path, gate: dict, timeout_seconds):
    """Run one gate through the real run_gate_wave and return the deadline run_gate received."""
    seen: list[float] = []
    monkeypatch.setattr(verify.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(verify, "verification_fingerprint", lambda *_args, **_kw: "0" * 64)
    monkeypatch.setattr(verify, "cache_path", lambda gate_id, fingerprint: tmp_path / f"{fingerprint}.json")
    monkeypatch.setattr(verify, "run_gate", lambda *_args, **kw: not seen.append(kw["deadline"]))
    assert verify.run_gate_wave(
        ["g"],
        {"g": gate},
        {},
        ["changed.py"],
        jobs=1,
        timeout_seconds=timeout_seconds,
        output_limit_bytes=1024,
        wave_name="t",
        aggregate_deadline=100.0 + 1800.0,
    )
    return seen


def test_registry_budget_above_the_generic_default_is_not_cut_at_the_default(monkeypatch, tmp_path):
    verify = load_verify()
    gate = {"command": "true", "timeout_seconds": 1500}
    assert _wave_deadlines(verify, monkeypatch, tmp_path, gate, None) == [1600.0]  # 100 + 1500, not 100 + 300
    assert _wave_deadlines(verify, monkeypatch, tmp_path, gate, 60.0) == [160.0]  # explicit ceiling still shortens


def test_unset_budgets_derive_the_run_deadline_from_the_implicated_set(monkeypatch):
    verify = load_verify()
    observed: list[float] = []
    reg = registry()
    reg["gates"]["cheap"]["timeout_seconds"] = 1500
    monkeypatch.setattr(verify.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(verify, "changed_set", lambda _base: ["changed.py"])
    monkeypatch.setattr(verify, "run_gate_wave", lambda *_args, **kw: not observed.append(kw["aggregate_deadline"]))
    monkeypatch.delenv("LIMEN_WORK_KEY", raising=False)
    monkeypatch.setattr(verify, "select", lambda *_args: (["cheap"], []))
    assert verify.cmd_changed(reg, None, jobs=1, gate_timeout_seconds=None, gate_output_bytes=1024) == 0
    assert set(observed) == {100.0 + 1800.0}
    observed.clear()
    monkeypatch.setattr(verify, "select", lambda *_args: (["heavy"], []))  # no declared budget -> legacy 600
    monkeypatch.setattr(verify, "heavy_admission", lambda **_kw: nullcontext())
    assert verify.cmd_changed(reg, None, jobs=1, gate_timeout_seconds=None, gate_output_bytes=1024) == 0
    assert set(observed) == {100.0 + 600.0}


def test_widened_default_deadline_never_extends_a_keeper_window(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import Mock
    from limen.conduct import client

    verify = load_verify()
    observed: list[float] = []
    reg = registry()
    reg["gates"]["cheap"]["timeout_seconds"] = 1500
    monkeypatch.setattr(verify.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(verify, "changed_set", lambda _base: ["changed.py"])
    monkeypatch.setattr(verify, "select", lambda *_args: (["cheap"], []))
    monkeypatch.setattr(verify, "run_gate_wave", lambda *_args, **kw: not observed.append(kw["aggregate_deadline"]))
    keeper = Mock()
    keeper.reserve_growth.return_value = {"deadline": (datetime.now(timezone.utc) + timedelta(seconds=40)).isoformat()}
    monkeypatch.setattr(client, "client_from_env", lambda: keeper)
    monkeypatch.setenv("LIMEN_WORK_KEY", "approved-fixture")
    assert verify.cmd_changed(reg, None, jobs=1, gate_timeout_seconds=None, gate_output_bytes=1024) == 0
    assert observed and all(100 < stamp <= 140 for stamp in observed)
