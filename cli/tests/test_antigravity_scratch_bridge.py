from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "antigravity-scratch-bridge.py"


def _load():
    spec = importlib.util.spec_from_file_location("antigravity_scratch_bridge", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_remote_preserved_repo(root: Path, name: str = "clean-root") -> Path:
    remote_parent = root.parent.parent if root.parent != root else root.parent
    remote = remote_parent / f"{root.parent.name}-{root.name}-{name}.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    repo = root / name
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "test@example.invalid"], repo)
    _git(["config", "user.name", "Test User"], repo)
    (repo / "README.md").write_text("preserved\n", encoding="utf-8")
    _git(["add", "README.md"], repo)
    _git(["commit", "-qm", "init"], repo)
    _git(["remote", "add", "origin", str(remote)], repo)
    _git(["push", "-q", "-u", "origin", "main"], repo)
    return repo


def _accepted_reap_proof(row: dict) -> tuple[list[dict], list[dict]]:
    preservation = [
        {
            "root": row["name"],
            "archive_verified": True,
            "archive_path": "/Volumes/Archive4T/limen-private/agy-scratch-preserve/demo/root",
            "private_receipt": ".limen-private/session-corpus/lifecycle/agy-scratch-preserve/demo/receipt.json",
            "private_receipt_sha256": "abc123",
            "head": row.get("head"),
            "disposition": row.get("disposition"),
            "size_bytes": row.get("size_bytes"),
        }
    ]
    acceptance = [
        {
            "accepted_at": "2026-07-06T05:00:00Z",
            "root": row["name"],
            "accepted": True,
            "archive_proof": "matching preservation event is archive_verified:true",
            "redaction_review": "private_archive_only",
            "redaction_proof": "raw scratch content remains in private archive only",
            "private_receipt_sha256": "abc123",
        }
    ]
    return preservation, acceptance


def test_clean_remote_preserved_root_is_reap_candidate(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    _make_remote_preserved_repo(scratch)

    report = bridge.build_report(scratch, min_idle_hours=0)
    row = report["roots"][0]

    assert row["name"] == "clean-root"
    assert row["kind"] == "git"
    assert row["disposition"] == "safe_reap_candidate"
    assert row["remote_preserved"] is True
    assert report["summary"]["by_disposition"] == {"safe_reap_candidate": 1}


def test_unborn_git_root_has_no_fake_head(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    repo = scratch / "empty-root"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)

    report = bridge.build_report(scratch, min_idle_hours=0)
    row = report["roots"][0]

    assert row["name"] == "empty-root"
    assert row["kind"] == "git"
    assert row["head"] is None
    assert row["disposition"] == "preserve_required"
    assert row["reason"] == "clean-but-head-not-proven-on-remote"


def test_dirty_root_requires_bridge(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    repo = _make_remote_preserved_repo(scratch, "dirty-root")
    (repo / "new_delta.py").write_text("unbridged work\n", encoding="utf-8")

    report = bridge.build_report(scratch, min_idle_hours=0)
    row = report["roots"][0]

    assert row["disposition"] == "bridge_required"
    assert row["reason"] == "dirty-or-untracked"
    assert row["dirty_entries"] == 1


def test_container_root_requires_nested_review(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    parent = scratch / "container"
    parent.mkdir()
    nested = parent / "nested-repo"
    _make_remote_preserved_repo(parent, "nested-repo")
    assert nested.exists()

    report = bridge.build_report(scratch, min_idle_hours=0)
    row = report["roots"][0]

    assert row["name"] == "container"
    assert row["kind"] == "container"
    assert row["disposition"] == "container_review_required"
    assert row["nested_git_roots"] == 1
    assert row["nested_by_disposition"] == {"safe_reap_candidate": 1}


def test_apply_safe_reap_requires_verified_archive_and_acceptance(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    clean = _make_remote_preserved_repo(scratch, "clean-root")
    dirty = _make_remote_preserved_repo(scratch, "dirty-root")
    (dirty / "new_delta.py").write_text("unbridged work\n", encoding="utf-8")

    report = bridge.build_report(scratch, min_idle_hours=0)
    reap = bridge.apply_safe_reap(report, min_idle_hours=0)

    assert reap["summary"]["reaped"] == 0
    assert reap["summary"]["skipped"] == 1
    assert reap["summary"]["failed"] == 0
    assert reap["results"][0]["reason"] == "missing-verified-archive-preservation"
    assert clean.exists()
    assert dirty.exists()


def test_apply_safe_reap_deletes_only_with_matching_archive_acceptance(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    clean = _make_remote_preserved_repo(scratch, "clean-root")

    report = bridge.build_report(scratch, min_idle_hours=0)
    row = report["roots"][0]
    preservation, acceptance = _accepted_reap_proof(row)
    reap = bridge.apply_safe_reap(
        report, min_idle_hours=0, preservation_history=preservation, acceptance_history=acceptance
    )

    assert reap["summary"]["reaped"] == 1
    assert reap["summary"]["skipped"] == 0
    assert reap["summary"]["failed"] == 0
    assert reap["results"][0]["reason"] == "clean-idle-remote-preserved"
    assert reap["results"][0]["private_receipt_sha256"] == "abc123"
    assert reap["results"][0]["archive_proof"] == "matching preservation event is archive_verified:true"
    assert reap["results"][0]["redaction_review"] == "private_archive_only"
    assert reap["results"][0]["redaction_proof"] == "raw scratch content remains in private archive only"
    assert not clean.exists()


def test_apply_safe_reap_requires_acceptance_archive_and_redaction_proofs(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    clean = _make_remote_preserved_repo(scratch, "clean-root")

    report = bridge.build_report(scratch, min_idle_hours=0)
    for required_field in bridge.REAP_ACCEPTANCE_REQUIRED_FIELDS:
        preservation, acceptance = _accepted_reap_proof(report["roots"][0])
        acceptance[0].pop(required_field)

        reap = bridge.apply_safe_reap(
            report, min_idle_hours=0, preservation_history=preservation, acceptance_history=acceptance
        )

        assert reap["summary"]["reaped"] == 0
        assert reap["summary"]["skipped"] == 1
        assert reap["results"][0]["reason"] == "missing-human-reap-acceptance"
        assert clean.exists()


def test_reap_history_appends_once_and_renders_cumulative_receipt(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    clean = _make_remote_preserved_repo(scratch, "clean-root")
    history = tmp_path / "history.jsonl"

    report = bridge.build_report(scratch, min_idle_hours=0)
    preservation, acceptance = _accepted_reap_proof(report["roots"][0])
    report["reap"] = bridge.apply_safe_reap(
        report, min_idle_hours=0, preservation_history=preservation, acceptance_history=acceptance
    )
    report["post_reap_summary"] = bridge.build_report(scratch, min_idle_hours=0)["summary"]
    report["reap_history"] = bridge.append_reap_history(report, history)
    report["reap_history"] = bridge.append_reap_history(report, history)

    assert not clean.exists()
    assert len(history.read_text(encoding="utf-8").splitlines()) == 1
    assert len(report["reap_history"]) == 1
    assert report["reap_history"][0]["summary"]["reaped"] == 1

    rendered = bridge.render_markdown(report)

    assert "## Reap History" in rendered
    assert "Cumulative reaped roots: `1`" in rendered
    assert "clean-root" in rendered


def test_render_markdown_groups_staged_missing_fingerprints_without_root_filenames():
    bridge = _load()
    report = {
        "generated_at": "2026-07-06T00:00:00+00:00",
        "scratch_root": "/tmp/scratch",
        "summary": {
            "total_roots": 2,
            "total_size": "2 KiB",
            "safe_reap_size": "0 B",
            "by_disposition": {"bridge_required": 2},
        },
        "roots": [
            {
                "name": "one",
                "size": "1 KiB",
                "kind": "git",
                "disposition": "bridge_required",
                "reason": "dirty-or-untracked",
                "repo": "example/one",
                "head": "abc123",
                "dirty_profile": {
                    "fingerprint": "full-one",
                    "staged_deleted_hash": "same-deleted",
                    "staged_deleted_count": 2,
                    "staged_deleted_untracked_overlap_count": 0,
                    "staged_deleted_absent_count": 2,
                    "untracked_count": 1,
                    "top_buckets": {"(root)": 1},
                    "staged_deleted_buckets": {"claude": 2},
                    "staged_deleted_absent_buckets": {"claude": 1},
                },
            },
            {
                "name": "two",
                "size": "1 KiB",
                "kind": "git",
                "disposition": "bridge_required",
                "reason": "dirty-or-untracked",
                "repo": "example/two",
                "head": "def456",
                "dirty_profile": {
                    "fingerprint": "full-two",
                    "staged_deleted_hash": "same-deleted",
                    "staged_deleted_count": 2,
                    "staged_deleted_untracked_overlap_count": 1,
                    "staged_deleted_absent_count": 1,
                    "untracked_count": 1,
                    "top_buckets": {"(root)": 1},
                    "staged_deleted_buckets": {"claude": 2},
                    "staged_deleted_absent_buckets": {"claude": 1},
                },
            },
        ],
    }

    rendered = bridge.render_markdown(report)

    assert "## Repeated Staged-Missing Fingerprints" in rendered
    assert "`one`, `two`" in rendered
    assert "`claude:2`" in rendered
    assert "Same path untracked" in rendered
    assert "Absent from worktree" in rendered
    assert "`0-1`" in rendered
    assert "`1-2`" in rendered
    assert "DISCOVERY.md" not in rendered


def test_render_markdown_shows_redacted_preservation_history():
    bridge = _load()
    report = {
        "generated_at": "2026-07-06T00:00:00+00:00",
        "scratch_root": "/tmp/scratch",
        "summary": {
            "total_roots": 1,
            "total_size": "1 KiB",
            "safe_reap_size": "0 B",
            "by_disposition": {"bridge_required": 1},
        },
        "roots": [],
        "preservation_history": [
            {
                "preserved_at": "2026-07-06T00:01:00Z",
                "root": "scratch-a",
                "status": "external_archive_preserved",
                "size_bytes": 1024,
                "archive_status": "verified",
                "archive_verified": True,
                "private_receipt": ".limen-private/session-corpus/lifecycle/agy-scratch-preserve/demo/receipt.json",
            }
        ],
    }

    rendered = bridge.render_markdown(report)

    assert "## Preservation History" in rendered
    assert "External archives verified: `1`" in rendered
    assert "scratch-a" in rendered
    assert "receipt.json" in rendered


def test_preserve_root_returns_final_private_receipt_hash(tmp_path: Path, monkeypatch):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    repo = _make_remote_preserved_repo(scratch, "dirty-root")
    (repo / "delta.txt").write_text("unbridged work\n", encoding="utf-8")
    monkeypatch.setattr(bridge, "PRIVATE_PRESERVE_ROOT", tmp_path / "private")
    monkeypatch.setattr(bridge, "ARCHIVE_PRESERVE_ROOT", tmp_path / "archive")

    report = bridge.build_report(scratch, min_idle_hours=0)
    receipt = bridge.preserve_root(report["roots"][0], scratch.resolve(), min_idle_hours=0, timeout=30)
    receipt_files = list((tmp_path / "private").rglob("receipt.json"))

    assert len(receipt_files) == 1
    private_receipt = json.loads(receipt_files[0].read_text(encoding="utf-8"))
    assert "private_receipt_sha256" not in private_receipt
    assert receipt["private_receipt_sha256"] == bridge.file_sha256(receipt_files[0])
    assert receipt["private_receipt"].endswith("receipt.json")


def test_append_preservation_history_repairs_existing_private_receipt_hash(tmp_path: Path):
    bridge = _load()
    receipt_file = tmp_path / "private" / "receipt.json"
    receipt_file.parent.mkdir()
    receipt_file.write_text('{"private_receipt_sha256":"old-self-hash","receipt":"final"}\n', encoding="utf-8")
    history = tmp_path / "preservation.jsonl"
    stale_event = {
        "preserved_at": "2026-07-06T00:00:00Z",
        "root": "scratch-a",
        "status": "external_archive_preserved",
        "private_receipt": str(receipt_file),
        "private_receipt_sha256": "stale",
    }
    history.write_text(json.dumps(stale_event, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    updated = bridge.append_preservation_history([], path=history)
    persisted = json.loads(history.read_text(encoding="utf-8").strip())
    private_receipt = json.loads(receipt_file.read_text(encoding="utf-8"))

    assert "private_receipt_sha256" not in private_receipt
    assert updated[0]["private_receipt_sha256"] == bridge.file_sha256(receipt_file)
    assert persisted["private_receipt_sha256"] == bridge.file_sha256(receipt_file)
