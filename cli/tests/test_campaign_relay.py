from __future__ import annotations

import json
import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from limen.bounded_subprocess import BoundedSubprocessError
from limen.conduct.campaign_relay import (
    CampaignRelayError,
    _primary_checkout,
    _relay_worktree,
    campaign_relay_lock,
    reserve_relay,
)
from limen.conduct.models import CampaignRelayReceiptV1
from limen.workstream_contract import RECEIPT_MODULES, new_contract, new_contract_v2


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


def test_unconsumed_reservation_tracks_current_main_when_main_moves(relay_repo) -> None:
    root, predecessor = relay_repo
    initial_main = _git(root, "rev-parse", "HEAD")
    first = reserve_relay(root, predecessor, exact_remote_main=initial_main)
    (root / "unrelated.txt").write_text("moving main is normal\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "advance main without changing predecessor")
    advanced_main = _git(root, "rev-parse", "HEAD")

    repeated = reserve_relay(root, predecessor, exact_remote_main=advanced_main)

    assert advanced_main != initial_main
    assert repeated.created is False
    assert repeated.receipt.relay_id == first.receipt.relay_id
    assert repeated.receipt.exact_remote_main == advanced_main
    assert repeated.receipt.state == "reserved"
    assert repeated.receipt.attempts == 0
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    store = common / "limen" / "campaign-relays"
    assert len(list(store.glob("*.json"))) == 1


def test_primary_checkout_and_successor_worktree_derive_from_shared_common_dir(
    relay_repo,
) -> None:
    root, _predecessor = relay_repo
    successor = root / ".worktrees" / "successor"
    observer = root.parent / "observer"
    successor.parent.mkdir()
    _git(root, "worktree", "add", "--detach", str(successor), "HEAD")
    _git(root, "worktree", "add", "--detach", str(observer), "HEAD")

    assert _primary_checkout(observer) == root.resolve()
    assert _relay_worktree(observer, "successor") == successor.resolve()


@pytest.mark.parametrize("length", [40, 64])
def test_relay_receipt_accepts_exact_git_object_lengths(relay_repo, length) -> None:
    root, predecessor = relay_repo
    payload = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    ).receipt.model_dump(mode="json")
    payload["predecessor_receipt_blob"] = "a" * length
    payload["exact_remote_main"] = "b" * length

    receipt = CampaignRelayReceiptV1.model_validate(payload)

    assert len(receipt.predecessor_receipt_blob) == length
    assert len(receipt.exact_remote_main) == length


@pytest.mark.parametrize("length", [41, 63])
def test_relay_receipt_rejects_intermediate_git_object_lengths(relay_repo, length) -> None:
    root, predecessor = relay_repo
    payload = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    ).receipt.model_dump(mode="json")

    for field in ("predecessor_receipt_blob", "exact_remote_main"):
        malformed = {**payload, field: "a" * length}
        with pytest.raises(ValueError, match="lowercase Git object id"):
            CampaignRelayReceiptV1.model_validate(malformed)


def test_reservation_rejects_a_symlinked_store_before_external_writes(relay_repo) -> None:
    root, predecessor = relay_repo
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    outside = root.parent / "outside"
    outside.mkdir()
    (common / "limen").symlink_to(outside, target_is_directory=True)

    with pytest.raises(CampaignRelayError, match="store is unavailable"):
        reserve_relay(root, predecessor, exact_remote_main=_git(root, "rev-parse", "HEAD"))

    assert list(outside.iterdir()) == []


def test_verified_store_fd_prevents_parent_swap_from_redirecting_write(
    relay_repo,
    monkeypatch,
) -> None:
    root, predecessor = relay_repo
    reserve_relay(root, predecessor, exact_remote_main=_git(root, "rev-parse", "HEAD"))
    predecessor.write_text(predecessor.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "advance predecessor blob")

    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    outside = root.parent / "swap-outside"
    outside.mkdir()
    original_replace = os.replace
    swapped = False

    def swap_parent_then_replace(
        source,
        destination,
        *,
        src_dir_fd=None,
        dst_dir_fd=None,
    ):
        nonlocal swapped
        if not swapped:
            (common / "limen").rename(common / "limen-original")
            (common / "limen").symlink_to(outside, target_is_directory=True)
            swapped = True
        return original_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr("limen.conduct.campaign_relay.os.replace", swap_parent_then_replace)
    with pytest.raises(CampaignRelayError, match="identity changed") as caught:
        reserve_relay(root, predecessor, exact_remote_main=_git(root, "rev-parse", "HEAD"))

    assert caught.value.code == "relay_store_changed"
    assert swapped is True
    assert list(outside.iterdir()) == []


def test_held_relay_lock_fails_at_a_finite_deadline(relay_repo) -> None:
    root, predecessor = relay_repo
    relay = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    ).receipt

    with campaign_relay_lock(root, relay.relay_id):
        with pytest.raises(CampaignRelayError, match="bounded acquire deadline"):
            with campaign_relay_lock(root, relay.relay_id, timeout_seconds=0.02):
                pytest.fail("a held relay lock must not be re-entered")


def test_lock_open_retries_one_verified_enoent(relay_repo, monkeypatch) -> None:
    root, _predecessor = relay_repo
    relay_id = "a" * 64
    lock_name = f"{relay_id}.lock"
    original_open = os.open
    attempts = 0

    def fail_first_lock_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal attempts
        if path == lock_name:
            attempts += 1
            if attempts == 1:
                raise FileNotFoundError(2, "injected bounded retry")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("limen.conduct.campaign_relay.os.open", fail_first_lock_open)
    with campaign_relay_lock(root, relay_id):
        pass

    assert attempts == 2


def test_lock_open_second_enoent_fails_closed(relay_repo, monkeypatch) -> None:
    root, _predecessor = relay_repo
    relay_id = "b" * 64
    lock_name = f"{relay_id}.lock"
    original_open = os.open
    attempts = 0

    def fail_both_lock_opens(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal attempts
        if path == lock_name:
            attempts += 1
            raise FileNotFoundError(2, "injected bounded failure")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("limen.conduct.campaign_relay.os.open", fail_both_lock_opens)
    with pytest.raises(CampaignRelayError) as caught:
        with campaign_relay_lock(root, relay_id):
            pytest.fail("a second ENOENT must fail closed")

    assert caught.value.code == "relay_lock_unavailable"
    assert attempts == 2


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (
            BoundedSubprocessError("timeout"),
            "relay_git_timeout",
        ),
        (
            BoundedSubprocessError("unavailable"),
            "relay_git_unavailable",
        ),
    ],
)
def test_git_probe_failure_is_bounded_and_path_free(
    relay_repo,
    monkeypatch,
    failure,
    code,
) -> None:
    root, predecessor = relay_repo

    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr("limen.conduct.campaign_relay.run_bounded_subprocess", fail)
    with pytest.raises(CampaignRelayError) as caught:
        reserve_relay(root, predecessor, exact_remote_main="a" * 40)

    assert caught.value.code == code
    assert "/private/secret" not in caught.value.public_reason


def test_non_utf8_committed_predecessor_has_a_path_free_error(relay_repo) -> None:
    root, predecessor = relay_repo
    predecessor.write_bytes(b"\xff")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "non-utf8 predecessor")

    with pytest.raises(CampaignRelayError) as caught:
        reserve_relay(root, predecessor, exact_remote_main=_git(root, "rev-parse", "HEAD"))

    assert caught.value.code == "relay_predecessor_invalid"
    assert str(predecessor) not in caught.value.public_reason


def test_non_scalar_contract_text_has_a_path_free_relay_error(relay_repo) -> None:
    root, predecessor = relay_repo
    payload = json.loads(predecessor.read_text(encoding="utf-8"))
    contract = new_contract_v2(
        "8h",
        agent="codex",
        model="\ud800",
        reasoning_effort="fixture-effort",
        sandbox="workspace-write",
    )
    contract["runway"] = payload["contract"]["runway"]
    payload["contract"] = contract
    predecessor.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "non-scalar contract text")

    with pytest.raises(CampaignRelayError) as caught:
        reserve_relay(root, predecessor, exact_remote_main=_git(root, "rev-parse", "HEAD"))

    assert caught.value.code == "relay_predecessor_invalid"
    assert caught.value.public_reason == (
        "relay_predecessor_invalid: committed predecessor contract cannot be canonicalized"
    )
    assert str(predecessor) not in caught.value.public_reason


def test_oversized_committed_predecessor_fails_before_blob_capture(relay_repo) -> None:
    root, predecessor = relay_repo
    payload = json.loads(predecessor.read_text(encoding="utf-8"))
    payload["padding"] = "x" * 300_000
    predecessor.write_text(json.dumps(payload), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "oversized predecessor")

    with pytest.raises(CampaignRelayError) as caught:
        reserve_relay(root, predecessor, exact_remote_main=_git(root, "rev-parse", "HEAD"))

    assert caught.value.code == "relay_predecessor_oversized"


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
