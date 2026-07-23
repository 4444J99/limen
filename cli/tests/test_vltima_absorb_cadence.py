from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "vltima-absorb-cadence.py"


def _load(name: str = "vltima_absorb_cadence_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_default_cadence_dry_run_plans_safe_chain() -> None:
    cadence = _load("vltima_absorb_default")

    receipt = cadence.build_receipt(
        execute=False,
        materialize_private=False,
        stop_on_failure=True,
        timeout=10,
    )
    step_ids = [item["id"] for item in receipt["results"]]

    assert receipt["status"] == "planned"
    assert receipt["materialize_private"] is False
    assert "capture" in step_ids
    assert "materialize-private" not in step_ids
    assert step_ids[-2:] == ["prior-excavations", "result-digest"]


def test_materialize_private_is_explicit_opt_in() -> None:
    cadence = _load("vltima_absorb_materialize")

    receipt = cadence.build_receipt(
        execute=False,
        materialize_private=True,
        stop_on_failure=True,
        timeout=10,
    )
    materialize = [item for item in receipt["results"] if item["id"] == "materialize-private"]

    assert len(materialize) == 1
    assert "--materialize" in materialize[0]["command"]
    assert receipt["privacy"]["raw_materialization_opt_in"] is True


def test_render_markdown_records_contract_and_commands() -> None:
    cadence = _load("vltima_absorb_markdown")
    receipt = cadence.build_receipt(
        execute=False,
        materialize_private=False,
        stop_on_failure=True,
        timeout=10,
    )

    markdown = cadence.render_markdown(receipt)

    assert "# VLTIMA Absorption Cadence" in markdown
    assert "brainstorms do not become current authority" in markdown
    assert "scripts/session-corpus-ledger.py --write --all" in markdown
    assert "--materialize-private" in markdown


def test_render_markdown_redacts_absolute_home_paths() -> None:
    cadence = _load("vltima_absorb_public_paths")
    receipt = {
        "generated_at": "2026-07-06T00:00:00+00:00",
        "status": "ok",
        "mode": "write",
        "materialize_private": False,
        "results": [
            {
                "id": "capture",
                "phase": "capture",
                "status": "ok",
                "command": "python3 scripts/session-corpus-ledger.py --write --all",
                "reason": "test",
                "stdout_tail": ["/Users/4jp/Workspace/limen/docs/session-corpus-ledger.md"],
                "stderr_tail": [],
            }
        ],
    }

    markdown = cadence.render_markdown(receipt)

    assert "/Users/4jp" not in markdown
    assert "$LIMEN_ROOT/docs/session-corpus-ledger.md" in markdown
