from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from limen import resource_envelope
from limen.prima_materia import ResourceClaimV1
from limen.resource_envelope import (
    ResourceTelemetry,
    evaluate_resource_envelope,
    load_task_graph_claims,
)

GIB = 1024**3
NOW = datetime(2026, 7, 28, tzinfo=UTC)


def test_host_telemetry_uses_its_native_process_seam(monkeypatch) -> None:
    class FakeProcess:
        returncode = 0

        def communicate(self, *, timeout: int) -> tuple[str, str]:
            assert timeout == 5
            return "observed\n", ""

    calls: list[list[str]] = []

    def native_popen(args: list[str], **_kwargs) -> FakeProcess:
        calls.append(args)
        return FakeProcess()

    def forbidden_caller_popen(*_args, **_kwargs):
        raise AssertionError("caller launch seam must not own telemetry")

    monkeypatch.setattr(resource_envelope, "_NATIVE_POPEN", native_popen)
    monkeypatch.setattr(resource_envelope.subprocess, "Popen", forbidden_caller_popen)

    assert resource_envelope._capture_command(["telemetry-probe"]) == "observed\n"
    assert calls == [["telemetry-probe"]]


def test_darwin_vm_stat_whitespace_is_parsed(monkeypatch) -> None:
    observations = {
        ("/usr/sbin/sysctl", "-n", "hw.memsize"): str(16 * GIB),
        ("/usr/sbin/sysctl", "-n", "hw.pagesize"): "4096",
        ("/usr/bin/vm_stat",): (
            "Mach Virtual Memory Statistics: (page size of 4096 bytes)\n"
            "Pages free:                               1.\n"
            "Pages inactive:                           2.\n"
            "Pages speculative:                        3.\n"
            "Pages purgeable:                          4."
        ),
        (
            "/usr/sbin/sysctl",
            "-n",
            "vm.swapusage",
        ): "total = 4.00G  used = 2.50G  free = 1.50G",
    }
    monkeypatch.setattr(
        resource_envelope,
        "_capture_command",
        lambda args: observations[tuple(args)],
    )

    assert resource_envelope._darwin_memory() == (
        16 * GIB,
        10 * 4096,
        int(2.5 * GIB),
    )


def _telemetry() -> ResourceTelemetry:
    return ResourceTelemetry(
        observed_at=NOW,
        ram_total_bytes=16 * GIB,
        ram_available_bytes=4 * GIB,
        swap_used_bytes=6 * GIB,
        updater_claim_bytes=1 * GIB,
        apfs_churn_bytes=2 * GIB,
        telemetry_error_bytes=1 * GIB,
    )


def _claim(identifier: str, scale: int = 1) -> ResourceClaimV1:
    return ResourceClaimV1(
        claim_id=identifier,
        hydrated_inputs_bytes=scale * GIB,
        workspace_bytes=scale * GIB,
        temporary_expansion_bytes=scale * GIB,
        output_bytes=scale * GIB,
        encryption_chunking_bytes=scale * GIB,
        rollback_bytes=scale * GIB,
        effective_from=NOW - timedelta(minutes=1),
        effective_until=NOW + timedelta(minutes=1),
        rollback_until=NOW + timedelta(hours=1),
    )


def test_required_free_grows_and_shrinks_with_selected_graph() -> None:
    empty = evaluate_resource_envelope(_telemetry(), ())
    one = evaluate_resource_envelope(_telemetry(), (_claim("claimIdentifier01"),))
    two = evaluate_resource_envelope(
        _telemetry(),
        (_claim("claimIdentifier01"), _claim("claimIdentifier02", 2)),
    )
    after = evaluate_resource_envelope(
        _telemetry(),
        (_claim("claimIdentifier01"),),
        observed_at=NOW + timedelta(hours=2),
    )
    assert empty.required_free_bytes < one.required_free_bytes < two.required_free_bytes
    assert after.required_free_bytes == empty.required_free_bytes


def test_every_live_telemetry_component_changes_requirement() -> None:
    baseline = evaluate_resource_envelope(_telemetry(), ()).required_free_bytes
    variants = (
        replace(_telemetry(), ram_available_bytes=3 * GIB),
        replace(_telemetry(), swap_used_bytes=7 * GIB),
        replace(_telemetry(), updater_claim_bytes=2 * GIB),
        replace(_telemetry(), apfs_churn_bytes=3 * GIB),
        replace(_telemetry(), telemetry_error_bytes=2 * GIB),
    )
    assert all(evaluate_resource_envelope(value, ()).required_free_bytes > baseline for value in variants)


def test_task_dimensions_and_rollback_lifetime_are_authoritative() -> None:
    claim = _claim("claimIdentifier01")
    baseline = evaluate_resource_envelope(_telemetry(), (claim,)).required_free_bytes
    dimensions = (
        "hydrated_inputs_bytes",
        "workspace_bytes",
        "temporary_expansion_bytes",
        "output_bytes",
        "encryption_chunking_bytes",
        "rollback_bytes",
    )
    for field in dimensions:
        larger = claim.model_copy(update={field: getattr(claim, field) + GIB})
        assert evaluate_resource_envelope(_telemetry(), (larger,)).required_free_bytes == baseline + GIB

    rollback_only = evaluate_resource_envelope(
        _telemetry(),
        (claim,),
        observed_at=NOW + timedelta(minutes=2),
    )
    expired = evaluate_resource_envelope(
        _telemetry(),
        (claim,),
        observed_at=NOW + timedelta(hours=2),
    )
    assert rollback_only.required_free_bytes > expired.required_free_bytes


def test_graph_uses_peak_concurrency_across_its_horizon() -> None:
    first = _claim("claimIdentifier01")
    nonoverlapping = first.model_copy(
        update={
            "claim_id": "claimIdentifier02",
            "effective_from": NOW + timedelta(hours=2),
            "effective_until": NOW + timedelta(hours=2, minutes=2),
            "rollback_until": NOW + timedelta(hours=3),
        }
    )
    overlapping = first.model_copy(update={"claim_id": "claimIdentifier03"})

    one = evaluate_resource_envelope(_telemetry(), (first,))
    sequential = evaluate_resource_envelope(
        _telemetry(),
        (first, nonoverlapping),
    )
    concurrent = evaluate_resource_envelope(
        _telemetry(),
        (first, overlapping),
    )

    assert sequential.required_free_bytes == one.required_free_bytes
    assert concurrent.required_free_bytes > sequential.required_free_bytes


def test_selected_task_graph_claims_are_registry_data(tmp_path) -> None:
    path = tmp_path / "graph.json"
    claims = [_claim("claimIdentifier01"), _claim("claimIdentifier02", 2)]
    path.write_text(
        json.dumps(
            {
                "schema": "limen.resource_task_graph.v1",
                "claims": [claim.model_dump(mode="json") for claim in reversed(claims)],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_task_graph_claims(path)

    assert [claim.claim_id for claim in loaded] == [
        "claimIdentifier02",
        "claimIdentifier01",
    ]


def test_missing_selected_task_graph_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("LIMEN_RESOURCE_TASK_GRAPH", raising=False)

    with pytest.raises(ValueError, match="selected resource task graph is required"):
        load_task_graph_claims()


def test_explicit_empty_graph_remains_observable(monkeypatch) -> None:
    monkeypatch.setattr(
        resource_envelope,
        "observe_resource_telemetry",
        _telemetry,
    )

    assert resource_envelope.current_required_free_gib(claims=()) == (
        evaluate_resource_envelope(_telemetry(), ()).required_free_gib
    )
