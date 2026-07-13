import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CVSTOS = ROOT / "scripts" / "cvstos-organ.py"
VVLTVS = ROOT / "scripts" / "vvltvs-organ.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cvstos_malformed_env_knobs_fail_open(monkeypatch):
    monkeypatch.setenv("LIMEN_CVSTOS_DEBT_CAP_GB", "bad")
    monkeypatch.setenv("LIMEN_CVSTOS_REAPER_STALE_H", "nan")
    monkeypatch.setenv("LIMEN_CVSTOS_SCAN_CAP", "0")
    monkeypatch.setenv("LIMEN_AGY_SCRATCH_MIN_IDLE_H", "bad")

    mod = _load("cvstos_organ_test", CVSTOS)

    assert mod.DEBT_CAP_GB == 5
    assert mod.REAPER_STALE_H == 48
    assert mod.SCAN_ENTRY_CAP == 600000
    assert mod.AGY_SCRATCH_MIN_IDLE_H == 24


def test_cvstos_reports_unsafe_antigravity_scratch_roots():
    mod = _load("cvstos_organ_scratch_test", CVSTOS)

    assessment = {
        "debt": {"over_cap": False},
        "factory": {
            "cartridge_connected": True,
            "bin_orphans": {"measured": True, "count": 0},
        },
        "reapers": {"stale": 0},
        "worktree_has_debt": False,
        "antigravity_scratch": {
            "measured": True,
            "unsafe_dispositions": {"bridge_required": 2, "preserve_required": 1},
        },
    }

    failures = mod.failures(assessment)

    assert failures == [
        "Antigravity scratch roots need bridge/preserve/review before local deletion "
        "(bridge_required=2, preserve_required=1)"
    ]


def test_cvstos_allows_preserved_antigravity_scratch_roots():
    mod = _load("cvstos_organ_scratch_preserved_test", CVSTOS)

    assessment = {
        "debt": {"over_cap": False},
        "factory": {
            "cartridge_connected": True,
            "bin_orphans": {"measured": True, "count": 0},
        },
        "reapers": {"stale": 0},
        "worktree_has_debt": False,
        "antigravity_scratch": {
            "measured": True,
            "unsafe_dispositions": {"bridge_required": 2, "preserve_required": 1},
            "unsafe_preserved_dispositions": {"bridge_required": 2, "preserve_required": 1},
            "unsafe_unpreserved_dispositions": {},
        },
    }

    assert mod.failures(assessment) == []


def test_cvstos_requires_exact_zero_worktree_debt():
    mod = _load("cvstos_organ_exact_zero_worktree_test", CVSTOS)

    assessment = {
        "debt": {"over_cap": False},
        "factory": {
            "cartridge_connected": True,
            "bin_orphans": {"measured": True, "count": 0},
        },
        "reapers": {"stale": 0},
        "worktree_has_debt": True,
        "antigravity_scratch": {"measured": True, "unsafe_unpreserved_dispositions": {}},
    }

    assert mod.failures(assessment) == ["worktree lifecycle debt not at zero (worktree-debt.py --fail-on-debt)"]


def test_vvltvs_malformed_env_knobs_fail_open(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("LIMEN_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_VVLTVS_REVIEW_FLOOR", "bad")
    monkeypatch.setenv("LIMEN_VVLTVS_MIX_STALE_DAYS", "nan")

    mod = _load("vvltvs_organ_env_test", VVLTVS)

    assert mod.REVIEW_FLOOR == 10
    assert mod.MIX_STALE_DAYS == 7


def test_vvltvs_malformed_freshness_numbers_fail_open(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("LIMEN_WORKSPACE_ROOT", str(tmp_path))
    mod = _load("vvltvs_organ_freshness_test", VVLTVS)
    (tmp_path / "register.json").write_text(json.dumps({"date": "2020-01-01", "covered": 1}))

    rows = mod.vena(
        {"present": True, "total_repos": 10},
        {
            "registers": [
                "bad-row",
                {
                    "key": "profile-register",
                    "home": "register.json",
                    "tracks": [],
                    "freshness": {
                        "date_locator": "date",
                        "max_lag_days": "bad",
                        "coverage_locator": "covered",
                        "coverage_of": "total_repos",
                        "min_coverage": "bad",
                    },
                },
            ],
        },
    )

    assert rows[0]["key"] == "profile-register"
    assert rows[0]["state"] == "live"


def test_vvltvs_malformed_track_rows_fail_open(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("LIMEN_WORKSPACE_ROOT", str(tmp_path))
    mod = _load("vvltvs_organ_track_test", VVLTVS)
    (tmp_path / "register.json").write_text(json.dumps({"count": 2}))

    rows = mod.vena(
        {"present": True, "total_repos": 2},
        {
            "registers": [
                {
                    "key": "profile-register",
                    "home": "register.json",
                    "tracks": [
                        "bad-row",
                        {"key": "missing-locator"},
                        {"locator": "count", "ssot_key": "total_repos"},
                    ],
                },
            ],
        },
    )

    assert rows[0]["state"] == "live"
    assert rows[0]["diverge"] == []


def test_vvltvs_wordshort_bad_source_is_unmeasurable(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("LIMEN_WORKSPACE_ROOT", str(tmp_path))
    mod = _load("vvltvs_organ_wordshort_test", VVLTVS)
    (tmp_path / "face.yml").write_text("words: 6K+\n")

    out = mod.mirror(
        {"present": True, "total_words_numeric": "not-a-number"},
        [],
        {
            "faces": [
                "bad-row",
                {
                    "key": "profile",
                    "path": "face.yml",
                    "format": "yaml",
                    "checks": [
                        {
                            "metric": "words",
                            "locator": "words",
                            "source": "ssot",
                            "ssot_key": "total_words_numeric",
                            "kind": "wordshort",
                        }
                    ],
                },
            ]
        },
    )

    check = out["faces"][0]["checks"][0]
    assert check["metric"] == "words"
    assert check["state"] == "unmeasurable"


def test_vvltvs_malformed_face_checks_fail_open(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("LIMEN_WORKSPACE_ROOT", str(tmp_path))
    mod = _load("vvltvs_organ_face_check_test", VVLTVS)
    (tmp_path / "face.yml").write_text("words: 6K+\n")

    out = mod.mirror(
        {"present": True, "total_words_numeric": 6000},
        [],
        {
            "faces": [
                {
                    "key": "profile",
                    "path": "face.yml",
                    "format": "yaml",
                    "checks": [
                        "bad-row",
                        {"metric": "missing-locator"},
                        {
                            "metric": "words",
                            "locator": "words",
                            "source": "ssot",
                            "ssot_key": "total_words_numeric",
                            "kind": "wordshort",
                        },
                    ],
                },
            ]
        },
    )

    checks = out["faces"][0]["checks"]
    assert checks[0]["metric"] == "missing-locator"
    assert checks[0]["state"] == "unmeasurable"
    assert checks[1]["metric"] == "words"
    assert checks[1]["state"] == "agree"
