from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from limen.cli import main
from limen.conduct.client import LocalConductClient
from limen.conduct.models import (
    AgentIdentityV1,
    CheckEvidenceV1,
    ConductorSessionV1,
    PredicateEvidenceV1,
    RunReceiptV1,
)
from limen.fanout import (
    FanoutError,
    FanoutManifestV1,
    canonical_entry_hash,
    compile_packets,
    harvest_root,
    plan_manifest,
    route_manifest,
    serialize_resource_conflicts,
    should_evaluate_fanout,
    start_manifest,
)
from limen.fanout_executor import (
    FanoutExecutionError,
    ProviderLaunch,
    _assert_topic_branch,
    _working_tree_changed_paths,
    register_execution_sessions,
)


FUTURE = datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat()
BASE = "a" * 40
HEAD = "b" * 40
DIGEST = "c" * 64
CODE_CAPABILITIES = [
    "code",
    "exact-base-receipt",
    "exact-diff-receipt",
    "exact-head-receipt",
    "predicate-receipt",
    "pull-request-receipt",
]


def manifest_payload() -> dict:
    identity = {
        "agent": "codex",
        "surface": "cli",
        "session_id": "session-1",
    }
    leaf = {
        "work_id": "leaf-a",
        "idempotency_key": "campaign/leaf-a",
        "owner_repository": "organvm/limen",
        "exact_base": BASE,
        "topic_branch": "work/leaf-a",
        "allowed_paths": ["cli/src/limen"],
        "resource_claims": [{"key": f"path/organvm/limen/{BASE}/cli/src/limen"}],
        "required_capabilities": ["code"],
        "intended_effect": "implement leaf A",
        "predicate": "pytest -q cli/tests/test_a.py",
        "receipt_target": "github:organvm/limen:pr",
        "deadline": FUTURE,
        "retry": {"max_attempts": 2, "transient_only": True},
        "spend": {"unit": "runs", "limit": 2},
        "prompt_hash": DIGEST,
        "plan_hash": "d" * 64,
    }
    return {
        "root_work_id": "campaign",
        "idempotency_key": "campaign/v1",
        "initiator": identity,
        "conductor": identity,
        "predicate": "limen fanout status campaign --json",
        "receipt_target": "conduct:campaign",
        "deadline": FUTURE,
        "leaves": [leaf],
    }


def session(
    session_id: str,
    *,
    agent: str,
    transport: str,
    capabilities: list[str] | None = None,
    concurrency: int = 4,
) -> dict:
    return {
        "session_id": session_id,
        "identity": {"agent": agent, "surface": "native", "session_id": session_id},
        "transport": transport,
        "capabilities": capabilities or CODE_CAPABILITIES,
        "healthy": True,
        "accepting_work": True,
        "active_leases": 0,
        "concurrency": concurrency,
    }


def test_manifest_rejects_raw_prompts_models_and_unbounded_retry() -> None:
    raw_prompt = manifest_payload()
    raw_prompt["leaves"][0]["prompt"] = "private text"
    with pytest.raises(ValidationError, match="may not contain prompt"):
        FanoutManifestV1.model_validate(raw_prompt)

    model = manifest_payload()
    model["leaves"][0]["model_id"] = "fixed-catalog-name"
    with pytest.raises(ValidationError, match="model_id"):
        FanoutManifestV1.model_validate(model)

    retry = manifest_payload()
    retry["leaves"][0]["retry"]["max_attempts"] = 0
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        FanoutManifestV1.model_validate(retry)


def test_portable_manifest_schema_matches_the_runtime_contract() -> None:
    schema_path = (
        Path(__file__).resolve().parents[2] / "spec" / "contracts" / "conduct" / "fanout-manifest-v1.schema.json"
    )
    expected = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **FanoutManifestV1.model_json_schema(mode="validation"),
    }
    assert json.loads(schema_path.read_text(encoding="utf-8")) == expected


def test_conflicts_become_dependencies_and_all_entry_hashes_match() -> None:
    payload = manifest_payload()
    second = deepcopy(payload["leaves"][0])
    second.update(
        {
            "work_id": "leaf-b",
            "idempotency_key": "campaign/leaf-b",
            "topic_branch": "work/leaf-b",
        }
    )
    payload["leaves"].append(second)
    manifest = FanoutManifestV1.model_validate(payload)
    canonical = serialize_resource_conflicts(manifest)

    assert canonical.leaves[1].dependencies == ("leaf-a",)
    assert plan_manifest(manifest)["topological_order"] == ["leaf-a", "leaf-b"]
    assert {canonical_entry_hash(manifest, entry=entry) for entry in ("automatic", "conversational", "cli")} == {
        canonical.manifest_hash
    }


def test_dynamic_route_prefers_remote_and_caps_local_fallback() -> None:
    manifest = FanoutManifestV1.model_validate(manifest_payload())
    live = {
        "sessions": [
            session("local-1", agent="arbitrary-local", transport="local-cli"),
            session("remote-1", agent="arbitrary-remote", transport="remote-api")
            | {"receipt_quality": 0.9, "cost_per_run": 1},
            session("remote-exhausted", agent="arbitrary-exhausted", transport="remote-api")
            | {"quota_remaining": 0, "receipt_quality": 1},
            session("remote-expensive", agent="arbitrary-expensive", transport="remote-api")
            | {"receipt_quality": 0.9, "cost_per_run": 2},
        ]
    }
    route = route_manifest(manifest, live, remote_first=True, local_max=1)
    assert route["routes"][0]["session_id"] == "remote-1"
    assert route["routes"][0]["local_heavy"] is False

    no_remote = {"sessions": [session("local-1", agent="renamed", transport="local-heavy")]}
    assert route_manifest(manifest, no_remote)["routes"][0]["local_heavy"] is True

    payload = manifest_payload()
    second = deepcopy(payload["leaves"][0])
    second.update(
        {
            "work_id": "leaf-b",
            "idempotency_key": "campaign/leaf-b",
            "topic_branch": "work/leaf-b",
            "resource_claims": [{"key": f"path/organvm/limen/{BASE}/docs"}],
            "allowed_paths": ["docs"],
        }
    )
    payload["leaves"].append(second)
    with pytest.raises(FanoutError, match="local fallback limit 1"):
        route_manifest(FanoutManifestV1.model_validate(payload), no_remote, local_max=1)

    one_slot = {
        "sessions": [
            session(
                "remote-one-slot",
                agent="runtime",
                transport="remote-api",
                concurrency=1,
            )
        ]
    }
    with pytest.raises(FanoutError, match="no live executor"):
        route_manifest(FanoutManifestV1.model_validate(payload), one_slot)


def test_working_tree_diff_sees_modified_added_deleted_and_untracked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.com"], cwd=repo, check=True)
    (repo / "modified.txt").write_text("before\n", encoding="utf-8")
    (repo / "deleted.txt").write_text("delete\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    (repo / "modified.txt").write_text("after\n", encoding="utf-8")
    (repo / "deleted.txt").unlink()
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=repo, check=True)
    (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    assert _working_tree_changed_paths(repo, base) == (
        "deleted.txt",
        "modified.txt",
        "staged.txt",
        "untracked.txt",
    )


def test_landing_refuses_the_live_default_branch(monkeypatch) -> None:
    monkeypatch.setattr("limen.fanout_executor._default_branch", lambda repository: "trunk")
    with pytest.raises(FanoutExecutionError, match="refuses"):
        _assert_topic_branch("organvm/limen", "trunk")
    assert _assert_topic_branch("organvm/limen", "work/topic") == "trunk"


def test_packet_compilation_is_board_independent_and_hash_bound() -> None:
    manifest = FanoutManifestV1.model_validate(manifest_payload())
    route = route_manifest(
        manifest,
        {"sessions": [session("remote-1", agent="renamed-remote", transport="remote-api")]},
    )
    root, leaf = compile_packets(manifest, route)

    assert root.task_id is None
    assert leaf.task_id is None
    assert leaf.parent_run_id == leaf.root_run_id
    assert leaf.execution["exact_base"] == BASE
    assert leaf.execution["manifest_hash"] == serialize_resource_conflicts(manifest).manifest_hash
    assert leaf.preferred_agent == "renamed-remote"
    assert set(CODE_CAPABILITIES) <= leaf.required_capabilities
    assert f"campaign:{manifest.manifest_hash}" in leaf.required_capabilities


class FakeKeeper:
    def __init__(self, harvest: dict | None = None):
        self._harvest = harvest
        self.submitted = ()
        self.sessions = {}
        self.nodes = []

    def capabilities(self) -> dict:
        return {"sessions": [value | {"healthy": True, "active_leases": 0} for value in self.sessions.values()]}

    def register(self, value):
        payload = value.model_dump(mode="json")
        self.sessions[value.session_id] = payload
        return payload

    def submit_graph(self, packets):
        self.submitted = packets
        self.nodes = []
        for index, packet in enumerate(packets):
            run_id = "run-root" if index == 0 else f"run-leaf-{index}"
            lease = None
            status = "running" if index == 0 else "reserved"
            if index:
                lease = {
                    "lease_id": f"lease-{index}",
                    "run_id": run_id,
                    "executor": self.sessions[packet.execution["executor_session_id"]]["identity"],
                    "resources": [],
                    "observed_heads": packet.execution["observed_heads"],
                    "generation": index,
                    "resource_generations": {},
                    "acquired_at": FUTURE,
                    "heartbeat_at": FUTURE,
                    "hard_deadline": FUTURE,
                    "state": "reserved",
                }
            self.nodes.append(
                {
                    "run_id": run_id,
                    "root_run_id": packets[1].root_run_id,
                    "status": status,
                    "executor_session_id": packet.execution.get("executor_session_id"),
                    "lease_id": lease["lease_id"] if lease else None,
                    "lease": lease,
                    "attempts": [],
                    "receipts": [],
                    "packet": packet.model_dump(mode="json"),
                }
            )
        return {
            "status": "reserved",
            "root_run_id": packets[1].root_run_id,
            "runs": [{"duplicate": False} for _ in packets],
        }

    def graph(self, root_run_id):
        return {"root_run_id": root_run_id, "nodes": deepcopy(self.nodes)}

    def claim(self, lease_id, generation):
        return {
            "lease_id": lease_id,
            "generation": generation,
            "capability_token": "fake-capability",
        }

    def heartbeat(self, lease_id, capability_token, *, generation, observed_heads, attempt=None):
        del capability_token, generation, observed_heads
        node = next(row for row in self.nodes if row["lease_id"] == lease_id)
        node["status"] = "running"
        if attempt is not None:
            payload = attempt.model_dump(mode="json")
            if node["attempts"]:
                node["attempts"][-1] = payload
            else:
                node["attempts"].append(payload)
        return {"status": "active", "lease": node["lease"]}

    def harvest(self, root_run_id):
        assert root_run_id == "run-root"
        return deepcopy(self._harvest)


class FakeExecutionAdapter:
    name = "fake-remote"
    transport = "remote-fake"
    local_heavy = False
    concurrency = 4
    receipt_quality = 1.0
    cost_per_run = 0.0
    quota_remaining = 10.0
    capabilities = frozenset(CODE_CAPABILITIES)
    conduct_token_env = "LIMEN_CONDUCT_TOKEN_FAKE"

    def __init__(self):
        self.launches = []

    def eligible(self, packet):
        return packet["execution"]["owner_repository"] == "organvm/limen"

    def launch(self, packet, attempt_id):
        self.launches.append((packet["work_id"], attempt_id))
        return ProviderLaunch("provider-run-1", "https://executor.example/runs/1")

    def recover(self, packet, attempt_id):
        del packet, attempt_id
        return None


def test_conductor_never_registers_executor_sessions(monkeypatch) -> None:
    manifest = FanoutManifestV1.model_validate(manifest_payload())
    conductor_client = FakeKeeper()
    executor_client = FakeKeeper()
    adapter = FakeExecutionAdapter()
    monkeypatch.setattr(
        "limen.fanout_executor._client_for_adapter",
        lambda client, selected: executor_client,
    )

    lanes = register_execution_sessions(manifest, conductor_client, (adapter,))

    assert set(conductor_client.sessions) == {manifest.conductor.session_id}
    assert len(executor_client.sessions) == 1
    assert set(lanes) == set(executor_client.sessions)


def test_start_uses_atomic_keeper_and_launches_every_ready_leaf(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = FanoutManifestV1.model_validate(manifest_payload())
    keeper = FakeKeeper()
    adapter = FakeExecutionAdapter()
    monkeypatch.setattr("limen.fanout_executor.remote_default_head", lambda repo: BASE)
    result = start_manifest(manifest, client=keeper, execution_adapters=(adapter,))
    assert result["root_run_id"]
    assert len(keeper.submitted) == 2
    assert len(result["attempts"]) == 1
    assert len(adapter.launches) == 1

    local = LocalConductClient(tmp_path / "conduct.sqlite")
    with pytest.raises(FanoutError, match="authenticated remote keeper"):
        start_manifest(manifest, client=local, execution_adapters=(adapter,))


def test_keeper_serializes_overlapping_dependencies_and_settles_campaign(
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = manifest_payload()
    second = deepcopy(payload["leaves"][0])
    second.update(
        {
            "work_id": "leaf-b",
            "idempotency_key": "campaign/leaf-b",
            "topic_branch": "work/leaf-b",
        }
    )
    payload["leaves"].append(second)
    manifest = FanoutManifestV1.model_validate(payload)
    keeper = LocalConductClient(tmp_path / "keeper.sqlite")
    conductor_identity = AgentIdentityV1.model_validate(payload["conductor"])
    executor_identity = AgentIdentityV1(
        agent="runtime-renamed",
        surface="remote",
        session_id="remote-runtime",
    )
    keeper.register(
        ConductorSessionV1(
            session_id=conductor_identity.session_id,
            identity=conductor_identity,
            origin="direct",
            capabilities=frozenset({"conduct"}),
            concurrency=1,
        )
    )
    keeper.register(
        ConductorSessionV1(
            session_id=executor_identity.session_id,
            identity=executor_identity,
            origin="relay",
            capabilities=frozenset(CODE_CAPABILITIES) | frozenset({f"campaign:{manifest.manifest_hash}"}),
            transport="remote-api",
            concurrency=2,
        )
    )
    adapter = FakeExecutionAdapter()
    monkeypatch.setattr("limen.fanout_executor.remote_default_head", lambda repo: BASE)
    started = start_manifest(
        manifest,
        client=keeper,
        allow_development_keeper=True,
        execution_adapters=(adapter,),
    )
    repeated = start_manifest(
        manifest,
        client=keeper,
        allow_development_keeper=True,
        execution_adapters=(adapter,),
    )
    assert repeated["root_run_id"] == started["root_run_id"]
    assert repeated["idempotent"] is True
    assert len(adapter.launches) == 1
    graph = keeper.graph(started["root_run_id"])
    statuses = {node["packet"]["work_id"]: node["status"] for node in graph["nodes"]}
    assert statuses == {"campaign": "running", "leaf-a": "running", "leaf-b": "waiting"}

    for work_id in ("leaf-a", "leaf-b"):
        graph = keeper.graph(started["root_run_id"])
        node = next(item for item in graph["nodes"] if item["packet"]["work_id"] == work_id)
        lease = keeper.store.snapshot()["leases"][node["lease_id"]]
        claimed = keeper.claim(lease["lease_id"], lease["generation"])
        receipt = RunReceiptV1(
            receipt_id=f"receipt-{work_id}",
            run_id=node["run_id"],
            lease_id=lease["lease_id"],
            lease_generation=lease["generation"],
            executor=AgentIdentityV1.model_validate(lease["executor"]),
            observed_heads_before={"organvm/limen": BASE},
            observed_heads_after={"organvm/limen": HEAD},
            changed_paths=("cli/src/limen/fanout.py",),
            provider_run_url=f"https://executor.example/{work_id}",
            predicate=PredicateEvidenceV1(command=node["packet"]["predicate"], exit_code=0),
            checks=(
                CheckEvidenceV1(
                    name="exact-diff",
                    status="success",
                    url=f"https://executor.example/{work_id}/diff",
                ),
                CheckEvidenceV1(
                    name="pull-request",
                    status="success",
                    url=f"https://github.com/organvm/limen/pull/{1 if work_id == 'leaf-a' else 2}",
                    head=HEAD,
                ),
            ),
            spend={"runs": 1},
            outcome="succeeded",
        )
        keeper.report(
            lease["lease_id"],
            claimed["capability_token"],
            receipt,
            generation=lease["generation"],
        )

    terminal = keeper.harvest(started["root_run_id"])
    assert terminal["unharvested"] == []
    assert terminal["by_status"] == {"succeeded": 3}
    assert terminal["receipt_count"] == 3
    after_terminal = start_manifest(
        manifest,
        client=keeper,
        allow_development_keeper=True,
        execution_adapters=(adapter,),
    )
    assert after_terminal["idempotent"] is True
    assert keeper.harvest(started["root_run_id"])["by_status"] == {"succeeded": 3}


def test_start_launches_disjoint_remote_leaves_while_dependency_waits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = manifest_payload()
    disjoint = deepcopy(payload["leaves"][0])
    disjoint.update(
        {
            "work_id": "leaf-b",
            "idempotency_key": "campaign/leaf-b",
            "topic_branch": "work/leaf-b",
            "resource_claims": [{"key": f"path/organvm/limen/{BASE}/docs"}],
            "allowed_paths": ["docs"],
        }
    )
    dependent = deepcopy(payload["leaves"][0])
    dependent.update(
        {
            "work_id": "leaf-c",
            "idempotency_key": "campaign/leaf-c",
            "topic_branch": "work/leaf-c",
            "resource_claims": [{"key": f"path/organvm/limen/{BASE}/web"}],
            "allowed_paths": ["web"],
            "dependencies": ["leaf-a"],
        }
    )
    payload["leaves"].extend([disjoint, dependent])
    manifest = FanoutManifestV1.model_validate(payload)
    keeper = LocalConductClient(tmp_path / "disjoint.sqlite")
    adapter = FakeExecutionAdapter()
    monkeypatch.setattr("limen.fanout_executor.remote_default_head", lambda repo: BASE)
    started = start_manifest(
        manifest,
        client=keeper,
        allow_development_keeper=True,
        execution_adapters=(adapter,),
    )
    graph = keeper.graph(started["root_run_id"])
    status = {node["packet"]["work_id"]: node["status"] for node in graph["nodes"]}
    assert status == {
        "campaign": "running",
        "leaf-a": "running",
        "leaf-b": "running",
        "leaf-c": "waiting",
    }
    assert {work_id for work_id, _ in adapter.launches} == {"leaf-a", "leaf-b"}


def terminal_harvest() -> dict:
    manifest = FanoutManifestV1.model_validate(manifest_payload())
    route = route_manifest(
        manifest,
        {"sessions": [session("remote-1", agent="renamed-remote", transport="remote-api")]},
    )
    _, packet = compile_packets(manifest, route)
    receipt = {
        "receipt_id": "receipt-1",
        "mutation_authorized": True,
        "outcome": "succeeded",
        "provider_run_url": "https://executor.example/runs/1",
        "observed_heads_before": {"organvm/limen": BASE},
        "observed_heads_after": {"organvm/limen": HEAD},
        "changed_paths": ["cli/src/limen/fanout.py"],
        "predicate": {"command": packet.predicate, "exit_code": 0},
        "checks": [
            {
                "name": "exact-diff",
                "status": "success",
                "url": "https://executor.example/diffs/1",
                "head": DIGEST,
            },
            {
                "name": "pull-request",
                "status": "success",
                "url": "https://github.com/organvm/limen/pull/9999",
                "head": HEAD,
            },
        ],
    }
    return {
        "root_run_id": "run-root",
        "receipt_count": 1,
        "unharvested": [],
        "nodes": [
            {
                "run_id": "run-leaf",
                "packet": packet.model_dump(mode="json"),
                "receipts": [receipt],
            }
        ],
    }


def test_harvest_validates_exact_receipt_and_returns_pr_without_local_state() -> None:
    result = harvest_root("run-root", client=FakeKeeper(terminal_harvest()))
    assert result["landed"] == [
        {
            "run_id": "run-leaf",
            "receipt_id": "receipt-1",
            "adapter": "pull-request-receipt",
            "pr": "https://github.com/organvm/limen/pull/9999",
            "merged": False,
        }
    ]


@pytest.mark.parametrize(
    ("schema_version", "evidence"),
    [
        (
            "limen.fanout_fence_receipt.v1",
            {
                "expected_heads": {"organvm/limen": BASE},
                "observed_heads": {},
                "reason": "required observed head omitted",
            },
        ),
        (
            "limen.fanout_expiry_receipt.v1",
            {
                "expected_heads": {"organvm/limen": BASE},
                "observed_heads": {},
                "reason": "authenticated lease heartbeat expired",
            },
        ),
        ("limen.fanout_dependency_receipt.v1", {}),
    ],
)
def test_harvest_accepts_exact_keeper_terminal_receipts(schema_version, evidence) -> None:
    payload = terminal_harvest()
    payload["nodes"][0]["receipts"] = [
        {
            "schema_version": schema_version,
            "receipt_id": "receipt-terminal",
            "run_id": "run-leaf",
            "outcome": "blocked",
            "mutation_authorized": True,
            **evidence,
        }
    ]
    result = harvest_root(
        "run-root",
        client=FakeKeeper(payload),
        execution_adapters=(),
    )
    assert result["landed"] == [
        {
            "run_id": "run-leaf",
            "receipt_id": "receipt-terminal",
            "outcome": "blocked",
            "merged": False,
        }
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda receipt: receipt.update(mutation_authorized=False), "not mutation-authorized"),
        (
            lambda receipt: receipt["observed_heads_before"].update({"organvm/limen": "e" * 40}),
            "exact base",
        ),
        (lambda receipt: receipt["checks"].pop(), "pull-request"),
        (lambda receipt: receipt.update(changed_paths=["tasks.yaml"]), "unauthorized path"),
    ],
)
def test_harvest_fails_closed_on_inexact_code_receipts(mutation, message) -> None:
    payload = terminal_harvest()
    mutation(payload["nodes"][0]["receipts"][0])
    with pytest.raises(FanoutError, match=message):
        harvest_root("run-root", client=FakeKeeper(payload))


def test_cli_plan_does_not_require_tasks_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LIMEN_CONDUCT_URL", raising=False)
    monkeypatch.delenv("LIMEN_CONDUCT_STATE", raising=False)
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_payload()), encoding="utf-8")
    result = CliRunner().invoke(main, ["fanout", "plan", "--manifest", str(manifest_file)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["launch"] is False


def test_conversational_and_automatic_triggers_are_provider_neutral() -> None:
    assert should_evaluate_fanout("please fan out this request", reversible_leaf_count=0)
    assert should_evaluate_fanout("ordinary request", reversible_leaf_count=2)
    assert not should_evaluate_fanout("ordinary request", reversible_leaf_count=1)
