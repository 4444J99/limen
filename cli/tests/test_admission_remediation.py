"""A blocked dispatch must print a remediation that can actually clear the block.

Both defects here produced the same operator-visible failure: run the printed command,
observe the identical block, run it again. A gate that names an insufficient remedy is
worse than one that names none — it looks actionable.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen import dispatch as D  # noqa: E402


def test_every_named_command_survives_not_just_the_first() -> None:
    payload = {"next_commands": ["python3 scripts/a.py --write", "python3 scripts/b.py --write"]}
    assert D._remediation_command(payload) == "python3 scripts/a.py --write && python3 scripts/b.py --write"


def test_stop_missing_inputs_keeps_the_producer_that_clears_it() -> None:
    """The live regression: batch_review_index's producer is the SECOND entry.

    session-value-review.py emits both commands for stop_missing_inputs; only
    prompt-batch-review-ledger.py writes the batch_review_index file, so dropping
    element [1] left the operator re-running a command with no effect on the block.
    """
    payload = {
        "next_commands": [
            "python3 scripts/prompt-priority-map.py --write",
            "python3 scripts/prompt-batch-review-ledger.py --write",
        ]
    }

    remediation = D._remediation_command(payload)

    assert "prompt-batch-review-ledger.py --write" in remediation
    assert remediation.index("prompt-priority-map") < remediation.index("prompt-batch-review-ledger")


def test_blank_and_whitespace_entries_are_dropped() -> None:
    payload = {"next_commands": ["  python3 scripts/a.py  ", "", "   ", "python3 scripts/b.py"]}
    assert D._remediation_command(payload) == "python3 scripts/a.py && python3 scripts/b.py"


def test_absent_or_malformed_next_commands_yield_empty_string() -> None:
    # An empty result is what lets the caller fall back to its own default command.
    assert D._remediation_command({}) == ""
    assert D._remediation_command({"next_commands": []}) == ""
    assert D._remediation_command({"next_commands": "not-a-list"}) == ""


def test_handoff_remediation_refreshes_headroom_before_checking_it() -> None:
    """handoff-relay only READS logs/usage.json, so it can never clear a stale-headroom fail."""
    remediation = D.HANDOFF_RELAY_REMEDIATION

    assert remediation.startswith("python3 scripts/usage-telemetry.py")
    assert "scripts/handoff-relay.py --check" in remediation
    assert remediation.index("usage-telemetry") < remediation.index("handoff-relay.py --check")


def test_handoff_remediation_names_scripts_that_exist() -> None:
    """A remedy naming a script that is not on disk is unrunnable advice."""
    for fragment in D.HANDOFF_RELAY_REMEDIATION.split(" && "):
        script = fragment.split()[1]
        assert (ROOT / script).exists(), f"remediation names a missing script: {script}"
