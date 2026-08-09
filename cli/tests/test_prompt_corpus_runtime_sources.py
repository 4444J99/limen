from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from limen.prompt_corpus import (
    LedgerPaths,
    _archive_custody_signature,
    preserve_raw_object,
    raw_object_reference,
    validate_raw_references,
)


ROOT = Path(__file__).resolve().parents[2]
ATOM_SCRIPT = ROOT / "scripts" / "prompt-atom-ledger.py"


def _occurrence(text: str = "an exact private prompt") -> tuple[dict[str, str], str]:
    prompt_hash = hashlib.sha256(text.encode()).hexdigest()
    return (
        {
            "occurrence_id": "po-fixture",
            "prompt_hash": prompt_hash,
            "raw_object": raw_object_reference(prompt_hash),
        },
        prompt_hash,
    )


def _write_archive_manifest(paths: LedgerPaths, objects: list[dict[str, str]]) -> None:
    paths.private_dir.mkdir(parents=True, exist_ok=True)
    (paths.private_dir / "raw-archive-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "limen.prompt_raw_archive_manifest.v1",
                "objects": objects,
            }
        )
    )


def _write_custody_receipt(
    paths: LedgerPaths,
    raw_object: str,
    prompt_hash: str,
    name: str = "custody-receipts/fixture.json",
    text: str = "an exact private prompt",
) -> str:
    archive_relative = Path("cold-archive") / raw_object
    archive = paths.private_dir / archive_relative
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(gzip.compress(text.encode()))
    archive.chmod(0o400)

    receipt = paths.private_dir / name
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "limen.prompt_raw_archive_custody_receipt.v1",
                "raw_object": raw_object,
                "prompt_hash": prompt_hash,
                "archive_location": str(archive_relative),
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        )
    )
    return name


def _load_atom_script():
    spec = importlib.util.spec_from_file_location("prompt_atom_runtime_source_test", ATOM_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_missing_raw_object_requires_exact_archive_custody(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, _prompt_hash = _occurrence()

    errors = validate_raw_references(paths, [occurrence], verify_content=True)

    assert errors == ["po-fixture: private raw object is missing"]


def test_exact_archive_manifest_substitutes_for_cold_object(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, prompt_hash = _occurrence()
    _write_archive_manifest(
        paths,
        [
            {
                "raw_object": occurrence["raw_object"],
                "prompt_hash": prompt_hash,
                "custody_receipt": _write_custody_receipt(
                    paths,
                    occurrence["raw_object"],
                    prompt_hash,
                ),
            }
        ],
    )

    assert validate_raw_references(paths, [occurrence], verify_content=True) == []


def test_archive_receipt_cannot_stand_in_for_missing_archived_bytes(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, prompt_hash = _occurrence()
    receipt = _write_custody_receipt(paths, occurrence["raw_object"], prompt_hash)
    receipt_payload = json.loads((paths.private_dir / receipt).read_text())
    (paths.private_dir / receipt_payload["archive_location"]).unlink()
    _write_archive_manifest(
        paths,
        [
            {
                "raw_object": occurrence["raw_object"],
                "prompt_hash": prompt_hash,
                "custody_receipt": receipt,
            }
        ],
    )

    errors = validate_raw_references(paths, [occurrence], verify_content=True)

    assert "archive_location does not resolve to a file" in "; ".join(errors)
    assert "private raw object is missing" in "; ".join(errors)


def test_archive_signature_normalizes_receipt_and_archive_paths(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, prompt_hash = _occurrence()
    receipt = _write_custody_receipt(paths, occurrence["raw_object"], prompt_hash)
    receipt_path = paths.private_dir / receipt
    payload = json.loads(receipt_path.read_text())
    payload["archive_location"] = f"  {payload["archive_location"]}  "
    receipt_path.write_text(json.dumps(payload))
    _write_archive_manifest(
        paths,
        [
            {
                "raw_object": occurrence["raw_object"],
                "prompt_hash": prompt_hash,
                "custody_receipt": f"  {receipt}  ",
            }
        ],
    )

    assert validate_raw_references(paths, [occurrence], verify_content=True) == []
    before = _archive_custody_signature(paths)
    (paths.private_dir / payload["archive_location"].strip()).unlink()

    assert _archive_custody_signature(paths) != before


def test_archive_signature_rejects_non_regular_archive(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, prompt_hash = _occurrence()
    receipt = _write_custody_receipt(paths, occurrence["raw_object"], prompt_hash)
    receipt_payload = json.loads((paths.private_dir / receipt).read_text())
    archive = paths.private_dir / receipt_payload["archive_location"]
    archive.unlink()
    archive.mkdir()
    _write_archive_manifest(
        paths,
        [
            {
                "raw_object": occurrence["raw_object"],
                "prompt_hash": prompt_hash,
                "custody_receipt": receipt,
            }
        ],
    )

    errors = validate_raw_references(paths, [occurrence], verify_content=True)

    assert "archive_location does not resolve to a regular file" in "; ".join(errors)
    assert _archive_custody_signature(paths)


def test_archive_signature_changes_when_archived_bytes_disappear(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, prompt_hash = _occurrence()
    receipt = _write_custody_receipt(paths, occurrence["raw_object"], prompt_hash)
    _write_archive_manifest(
        paths,
        [
            {
                "raw_object": occurrence["raw_object"],
                "prompt_hash": prompt_hash,
                "custody_receipt": receipt,
            }
        ],
    )
    before = _archive_custody_signature(paths)
    receipt_payload = json.loads((paths.private_dir / receipt).read_text())
    (paths.private_dir / receipt_payload["archive_location"]).unlink()

    assert _archive_custody_signature(paths) != before


def test_archive_manifest_cannot_bind_the_wrong_digest(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, _prompt_hash = _occurrence()
    wrong_hash = "b" * 64
    _write_archive_manifest(
        paths,
        [
            {
                "raw_object": occurrence["raw_object"],
                "prompt_hash": wrong_hash,
                "custody_receipt": "ignored-because-manifest-row-is-invalid.json",
            }
        ],
    )

    errors = validate_raw_references(paths, [occurrence], verify_content=True)

    assert "raw_object does not match prompt_hash" in "; ".join(errors)
    assert "private raw object is missing" in "; ".join(errors)


def test_manifest_never_masks_a_present_corrupt_object(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, prompt_hash = _occurrence()
    relative = preserve_raw_object(paths, prompt_hash, "an exact private prompt")
    candidate = paths.raw_objects / relative
    candidate.chmod(0o600)
    candidate.write_bytes(gzip.compress(b"different content"))
    candidate.chmod(0o400)
    _write_archive_manifest(
        paths,
        [
            {
                "raw_object": relative,
                "prompt_hash": prompt_hash,
                "custody_receipt": _write_custody_receipt(paths, relative, prompt_hash),
            }
        ],
    )

    errors = validate_raw_references(paths, [occurrence], verify_content=True)

    assert errors == ["po-fixture: private raw object digest mismatch"]


def test_archive_receipt_must_bind_the_same_digest(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, prompt_hash = _occurrence()
    wrong_hash = "c" * 64
    receipt = _write_custody_receipt(paths, occurrence["raw_object"], wrong_hash)
    _write_archive_manifest(
        paths,
        [
            {
                "raw_object": occurrence["raw_object"],
                "prompt_hash": prompt_hash,
                "custody_receipt": receipt,
            }
        ],
    )

    errors = validate_raw_references(paths, [occurrence], verify_content=True)

    assert "custody_receipt prompt_hash mismatch" in "; ".join(errors)
    assert "private raw object is missing" in "; ".join(errors)


def test_archive_manifest_cannot_mask_a_non_file_object(tmp_path: Path) -> None:
    paths = LedgerPaths.for_root(tmp_path)
    occurrence, prompt_hash = _occurrence()
    candidate = paths.raw_objects / occurrence["raw_object"]
    candidate.mkdir(parents=True)
    receipt = _write_custody_receipt(paths, occurrence["raw_object"], prompt_hash)
    _write_archive_manifest(
        paths,
        [
            {
                "raw_object": occurrence["raw_object"],
                "prompt_hash": prompt_hash,
                "custody_receipt": receipt,
            }
        ],
    )

    errors = validate_raw_references(paths, [occurrence], verify_content=True)

    assert errors == ["po-fixture: private raw object exists but is not a regular file"]


def test_runtime_root_follows_limen_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))

    module = _load_atom_script()
    lifecycle = module.load_lifecycle_module()

    assert lifecycle.RUNTIME_ROOT == tmp_path / ".agent-runtime"


def test_runtime_roots_survive_source_home_override(tmp_path: Path, monkeypatch) -> None:
    module = _load_atom_script()
    shim_home = tmp_path / "shim-home"
    monkeypatch.setattr(module, "SOURCE_HOME_OVERRIDE", shim_home)

    lifecycle = module.load_lifecycle_module()
    roots = [(source, Path(root), patterns) for source, root, patterns in lifecycle.LOCAL_SOURCES]

    assert ("codex-sessions", shim_home / ".codex" / "sessions", ("*",)) in roots
    assert ("codex-sessions", ROOT / ".agent-runtime" / "codex" / "sessions", ("*",)) in roots
    assert ("claude-projects", ROOT / ".agent-runtime" / "claude" / "projects", ("*",)) in roots
    assert (
        "gemini-tmp-agy",
        shim_home / ".gemini" / "tmp",
        ("capfill-agy-*/chats/*.jsonl", "*agy*/chats/*.jsonl"),
    ) in roots


def test_runtime_source_discovery_survives_source_home_override(tmp_path: Path, monkeypatch) -> None:
    module = _load_atom_script()
    runtime_root = tmp_path / ".agent-runtime"
    session = runtime_root / "codex" / "sessions" / "2026" / "08" / "08" / "rollout.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text("{}\n")
    monkeypatch.setattr(module, "SOURCE_HOME_OVERRIDE", tmp_path / "shim-home")
    lifecycle = SimpleNamespace(
        HOME=tmp_path / "shim-home",
        RUNTIME_ROOT=runtime_root,
        LOCAL_SOURCES=[("codex-sessions", runtime_root / "codex" / "sessions", ("*",))],
    )

    rows = module.regular_source_rows(lifecycle, None)

    assert rows.discovery_errors == []
    assert [Path(row["path"]) for row in rows] == [session]


def test_regular_source_rows_deduplicate_symlinked_runtime_aliases(tmp_path: Path) -> None:
    module = _load_atom_script()
    runtime = tmp_path / ".agent-runtime" / "codex" / "sessions"
    runtime.mkdir(parents=True)
    session = runtime / "rollout.jsonl"
    session.write_text("{}\n")
    shim = tmp_path / "shim-home"
    shim.mkdir()
    (shim / ".codex").symlink_to(tmp_path / ".agent-runtime", target_is_directory=True)
    lifecycle = SimpleNamespace(
        LOCAL_SOURCES=[
            ("codex-sessions", shim / ".codex" / "codex" / "sessions", ("*",)),
            ("codex-sessions", runtime, ("*",)),
        ]
    )

    rows = module.regular_source_rows(lifecycle, None)

    assert [Path(row["path"]).resolve() for row in rows] == [session.resolve()]


def test_source_relative_path_uses_the_containing_duplicate_root(tmp_path: Path) -> None:
    module = _load_atom_script()
    first = tmp_path / "home-sessions"
    second = tmp_path / "runtime-sessions"
    session = second / "2026" / "08" / "08" / "rollout-fixture.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text("")
    lifecycle = SimpleNamespace(
        LOCAL_SOURCES=[
            ("codex-sessions", first, ("*",)),
            ("codex-sessions", second, ("*",)),
        ]
    )

    relative = module.source_relative_path(lifecycle, "codex-sessions", session)

    assert relative == Path("2026/08/08/rollout-fixture.jsonl")
