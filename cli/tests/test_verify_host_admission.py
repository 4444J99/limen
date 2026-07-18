from __future__ import annotations

import importlib.util
from contextlib import contextmanager
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
        lambda gate_id, *_args: not events.append(f"gate:{gate_id}"),
    )
    monkeypatch.setattr(verify, "heavy_admission", held)
    monkeypatch.setenv("LIMEN_VERIFY_LOCK_FILE", str(tmp_path / "verify.lock"))

    assert verify.cmd_changed(registry(), None) == 0
    assert events == ["gate:cheap", "acquire", "gate:heavy", "gate:serialized", "release"]


def test_scoped_verifier_returns_temporary_failure_on_admission_denial(monkeypatch) -> None:
    verify = load_verify()

    @contextmanager
    def denied(*_args, **_kwargs):
        raise verify.HostAdmissionFailure("vitals-shed")
        yield  # pragma: no cover

    monkeypatch.setattr(verify, "changed_set", lambda _base: ["changed.py"])
    monkeypatch.setattr(verify, "select", lambda _registry, _changed: (["heavy"], []))
    monkeypatch.setattr(verify, "run_gate", lambda *_args: True)
    monkeypatch.setattr(verify, "heavy_admission", denied)

    assert verify.cmd_changed(registry(), None) == 75


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
    monkeypatch.setattr(verify, "run_gate", lambda *_args: True)

    assert verify.cmd_changed(registry(), None) == 75


def test_verify_whole_takes_legacy_flock_before_host_admission() -> None:
    text = (ROOT / "scripts" / "verify-whole.sh").read_text(encoding="utf-8")
    assert text.index("fcntl.flock") < text.index('host_admission_acquire "verify-whole"')
    assert "trap host_admission_exit_trap EXIT" in text


def test_verify_scoped_remains_contractual_thin_wrapper() -> None:
    lines = (ROOT / "scripts" / "verify-scoped.sh").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 20
    assert any('exec python3 "$ROOT/scripts/verify.py" --changed' in line for line in lines)
