"""Lock-serialized lifecycle transitions for one finite campaign relay attempt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from limen.conduct.campaign_relay import (
    _IMMUTABLE_FIELDS,
    _LINEAGE_FIELDS,
    CampaignRelayError,
    RelayLaunch,
    _read_receipt,
    _relay_names,
    _write_receipt,
    campaign_relay_lock,
)
from limen.conduct.models import CampaignRelayReceiptV1


def _read_relay(
    root: Path,
    relay_id: str,
    *,
    deadline_monotonic: float | None = None,
) -> CampaignRelayReceiptV1:
    receipt_name, _lock_name = _relay_names(relay_id)
    with campaign_relay_lock(
        root,
        relay_id,
        deadline_monotonic=deadline_monotonic,
    ) as store:
        receipt = _read_receipt(store, receipt_name)
    if receipt is None:
        raise CampaignRelayError(
            "relay_receipt_missing",
            "campaign relay receipt is missing",
        )
    return receipt


def _same_relay_identity(
    left: CampaignRelayReceiptV1,
    right: CampaignRelayReceiptV1,
) -> bool:
    return all(getattr(left, field) == getattr(right, field) for field in _IMMUTABLE_FIELDS)


def _same_relay_lineage(
    left: CampaignRelayReceiptV1,
    right: CampaignRelayReceiptV1,
) -> bool:
    return all(getattr(left, field) == getattr(right, field) for field in _LINEAGE_FIELDS)


def _adopt_remote_relay(
    root: Path,
    relay_id: str,
    *,
    expected_states: frozenset[str],
    remote: CampaignRelayReceiptV1,
    deadline_monotonic: float | None = None,
) -> CampaignRelayReceiptV1:
    receipt_name, _lock_name = _relay_names(relay_id)
    with campaign_relay_lock(
        root,
        relay_id,
        deadline_monotonic=deadline_monotonic,
    ) as store:
        current = _read_receipt(store, receipt_name)
        if current is None:
            raise CampaignRelayError(
                "relay_receipt_missing",
                "campaign relay receipt is missing",
            )
        if current.state not in expected_states:
            raise CampaignRelayError(
                "relay_state_conflict",
                "campaign relay lifecycle no longer permits remote adoption",
            )
        if current.relay_id != relay_id or not _same_relay_lineage(current, remote):
            raise CampaignRelayError(
                "relay_identity_changed",
                "campaign relay lineage changed during remote adoption",
            )
        _write_receipt(store, receipt_name, remote)
        return remote


def _adopt_remote_base(
    root: Path,
    relay_id: str,
    *,
    exact_remote_main: str,
    deadline_monotonic: float | None = None,
) -> CampaignRelayReceiptV1:
    receipt_name, _lock_name = _relay_names(relay_id)
    with campaign_relay_lock(
        root,
        relay_id,
        deadline_monotonic=deadline_monotonic,
    ) as store:
        current = _read_receipt(store, receipt_name)
        if current is None:
            raise CampaignRelayError(
                "relay_receipt_missing",
                "campaign relay receipt is missing",
            )
        if current.state != "reserved":
            raise CampaignRelayError(
                "relay_state_conflict",
                "campaign relay lifecycle no longer permits remote-base adoption",
            )
        try:
            adopted = CampaignRelayReceiptV1.model_validate(
                {
                    **current.model_dump(mode="json"),
                    "exact_remote_main": exact_remote_main,
                }
            )
        except ValueError as exc:
            raise CampaignRelayError(
                "relay_transition_invalid",
                "campaign relay remote base is invalid",
            ) from exc
        if not _same_relay_lineage(current, adopted):
            raise CampaignRelayError(
                "relay_identity_changed",
                "campaign relay lineage changed during remote-base adoption",
            )
        _write_receipt(store, receipt_name, adopted)
        return adopted


def _replace_relay(
    root: Path,
    relay_id: str,
    *,
    expected_states: frozenset[str],
    updates: dict[str, Any],
    deadline_monotonic: float | None = None,
) -> CampaignRelayReceiptV1:
    receipt_name, _lock_name = _relay_names(relay_id)
    with campaign_relay_lock(
        root,
        relay_id,
        deadline_monotonic=deadline_monotonic,
    ) as store:
        current = _read_receipt(store, receipt_name)
        if current is None:
            raise CampaignRelayError(
                "relay_receipt_missing",
                "campaign relay receipt is missing",
            )
        if current.state not in expected_states:
            raise CampaignRelayError(
                "relay_state_conflict",
                "campaign relay lifecycle no longer permits this transition",
            )
        try:
            updated = CampaignRelayReceiptV1.model_validate({**current.model_dump(mode="json"), **updates})
        except ValueError as exc:
            raise CampaignRelayError(
                "relay_transition_invalid",
                "campaign relay lifecycle transition is invalid",
            ) from exc
        if not _same_relay_identity(current, updated):
            raise CampaignRelayError(
                "relay_identity_changed",
                "campaign relay identity changed during launch",
            )
        _write_receipt(store, receipt_name, updated)
        return updated


def _claim_relay_attempt(
    root: Path,
    relay_id: str,
    *,
    controller_pid: int,
    controller_process_started: str,
    remote_attempt_commit: str | None = None,
    remote_attempt_token: str | None = None,
    deadline_monotonic: float | None = None,
) -> RelayLaunch:
    receipt_name, _lock_name = _relay_names(relay_id)
    with campaign_relay_lock(
        root,
        relay_id,
        deadline_monotonic=deadline_monotonic,
    ) as store:
        current = _read_receipt(store, receipt_name)
        if current is None:
            raise CampaignRelayError(
                "relay_receipt_missing",
                "campaign relay receipt is missing",
            )
        if current.state != "reserved":
            return RelayLaunch(receipt=current, launched=False)
        try:
            launching = CampaignRelayReceiptV1.model_validate(
                {
                    **current.model_dump(mode="json"),
                    "state": "launching",
                    "attempts": 1,
                    "controller_pid": controller_pid,
                    "controller_process_started": controller_process_started,
                    "remote_attempt_commit": remote_attempt_commit,
                    "remote_attempt_token": remote_attempt_token,
                }
            )
        except ValueError as exc:
            raise CampaignRelayError(
                "relay_transition_invalid",
                "campaign relay launch claim is invalid",
            ) from exc
        _write_receipt(store, receipt_name, launching)
        return RelayLaunch(receipt=launching, launched=True)
