"""Synthetic integration proofs: collection is evidence, never launch authority."""

import copy
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import importlib.util
import json
import os
import stat
from datetime import date, datetime, timezone
from pathlib import Path
import subprocess
import sys
import threading

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _schedule_evidence as E


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


U = load("schedule-utilization")
C = load("check-schedules")
K = load("schedule-collect")
NOW = "2026-10-23T12:00:00Z"
DAY = date(2026, 10, 23)


def artifact(**changes):
    value = dict(
        provider="chatgpt",
        surface="external",
        account_ref="account:synthetic",
        owner_ref="project:synthetic",
        source_ref="source:synthetic",
        native_task_id="private-task",
        native_run_id="private-run",
        native_artifact_id="private-artifact",
        content="SYNTHETIC BODY",
        coverage="complete",
        attribution_evidence="receipt:synthetic",
        execution_status="completed",
        times={
            "started_at": "2026-10-23T10:00:00Z",
            "completed_at": "2026-10-23T10:01:00Z",
            "scheduled_for": "2026-10-23T10:00:00Z",
        },
    )
    value.update(changes)
    return value


def snapshot(tmp_path, rows=None, assess=False):
    private = tmp_path / "private"
    private.mkdir(mode=0o700, exist_ok=True)
    with E.EvidenceStore(private / "store.db") as store:
        rows = rows or [E.normalize_artifact(artifact(), observed_at=NOW)]
        store.ingest(rows)
        if assess:
            for status in ("accepted", "delivered"):
                store.assess(
                    rows[0]["observation_id"],
                    status=status,
                    owner_ref="project:synthetic",
                    predicate="predicate:synthetic",
                    evidence_ref="receipt:synthetic",
                    artifact_sha256=rows[0]["artifact"]["sha256"],
                    destination_ref="destination:synthetic" if status == "delivered" else None,
                )
        result = store.export()
    path = private / "snapshot.json"
    path.write_text(json.dumps(result))
    path.chmod(0o600)
    return path, result


def cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "schedule-collect.py"), *map(str, args)], capture_output=True, text=True
    )


def test_collect_cli_deduplicates_without_printing_body_or_ids(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    source = private / "source.json"
    source.write_text(json.dumps([artifact(), artifact()]))
    args = [
        "collect",
        "--source",
        "artifact",
        "--input",
        source,
        "--db",
        private / "db.sqlite",
        "--observed-at",
        NOW,
        "--account-ref",
        "account:synthetic",
        "--owner-ref",
        "project:synthetic",
    ]
    run = cli(*args)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {"status": "ok", "inserted": 1, "deduplicated": 1}
    assert "SYNTHETIC BODY" not in run.stdout + run.stderr
    assert "private-run" not in run.stdout + run.stderr
    assert json.loads(cli(*args).stdout)["inserted"] == 0
    exported = private / "export.json"
    assert cli("export", "--db", private / "db.sqlite", "--output", exported).returncode == 0
    assert exported.stat().st_mode & 0o777 == 0o600
    assert cli("import", "--db", private / "other.db", "--input", exported).returncode == 0


def test_cli_atomic_batch_error_is_sanitized(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    source = private / "source.json"
    source.write_text(json.dumps([artifact(), "SYNTHETIC SECRET BAD ROW"]))
    run = cli(
        "collect",
        "--source",
        "artifact",
        "--input",
        source,
        "--db",
        private / "db",
        "--observed-at",
        NOW,
        "--account-ref",
        "account:synthetic",
        "--owner-ref",
        "project:synthetic",
    )
    assert run.returncode == 2
    assert "SYNTHETIC" not in run.stdout + run.stderr
    with E.EvidenceStore(private / "db") as store:
        assert not store.export()["observations"]


def test_checkpoint_cli_requires_durable_observation_ids_and_explicit_complete(tmp_path):
    path, snap = snapshot(tmp_path)
    db = path.parent / "store.db"
    cursor = path.parent / "cursor.json"
    cursor.write_text(json.dumps({"window_end": NOW}))
    args = [
        "checkpoint",
        "--db",
        db,
        "--source-id",
        "source:synthetic",
        "--cursor",
        cursor,
        "--observation-id",
        snap["observations"][0]["observation_id"],
    ]
    assert json.loads(cli(*args).stdout)["advanced"] is False
    assert json.loads(cli(*args, "--complete").stdout)["advanced"] is True
    run = cli(*args, "--observation-id", "missing", "--complete")
    assert run.returncode == 2


def test_native_reader_counts_current_identity_and_exact_assessments(tmp_path):
    old = E.normalize_artifact(artifact(execution_status="running"), observed_at="2026-10-23T11:00:00Z")
    current = E.normalize_artifact(artifact(), observed_at=NOW)
    path, _ = snapshot(tmp_path, [current, old], assess=True)
    plane = {"evidence": {"locator": str(path), "provider": "chatgpt", "surface": "external"}}
    observed, _, extra = U.read_native_snapshot("p", plane, [], DAY, tmp_path)
    assert observed == 1
    counts = extra["native_counts"]
    assert counts["observations"] == 2 and counts["current_tasks"] == counts["current_runs"] == 1
    assert counts["collected_complete"] == counts["accepted"] == counts["delivered"] == 1
    assert extra["coverage"] == "partial"  # metadata alone never proves account/window completeness
    public = json.dumps(extra)
    assert "private-task" not in public and "private-artifact" not in public and "source:synthetic" not in public


def test_native_reader_stale_results_and_forged_snapshot_fail_closed(tmp_path):
    old = E.normalize_artifact(artifact(times={"completed_at": "2026-10-22T10:01:00Z"}), observed_at=NOW)
    path, result = snapshot(tmp_path, [old])
    plane = {"evidence": {"locator": str(path), "provider": "chatgpt"}}
    count, _, extra = U.read_native_snapshot("p", plane, [], DAY, tmp_path)
    assert count == 0 and extra["native_counts"]["observations"] == 1
    result["observations"][0]["attribution_state"] = "correlated-forged"
    path.write_text(json.dumps(result))
    count, detail, _ = U.read_native_snapshot("p", plane, [], DAY, tmp_path)
    assert count is None and "invalid" in detail


def test_partial_native_evidence_and_comments_never_establish_full():
    assert U.verdict_for({"fill_policy": "declared", "evidence": {"kind": "issue-comments"}}, 10, 20, 0.5) != "full"
    assert U.verdict_for({"fill_policy": "declared", "evidence": {"kind": "native-snapshot"}}, 1, 1, 0.5) != "full"


def test_failed_remote_bookend_read_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "gh_available", lambda: True)
    monkeypatch.setattr(U, "_gh_api", lambda path: (-1, None))
    monkeypatch.setattr(U.S, "sibling_root", lambda *args: None)
    plane = {"evidence": {"locator": "owner/repo:bookends"}}
    assert U.read_bookend_tsv("p", plane, [], DAY, tmp_path)[0] is None


def test_public_board_absence_is_unknown_jules_usage(tmp_path):
    (tmp_path / "tasks.yaml").write_text("schema_version: limen.public_board_projection.v1\ntasks: []\n")
    assert (
        U.read_board_dispatch_receipts("jules", {"evidence": {"locator": "tasks.yaml"}}, [], DAY, tmp_path)[0] is None
    )


def test_claude_snapshot_counts_configuration_separately(tmp_path, monkeypatch):
    monkeypatch.setattr(
        U.S,
        "newest_snapshot",
        lambda root: (Path("dated.json"), {"observed_at": NOW, "triggers": [{"routine": "a", "enabled": True}]}),
    )
    job = U.S.Job("claude/a", "p", [], "UTC", True, True, "manifest")
    count, _, extra = U.read_claude_snapshot("p", {}, [job], DAY, tmp_path)
    assert count is None
    assert extra["configured_enabled"] == 1 and extra["measurement_kind"] == "configuration"


def test_capacity_requires_matching_fresh_complete_evidence():
    now = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
    cap = dict(
        verified_allowance={"value": 10, "account_ref": "a", "unit": "runs", "window": "w", "evidence_ref": "e"},
        usage={
            "value": 3,
            "account_ref": "a",
            "unit": "runs",
            "window": "w",
            "evidence_ref": "u",
            "coverage": "complete",
            "observed_at": NOW,
        },
        downstream={"review": 4, "delivery": 2, "observed_at": NOW, "evidence_ref": "d"},
    )
    assert (
        U.capacity_report({"capacity": cap, "allotment": {"runs": 100, "entitlement": "unverified"}}, now)[
            "usable_remainder"
        ]
        == 2
    )
    for changes in (
        {"coverage": "partial"},
        {"account_ref": "b"},
        {"unit": "tokens"},
        {"window": "yesterday"},
        {"observed_at": "2026-10-22T12:00:00Z"},
    ):
        bad = copy.deepcopy(cap)
        bad["usage"].update(changes)
        assert U.capacity_report({"capacity": bad}, now)["usable_remainder"] is None
    assert U.capacity_report({"allotment": {"runs": 100, "entitlement": "verified"}}, now)["usable_remainder"] is None


def test_audit_schema_rejects_dispatch_capability_and_ownerless_gaps():
    registry = yaml.safe_load((SCRIPTS.parent / "institutio/governance/schedules.yaml").read_text())
    assert registry["audit_only"] is True
    C._failures.clear()
    C.check_schema(registry)
    assert not C._failures
    bad = copy.deepcopy(registry)
    bad["audit_only"] = False
    bad["planes"]["chatgpt-scheduled-tasks"]["capabilities"]["retrieval"]["state"] = "magic"
    bad["coverage_gaps"].append({"gap": "missing", "next_action": "retrieve"})
    C.check_schema(bad)
    assert any("audit_only" in x for x in C._failures)
    assert any("capabilit" in x for x in C._failures)
    assert any("owner" in x for x in C._failures)


def test_duplicate_logical_launch_authority_is_independent_of_minutes():
    registry = {
        "planes": {},
        "jobs": [
            {"id": "one/a", "logical_job": "same", "launch_authority": "one", "enabled": True, "cron": "1 * * * *"},
            {"id": "two/b", "logical_job": "same", "launch_authority": "two", "enabled": True, "cron": "2 * * * *"},
        ],
    }
    C._failures.clear()
    C.check_launch_authority(registry)
    assert any("same" in x for x in C._failures)


def test_offline_flags_are_real_cli_contracts(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        yaml.safe_dump(
            {
                "planes": {
                    "p": {
                        "provider": "x",
                        "enabled": True,
                        "fill_policy": "declared",
                        "evidence": {"kind": "none"},
                        "allotment": {},
                    }
                },
                "jobs": [],
            }
        )
    )
    run = subprocess.run(
        [sys.executable, str(SCRIPTS / "schedule-utilization.py"), "--registry", str(registry), "--json"],
        text=True,
        capture_output=True,
    )
    assert run.returncode in (0, 3), run.stderr
    assert json.loads(run.stdout)["planes"][0]["capacity"]["usable_remainder"] is None
    run = subprocess.run(
        [sys.executable, str(SCRIPTS / "check-schedules.py"), "--registry", str(registry), "--json"],
        text=True,
        capture_output=True,
    )
    result = json.loads(run.stdout)
    assert result["schema_valid"] is False and result["operational_readiness"] == "unverified"


def test_cli_export_requires_expected_revision_and_private_target(tmp_path):
    path, _ = snapshot(tmp_path)
    args = ["export", "--db", path.parent / "store.db", "--output", path]
    original = path.read_bytes()
    assert cli(*args).returncode == 2
    assert path.read_bytes() == original
    digest = hashlib.sha256(original).hexdigest()
    assert cli(*args, "--expected-sha256", digest).returncode == 0
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    assert cli("export", "--db", path.parent / "store.db", "--output", public / "public.json").returncode == 2


@pytest.mark.parametrize(
    "source,payload",
    [
        ("chatgpt", {"id": "synthetic-task", "run_details": {"last_run": None, "latest_result": None}}),
        (
            "grok-email",
            {
                "id": "synthetic-message",
                "threadId": "synthetic-thread",
                "internalDate": "1792750200000",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [{"name": "From", "value": "noreply@x.ai"}],
                    "body": {"data": "U1lOVEhFVElD"},
                    "parts": None,
                },
            },
        ),
    ],
)
def test_cli_native_adapter_routes(source, payload, tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    incoming = private / "incoming.json"
    incoming.write_text(json.dumps(payload))
    run = cli(
        "collect",
        "--source",
        source,
        "--input",
        incoming,
        "--db",
        private / "db",
        "--observed-at",
        NOW,
        "--account-ref",
        "a",
        "--owner-ref",
        "o",
    )
    assert run.returncode == 0, run.stderr
    with E.EvidenceStore(private / "db") as store:
        row = store.export()["observations"][0]
    assert row["attribution_state"] == "unresolved"
    assert row["artifact"]["coverage"] != "complete"


def test_cli_assess_exact_artifact_and_delivery_order(tmp_path):
    path, result = snapshot(tmp_path)
    row = result["observations"][0]
    args = [
        "assess",
        "--db",
        path.parent / "store.db",
        "--observation-id",
        row["observation_id"],
        "--owner-ref",
        row["owner_ref"],
        "--predicate",
        "predicate:synthetic",
        "--evidence-ref",
        "receipt:synthetic",
        "--artifact-sha256",
        row["artifact"]["sha256"],
    ]
    assert cli(*args, "--status", "delivered", "--destination-ref", "destination:synthetic").returncode == 2
    assert cli(*args, "--status", "accepted").returncode == 0
    assert cli(*args, "--status", "delivered", "--destination-ref", "destination:synthetic").returncode == 0
    assert cli(*args, "--status", "accepted", "--artifact-sha256", "0" * 64).returncode == 2


def test_native_snapshot_cli_report_is_partial_and_redacted(tmp_path):
    path, _ = snapshot(tmp_path)
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        yaml.safe_dump(
            {
                "planes": {
                    "p": {
                        "provider": "chatgpt",
                        "enabled": True,
                        "fill_policy": "declared",
                        "native_inventory": {"enabled_count": 1},
                        "allotment": {"window": "active-tasks"},
                        "evidence": {"kind": "native-snapshot", "locator": "unused", "provider": "chatgpt"},
                    }
                },
                "jobs": [],
            }
        )
    )
    run = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "schedule-utilization.py"),
            "--registry",
            str(registry),
            "--snapshot",
            str(path),
            "--day",
            str(DAY),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    plane = json.loads(run.stdout)["planes"][0]
    assert plane["verdict"] == "partial-evidence" and plane["coverage"] == "partial"
    assert "private-task" not in run.stdout and "SYNTHETIC" not in run.stdout


def test_capacity_schema_rejects_boolean_quantities():
    registry = yaml.safe_load((SCRIPTS.parent / "institutio/governance/schedules.yaml").read_text())
    registry["planes"]["jules"]["capacity"] = {
        "usage": {
            "value": True,
            "account_ref": "a",
            "unit": "runs",
            "window": "w",
            "coverage": "full",
            "evidence_ref": "r",
            "observed_at": NOW,
        }
    }
    C._failures.clear()
    C.check_schema(registry)
    assert any("capacity quantity" in f for f in C._failures)
    assert any("capacity coverage" in f for f in C._failures)


def test_malformed_github_run_payload_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "gh_available", lambda: True)
    monkeypatch.setattr(U, "workflow_states", lambda repo: {"a.yml": "active"})
    monkeypatch.setattr(U, "gh_json", lambda args: {"message": "synthetic-error"})
    job = U.S.Job("p/a", "p", ["1 * * * *"], "UTC", True, True, "workflow", extra={"workflow_file": "a.yml"})
    assert U.read_gh_actions_runs("p", {"evidence": {"locator": "o/r"}}, [job], DAY, tmp_path)[0] is None


def test_full_sized_github_run_page_cannot_claim_complete_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "gh_available", lambda: True)
    monkeypatch.setattr(U, "workflow_states", lambda repo: {"a.yml": "active"})
    monkeypatch.setattr(U, "gh_json", lambda args: [{"conclusion": "success"}] * 100)
    job = U.S.Job("p/a", "p", ["1 * * * *"], "UTC", True, True, "workflow", extra={"workflow_file": "a.yml"})
    _, _, extra = U.read_gh_actions_runs("p", {"evidence": {"locator": "o/r"}}, [job], DAY, tmp_path)
    assert extra["coverage"] == "partial"


def test_new_unknown_attempt_does_not_retain_old_completed_as_current(tmp_path):
    old = E.normalize_artifact(artifact(), observed_at="2026-10-23T11:00:00Z")
    unknown = E.normalize_artifact(
        artifact(native_run_id=None, native_artifact_id=None, execution_status="unknown", times={}), observed_at=NOW
    )
    path, _ = snapshot(tmp_path, [old, unknown])
    observed, _, extra = U.read_native_snapshot("p", {"evidence": {"locator": str(path)}}, [], DAY, tmp_path)
    assert observed == 0 and extra["native_counts"]["current_runs"] == 0


def test_local_policy_cap_is_not_a_published_account_ceiling():
    report = U.capacity_report(
        {"allotment": {"runs": 2000, "classification": "local-policy"}, "floor": 25},
        datetime(2026, 10, 23, 12, tzinfo=timezone.utc),
    )
    assert report["published_ceiling"] is None and report["local_policy"]["limit"] == 2000
    assert report["verified_allowance"] is None and report["usable_remainder"] is None


def test_export_cannot_replace_its_live_database(tmp_path):
    path, _ = snapshot(tmp_path)
    db = path.parent / "store.db"
    original = db.read_bytes()
    assert (
        cli("export", "--db", db, "--output", db, "--expected-sha256", hashlib.sha256(original).hexdigest()).returncode
        == 2
    )
    with E.EvidenceStore(db) as store:
        assert len(store.export()["observations"]) == 1


@pytest.mark.parametrize("command", ["export", "assess", "checkpoint"])
def test_noncollection_commands_never_create_missing_db(tmp_path, command):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    missing = private / "missing.db"
    if command == "export":
        args = ["--output", private / "new.json"]
    elif command == "assess":
        args = [
            "--observation-id",
            "synthetic",
            "--owner-ref",
            "o",
            "--predicate",
            "p",
            "--evidence-ref",
            "e",
            "--artifact-sha256",
            "0" * 64,
            "--status",
            "accepted",
        ]
    else:
        cursor = private / "cursor.json"
        cursor.write_text("{}")
        args = ["--source-id", "s", "--cursor", cursor, "--empty-window", "--complete"]
    assert cli(command, "--db", missing, *args).returncode == 2
    assert not missing.exists()
    assert not (private / "new.json").exists()


def test_expected_missing_export_does_not_leave_sentinel(tmp_path):
    path, _ = snapshot(tmp_path)
    output = path.parent / "missing.json"
    assert (
        cli("export", "--db", path.parent / "store.db", "--output", output, "--expected-sha256", "0" * 64).returncode
        == 2
    )
    assert not output.exists()


def native_readback(*, complete, observed_at):
    task = {"id": "synthetic-native-task", "run_details": None}
    if complete:
        task["run_details"] = {
            "last_run": {
                "id": "synthetic-run",
                "status": "completed",
                "started_at": "2026-10-23T10:00:00Z",
                "completed_at": "2026-10-23T10:02:00Z",
                "scheduled_for": "2026-10-23T10:00:00Z",
            },
            "latest_result": {
                "id": "synthetic-result",
                "run_id": "synthetic-run",
                "created_at": "2026-10-23T10:01:00Z",
                "scheduled_for": "2026-10-23T10:00:00Z",
                "content": "SYNTHETIC",
                "coverage": "complete",
            },
        }
    return E.normalize_chatgpt(
        task, observed_at=observed_at, account_ref="synthetic-account", owner_ref="synthetic-owner"
    )


@pytest.mark.parametrize("first_complete", [False, True])
def test_repeated_latest_readback_wins_and_roundtrips_with_history(tmp_path, first_complete):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    rows = [
        native_readback(complete=complete, observed_at=f"2026-10-23T{hour}:00:00Z")
        for complete, hour in [(first_complete, "11"), (not first_complete, "12"), (first_complete, "13")]
    ]
    with E.EvidenceStore(private / "first.db") as store:
        store.ingest(rows)
        accepted = next(row for row in rows if row["artifact"]["coverage"] == "complete")
        for status in ("accepted", "delivered"):
            store.assess(
                accepted["observation_id"],
                status=status,
                owner_ref="synthetic-owner",
                predicate="synthetic-predicate",
                evidence_ref="synthetic-receipt",
                artifact_sha256=accepted["artifact"]["sha256"],
                destination_ref="synthetic-destination" if status == "delivered" else None,
            )
        original = store.export()
    with E.EvidenceStore(private / "roundtrip.db") as store:
        store.import_snapshot(original)
        assert store.export() == original
        snapshot = store.export()
    path = private / "union.json"
    path.write_text(json.dumps(snapshot))
    observed, _, extra = U.read_native_snapshot("p", {"evidence": {"locator": str(path)}}, [], DAY, tmp_path)
    counts = extra["native_counts"]
    assert counts["observations"] == 2 and counts["current_tasks"] == 1
    for key in ("current_runs", "collected_complete", "attributed", "accepted", "delivered"):
        assert counts[key] == int(first_complete), (key, counts)
    assert observed == int(first_complete)
    assert counts["accepted_history"] == counts["delivered_history"] == 1


def test_later_historical_import_preserves_actual_old_readback_time(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    current = native_readback(complete=False, observed_at="2026-10-23T13:00:00Z")
    older = native_readback(complete=True, observed_at="2026-10-23T11:00:00Z")
    with E.EvidenceStore(private / "history.db") as history:
        history.ingest([older])
        old_snapshot = history.export()
    with E.EvidenceStore(private / "current.db") as store:
        store.ingest([current])
        store.import_snapshot(old_snapshot)  # imported later, actual historical observation stays 11:00
        exported = store.export()
        old_row = next(row for row in exported["observations"] if row["observation_id"] == older["observation_id"])
        assert old_row["last_observed_at"] == "2026-10-23T11:00:00Z"
    path = private / "union.json"
    path.write_text(json.dumps(exported))
    observed, _, extra = U.read_native_snapshot("p", {"evidence": {"locator": str(path)}}, [], DAY, tmp_path)
    assert observed == 0 and extra["native_counts"]["current_runs"] == 0


@pytest.mark.parametrize("existing", [True, False])
def test_same_revision_export_writers_are_serialized(tmp_path, monkeypatch, existing):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "union.json"
    if existing:
        target.write_text('{"previous": true}')
        target.chmod(0o600)
    expected = hashlib.sha256(target.read_bytes()).hexdigest() if existing else None
    at_validation = threading.Barrier(2)
    interleaved = threading.Event()
    state = threading.local()
    guard = threading.Lock()
    reads = 0
    temporaries = 0
    original_private = K._private_path
    original_read = Path.read_bytes
    original_temp = K.tempfile.mkstemp
    original_flock = fcntl.flock

    def validate(path, *args, **kwargs):
        if Path(path) == target and not getattr(state, "validated", False):
            state.validated = True
            at_validation.wait(timeout=5)
        return original_private(path, *args, **kwargs)

    def read(path):
        nonlocal reads
        value = original_read(path)
        if path == target:
            with guard:
                reads += 1
                if reads > 1:
                    interleaved.set()
        return value

    def flock(fd, mode):
        try:
            return original_flock(fd, mode)
        except BlockingIOError:
            interleaved.set()  # competing writer reached the held stable lock
            raise

    def temporary(*args, **kwargs):
        nonlocal temporaries
        with guard:
            temporaries += 1
            first = temporaries == 1
        if first:
            assert interleaved.wait(timeout=5), "other writer did not reach the read/lock boundary"
        else:
            interleaved.set()  # old code: both writers reached temp creation after checking revision
        return original_temp(*args, **kwargs)

    monkeypatch.setattr(K, "_private_path", validate)
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(K.tempfile, "mkstemp", temporary)
    monkeypatch.setattr(fcntl, "flock", flock)

    def write(value):
        try:
            K.write_snapshot(target, {"writer": value}, expected)
            return "ok"
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(write, ("A", "B")))
    assert sorted(results) == ["conflict", "ok"]
    assert json.loads(original_read(target))["writer"] in {"A", "B"}
    lock = private / ".union.json.lock"
    assert lock.is_file() and stat.S_IMODE(lock.stat().st_mode) == 0o600


def test_export_fsyncs_directory_and_reports_post_replace_failure(tmp_path, monkeypatch):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "union.json"
    original_fsync = os.fsync
    synced_directory = []

    def sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            synced_directory.append(True)
            assert target.is_file(), "directory must sync after rename"
        return original_fsync(fd)

    monkeypatch.setattr(K.os, "fsync", sync)
    K.write_snapshot(target, {"revision": 1}, None)
    assert synced_directory

    def failed_sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("synthetic directory sync failure")
        return original_fsync(fd)

    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    monkeypatch.setattr(K.os, "fsync", failed_sync)
    with pytest.raises(OSError, match="readback required"):
        K.write_snapshot(target, {"revision": 2}, expected)
    assert json.loads(target.read_text()) == {"revision": 2}  # rename happened; never imply rollback


@pytest.mark.parametrize(
    "allotment",
    [
        {"runs": 7, "classification": "unmeasured"},
        {"runs": 7},
        {"runs": 7, "classification": "published-ceiling", "source": "secondary rumor"},
    ],
)
def test_unclassified_or_unevidenced_quota_is_not_a_published_ceiling(allotment):
    assert (
        U.capacity_report({"allotment": allotment}, datetime(2026, 10, 23, tzinfo=timezone.utc))["published_ceiling"]
        is None
    )


def test_classified_publication_is_distinct_from_account_entitlement():
    allotment = {
        "runs": 7,
        "classification": "published-ceiling",
        "publication": {"source": "https://provider.example/docs/limits", "observed_at": NOW},
    }
    report = U.capacity_report({"allotment": allotment}, datetime(2026, 10, 23, tzinfo=timezone.utc))
    assert report["published_ceiling"] == 7 and report["verified_allowance"] is None
    assert report["usable_remainder"] is None


def test_registry_has_no_invented_chatgpt_ceiling():
    registry = yaml.safe_load((SCRIPTS.parent / "institutio/governance/schedules.yaml").read_text())
    chatgpt = registry["planes"]["chatgpt-scheduled-tasks"]
    assert chatgpt["allotment"]["runs"] is None
    assert chatgpt["native_inventory"]["enabled_count"] == 15


def test_registry_has_correct_grok_sample_date():
    registry = yaml.safe_load((SCRIPTS.parent / "institutio/governance/schedules.yaml").read_text())
    sample = next(row for row in registry["provenance"] if "20 excerpts" in row["coverage"])
    assert sample["observed_at"] == "2026-10-23T19:37:34Z"


def test_published_ceiling_classification_requires_dated_publication_evidence():
    registry = yaml.safe_load((SCRIPTS.parent / "institutio/governance/schedules.yaml").read_text())
    quota = registry["planes"]["jules"]["allotment"]
    quota.update(classification="published-ceiling", runs=7)
    quota.pop("publication", None)
    C._failures.clear()
    C.check_schema(registry)
    assert any("publication" in failure for failure in C._failures)
    quota["publication"] = {"source": "https://provider.example/docs/limits", "observed_at": NOW}
    C._failures.clear()
    C.check_schema(registry)
    assert not C._failures


def test_export_refuses_symlink_lock(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    other = private / "other"
    other.write_text("SYNTHETIC")
    (private / ".union.json.lock").symlink_to(other)
    with pytest.raises(ValueError, match="symlink"):
        K.write_snapshot(private / "union.json", {"value": 1}, None)
    assert not (private / "union.json").exists()


def test_directory_sync_cli_failure_requires_readback(tmp_path, monkeypatch, capsys):
    path, _ = snapshot(tmp_path)
    target = path.parent / "new.json"
    original_fsync = os.fsync

    def failed_sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("synthetic directory sync failure")
        return original_fsync(fd)

    monkeypatch.setattr(K.os, "fsync", failed_sync)
    result = K.main(["export", "--db", str(path.parent / "store.db"), "--output", str(target)])
    output = capsys.readouterr()
    assert result == 2 and "readback required" in output.err
    assert target.is_file()  # visible replacement must not be mistaken for rollback or durable success


def test_busy_export_lock_has_finite_deadline_and_preserves_target(tmp_path, monkeypatch):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "union.json"
    target.write_text('{"revision": 1}')
    lock = private / ".union.json.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    original = target.read_bytes()
    try:
        monkeypatch.setattr(K, "LOCK_TIMEOUT_SECONDS", 0)
        with pytest.raises(TimeoutError, match="deadline"):
            K.write_snapshot(target, {"revision": 2}, hashlib.sha256(original).hexdigest())
        assert target.read_bytes() == original
        assert lock.stat().st_ino == os.fstat(descriptor).st_ino
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("publication", ["not-a-record", {"source": "https://[invalid", "observed_at": NOW}])
def test_malformed_publication_is_rejected_without_report_crash(publication):
    registry = yaml.safe_load((SCRIPTS.parent / "institutio/governance/schedules.yaml").read_text())
    allotment = registry["planes"]["jules"]["allotment"]
    allotment.update(classification="published-ceiling", publication=publication)
    C._failures.clear()
    C.check_schema(registry)
    assert any("publication" in failure for failure in C._failures)
    assert (
        U.capacity_report({"allotment": allotment}, datetime(2026, 10, 23, tzinfo=timezone.utc))["published_ceiling"]
        is None
    )
