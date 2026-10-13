from datetime import UTC, datetime, timedelta

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
