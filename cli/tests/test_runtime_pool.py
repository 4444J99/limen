from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from limen import runtime_pool as module
from limen.conduct.client import BrokerQuotaExhausted, ConductError
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

    def missing():
        raise ValueError("broker_storage_census_unavailable")

    monkeypatch.setattr(module, "broker_storage_claims", missing)
    assert pool.observe(tmp_path)["denial_reasons"] == ["broker_storage_census_unavailable"]


def test_broker_write_quota_is_named_not_mistaken_for_a_census_fault(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)

    def spent():
        raise BrokerQuotaExhausted("conduct broker rejected request (500): rows written", status=500)

    monkeypatch.setattr(module, "broker_storage_claims", spent)
    decision = pool.observe(tmp_path)
    assert decision["allowed"] is False
    assert decision["denial_reasons"] == ["broker_quota_exhausted"]
    assert decision["available_growth_bytes"] is None


def test_other_broker_errors_still_read_as_census_unavailable(pool, tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)

    def broken():
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
