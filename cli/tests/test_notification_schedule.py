"""Tests for the processless notification schedule editor."""

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "notification-schedule.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("notification_schedule", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replace_block_preserves_unrelated_crontab_and_is_idempotent():
    module = _load_module()
    original = "# existing owner\n5 4 * * * /usr/bin/true\n"
    block = f"{module.BEGIN}\n*/10 * * * * /usr/bin/true\n{module.END}"

    first = module.replace_block(original, block)
    second = module.replace_block(first, block)

    assert first == second
    assert first.startswith(original)
    assert first.count(module.BEGIN) == 1
    assert first.count(module.END) == 1


def test_replace_block_refuses_corrupt_markers():
    module = _load_module()
    with pytest.raises(ValueError, match="markers are corrupt"):
        module.replace_block(f"{module.BEGIN}\n", "replacement")
