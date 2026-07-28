from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from limen.omega_owner_receipt import (
    OmegaOwnerReceiptError,
    OmegaOwnerReceiptV1,
    build_owner_receipt,
    load_owner_receipt,
    normalized_owner_receipt,
    run_owner_predicate,
    write_owner_receipt,
)


def test_owner_receipt_is_content_free_and_binds_explicit_outcome() -> None:
    receipt = build_owner_receipt(
        rung_id="sensor.example",
        predicate="python3 scripts/example.py --strict",
        returncode=77,
        stdout=b"unavailable",
        observed_at=datetime(2026, 7, 27, tzinfo=UTC),
    )

    assert receipt.status == "SKIP"
    assert receipt.exit_code == 77
    payload = receipt.model_dump(mode="json", by_alias=True)
    assert payload["schema"] == "limen.omega_owner_receipt.v1"
    assert "unavailable" not in json.dumps(payload)
    with pytest.raises(ValueError, match="extra"):
        OmegaOwnerReceiptV1.model_validate(payload | {"raw_output": "secret"})


def test_owner_receipt_rejects_mismatch_stale_future_and_downgrade(tmp_path) -> None:
    now = datetime(2026, 7, 27, 18, tzinfo=UTC)
    path = tmp_path / "receipt.json"
    receipt = build_owner_receipt(
        rung_id="core.live",
        predicate="python3 scripts/live.py --check",
        returncode=0,
        stdout=b"green",
        observed_at=now,
    )
    write_owner_receipt(path, receipt)
    assert (
        load_owner_receipt(
            path,
            rung_id="core.live",
            predicate="python3 scripts/live.py --check",
            max_age_seconds=300,
            now=now,
        ).status
        == "PASS"
    )

    with pytest.raises(OmegaOwnerReceiptError, match="another predicate"):
        load_owner_receipt(
            path,
            rung_id="core.live",
            predicate="python3 scripts/other.py",
            max_age_seconds=300,
            now=now,
        )
    with pytest.raises(OmegaOwnerReceiptError, match="stale"):
        load_owner_receipt(
            path,
            rung_id="core.live",
            predicate="python3 scripts/live.py --check",
            max_age_seconds=300,
            now=now + timedelta(seconds=301),
        )

    future = receipt.model_copy(update={"observed_at": now + timedelta(minutes=2)})
    write_owner_receipt(path, future)
    with pytest.raises(OmegaOwnerReceiptError, match="future-dated"):
        load_owner_receipt(
            path,
            rung_id="core.live",
            predicate="python3 scripts/live.py --check",
            max_age_seconds=300,
            now=now,
        )

    failed = build_owner_receipt(
        rung_id="core.live",
        predicate="python3 scripts/live.py --check",
        returncode=1,
        observed_at=now,
    )
    write_owner_receipt(path, failed)
    with pytest.raises(OmegaOwnerReceiptError, match="is FAIL"):
        load_owner_receipt(
            path,
            rung_id="core.live",
            predicate="python3 scripts/live.py --check",
            max_age_seconds=300,
            now=now,
        )


def test_owner_runner_bounds_output_and_normalizes_non_protocol_exit(tmp_path) -> None:
    receipt_path = tmp_path / "owner.json"
    exit_code, stdout, stderr, receipt = run_owner_predicate(
        root=tmp_path,
        rung_id="sensor.bounded",
        predicate="python3 -c 'import sys; print(\"x\" * 70000); sys.exit(9)'",
        receipt_path=receipt_path,
        timeout_seconds=10,
    )

    assert exit_code == 1
    assert len(stdout) + len(stderr) <= 65_536
    assert receipt.status == "FAIL"
    assert receipt.evidence_truncated is True
    assert json.loads(receipt_path.read_text())["schema"] == "limen.omega_owner_receipt.v1"


def test_normalized_owner_receipt_excludes_only_observation_time() -> None:
    first = build_owner_receipt(
        rung_id="sensor.same",
        predicate="true",
        returncode=0,
        stdout=b"same",
        observed_at=datetime(2026, 7, 27, 18, tzinfo=UTC),
    )
    second = build_owner_receipt(
        rung_id="sensor.same",
        predicate="true",
        returncode=0,
        stdout=b"same",
        observed_at=datetime(2026, 7, 27, 19, tzinfo=UTC),
    )

    assert normalized_owner_receipt(first) == normalized_owner_receipt(second)
