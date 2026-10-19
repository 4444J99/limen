import json
import stat
from datetime import UTC, datetime, timedelta

import pytest
from limen import storage_claim_census as census
from limen.conduct import client as conduct_client
from limen.prima_materia import ResourceClaimV1
from limen.storage_claim_census import storage_claim_census


def test_broker_empty_census_is_explicit_and_complete():
    census = storage_claim_census({"runs": {}, "leases": {}, "sessions": {}}, datetime.now(UTC))
    assert census["complete"] is True
    assert census["claims"] == []


def test_missing_active_local_write_claim_and_expired_claim_deny():
    now = datetime.now(UTC)
    state = {
        "runs": {"r": {"executor_session_id": "s", "packet": {"effect": "write"}}},
        "sessions": {"s": {"capabilities": ["local-worktree"]}},
        "leases": {
            "l": {
                "run_id": "r",
                "lease_id": "l",
                "state": "active",
                "hard_deadline": (now + timedelta(minutes=1)).isoformat(),
            }
        },
    }
    census = storage_claim_census(state, now)
    assert census["denial_reasons"] == ["active_local_writer_without_claim"]
    state["leases"]["l"]["hard_deadline"] = (now - timedelta(minutes=1)).isoformat()
    assert storage_claim_census(state, now)["complete"]
    # An unresolved remote attempt retains occupancy even after lease expiry.
    assert not storage_claim_census(state, now, lambda _: [{"lease_id": "l"}])["complete"]


def test_invalid_claim_is_not_silently_omitted():
    state = {
        "runs": {"r": {"packet": {"storage_envelope_claims": [{"claim_id": "bad"}]}}},
        "sessions": {},
        "leases": {},
    }
    assert storage_claim_census(state, datetime.now(UTC))["denial_reasons"] == ["invalid_storage_claim"]


def test_live_claims_dedup_and_expired_active_writers_fail_closed():
    from test_conduct_protocol import storage_claim

    claim = storage_claim()
    now = claim.effective_from
    raw = claim.model_dump(mode="json")
    state = {
        "runs": {
            "r": {"executor_session_id": "s", "packet": {"effect": "write", "storage_envelope_claims": [raw, raw]}}
        },
        "sessions": {"s": {"capabilities": ["local-worktree"]}},
        "leases": {
            "l": {
                "run_id": "r",
                "lease_id": "l",
                "state": "active",
                "hard_deadline": (claim.rollback_until + timedelta(minutes=1)).isoformat(),
            }
        },
    }
    census = storage_claim_census(state, now)
    assert census["complete"] and len(census["claims"]) == 1
    assert storage_claim_census(state, claim.rollback_until)["denial_reasons"] == ["active_writer_claim_expired"]


# ── last-good broker claim snapshot ────────────────────────────────────────────────────────────


def _claim(now, claim_id="claim_000000000001"):
    return ResourceClaimV1(
        claim_id=claim_id,
        source_instance_id="source_00000000001",
        operation_id="operation_00000001",
        hydrated_inputs_bytes=0,
        workspace_bytes=0,
        temporary_expansion_bytes=0,
        output_bytes=600,
        encryption_chunking_bytes=0,
        rollback_bytes=0,
        memory_bytes=0,
        file_count=1,
        network_bytes=0,
        wall_time_seconds=60,
        effective_from=now - timedelta(seconds=1),
        effective_until=now + timedelta(seconds=60),
        rollback_until=now + timedelta(seconds=120),
    )


@pytest.fixture
def keeper(monkeypatch):
    """A fake conduct keeper whose census the test rewrites between calls."""
    answers = {}
    monkeypatch.setattr(
        census,
        "cached_conduct_credentials",
        lambda: {"LIMEN_CONDUCT_URL": "https://keeper.test", "LIMEN_CONDUCT_TOKEN": "token"},
    )

    class Keeper:
        def __init__(self, *args, **kwargs):
            pass

        def capabilities(self):
            return {"storage_claim_census": dict(answers)}

    monkeypatch.setattr(conduct_client, "HttpConductClient", Keeper)
    return answers


def test_snapshot_round_trip_is_private_atomic_and_offset_aware(tmp_path):
    now = datetime.now(UTC)
    claim = _claim(now)
    path = tmp_path / census.SNAPSHOT_NAME
    assert census.write_claim_snapshot(path, (claim,), broker_observed_at=now.isoformat(), now=now)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # Temp file + os.replace: nothing but the snapshot itself is left behind.
    assert [entry.name for entry in tmp_path.iterdir()] == [path.name]
    state = json.loads(path.read_text())
    assert state["schema"] == census.SNAPSHOT_SCHEMA
    assert state["observed_at"] == now.isoformat()
    assert state["broker_observed_at"] == now.isoformat()
    assert census.read_claim_snapshot(path) == census.ClaimSnapshot(now, now, (claim,))
    # A second write replaces, never appends or leaks a temp file.
    other = _claim(now, "claim_000000000002")
    assert census.write_claim_snapshot(path, (other,), broker_observed_at=now.isoformat(), now=now)
    assert [entry.name for entry in tmp_path.iterdir()] == [path.name]
    assert census.read_claim_snapshot(path).claims == (other,)
    assert census.read_claim_snapshot(tmp_path / "absent.json") is None


def test_broker_read_remembers_only_a_census_it_accepted(tmp_path, keeper):
    now = datetime.now(UTC)
    claim = _claim(now)
    path = tmp_path / census.SNAPSHOT_NAME
    keeper.update({"schema": census.SCHEMA, "observed_at": now.isoformat(), "complete": False, "claims": []})
    with pytest.raises(ValueError, match="broker_storage_census_incomplete"):
        census.broker_storage_claims(path)
    assert not path.exists()
    keeper.update({"observed_at": (now - timedelta(seconds=300)).isoformat(), "complete": True})
    with pytest.raises(ValueError, match="broker_storage_census_stale"):
        census.broker_storage_claims(path)
    assert not path.exists()
    raw = claim.model_dump(mode="json")
    keeper.update({"observed_at": now.isoformat(), "claims": [raw, raw]})
    with pytest.raises(ValueError, match="broker_storage_census_duplicate"):
        census.broker_storage_claims(path)
    assert not path.exists()
    keeper.update({"claims": [raw]})
    assert census.broker_storage_claims(path) == (claim,)
    snapshot = census.read_claim_snapshot(path)
    assert snapshot is not None
    assert snapshot.claims == (claim,)
    assert snapshot.broker_observed_at == now
    # Without a snapshot path the read is exactly what it was: claims out, nothing written.
    path.unlink()
    assert census.broker_storage_claims() == (claim,)
    assert not path.exists()


def test_snapshot_write_failure_never_fails_the_live_read(tmp_path, keeper):
    now = datetime.now(UTC)
    claim = _claim(now)
    keeper.update(
        {
            "schema": census.SCHEMA,
            "observed_at": now.isoformat(),
            "complete": True,
            "claims": [claim.model_dump(mode="json")],
        }
    )
    unwritable = tmp_path / "absent-directory" / census.SNAPSHOT_NAME
    assert census.broker_storage_claims(unwritable) == (claim,)
    assert not unwritable.exists()
    assert census.write_claim_snapshot(unwritable, (claim,), broker_observed_at=now.isoformat()) is False
