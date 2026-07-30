from __future__ import annotations

import json
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from limen.conduct.campaign_relay import CampaignRelayError, reserve_relay
from limen.workstream_contract import RECEIPT_MODULES, new_contract


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def relay_repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "relay@example.invalid")
    _git(root, "config", "user.name", "Relay Test")
    started = 2_000_000_000
    contract = new_contract("8h")
    contract["runway"].update(
        {
            "started_epoch": started,
            "deadline_epoch": started + 28_800,
            "started_at": datetime.fromtimestamp(started, UTC).isoformat(timespec="seconds"),
            "deadline_at": datetime.fromtimestamp(started + 28_800, UTC).isoformat(timespec="seconds"),
        }
    )
    receipt = root / "docs" / "continuations" / "predecessor" / "workstream.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "branch": "work/predecessor",
                "contract": contract,
                "private_capsule": {
                    "content": "redacted",
                    "modules": list(RECEIPT_MODULES),
                },
                "schema": "limen.workstream.receipt.v1",
                "slug": "predecessor",
                "workstream": "institutional-omega",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    return root, receipt


def test_reservation_is_private_deterministic_and_byte_stable(relay_repo) -> None:
    root, predecessor = relay_repo
    exact_main = _git(root, "rev-parse", "HEAD")
    first = reserve_relay(root, predecessor, exact_remote_main=exact_main)
    assert first.created is True
    assert first.receipt.state == "reserved"
    assert first.receipt.attempts == 0

    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    path = common / "limen" / "campaign-relays" / f"{first.receipt.relay_id}.json"
    before = path.read_bytes()
    second = reserve_relay(root, predecessor, exact_remote_main=exact_main)

    assert second.created is False
    assert second.receipt == first.receipt
    assert path.read_bytes() == before
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_reservation_identity_uses_the_committed_predecessor_blob(relay_repo) -> None:
    root, predecessor = relay_repo
    exact_main = _git(root, "rev-parse", "HEAD")
    baseline = reserve_relay(root, predecessor, exact_remote_main=exact_main)
    predecessor.write_text(
        predecessor.read_text(encoding="utf-8").replace(
            '"workstream": "institutional-omega"',
            '"workstream": "different-campaign"',
        ),
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "different mutable head")
    repeated = reserve_relay(root, predecessor, exact_remote_main=exact_main)

    assert repeated.created is False
    assert repeated.receipt == baseline.receipt
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    store = common / "limen" / "campaign-relays"
    assert len(list(store.glob("*.json"))) == 1


def test_reservation_rejects_a_symlinked_store_before_external_writes(relay_repo) -> None:
    root, predecessor = relay_repo
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    outside = root.parent / "outside"
    outside.mkdir()
    (common / "limen").symlink_to(outside, target_is_directory=True)

    with pytest.raises(CampaignRelayError, match="store is unavailable"):
        reserve_relay(root, predecessor, exact_remote_main=_git(root, "rev-parse", "HEAD"))

    assert list(outside.iterdir()) == []


def test_unadmitted_predecessor_fails_before_reservation(relay_repo) -> None:
    root, predecessor = relay_repo
    payload = json.loads(predecessor.read_text(encoding="utf-8"))
    payload["contract"]["runway"].update(
        {
            "started_epoch": None,
            "deadline_epoch": None,
            "started_at": None,
            "deadline_at": None,
        }
    )
    predecessor.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "unadmitted")

    with pytest.raises(CampaignRelayError, match="has not been admitted"):
        reserve_relay(root, predecessor, exact_remote_main=_git(root, "rev-parse", "HEAD"))
