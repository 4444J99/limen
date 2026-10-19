import json
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from limen import runtime_pool as module
from limen import storage_claim_census as census
from limen.conduct import client as conduct_client
from limen.conduct.client import BrokerQuotaExhausted, BrokerUnavailable, ConductError
from limen.prima_materia import ResourceClaimV1
from limen.resource_envelope import ResourceTelemetry


@pytest.fixture
def pool(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(
        module,
        "observe_resource_telemetry",
        lambda: ResourceTelemetry(
            now,
            100,
            100,
            0,
            10,
            10,
            10,
        ),
    )
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: SimpleNamespace(free=1000))
    return module.RuntimePool(
        tmp_path / "host", clock=lambda: now.timestamp(), alive=lambda _: True, identity=lambda _: "start:1"
    )


def _claim(now, *, claim_id="claim_000000000001", output_bytes=600, start=-1, end=60, rollback=120):
    return ResourceClaimV1(
        claim_id=claim_id,
        source_instance_id="source_00000000001",
        operation_id="operation_00000001",
        hydrated_inputs_bytes=0,
        workspace_bytes=0,
        temporary_expansion_bytes=0,
        output_bytes=output_bytes,
        encryption_chunking_bytes=0,
        rollback_bytes=0,
        memory_bytes=0,
        file_count=1,
        network_bytes=0,
        wall_time_seconds=60,
        effective_from=now + timedelta(seconds=start),
        effective_until=now + timedelta(seconds=end),
        rollback_until=now + timedelta(seconds=rollback),
    )


def _spent(snapshot_path=None):
    raise BrokerQuotaExhausted(
        "conduct broker rejected request (500): Exceeded allowed rows written in Durable Objects free tier.",
        status=500,
    )


def _remember(pool, now, *claims):
    pool.root.mkdir(mode=0o700, exist_ok=True)
    assert census.write_claim_snapshot(pool.snapshot_path, claims, broker_observed_at=now.isoformat(), now=now)


def test_one_shared_pot_across_vendor_owners(pool, tmp_path):
    first = pool.reserve(tmp_path, owner="codex", pid=1, growth_bytes=600, claims=())
    assert first["allowed"]
    second = pool.reserve(tmp_path, owner="claude", pid=2, growth_bytes=400, claims=())
    assert second["denial_reasons"] == ["shared_pool_exhausted"]
    assert pool.observe(tmp_path, claims=())["available_growth_bytes"] == 370


def test_competing_writers_cannot_over_reserve(pool, tmp_path):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda owner: pool.reserve(tmp_path, owner=owner, pid=1, growth_bytes=600, claims=()),
                ("codex", "claude"),
            )
        )
    assert sum(result["allowed"] for result in results) == 1


def test_live_expired_writer_retains_capacity_then_dead_writer_releases(pool, tmp_path):
    pool.reserve(tmp_path, owner="codex", pid=1, growth_bytes=600, ttl_seconds=1, claims=())
    pool.clock = lambda: datetime.now(UTC).timestamp() + 5
    assert pool.observe(tmp_path, claims=())["outstanding_growth_bytes"] == 600
    pool.alive = lambda _: False
    assert pool.observe(tmp_path, claims=())["outstanding_growth_bytes"] == 0


def test_release_is_owner_bound_and_idempotent(pool, tmp_path):
    result = pool.reserve(tmp_path, owner="codex", pid=1, growth_bytes=10, claims=())
    with pytest.raises(module.PoolUnavailable, match="owner_mismatch"):
        pool.release_growth(result["reservation_id"], owner="claude", pid=1)
    assert pool.release_growth(result["reservation_id"], owner="codex", pid=1)["released"]
    assert pool.release_growth(result["reservation_id"], owner="codex", pid=1)["already_released"]


def test_claim_in_envelope_is_counted_once(pool, tmp_path):
    now = datetime.fromtimestamp(pool.clock(), UTC)
    claim = ResourceClaimV1(
        claim_id="claim_000000000001",
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
    result = pool.reserve(
        tmp_path, owner="codex", pid=1, growth_bytes=600, claim_id="claim_000000000001", claims=(claim,)
    )
    assert result["allowed"]
    assert result["required_reserve_bytes"] == 630
    assert result["outstanding_growth_bytes"] == 0
    assert result["available_growth_bytes"] == 370
    with pytest.raises(module.PoolUnavailable, match="claim_already_owned"):
        pool.reserve(tmp_path, owner="claude", pid=2, growth_bytes=600, claim_id="claim_000000000001", claims=(claim,))


def test_invalid_state_is_preserved_and_fails_closed(pool, tmp_path):
    pool.root.mkdir(mode=0o700)
    pool.pool_path.write_text('{"schema":"wrong"}')
    pool.pool_path.chmod(0o600)
    assert pool.observe(tmp_path, claims=())["denial_reasons"] == ["pool_state_invalid"]
    assert pool.pool_path.read_text() == '{"schema":"wrong"}'


def test_stale_telemetry_fails_closed(pool, tmp_path):
    pool.clock = lambda: datetime.now(UTC).timestamp() + 121
    assert pool.observe(tmp_path, claims=())["denial_reasons"] == ["resource_telemetry_stale"]


def test_missing_selected_graph_does_not_invent_empty_claims(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)

    def missing(snapshot_path=None):
        raise ValueError("broker_storage_census_unavailable")

    monkeypatch.setattr(module, "broker_storage_claims", missing)
    assert pool.observe(tmp_path)["denial_reasons"] == ["broker_storage_census_unavailable"]


def test_broker_write_quota_is_named_not_mistaken_for_a_census_fault(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)

    def spent(snapshot_path=None):
        raise BrokerQuotaExhausted("conduct broker rejected request (500): rows written", status=500)

    monkeypatch.setattr(module, "broker_storage_claims", spent)
    decision = pool.observe(tmp_path)
    assert decision["allowed"] is False
    assert decision["denial_reasons"] == ["broker_quota_exhausted"]
    assert decision["available_growth_bytes"] is None


def test_other_broker_errors_still_read_as_census_unavailable(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)

    def broken(snapshot_path=None):
        raise ConductError("conduct broker rejected request (500): boom", status=500)

    monkeypatch.setattr(module, "broker_storage_claims", broken)
    assert pool.observe(tmp_path)["denial_reasons"] == ["broker_storage_census_unavailable"]


def test_symlink_state_cannot_redirect_writes(pool, tmp_path):
    pool.root.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.write_text("preserve")
    pool.pool_path.symlink_to(outside)
    assert not pool.observe(tmp_path, claims=())["allowed"]
    assert outside.read_text() == "preserve"


# ── last-good broker claim snapshot (4444J99/limen#2054: a spent write quota must not refuse launches) ──


def test_successful_broker_read_persists_a_last_good_snapshot(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)
    now = datetime.fromtimestamp(pool.clock(), UTC)
    claim = _claim(now)
    monkeypatch.setattr(
        census,
        "cached_conduct_credentials",
        lambda: {"LIMEN_CONDUCT_URL": "https://keeper.test", "LIMEN_CONDUCT_TOKEN": "token"},
    )

    class LiveKeeper:
        def __init__(self, *args, **kwargs):
            pass

        def capabilities(self):
            return {
                "storage_claim_census": {
                    "schema": census.SCHEMA,
                    "observed_at": datetime.now(UTC).isoformat(),
                    "complete": True,
                    "claims": [claim.model_dump(mode="json")],
                }
            }

    monkeypatch.setattr(conduct_client, "HttpConductClient", LiveKeeper)
    decision = pool.observe(tmp_path)
    assert decision["allowed"] is True
    assert decision["broker_ledger"] == "live"
    assert "frozen_at" not in decision
    assert pool.snapshot_path.parent == pool.pool_path.parent
    assert stat.S_IMODE(pool.snapshot_path.stat().st_mode) == 0o600
    snapshot = census.read_claim_snapshot(pool.snapshot_path)
    assert snapshot is not None
    assert snapshot.claims == (claim,)
    assert snapshot.observed_at.tzinfo is not None
    assert snapshot.broker_observed_at.tzinfo is not None


def test_spent_write_quota_rides_on_the_last_good_snapshot(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)
    now = datetime.fromtimestamp(pool.clock(), UTC)
    _remember(pool, now, _claim(now))
    monkeypatch.setattr(module, "broker_storage_claims", _spent)
    decision = pool.observe(tmp_path)
    assert decision["allowed"] is True
    assert decision["denial_reasons"] == []
    assert decision["broker_ledger"] == "frozen"
    assert decision["frozen_at"] == now.isoformat()
    assert decision["reason"] == "broker_quota_exhausted"
    assert decision["storage_claim_count"] == 1
    assert decision["required_reserve_bytes"] == 630
    assert decision["available_growth_bytes"] == 370
    # The marker survives JSON, which is how scripts/runtime-pool.py hands it to the launcher.
    assert json.loads(json.dumps(decision, sort_keys=True))["broker_ledger"] == "frozen"
    # Reservations taken during the outage carry the same marker and the same remembered claims.
    reservation = pool.reserve(tmp_path, owner="codex", pid=1, growth_bytes=100)
    assert reservation["allowed"] is True
    assert reservation["broker_ledger"] == "frozen"
    assert reservation["frozen_at"] == now.isoformat()


def test_frozen_snapshot_honours_each_claim_to_its_own_rollback(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)
    now = datetime.fromtimestamp(pool.clock(), UTC)
    live = _claim(now, claim_id="claim_000000000001")
    # Effective window already closed, rollback still ahead: the broker's census would keep it, so do we.
    fading = _claim(now, claim_id="claim_000000000002", start=-120, end=-60, rollback=60)
    # Rollback already passed: the broker's census would have dropped it, so do we.
    dead = _claim(now, claim_id="claim_000000000003", start=-300, end=-240, rollback=-120)
    _remember(pool, now, live, fading, dead)
    monkeypatch.setattr(module, "broker_storage_claims", _spent)
    selection = module.selected_claims(pool.snapshot_path, now=now)
    assert selection.claims == (live, fading)
    assert selection.broker_ledger == {
        "broker_ledger": "frozen",
        "frozen_at": now.isoformat(),
        "reason": "broker_quota_exhausted",
    }
    assert pool.observe(tmp_path)["storage_claim_count"] == 2
    # No age cutoff beyond rollback_until: three days into an outage a claim whose rollback is still
    # ahead is still honoured, and one whose rollback has passed is not. The snapshot itself is never
    # "too old" while the keeper refuses writes — see runtime_pool._broker_claims.
    long_lived = _claim(now, claim_id="claim_000000000004", rollback=4 * 86400)
    _remember(pool, now, live, long_lived)
    later = module.selected_claims(pool.snapshot_path, now=now + timedelta(days=3))
    assert later.claims == (long_lived,)
    assert later.broker_ledger is not None and later.broker_ledger["frozen_at"] == now.isoformat()


def test_spent_write_quota_without_a_snapshot_still_fails_closed(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)
    monkeypatch.setattr(module, "broker_storage_claims", _spent)
    decision = pool.observe(tmp_path)
    assert decision["allowed"] is False
    assert decision["denial_reasons"] == ["broker_quota_exhausted"]
    assert decision["available_growth_bytes"] is None
    assert "broker_ledger" not in decision
    # A refused read remembers nothing: there is no snapshot to be found afterwards.
    assert not pool.snapshot_path.exists()


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        pytest.param(
            ConductError("conduct broker rejected request (500): boom", status=500),
            "broker_storage_census_unavailable",
            id="keeper-500",
        ),
        pytest.param(
            BrokerUnavailable("conduct broker unavailable: timed out"),
            "broker_storage_census_unavailable",
            id="network",
        ),
        pytest.param(
            ValueError("broker_storage_census_incomplete"), "broker_storage_census_incomplete", id="incomplete"
        ),
        pytest.param(ValueError("broker_storage_census_stale"), "broker_storage_census_stale", id="stale"),
        pytest.param(ValueError("broker_storage_census_duplicate"), "broker_storage_census_duplicate", id="duplicate"),
        pytest.param(ValueError("credential_cache_unsafe"), "broker_storage_census_unavailable", id="credentials"),
    ],
)
def test_only_a_spent_write_quota_may_fall_back_to_the_snapshot(pool, tmp_path, monkeypatch, failure, reason):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)
    now = datetime.fromtimestamp(pool.clock(), UTC)
    _remember(pool, now, _claim(now))

    def broken(snapshot_path=None):
        raise failure

    monkeypatch.setattr(module, "broker_storage_claims", broken)
    decision = pool.observe(tmp_path)
    assert decision["allowed"] is False
    assert decision["denial_reasons"] == [reason]
    assert decision["available_growth_bytes"] is None
    assert "broker_ledger" not in decision


def test_corrupt_or_unsafe_snapshot_reads_as_absent(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)
    now = datetime.fromtimestamp(pool.clock(), UTC)
    monkeypatch.setattr(module, "broker_storage_claims", _spent)
    pool.root.mkdir(mode=0o700)
    stamp = now.isoformat()
    damaged = (
        "{not json",
        json.dumps({"schema": "wrong", "observed_at": stamp, "broker_observed_at": stamp, "claims": []}),
        json.dumps({"schema": census.SNAPSHOT_SCHEMA, "observed_at": stamp, "claims": []}),
        json.dumps(
            {"schema": census.SNAPSHOT_SCHEMA, "observed_at": "soon", "broker_observed_at": stamp, "claims": []}
        ),
        json.dumps(
            {
                "schema": census.SNAPSHOT_SCHEMA,
                "observed_at": "2026-10-18T00:00:00",
                "broker_observed_at": stamp,
                "claims": [],
            }
        ),
        json.dumps({"schema": census.SNAPSHOT_SCHEMA, "observed_at": stamp, "broker_observed_at": stamp, "claims": {}}),
        json.dumps(
            {
                "schema": census.SNAPSHOT_SCHEMA,
                "observed_at": stamp,
                "broker_observed_at": stamp,
                "claims": [{"claim_id": "bad"}],
            }
        ),
    )
    for text in damaged:
        pool.snapshot_path.write_text(text)
        pool.snapshot_path.chmod(0o600)
        assert census.read_claim_snapshot(pool.snapshot_path) is None, text
        assert pool.observe(tmp_path)["denial_reasons"] == ["broker_quota_exhausted"], text
    # A duplicated claim id is a census the live gate would have refused; so is the snapshot.
    good = _claim(now)
    _remember(pool, now, good, good)
    assert census.read_claim_snapshot(pool.snapshot_path) is None
    # A snapshot anyone else can read is not trusted either.
    _remember(pool, now, good)
    assert census.read_claim_snapshot(pool.snapshot_path) is not None
    pool.snapshot_path.chmod(0o644)
    assert census.read_claim_snapshot(pool.snapshot_path) is None
    assert pool.observe(tmp_path)["denial_reasons"] == ["broker_quota_exhausted"]
    # Nor a symlink, however private its target.
    pool.snapshot_path.unlink()
    outside = tmp_path / "outside.json"
    assert census.write_claim_snapshot(outside, (good,), broker_observed_at=stamp, now=now)
    pool.snapshot_path.symlink_to(outside)
    assert census.read_claim_snapshot(pool.snapshot_path) is None
    assert pool.observe(tmp_path)["denial_reasons"] == ["broker_quota_exhausted"]
