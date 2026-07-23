from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "life-organ.py"


def load_life_organ(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_LIFE_DIR", str(tmp_path / "_life-private"))
    spec = importlib.util.spec_from_file_location("life_organ_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def private_chart() -> dict:
    return {
        "platforms": {"console": {"owner": "Private Owner"}},
        "accounts": [
            {
                "platform": "ConsoleNet",
                "email": "private-main@example.test",
                "handle": "private-handle-main",
                "role": "MAIN",
                "note": "private account note",
            },
            {
                "platform": "ConsoleNet",
                "email": "private-alt@example.test",
                "handle": "private-handle-alt",
                "note": "merge this private account",
            },
        ],
        "assets": [
            {
                "name": "Private Save Archive",
                "owned_on": ["ConsoleNet"],
                "note": "private asset note",
            }
        ],
        "open_actions": [
            {
                "ask": "Check the private console save",
                "why": "private action reason",
                "status": "open",
            }
        ],
        "subscriptions": [],
    }


def assert_private_strings_absent(encoded: str) -> None:
    private_needles = [
        "Private Owner",
        "private-main@example.test",
        "private-alt@example.test",
        "private-handle-main",
        "private-handle-alt",
        "private account note",
        "Private Save Archive",
        "private asset note",
        "Check the private console save",
        "private action reason",
    ]
    for needle in private_needles:
        assert needle not in encoded


def test_census_is_counts_only(tmp_path: Path, monkeypatch) -> None:
    module = load_life_organ(tmp_path, monkeypatch)
    derived = module.derive(private_chart())

    census = module.census(derived)

    assert census == {
        "accounts": 2,
        "assets": 1,
        "open_actions": 1,
        "purge_due": 0,
        "purge_upcoming": 0,
        "duplicate_accounts": 2,
    }
    encoded = json.dumps(census, sort_keys=True)
    assert_private_strings_absent(encoded)
    assert str(tmp_path) not in encoded


def test_repo_liveness_stamp_is_counts_only(tmp_path: Path, monkeypatch) -> None:
    module = load_life_organ(tmp_path, monkeypatch)
    derived = module.derive(private_chart())

    module.write_stamp(present=True, d=derived)

    stamp = tmp_path / "logs" / "life-organ-state.json"
    encoded = stamp.read_text(encoding="utf-8")
    assert '"accounts": 2' in encoded
    assert '"duplicate_accounts": 2' in encoded
    assert_private_strings_absent(encoded)
    assert str(tmp_path) not in encoded
