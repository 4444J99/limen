"""A spent keeper storage plan is a homed lever, not a rung defect.

The Cloudflare Durable Objects free tier has a daily write ceiling. When it is reached
the keeper answers every write with HTTP 500 `Exceeded allowed rows written in Durable
Objects free tier`, which the client raises as :class:`BrokerQuotaExhausted`.

`heal-board.py` and `self-heal.py` already treat that as EX_TEMPFAIL (75) and cite lever
L-CLOUDFLARE-DO-QUOTA. `release-stale` and `heal-dispatch` did not: they exited 1, which
in the beat ledger is indistinguishable from "this rung is broken" — and on 2026-08-15
that is exactly how it read, sending a reader hunting a defect that did not exist while
the real owner was a spend decision already sitting in the registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from limen.cli import EX_TEMPFAIL, QUOTA_OWNER, main
from limen.conduct.client import BrokerQuotaExhausted

BOARD = """version: '1.0'
portal:
  name: 'Universal Task Intake'
  budget:
    daily: 600
    per_agent:
      codex: 100
tasks:
  - id: STALE-1
    title: Stale task
    status: in_progress
    target_agent: codex
    priority: high
    budget_cost: 1
    created: 2026-06-01
    dispatch_log: []
"""


def test_release_stale_reports_quota_as_tempfail_naming_the_lever(tmp_path: Path, monkeypatch) -> None:
    board = tmp_path / "tasks.yaml"
    board.write_text(BOARD, encoding="utf-8")
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.delenv("LIMEN_PRIVATE_TASKS", raising=False)

    def exhausted(*_args, **_kwargs):
        raise BrokerQuotaExhausted(
            'conduct broker rejected request (500): {"detail": "Exceeded allowed rows written '
            'in Durable Objects free tier."}',
            status=500,
        )

    monkeypatch.setattr("limen.cli.release_stale_tasks", exhausted)

    result = CliRunner().invoke(main, ["release-stale", "--hours", "24", "--apply"])

    assert result.exit_code == EX_TEMPFAIL, result.output
    assert result.exit_code != 1, "quota exhaustion must not read as a rung defect"
    assert QUOTA_OWNER in result.stderr
    assert "spent, not broken" in result.stderr


def test_quota_owner_matches_the_sibling_organs() -> None:
    """One owner, four surfaces — and it must not be the RETIRED lever.

    L-CLOUDFLARE-DO-QUOTA was retired 2026-08-10: the recurrence proved the defect is
    Limen's own write amplification (issue #2054), and that issue states in terms that no
    Cloudflare support case, billing change, plan change or operator action is required.
    Citing the lever would send a reader to a human action its owner explicitly ruled out.
    """

    root = Path(__file__).resolve().parents[2]
    for organ in ("scripts/heal-board.py", "scripts/self-heal.py", "scripts/heal-dispatch.py"):
        text = (root / organ).read_text(encoding="utf-8")
        assert f'QUOTA_OWNER = "{QUOTA_OWNER}"' in text, organ
        assert "L-CLOUDFLARE-DO-QUOTA was" in text, f"{organ} must record WHY the lever is not the owner"


@pytest.mark.parametrize("organ", ["scripts/heal-dispatch.py"])
def test_organ_returns_tempfail_not_one_on_quota(organ: str) -> None:
    text = (Path(__file__).resolve().parents[2] / organ).read_text(encoding="utf-8")
    assert "except BrokerQuotaExhausted" in text
    assert "return EX_TEMPFAIL" in text
