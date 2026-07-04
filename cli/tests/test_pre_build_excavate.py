from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _fake_gh(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "pr" ] && [ "${2:-}" = "list" ]; then
  state=""
  while [ $# -gt 0 ]; do
    if [ "$1" = "--state" ]; then state="${2:-}"; shift 2; continue; fi
    shift
  done
  if [ "$state" = "open" ]; then
    printf '#12\\t[open]\\t@agent\\tmoneta-checkout rail\\n'
  else
    printf '#9\\t[merged]\\tlicence return path\\n'
  fi
  exit 0
fi
if [ "${1:-}" = "api" ]; then
  printf 'abc1234\\tship checkout page\\n'
  exit 0
fi
if [ "${1:-}" = "repo" ] && [ "${2:-}" = "view" ]; then
  exit 0
fi
exit 99
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    return fake_bin


def _run(tmp_path: Path, *keywords: str) -> subprocess.CompletedProcess[str]:
    fake_bin = _fake_gh(tmp_path)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / "pre-build-excavate.sh"), "organvm/example", *keywords],
        text=True,
        capture_output=True,
        env=env,
        timeout=5,
    )


def test_pre_build_excavate_flags_literal_keyword_hits(tmp_path: Path) -> None:
    result = _run(tmp_path, "checkout")

    assert result.returncode == 3
    assert "LIKELY-DUP" in result.stdout
    assert "ship checkout page" in result.stdout


def test_pre_build_excavate_keyword_matching_is_fixed_string(tmp_path: Path) -> None:
    result = _run(tmp_path, "moneta.checkout")

    assert result.returncode == 0
    assert "CLEAR" in result.stdout
    assert "LIKELY-DUP" not in result.stdout
