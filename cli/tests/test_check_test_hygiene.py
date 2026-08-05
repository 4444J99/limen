"""Tests for scripts/check-test-hygiene.py — the order-independence gate.

A fixture repo tree is built under tmp_path and scanned via --root/--baseline, so the test never
depends on the real repo layout.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-test-hygiene.py"

CONFTEST = (
    "import os\n"
    "import pytest\n\n\n"
    "@pytest.fixture(autouse=True)\n"
    "def _restore_os_environ():\n"
    "    saved = dict(os.environ)\n"
    "    try:\n"
    "        yield\n"
    "    finally:\n"
    "        os.environ.clear()\n"
    "        os.environ.update(saved)\n"
)


def _tree(tmp: Path, *, cli_conftest=True, api_conftest=True) -> None:
    for rel, present in (("cli/tests", cli_conftest), ("web/api/tests", api_conftest)):
        d = tmp / rel
        d.mkdir(parents=True, exist_ok=True)
        if present:
            (d / "conftest.py").write_text(CONFTEST, encoding="utf-8")


def run(tmp: Path, *extra):
    baseline = tmp / "baseline.txt"
    return subprocess.run(
        [sys.executable, str(CHECK), "--root", str(tmp), "--baseline", str(baseline), *extra],
        capture_output=True,
        text=True,
    )


def test_green_when_conftests_present_and_no_writes(tmp_path):
    _tree(tmp_path)
    (tmp_path / "cli/tests/test_ok.py").write_text(
        "def test_x(monkeypatch):\n    monkeypatch.setenv('A', 'b')\n", encoding="utf-8"
    )
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "OK" in r.stdout


def test_red_on_new_direct_write(tmp_path):
    _tree(tmp_path)
    (tmp_path / "cli/tests/test_leak.py").write_text(
        "import os\ndef test_x():\n    os.environ['LIMEN_LEAK'] = '1'\n", encoding="utf-8"
    )
    r = run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "test_leak.py::LIMEN_LEAK" in r.stdout


def test_direct_write_grandfathered_by_baseline(tmp_path):
    _tree(tmp_path)
    (tmp_path / "cli/tests/test_leak.py").write_text(
        "import os\ndef test_x():\n    os.environ['LIMEN_LEAK'] = '1'\n", encoding="utf-8"
    )
    # first --update folds it into the baseline → then the gate is green
    assert run(tmp_path, "--update").returncode == 0
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout


def test_red_on_missing_conftest(tmp_path):
    _tree(tmp_path, api_conftest=False)
    r = run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "web/api/tests/conftest.py MISSING" in r.stdout


def test_setdefault_and_putenv_detected(tmp_path):
    _tree(tmp_path)
    (tmp_path / "cli/tests/test_more.py").write_text(
        "import os\ndef test_a():\n    os.environ.setdefault('X', '1')\ndef test_b():\n    os.putenv('Y', '2')\n",
        encoding="utf-8",
    )
    r = run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "environ.setdefault" in r.stdout and "os.putenv" in r.stdout


def test_double_equals_not_flagged(tmp_path):
    _tree(tmp_path)
    (tmp_path / "cli/tests/test_cmp.py").write_text(
        "import os\ndef test_x():\n    assert os.environ['PATH'] == os.environ['PATH']\n", encoding="utf-8"
    )
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout
