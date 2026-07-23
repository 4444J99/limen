from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "vltima-result-digest.py"
NOW = dt.datetime(2026, 7, 6, tzinfo=dt.UTC)


def _load(name: str = "vltima_result_digest_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _claim(**overrides):
    claim = {
        "id": "surface:test:subject",
        "surface": "surface",
        "lane": "lane",
        "claim_type": "test",
        "subject": "subject",
        "summary": "current claim",
        "metric": "count",
        "value": 1,
        "generated_at": "2026-07-06T00:00:00+00:00",
        "evidence_label": "fixture",
        "source_status": "current",
        "next_action": "",
        "recurrence": 1,
    }
    claim.update(overrides)
    return claim


def test_redact_sensitive_values_blocks_body_prompt_and_raw_secret() -> None:
    digest = _load("vltima_result_redaction")

    cleaned = digest.redact_value(
        {
            "body": "SECRET_PROMPT_BODY",
            "prompt": "another secret",
            "safe": "use SECRET_VALUE carefully",
            "prompt_events": 12,
        }
    )

    rendered = json.dumps(cleaned, sort_keys=True)
    assert "SECRET_PROMPT_BODY" not in rendered
    assert "SECRET_VALUE" not in rendered
    assert cleaned["prompt_events"] == 12


def test_classify_fresh_current_result_as_current_doctrine() -> None:
    digest = _load("vltima_result_current")

    classified = digest.classify_claim(_claim(), now=NOW)

    assert classified["authority"] == "current_doctrine"
    assert classified["trust"] == "high"


def test_classify_old_recurring_result_as_living_lineage() -> None:
    digest = _load("vltima_result_lineage")

    classified = digest.classify_claim(
        _claim(generated_at="2025-01-01T00:00:00+00:00", recurrence=7),
        now=NOW,
    )

    assert classified["authority"] == "living_lineage"


def test_classify_old_oneoff_result_as_dormant_ore() -> None:
    digest = _load("vltima_result_dormant")

    classified = digest.classify_claim(
        _claim(generated_at="2025-01-01T00:00:00+00:00", recurrence=1),
        now=NOW,
    )

    assert classified["authority"] == "dormant_ore"


def test_classify_superseded_result_as_superseded_material() -> None:
    digest = _load("vltima_result_superseded")

    classified = digest.classify_claim(
        _claim(summary="root is remote-superseded by current main"),
        now=NOW,
    )

    assert classified["authority"] == "superseded_material"


def test_classify_private_auth_result_as_quarantined_ghost() -> None:
    digest = _load("vltima_result_quarantined")

    classified = digest.classify_claim(
        _claim(subject="auth_credentials", source_status="private-only"),
        now=NOW,
    )

    assert classified["authority"] == "quarantined_ghost"


def test_display_subject_redacts_local_paths() -> None:
    digest = _load("vltima_result_path_redaction")

    rendered = digest.display_subject("/Users/4jp/Workspace/limen/.claude/worktrees/example-root")

    assert rendered == "local-path:example-root"
    assert "/Users/4jp" not in rendered


def test_build_digest_from_fixture_redacts_and_renders_cadence(tmp_path: Path) -> None:
    digest = _load("vltima_result_fixture")
    private_root = tmp_path / ".limen-private" / "session-corpus"
    lifecycle = private_root / "lifecycle"
    lifecycle.mkdir(parents=True)
    attack_path = lifecycle / "session-attack-paths.json"
    attack_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-06T00:00:00+00:00",
                "coverage": {"sessions": 2},
                "lane_counts": {"family": 2},
                "ranked_paths": [
                    {
                        "id": "session_lifecycle",
                        "kind": "family",
                        "lane": "family",
                        "next_action": "collapse repeats into receipts",
                        "prompt_events": 3,
                        "recency": "<=7d",
                        "score": 10,
                        "sessions": 2,
                    },
                    {
                        "id": "auth_credentials",
                        "kind": "family",
                        "lane": "parked",
                        "next_action": "SECRET_PROMPT_BODY must never leak",
                        "prompt_events": 2,
                        "recency": "<=7d",
                        "score": 9,
                        "sessions": 2,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    prior_index = lifecycle / "vltima-prior-excavations.json"
    prior_index.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-06T00:00:00+00:00",
                "surfaces": [
                    {
                        "id": "session-attack-paths",
                        "lane": "priority-routing",
                        "status": "current",
                        "generated_at": "2026-07-06T00:00:00+00:00",
                        "refresh_mode": "write-safe-redacted",
                        "tracked": [],
                        "logs": [],
                        "private": [
                            {
                                "label": ".limen-private/session-corpus/lifecycle/session-attack-paths.json",
                                "exists": True,
                                "path": str(attack_path),
                                "summary": {
                                    "kind": "json",
                                    "collection_counts": {"ranked_paths": 2},
                                    "generated_at": "2026-07-06T00:00:00+00:00",
                                },
                            }
                        ],
                        "tracked_present": 0,
                        "private_present": 1,
                        "logs_present": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = digest.build_digest(
        prior_index=prior_index,
        root=tmp_path,
        private_root=private_root,
        now=NOW,
        max_claims=50,
    )
    markdown = digest.render_markdown(result)
    rendered = json.dumps(result, sort_keys=True) + markdown

    assert "SECRET_PROMPT_BODY" not in rendered
    assert "Continual Absorption Cadence" in markdown
    assert "Claude has extra lifecycle phases" in markdown
    assert any(claim["subject"] == "session_lifecycle" for claim in result["claims"])
    assert any(claim["authority"] == "quarantined_ghost" for claim in result["claims"])


def test_missing_prior_index_explains_refresh_command(tmp_path: Path) -> None:
    digest = _load("vltima_result_missing_prior")

    try:
        digest.load_prior_index(tmp_path / "missing.json")
    except FileNotFoundError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected missing prior index failure")

    assert "vltima-prior-excavations.py --write" in message
