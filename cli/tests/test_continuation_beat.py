import importlib.util
import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "continuation-beat.py"


def _load(monkeypatch, root: Path, photos: Path, portvs: Path):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_PHOTOS_UNIVERSE_ROOT", str(photos))
    monkeypatch.setenv("LIMEN_PORTVS_TRIPTYCH_ROOT", str(portvs))
    spec = importlib.util.spec_from_file_location("continuation_beat_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_census_is_counts_only(tmp_path, monkeypatch):
    root = tmp_path / "limen"
    photos = tmp_path / "private-photos-root"
    portvs = tmp_path / "private-portvs-root"
    triptych = portvs / "incubator" / "triptych-video-canon"
    docs = root / "docs"
    logs = root / "logs"
    docs.mkdir(parents=True)
    logs.mkdir(parents=True)
    photos.mkdir()
    triptych.mkdir(parents=True)
    (docs / "worktree-preservation-receipts.json").write_text(
        json.dumps({"receipts": [{"root": "private-root", "path": "/private/path"}]}),
        encoding="utf-8",
    )
    (logs / "continuation-beat.json").write_text(
        json.dumps({"ok": True, "steps": {"private-step": {"detail": "private detail"}}}),
        encoding="utf-8",
    )
    (logs / "codex-token-report.json").write_text(json.dumps({"private": "token detail"}), encoding="utf-8")

    module = _load(monkeypatch, root, photos, portvs)
    census = module.census()
    encoded = json.dumps(census, sort_keys=True)

    assert census == {
        "receipts_present": True,
        "preservation_receipts": 1,
        "last_log_present": True,
        "last_step_count": 1,
        "last_ok": True,
        "token_report_present": True,
        "photos_root_present": True,
        "portvs_root_present": True,
        "triptych_root_present": True,
        "lock_present": False,
    }
    assert "private-root" not in encoded
    assert "/private/path" not in encoded
    assert "private-step" not in encoded
    assert "token detail" not in encoded


def test_advance_photos_treats_nothing_to_prove_as_skip(tmp_path, monkeypatch):
    root = tmp_path / "limen"
    photos = tmp_path / "photos"
    portvs = tmp_path / "portvs"
    root.mkdir()
    photos.mkdir()
    portvs.mkdir()
    module = _load(monkeypatch, root, photos, portvs)

    monkeypatch.setattr(module, "repo_clean", lambda repo: True)
    monkeypatch.setattr(
        module,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a[0],
            1,
            "",
            "[photos-duplicate-proof] candidates missing - nothing to prove",
        ),
    )

    result = module.advance_photos(apply=False, limit_groups=25)

    assert result["ok"] is True
    assert result["skipped"] == "no duplicate candidates to prove"


def test_session_value_gate_blocks_continuation_lane_switch(tmp_path, monkeypatch):
    root = tmp_path / "limen"
    photos = tmp_path / "photos"
    portvs = tmp_path / "portvs"
    root.mkdir()
    photos.mkdir()
    portvs.mkdir()
    module = _load(monkeypatch, root, photos, portvs)

    def fake_run(args, cwd, timeout=120):
        assert args[:3] == ["python3", "scripts/session-value-review.py", "--gate"]
        return subprocess.CompletedProcess(
            args,
            10,
            json.dumps(
                {
                    "action": "switch_to_packetization",
                    "reason": "lane switch required",
                    "next_commands": ["python3 scripts/prompt-packet-ledger.py --write"],
                }
            ),
            "",
        )

    monkeypatch.setattr(module, "run", fake_run)

    result = module.session_value_gate()

    assert result["ok"] is False
    assert result["returncode"] == 10
    assert result["lane_switch"] is True
    assert result["action"] == "switch_to_packetization"
    assert result["next_command"] == "python3 scripts/prompt-packet-ledger.py --write"


def test_receipt_refresh_does_not_churn_timestamp_without_new_evidence(tmp_path, monkeypatch):
    root = tmp_path / "limen"
    photos = tmp_path / "photos"
    portvs = tmp_path / "portvs"
    (root / "docs").mkdir(parents=True)
    photos.mkdir()
    portvs.mkdir()
    receipt_path = root / "docs" / "worktree-preservation-receipts.json"
    receipt_path.write_text(json.dumps({"receipts": [{"root": "lane"}]}), encoding="utf-8")
    module = _load(monkeypatch, root, photos, portvs)
    monkeypatch.setattr(
        module,
        "pr_view",
        lambda *args, **kwargs: {
            "number": 7,
            "state": "OPEN",
            "isDraft": True,
            "headRefName": "work/lane",
            "headRefOid": "abc123",
            "url": "https://example.test/pull/7",
        },
    )
    times = iter(["2026-07-18T00:00:00Z", "2026-07-18T00:01:00Z"])
    monkeypatch.setattr(module, "utc_now", lambda: next(times))
    rows = [
        {
            "name": "lane",
            "path": str(tmp_path / "missing-worktree"),
            "repo": "organvm/example",
            "branch": "work/lane",
            "url": "https://example.test/pull/7",
        }
    ]

    first = module.update_pr_receipts(rows, apply=True)
    first_bytes = receipt_path.read_bytes()
    second = module.update_pr_receipts(rows, apply=True)

    assert first["updated"] == 1
    assert second["updated"] == 0
    assert receipt_path.read_bytes() == first_bytes


def test_merged_pr_custody_clears_exact_retry_ref_then_clean_beat_is_fixed_point(tmp_path, monkeypatch):
    root = tmp_path / "limen"
    photos = tmp_path / "photos"
    portvs = tmp_path / "portvs"
    remote = tmp_path / "remote.git"
    photos.mkdir()
    portvs.mkdir()

    def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True,
        )

    git(tmp_path, "init", "--bare", str(remote))
    git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    git(tmp_path, "clone", str(remote), str(root))
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "seed")
    git(root, "push", "-u", "origin", "main")

    module = _load(monkeypatch, root, photos, portvs)
    path = "foo-receipts.json"
    branch = module._main_preservation_branch([path])
    local_ref = f"refs/limen/continuation-beat/{branch.rsplit('/', 1)[-1]}"
    local_custody = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "checkout", "-b", branch)
    (root / path).write_text('{"settled": true}\n', encoding="utf-8")
    git(root, "add", path)
    git(root, "commit", "-m", "preserve receipt")
    custody = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "push", "origin", f"HEAD:refs/heads/{branch}")
    git(root, "checkout", "main")
    git(root, "update-ref", local_ref, local_custody)
    pr = {"head": "0" * 40, "state": "OPEN", "merged_at": None}

    def merged_gh(cwd, *args, timeout=120):
        assert args[:2] == ("pr", "list")
        return subprocess.CompletedProcess(
            args,
            0,
            json.dumps(
                [
                    {
                        "number": 7,
                        "url": "https://example.test/pull/7",
                        "headRefOid": pr["head"],
                        "state": pr["state"],
                        "mergedAt": pr["merged_at"],
                    }
                ]
            ),
            "",
        )

    monkeypatch.setattr(module, "gh", merged_gh)

    unverified = module.commit_paths(root, [path], "beat: unsettled", apply=True)
    assert unverified["deferred"] is True
    assert unverified["reason"] == "preservation-pr-head-unverified"
    assert module.git(root, "rev-parse", "--verify", local_ref).stdout.strip() == local_custody

    pr.update(
        {
            "head": custody,
            "state": "MERGED",
            "merged_at": "2026-07-18T00:00:00Z",
        }
    )
    settled = module.commit_paths(root, [path], "beat: settled", apply=True)
    fixed_point = module.commit_paths(root, [path], "beat: settled", apply=True)

    assert settled["custody_verified"] is True
    assert settled["custody_ref_cleared"] is True
    assert settled["settled"] is True
    assert module.git(root, "rev-parse", "--verify", local_ref).returncode != 0
    assert fixed_point == {"changed": False}
