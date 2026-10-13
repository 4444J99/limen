"""A process scratch directory must never create a second machine admission pool."""

import ctypes
import importlib.util
import os
import tempfile
from pathlib import Path

import pytest
from limen import host_admission

ROOT = Path(__file__).resolve().parents[2]


def test_auto_admission_root_ignores_process_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_ROOT", "auto")
    expected = host_admission.default_state_root()
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    assert host_admission.default_state_root() == expected


def test_linux_auto_root_is_shared_even_when_tmpdir_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_ROOT", "auto")
    monkeypatch.setattr(host_admission.sys, "platform", "linux")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    assert host_admission.default_state_root() == Path("/tmp") / f"limen-host-admission-{os.getuid()}"


def test_native_root_lookup_failure_blocks_instead_of_falling_back(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_ROOT", "auto")
    monkeypatch.setattr(host_admission.sys, "platform", "darwin")

    def unavailable(*_args, **_kwargs):
        raise OSError("native lookup unavailable")

    monkeypatch.setattr(ctypes, "CDLL", unavailable)
    with pytest.raises(ValueError, match="host_temp_root_unavailable"):
        host_admission.default_state_root()


def test_registered_explicit_root_override_remains_supported(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_ROOT", str(tmp_path / "$UID"))
    assert host_admission.default_state_root() == tmp_path / str(os.getuid())


def test_verification_flock_uses_admission_parent_and_honors_explicit_override(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("verify_shared_temp", ROOT / "scripts/verify.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    canonical = tmp_path / "host-os-temp"
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_ROOT", str(canonical / "limen-host-admission-501"))
    monkeypatch.delenv("LIMEN_VERIFY_LOCK_FILE", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "scratch"))
    assert verifier.verification_lock_path() == canonical / "limen-verify-whole.lock"
    monkeypatch.setenv("LIMEN_VERIFY_LOCK_FILE", str(tmp_path / "explicit.lock"))
    assert verifier.verification_lock_path() == tmp_path / "explicit.lock"
